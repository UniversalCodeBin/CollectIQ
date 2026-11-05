"""Statement import (E053): TS-031, F-6, credit-only default, coverage confirmation, INV-11."""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from collectiq.platform import clock
from tests.integration.test_import import HEADER, _import
from tests.support import API, add_member, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")
NOW = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)
CSV_HEADER = "Date,Narration,Amount\n"


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


def _statement(rows: list[tuple[str, str, str]]) -> bytes:
    return (CSV_HEADER + "".join(f'{d},{n},"{a}"\n' for d, n, a in rows)).encode()


def _days(start: int, count: int, amount: str = "100.00") -> list[tuple[str, str, str]]:
    """One distinct credit per day, counted from 2026-10-01."""
    return [
        (
            (date(2026, 10, 1) + timedelta(days=start + i)).isoformat(),
            f"Client {start + i} INV-{start + i}",
            amount,
        )
        for i in range(count)
    ]


def _account(client: APIClient, ws: str, label: str = "Main bank", currency: str = "INR") -> str:
    response = client.post(
        f"{API}/workspaces/{ws}/payment-accounts",
        {"kind": "BANK", "label": label, "currency": currency},
        format="json",
        **idem(),
    )
    assert response.status_code == 201, response.content
    return str(response.json()["id"])


def _post(
    client: APIClient, ws: str, account: str, data: bytes, name: str = "statement.csv", **fields: Any
) -> Any:
    body: dict[str, Any] = {
        "file": SimpleUploadedFile(name, data, content_type="text/csv"),
        "source_type": "BANK_CSV",
        "payment_account_id": account,
        "mapping": json.dumps({"date": "Date", "description": "Narration", "amount": "Amount"}),
        "date_format": "YYYY-MM-DD",
    }
    body.update({k: (v if isinstance(v, str) else json.dumps(v)) for k, v in fields.items()})
    return client.post(f"{API}/workspaces/{ws}/imports/transactions", body, format="multipart", **idem())


def _txns(owner_db: Any, ws: str) -> list[tuple[Any, ...]]:
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    return owner_db.execute(
        "SELECT value_date, amount_minor, direction, occurrence_index, status FROM payment_transactions"
        " ORDER BY value_date, occurrence_index, amount_minor"
    ).fetchall()


def test_import_stores_credits_and_reports_totals(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "stmt1@example.test")
    account = _account(client, ws)
    data = _statement([("2026-10-01", "Acme INV-1", "1,500.50"), ("2026-10-02", "Rent", "-200.00")])
    response = _post(client, ws, account, data)
    assert response.status_code == 201, response.content
    body = response.json()
    counts = body["counts"]
    assert counts == {
        "total_rows": 2,
        "added": 1,
        "skipped_duplicate": 0,
        "held_for_confirmation": 0,
        "discarded_debits": 1,
        "invalid": 0,
    }
    assert body["status"] == "COMMITTED" and body["dry_run"] is False
    assert _txns(owner_db, ws) == [(date(2026, 10, 1), 150050, "CREDIT", 0, "ACTIVE")]
    refs = owner_db.execute(
        "SELECT reference_candidates, payer_descriptor FROM payment_transactions"
    ).fetchone()
    assert refs == (["INV-1"], "Acme INV-1")


def test_negative_debit_rows_not_treated_as_credits(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "stmt2@example.test")
    account = _account(client, ws)
    response = _post(client, ws, account, _statement([("2026-10-01", "Refund out", "-75.00")]))
    assert response.status_code == 201
    assert _txns(owner_db, ws) == []
    assert response.json()["counts"]["discarded_debits"] == 1


def test_debits_stored_as_debits_only_when_opted_in(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "stmt3@example.test")
    account = _account(client, ws)
    data = _statement([("2026-10-01", "In", "10.00"), ("2026-10-02", "Out", "-20.00")])
    assert _post(client, ws, account, data, include_debits="true").status_code == 201
    assert _txns(owner_db, ws) == [
        (date(2026, 10, 1), 1000, "CREDIT", 0, "ACTIVE"),
        (date(2026, 10, 2), 2000, "DEBIT", 0, "ACTIVE"),
    ]


def test_overlap_of_twenty_rows_is_skipped_and_totals_reconcile(owner_db: Any) -> None:
    """TS-031."""
    client, ws = owner_workspace(owner_db, "ts031@example.test")
    account = _account(client, ws)
    assert _post(client, ws, account, _statement(_days(0, 30))).status_code == 201
    second = _post(client, ws, account, _statement(_days(10, 30)))  # days 10..39: 20 overlap, 10 new
    assert second.status_code == 201, second.content
    counts = second.json()["counts"]
    assert counts["total_rows"] == 30 and counts["skipped_duplicate"] == 20 and counts["added"] == 10
    assert counts["total_rows"] == sum(
        counts[k]
        for k in ("added", "skipped_duplicate", "held_for_confirmation", "discarded_debits", "invalid")
    )
    assert len(_txns(owner_db, ws)) == 40


