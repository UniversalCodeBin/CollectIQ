"""Payment accounts, coverage and attestations (E029-E032, E054): TSD M08, SAD 6.8, TS-032."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from collectiq.evidence import service_accounts as service
from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from tests.integration.test_import import HEADER, _import
from tests.support import API, add_member, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")
NOW = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


def _ctx(owner_db: Any, ws: str) -> RequestContext:
    import uuid

    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    user = owner_db.execute("SELECT user_id FROM workspace_memberships WHERE role = 'OWNER'").fetchone()[0]
    return RequestContext(uuid.UUID(ws), user, "OWNER", str(uuid.uuid4()), "USER")


def _invoices(client: APIClient, ws: str, *rows: tuple[str, str]) -> dict[str, str]:
    """(number, issue date) pairs. All for one client and currency, 100.00 each."""
    body = HEADER + "".join(
        f"{n},Northwind,2026-10-20,INR,{100 + i}.00,{issued}\n" for i, (n, issued) in enumerate(rows)
    )
    _import(client, ws, body.encode())
    page = client.get(f"{API}/workspaces/{ws}/invoices?limit=200").json()
    return {item["invoice_number"]: item["id"] for item in page["items"]}


def _account(
    client: APIClient, ws: str, label: str = "Main bank", kind: str = "BANK", currency: str = "INR"
) -> dict[str, Any]:
    response = client.post(
        f"{API}/workspaces/{ws}/payment-accounts",
        {"kind": kind, "label": label, "currency": currency},
        format="json",
        **idem(),
    )
    assert response.status_code == 201, response.content
    return response.json()


def _state(client: APIClient, ws: str, invoice_id: str) -> dict[str, Any]:
    return client.get(f"{API}/workspaces/{ws}/invoices/{invoice_id}").json()


def _coverage(client: APIClient, ws: str, invoice_id: str) -> tuple[str, Any]:
    state = _state(client, ws, invoice_id)
    return state["derived"]["evidence_coverage"], state["derived"]["evidence_as_of"]


def _attest(client: APIClient, ws: str, **body: Any) -> Any:
    return client.post(f"{API}/workspaces/{ws}/attestations", body, format="json", **idem())


def _audit(owner_db: Any, ws: str, action: str) -> list[tuple[Any, ...]]:
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    return owner_db.execute(
        "SELECT object_type, object_id, actor_id, after_masked FROM audit_events"
        " WHERE action = %s ORDER BY id",
        [action],
    ).fetchall()


def test_ts_032_missing_then_supported_then_stale(owner_db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client, ws = owner_workspace(owner_db, "ts032@example.test")
    ids = _invoices(client, ws, ("INV-1", "2026-10-01"))
    inv = ids["INV-1"]
    assert _coverage(client, ws, inv)[0] == "MISSING"
    account = _account(client, ws)
    assert _coverage(client, ws, inv)[0] == "MISSING"  # declaring an account cannot create coverage
    service.record_coverage(
        _ctx(owner_db, ws), __import__("uuid").UUID(account["id"]), date(2026, 10, 1), date(2026, 10, 28)
    )
    assert _coverage(client, ws, inv)[0] == "SUPPORTED"
    # time passes with nothing new looked at
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(days=20))
    service.recompute_coverage(_ctx(owner_db, ws))
    assert _coverage(client, ws, inv)[0] == "STALE"


def test_gap_in_ranges_stops_contiguous_coverage(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "gap@example.test")
    inv = _invoices(client, ws, ("INV-1", "2026-10-01"))["INV-1"]
    ctx = _ctx(owner_db, ws)
    account = __import__("uuid").UUID(_account(client, ws)["id"])
    service.record_coverage(ctx, account, date(2026, 10, 1), date(2026, 10, 10))
    service.record_coverage(ctx, account, date(2026, 10, 15), date(2026, 10, 28))
    status, as_of = _coverage(client, ws, inv)
    assert (status, str(as_of)[:10]) == (
        "STALE",
        "2026-10-10",
    )  # 20 days old at NOW: contiguous end is the 10th
    detail = client.get(f"{API}/workspaces/{ws}/payment-accounts/{account}/coverage").json()
    assert detail["gaps"] == [{"from": "2026-10-11", "to": "2026-10-14"}]
    assert detail["covered_through"] == "2026-10-10"


def test_no_accounts_only_invoice_attestation_counts(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "noacct@example.test")
    ids = _invoices(client, ws, ("INV-1", "2026-10-01"), ("INV-2", "2026-10-01"))
    response = _attest(
        client, ws, scope="INVOICE", invoice_ids=[ids["INV-1"]], as_of="2026-10-29T10:00:00Z", note="Checked"
    )
    assert response.status_code == 201, response.content
    assert _coverage(client, ws, ids["INV-1"])[0] == "SUPPORTED"
    assert _coverage(client, ws, ids["INV-2"])[0] == "MISSING"  # another invoice is not vouched for


def test_account_attestation_covers_every_invoice_behind_that_account(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "acctatt@example.test")
    ids = _invoices(client, ws, ("INV-1", "2026-10-01"))
    account = _account(client, ws)
    assert (
        _attest(
            client, ws, scope="ACCOUNT", account_id=account["id"], as_of="2026-10-29T10:00:00Z"
        ).status_code
        == 201
    )
    assert _coverage(client, ws, ids["INV-1"])[0] == "SUPPORTED"


def test_attestation_does_not_resolve_unrelated_claim(owner_db: Any) -> None:
    """Attesting changes coverage only: payment status, balances and the open-task count stay as they were."""
    client, ws = owner_workspace(owner_db, "claim@example.test")
    inv = _invoices(client, ws, ("INV-1", "2026-10-01"))["INV-1"]
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    owner_db.execute(
        "UPDATE invoice_state SET open_task_count = 1, payment_status = 'AWAITING_VERIFICATION'"
        " WHERE invoice_id = %s",
        [inv],
    )
    before = owner_db.execute(
        "SELECT payment_status, open_task_count, paid_minor, outstanding_minor"
        " FROM invoice_state WHERE invoice_id = %s",
        [inv],
    ).fetchone()
    assert (
        _attest(client, ws, scope="INVOICE", invoice_ids=[inv], as_of="2026-10-29T10:00:00Z").status_code
        == 201
    )
    after = owner_db.execute(
        "SELECT payment_status, open_task_count, paid_minor, outstanding_minor"
        " FROM invoice_state WHERE invoice_id = %s",
        [inv],
    ).fetchone()
    assert after == before == ("AWAITING_VERIFICATION", 1, 0, 10000)


def test_attestation_records_actor_scope_timestamp_coverage_and_audit(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "audit@example.test")
    inv = _invoices(client, ws, ("INV-1", "2026-10-01"))["INV-1"]
    assert (
        _attest(
            client,
            ws,
            scope="INVOICE",
            invoice_ids=[inv],
            as_of="2026-10-29T10:00:00Z",
            note="Checked bank app",
        ).status_code
        == 201
    )
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    row = owner_db.execute(
        "SELECT scope, invoice_id::text, as_of, note, attested_by FROM evidence_attestations"
    ).fetchone()
    assert row[0] == "INVOICE" and row[1] == inv and row[2] == datetime(2026, 10, 29, 10, tzinfo=UTC)
    assert row[3] == "Checked bank app" and row[4] is not None
    events = _audit(owner_db, ws, "attestation.recorded")
    assert len(events) == 1
    object_type, object_id, actor_id, after = events[0]
    assert (object_type, object_id, actor_id) == ("invoice", inv, row[4])
    assert (
        after["scope"] == "INVOICE"
        and after["coverage_date"] == "2026-10-29"
        and after["as_of"].startswith("2026-10-29T10:00")
    )


def test_attestation_in_the_future_is_refused(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "future@example.test")
    inv = _invoices(client, ws, ("INV-1", "2026-10-01"))["INV-1"]
    response = _attest(client, ws, scope="INVOICE", invoice_ids=[inv], as_of="2026-10-31T00:00:00Z")
    assert response.status_code == 422
    assert owner_db.execute("SELECT count(*) FROM evidence_attestations").fetchone()[0] == 0


@pytest.mark.parametrize(
    "body",
    [
        {"scope": "ACCOUNT"},  # no account
        {"scope": "INVOICE"},  # no invoices
        {"scope": "INVOICE", "invoice_ids": ["X"], "account_id": "Y"},  # both
        {"scope": "WORKSPACE"},
    ],
)
def test_attestation_scope_must_match_its_target(owner_db: Any, body: dict[str, Any]) -> None:
    client, ws = owner_workspace(owner_db, "scope@example.test")
    inv = _invoices(client, ws, ("INV-1", "2026-10-01"))["INV-1"]
    account = _account(client, ws)["id"]
    body = {
        k: ([inv] if k == "invoice_ids" else account if k == "account_id" else v) for k, v in body.items()
    }
    assert _attest(client, ws, as_of="2026-10-29T10:00:00Z", **body).status_code in (400, 422)


def test_missing_event_does_not_change_status(owner_db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Critical negative 2: when coverage lapses the invoice is not found unpaid, or anything else."""
    client, ws = owner_workspace(owner_db, "negative@example.test")
    inv = _invoices(client, ws, ("INV-1", "2026-10-01"))["INV-1"]
    account = __import__("uuid").UUID(_account(client, ws)["id"])
    service.record_coverage(_ctx(owner_db, ws), account, date(2026, 10, 1), date(2026, 10, 28))
    snapshot = lambda: owner_db.execute(  # noqa: E731
        "SELECT payment_status, paid_minor, outstanding_minor, overpayment_flag,"
        " dispute_status, reminder_status"
        " FROM invoice_state WHERE invoice_id = %s",
        [inv],
    ).fetchone()
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    before = snapshot()
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(days=90))
    service.recompute_coverage(_ctx(owner_db, ws))
    assert _coverage(client, ws, inv)[0] == "STALE"
    assert snapshot() == before == ("OUTSTANDING", 0, 10000, False, "NONE", "NOT_CONTACTED")


