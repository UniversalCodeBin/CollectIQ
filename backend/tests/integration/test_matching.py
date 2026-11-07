"""Match suggestions (E055, E056): TS-004, BR-11..15, critical negative 3."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from rest_framework.test import APIClient

from collectiq.evidence import service_matching as matching
from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx
from tests.integration.test_import import HEADER, _import
from tests.integration.test_statements import _account, _post, _statement
from tests.support import API, drain_jobs, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")
NOW = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


def _ctx(owner_db: Any, ws: str) -> RequestContext:
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    user = owner_db.execute("SELECT user_id FROM workspace_memberships WHERE role = 'OWNER'").fetchone()[0]
    return RequestContext(uuid.UUID(ws), user, "OWNER", str(uuid.uuid4()), "USER")


def _load(client: APIClient, ws: str, *rows: tuple[str, str, str]) -> dict[str, str]:
    """(number, client, total) rows, issued 2026-10-01, due 2026-10-31. Returns invoice ids by number."""
    body = HEADER + "".join(f"{n},{c},2026-10-31,INR,{t},2026-10-01\n" for n, c, t in rows)
    _import(client, ws, body.encode())
    items = client.get(f"{API}/workspaces/{ws}/invoices?limit=200").json()["items"]
    return {i["invoice_number"]: i["id"] for i in items}


def _pay(client: APIClient, ws: str, account: str, *rows: tuple[str, str, str]) -> None:
    response = _post(client, ws, account, _statement(list(rows)))
    assert response.status_code == 201, response.content
    drain_jobs()


def _state(owner_db: Any, invoice: str) -> tuple[Any, ...]:
    return owner_db.execute(
        "SELECT payment_status, paid_minor, outstanding_minor FROM invoice_state WHERE invoice_id = %s",
        [invoice],
    ).fetchone()


def _proposals(client: APIClient, ws: str) -> list[dict[str, Any]]:
    response = client.get(f"{API}/workspaces/{ws}/reconciliation/proposals")
    assert response.status_code == 200, response.content
    return response.json()["items"]


def test_ts004_unique_strong_match_waits_for_a_person(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "m1@example.test")
    ids = _load(client, ws, ("INV-7", "Northwind", "100.00"))
    _pay(client, ws, _account(client, ws), ("2026-10-20", "NEFT Northwind INV-7", "100.00"))
    [item] = _proposals(client, ws)
    assert item["label"] == "Strong" and not item["ambiguous"]
    assert item["invoice"]["id"] == ids["INV-7"]
    assert "score" not in str(item).lower() and "points" not in str(item).lower()
    assert any(r["code"] == "REFERENCE_EXACT" for r in item["reasons"])
    _scoped = _ctx(owner_db, ws)
    status, paid, outstanding = _state(owner_db, ids["INV-7"])
    # suggested match does not change the balance (critical negative 3)
    assert (status, paid, outstanding) == ("AWAITING_VERIFICATION", 0, 10_000)
    assert _scoped.workspace_id


def test_nothing_is_auto_applied(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "m2@example.test")
    ids = _load(client, ws, ("INV-1", "A", "50.00"), ("INV-2", "B", "60.00"))
    _pay(client, ws, _account(client, ws), ("2026-10-20", "INV-1", "50.00"), ("2026-10-21", "INV-2", "60.00"))
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    assert {_state(owner_db, i)[0] for i in ids.values()} == {"AWAITING_VERIFICATION"}
    assert (
        owner_db.execute("SELECT count(*) FROM reconciliation_matches WHERE status = 'CONFIRMED'").fetchone()[
            0
        ]
        == 0
    )
    assert {_state(owner_db, i)[1] for i in ids.values()} == {0}


def test_ambiguous_candidates_make_invoices_uncertain(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "m3@example.test")
    ids = {}
    ids.update(_load(client, ws, ("INV-9", "Acme", "100.00")))
    other = _load(client, ws, ("INV-9", "Zenith", "100.00"))
    both = [i["id"] for i in client.get(f"{API}/workspaces/{ws}/invoices?limit=200").json()["items"]]
    assert len(both) == 2 and other
    _pay(client, ws, _account(client, ws), ("2026-10-20", "INV-9", "100.00"))
    items = _proposals(client, ws)
    assert len(items) == 2 and all(i["ambiguous"] and i["label"] == "Possible" for i in items)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    assert {_state(owner_db, i)[0] for i in both} == {"UNCERTAIN"}


def test_rejected_match_not_reproposed_unless_inputs_change(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "m4@example.test")
    ids = _load(client, ws, ("INV-3", "Northwind", "100.00"))
    _pay(client, ws, _account(client, ws), ("2026-10-20", "INV-3", "100.00"))
    ctx = _ctx(owner_db, ws)
    [item] = _proposals(client, ws)
    matching.reject(ctx, uuid.UUID(item["id"]), "different customer")
    assert _state(owner_db, ids["INV-3"])[0] == "OUTSTANDING"
    txn = [r[0] for r in owner_db.execute("SELECT id FROM payment_transactions").fetchall()]
    with tenant_tx(ctx):
        assert matching.reconcile(ctx, txn) == 0
    assert _proposals(client, ws) == []
    # the invoice total changes, so the inputs are no longer the ones that were rejected
    owner_db.execute("UPDATE invoices SET gross_minor = 10_001 WHERE id = %s", [ids["INV-3"]])
    owner_db.execute(
        "UPDATE invoice_state SET outstanding_minor = 10_001 WHERE invoice_id = %s", [ids["INV-3"]]
    )
    with tenant_tx(ctx):
        assert matching.reconcile(ctx, txn) == 1
    assert len(_proposals(client, ws)) == 1


def test_other_workspace_never_a_candidate(owner_db: Any) -> None:
    other, ows = owner_workspace(owner_db, "m5a@example.test")
    _load(other, ows, ("INV-5", "Elsewhere", "100.00"))
    client, ws = owner_workspace(owner_db, "m5b@example.test")
    _pay(client, ws, _account(client, ws), ("2026-10-20", "INV-5", "100.00"))
    assert _proposals(client, ws) == []
    assert _proposals(other, ows) == []


def test_currency_mismatch_is_not_proposed(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "m6@example.test")
    _import(client, ws, (HEADER + "INV-8,Northwind,2026-10-31,USD,100.00,2026-10-01\n").encode())
    _pay(client, ws, _account(client, ws), ("2026-10-20", "INV-8", "100.00"))
    assert _proposals(client, ws) == []


def test_unmatched_lists_credits_without_confirmed_match(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "m7@example.test")
    _load(client, ws, ("INV-4", "Northwind", "100.00"))
    _pay(
        client, ws, _account(client, ws), ("2026-10-20", "INV-4", "100.00"), ("2026-10-21", "Mystery", "7.00")
    )
    items = client.get(f"{API}/workspaces/{ws}/transactions/unmatched").json()["items"]
    by_amount = {i["amount_minor"]: i for i in items}
    assert set(by_amount) == {10_000, 700}
    assert by_amount[10_000]["proposal_count"] == 1 and by_amount[700]["proposal_count"] == 0


def test_proposals_require_login(owner_db: Any) -> None:
    _, ws = owner_workspace(owner_db, "m8@example.test")
    assert APIClient().get(f"{API}/workspaces/{ws}/reconciliation/proposals").status_code == 401


def test_what_the_matcher_has_learned_is_read_once_per_client_not_once_per_candidate(
    owner_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pool of five invoices for one client and two payments must not cost ten history queries."""
    client, ws = owner_workspace(owner_db, "m9@example.test")
    _load(client, ws, *((f"INV-{n}", "Northwind", f"{n}00.00") for n in range(1, 6)))
    reads: list[Any] = []
    real = matching._history_rows

    def counted(client_id: Any) -> list[dict[str, Any]]:
        reads.append(client_id)
        return real(client_id)

    monkeypatch.setattr(matching, "_history_rows", counted)
    _pay(
        client,
        ws,
        _account(client, ws),
        ("2026-10-20", "NEFT Northwind INV-1", "100.00"),
        ("2026-10-21", "NEFT Northwind INV-2", "200.00"),
    )
    assert _proposals(client, ws), "the run should still propose"
    assert len(reads) == 1