def test_reimport_yields_zero_new_transactions(owner_db: Any) -> None:
    """F-6 / INV-11."""
    client, ws = owner_workspace(owner_db, "f6@example.test")
    account = _account(client, ws)
    data = _statement(_days(0, 12))
    assert _post(client, ws, account, data).status_code == 201
    again = _post(client, ws, account, data)
    assert again.status_code == 201
    assert again.json()["counts"]["added"] == 0 and again.json()["counts"]["skipped_duplicate"] == 12
    assert len(_txns(owner_db, ws)) == 12


def test_identical_same_day_rows_in_one_first_file_are_both_kept(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "same1@example.test")
    account = _account(client, ws)
    row = ("2026-10-01", "Acme INV-9", "50.00")
    assert _post(client, ws, account, _statement([row, row])).status_code == 201
    assert [t[3] for t in _txns(owner_db, ws)] == [0, 1]


def test_identical_same_day_rows_overlapping_an_earlier_import_need_confirmation(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "same2@example.test")
    account = _account(client, ws)
    row = ("2026-10-01", "Acme INV-9", "50.00")
    assert _post(client, ws, account, _statement([row])).status_code == 201
    held = _post(client, ws, account, _statement([row, row]))
    assert held.status_code == 201
    counts = held.json()["counts"]
    assert (counts["skipped_duplicate"], counts["held_for_confirmation"], counts["added"]) == (1, 1, 0)
    assert held.json()["held_rows"] == [{"row": 3, "reason": "REPEATED_SAME_DAY"}]
    assert len(_txns(owner_db, ws)) == 1
    confirmed = _post(client, ws, account, _statement([row, row]), confirm_repeated="true")
    assert confirmed.json()["counts"]["added"] == 1
    assert len(_txns(owner_db, ws)) == 2


def test_bad_rows_refuse_the_whole_import_unless_skipped(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "bad@example.test")
    account = _account(client, ws)
    data = _statement(
        [("2026-10-01", "Good", "10.00"), ("2026-13-45", "Bad date", "10.00"), ("2026-10-03", "Bad", "ten")]
    )
    refused = _post(client, ws, account, data)
    assert refused.status_code == 422
    errors = refused.json()["errors"]
    assert [e["row"] for e in errors] == [3, 4]
    assert _txns(owner_db, ws) == []
    skipped = _post(client, ws, account, data, skip_invalid="true")
    assert skipped.status_code == 201
    assert skipped.json()["counts"]["invalid"] == 2 and skipped.json()["counts"]["added"] == 1
    assert len(_txns(owner_db, ws)) == 1


def test_dry_run_writes_nothing(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "dry@example.test")
    account = _account(client, ws)
    response = _post(client, ws, account, _statement(_days(0, 3)), dry_run="true")
    assert response.status_code == 200
    assert response.json()["dry_run"] is True and response.json()["counts"]["added"] == 3
    assert _txns(owner_db, ws) == []
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    assert (
        owner_db.execute("SELECT count(*) FROM import_batches WHERE kind = 'STATEMENT_CSV'").fetchone()[0]
        == 0
    )


def test_locale_file_with_bom_semicolons_and_indian_grouping(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "locale@example.test")
    account = _account(client, ws)
    data = '﻿Date;Narration;Amount\n03/04/2026;Acme;"2,50,000.00"\n'.encode()
    response = _post(client, ws, account, data, date_format="DD/MM/YYYY")
    assert response.status_code == 201, response.content
    assert _txns(owner_db, ws)[0][:2] == (date(2026, 4, 3), 25000000)


def test_ambiguous_date_without_a_format_is_refused(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "ambig@example.test")
    account = _account(client, ws)
    body = _post(
        client, ws, account, b"Date,Narration,Amount\n03/04/2026,Acme,10.00\n", date_format=""
    )
    assert body.status_code == 422
    assert "date format" in json.dumps(body.json()).lower()


def test_missing_mapped_column_is_named(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "col@example.test")
    account = _account(client, ws)
    response = _post(
        client,
        ws,
        account,
        _statement(_days(0, 1)),
        mapping={"date": "When", "description": "Narration", "amount": "Amount"},
    )
    assert response.status_code == 422 and "When" in json.dumps(response.json())


def test_row_currency_must_match_the_account(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "cur@example.test")
    account = _account(client, ws)
    data = b"Date,Narration,Amount,Cur\n2026-10-01,Acme,10.00,USD\n"
    mapping = {"date": "Date", "description": "Narration", "amount": "Amount", "currency": "Cur"}
    response = _post(client, ws, account, data, mapping=mapping)
    assert response.status_code == 422 and "USD" in json.dumps(response.json())