def test_declaring_a_second_account_narrows_coverage_and_deactivating_widens_it(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "narrow@example.test")
    inv = _invoices(client, ws, ("INV-1", "2026-10-01"))["INV-1"]
    first = _account(client, ws, "Main bank")
    service.record_coverage(
        _ctx(owner_db, ws), __import__("uuid").UUID(first["id"]), date(2026, 10, 1), date(2026, 10, 28)
    )
    assert _coverage(client, ws, inv)[0] == "SUPPORTED"
    second = _account(client, ws, "PayPal", kind="PAYPAL")
    assert _coverage(client, ws, inv)[0] == "MISSING"  # PayPal has not been looked at
    response = client.patch(
        f"{API}/workspaces/{ws}/payment-accounts/{second['id']}",
        {"status": "INACTIVE"},
        format="json",
        HTTP_IF_MATCH='"1"',
    )
    assert response.status_code == 200, response.content
    assert _coverage(client, ws, inv)[0] == "SUPPORTED"


def test_coverage_cannot_end_in_the_future(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "futurecov@example.test")
    account = __import__("uuid").UUID(_account(client, ws)["id"])
    from collectiq.platform.errors import ProblemError

    with pytest.raises(ProblemError) as caught:
        service.record_coverage(_ctx(owner_db, ws), account, date(2026, 10, 1), date(2026, 11, 2))
    assert caught.value.status == 422


def test_accounts_audit_duplicates_and_versions(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "acct@example.test")
    account = _account(client, ws, "Main bank")
    assert len(_audit(owner_db, ws, "account.declared")) == 1
    duplicate = client.post(
        f"{API}/workspaces/{ws}/payment-accounts",
        {"kind": "BANK", "label": "MAIN  bank", "currency": "INR"},
        format="json",
        **idem(),
    )
    assert duplicate.status_code == 409
    url = f"{API}/workspaces/{ws}/payment-accounts/{account['id']}"
    stale = client.patch(url, {"label": "Renamed"}, format="json", HTTP_IF_MATCH='"7"')
    assert stale.status_code == 409
    ok = client.patch(url, {"label": "Renamed"}, format="json", HTTP_IF_MATCH='"1"')
    assert ok.status_code == 200 and ok.json()["version"] == 2 and ok["ETag"] == '"2"'
    assert len(_audit(owner_db, ws, "account.updated")) == 1
    listing = client.get(f"{API}/workspaces/{ws}/payment-accounts").json()
    assert [a["label"] for a in listing["items"]] == ["Renamed"]
    assert listing["items"][0]["coverage_status"] == "MISSING"


def test_roles_and_tenant_isolation(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "roles@example.test")
    other, other_ws = owner_workspace(owner_db, "elsewhere@example.test")
    account = _account(client, ws)
    lead, _ = add_member(owner_db, ws, "lead@example.test", "PROJECT_LEAD")
    assert lead.get(f"{API}/workspaces/{ws}/payment-accounts").status_code == 403
    assert (
        lead.post(
            f"{API}/workspaces/{ws}/payment-accounts",
            {"kind": "BANK", "label": "X", "currency": "INR"},
            format="json",
            **idem(),
        ).status_code
        == 403
    )
    assert (
        _attest(lead, ws, scope="ACCOUNT", account_id=account["id"], as_of="2026-10-29T10:00:00Z").status_code
        == 403
    )
    # another workspace's owner cannot see or touch this account
    assert (
        other.get(f"{API}/workspaces/{other_ws}/payment-accounts/{account['id']}/coverage").status_code == 404
    )
    assert other.get(f"{API}/workspaces/{ws}/payment-accounts").status_code in (
        403,
        404,
    )  # non-member learns nothing
    assert (
        _attest(
            other, other_ws, scope="ACCOUNT", account_id=account["id"], as_of="2026-10-29T10:00:00Z"
        ).status_code
        == 404
    )
    assert other.get(f"{API}/workspaces/{other_ws}/payment-accounts").json()["items"] == []


def test_coverage_and_attestation_rows_cannot_be_rewritten_by_the_app(owner_db: Any, pg: None) -> None:
    import psycopg
    from django.db import connection

    client, ws = owner_workspace(owner_db, "append@example.test")
    account = __import__("uuid").UUID(_account(client, ws)["id"])
    service.record_coverage(_ctx(owner_db, ws), account, date(2026, 10, 1), date(2026, 10, 2))
    for statement in (
        "UPDATE account_coverages SET covers_to = covers_to + 1",
        "DELETE FROM account_coverages",
        "DELETE FROM evidence_attestations",
    ):
        with pytest.raises((psycopg.errors.InsufficientPrivilege, Exception)) as caught:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
                cursor.execute(statement)
        assert "permission denied" in str(caught.value)
        connection.rollback() if not connection.in_atomic_block else None