def test_confirmed_coverage_is_recorded_and_unconfirmed_is_not(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "cov@example.test")
    account = _account(client, ws)
    _import(client, ws, (HEADER + "INV-1,Northwind,2026-10-20,INR,100.00,2026-10-01\n").encode())
    inv = client.get(f"{API}/workspaces/{ws}/invoices?limit=5").json()["items"][0]["id"]
    assert _post(client, ws, account, _statement(_days(0, 3))).status_code == 201
    assert (
        client.get(f"{API}/workspaces/{ws}/invoices/{inv}").json()["derived"]["evidence_coverage"]
        == "MISSING"
    )
    confirmed = _post(
        client, ws, account, _statement(_days(3, 3)), coverage_from="2026-10-01", coverage_to="2026-10-28"
    )
    assert confirmed.status_code == 201, confirmed.content
    assert confirmed.json()["coverage"] == {"covers_from": "2026-10-01", "covers_to": "2026-10-28"}
    assert (
        client.get(f"{API}/workspaces/{ws}/invoices/{inv}").json()["derived"]["evidence_coverage"]
        == "SUPPORTED"
    )
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    row = owner_db.execute("SELECT import_batch_id FROM account_coverages").fetchone()
    assert row and row[0] is not None


def test_coverage_in_the_future_or_half_given_is_refused(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "covbad@example.test")
    account = _account(client, ws)
    future = _post(
        client, ws, account, _statement(_days(0, 1)), coverage_from="2026-10-01", coverage_to="2026-12-01"
    )
    assert future.status_code == 422
    half = _post(client, ws, account, _statement(_days(0, 1)), coverage_from="2026-10-01")
    assert half.status_code == 422
    assert _txns(owner_db, ws) == []


def test_import_never_allocates_or_changes_payment_status(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "noalloc@example.test")
    account = _account(client, ws)
    _import(client, ws, (HEADER + "INV-1,Northwind,2026-10-20,INR,100.00,2026-10-01\n").encode())
    assert (
        _post(client, ws, account, _statement([("2026-10-02", "Northwind INV-1", "100.00")])).status_code
        == 201
    )
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    status = owner_db.execute(
        "SELECT payment_status, paid_minor, outstanding_minor FROM invoice_state"
    ).fetchone()
    assert status == ("OUTSTANDING", 0, 10000)


def test_audit_event_and_stored_file(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "audit2@example.test")
    account = _account(client, ws)
    body = _post(client, ws, account, _statement(_days(0, 2))).json()
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    events = owner_db.execute(
        "SELECT object_id, after_masked FROM audit_events WHERE action = 'transactions.imported'"
    ).fetchall()
    assert len(events) == 1 and events[0][0] == body["id"]
    assert events[0][1]["added"] == 2 and events[0][1]["payment_account_id"] == account
    assert owner_db.execute("SELECT kind FROM stored_files WHERE kind = 'STATEMENT_CSV'").fetchone()


def test_idempotent_replay_returns_the_same_batch(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "idem@example.test")
    account = _account(client, ws)
    key = idem()
    data = _statement(_days(0, 2))

    def send() -> Any:
        body = {
            "file": SimpleUploadedFile("s.csv", data, content_type="text/csv"),
            "source_type": "BANK_CSV",
            "payment_account_id": account,
            "mapping": json.dumps({"date": "Date", "description": "Narration", "amount": "Amount"}),
            "date_format": "YYYY-MM-DD",
        }
        return client.post(f"{API}/workspaces/{ws}/imports/transactions", body, format="multipart", **key)

    first, second = send(), send()
    assert first.status_code == 201 and first.json()["id"] == second.json()["id"]
    assert len(_txns(owner_db, ws)) == 2


def test_file_checks_roles_and_tenant_isolation(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "stmtauth@example.test")
    other, other_ws = owner_workspace(owner_db, "stmtother@example.test")
    account = _account(client, ws)
    assert _post(client, ws, account, b"PK\x03\x04zip", name="s.csv").status_code == 415
    assert _post(client, ws, account, _statement(_days(0, 1)), name="s.xlsx").status_code == 415
    assert _post(client, ws, str(UUID(int=7)), _statement(_days(0, 1))).status_code == 404
    assert _post(other, other_ws, account, _statement(_days(0, 1))).status_code == 404
    lead, _ = add_member(owner_db, ws, "lead2@example.test", "PROJECT_LEAD")
    assert _post(lead, ws, account, _statement(_days(0, 1))).status_code == 403
    inactive = client.patch(
        f"{API}/workspaces/{ws}/payment-accounts/{account}",
        {"status": "INACTIVE"},
        format="json",
        HTTP_IF_MATCH='"1"',
    )
    assert inactive.status_code == 200
    assert _post(client, ws, account, _statement(_days(0, 1))).status_code == 409


def test_transactions_cannot_be_deleted_or_rewritten_by_the_app(owner_db: Any) -> None:
    from django.db import connection

    client, ws = owner_workspace(owner_db, "immut@example.test")
    account = _account(client, ws)
    assert _post(client, ws, account, _statement(_days(0, 1))).status_code == 201
    for statement in (
        "DELETE FROM payment_transactions",
        "UPDATE payment_transactions SET amount_minor = amount_minor + 1",
        "UPDATE payment_transactions SET value_date = value_date + 1",
    ):
        with pytest.raises(Exception) as caught, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
            cursor.execute(statement)
        assert "permission denied" in str(caught.value)
