"""The ledger (SAD 6.6, TSD 9): F-1..F-5 as the app role, then TS-011/012/013 and money paths over HTTP."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from django.conf import settings
from hypothesis import HealthCheck, given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st
from rest_framework.test import APIClient

from collectiq.evidence import service_allocation as ledger
from collectiq.evidence import service_state
from collectiq.evidence.domain.derive import derive
from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx
from collectiq.platform.errors import ProblemError
from tests.integration.test_import import HEADER, _import
from tests.integration.test_statements import _account, _post, _statement
from tests.support import API, add_member, drain_jobs, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")
NOW = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


@dataclass
class World:
    client: APIClient
    ws: str
    user: uuid.UUID
    invoices: dict[str, str]
    txns: list[str]
    owner_db: Any

    def ctx(self) -> RequestContext:
        return RequestContext(uuid.UUID(self.ws), self.user, "OWNER", str(uuid.uuid4()), "USER")


def load_invoices(client: APIClient, ws: str, *rows: tuple[str, str, str]) -> dict[str, str]:
    body = HEADER + "".join(f"{n},{c},2026-10-31,INR,{t},2026-10-01\n" for n, c, t in rows)
    _import(client, ws, body.encode())
    items = client.get(f"{API}/workspaces/{ws}/invoices?limit=200").json()["items"]
    return {i["invoice_number"]: i["id"] for i in items}


def world(
    owner_db: Any,
    email: str,
    invoices: tuple[tuple[str, str, str], ...] = (("INV-1", "Acme", "100.00"),),
    payments: tuple[str, ...] = ("100.00",),
) -> World:
    client, ws = owner_workspace(owner_db, email)
    ids = load_invoices(client, ws, *invoices)
    rows = [(f"2026-10-{10 + n:02d}", f"Receipt {n}", amount) for n, amount in enumerate(payments)]
    if rows:
        response = _post(client, ws, _account(client, ws), _statement(rows))
        assert response.status_code == 201, response.content
    drain_jobs()
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    txns = [
        str(r[0])
        for r in owner_db.execute("SELECT id FROM payment_transactions ORDER BY value_date").fetchall()
    ]
    user = owner_db.execute("SELECT user_id FROM workspace_memberships WHERE role = 'OWNER'").fetchone()[0]
    return World(client, ws, user, ids, txns, owner_db)


@contextmanager
def app_connection(w: World) -> Iterator[psycopg.Connection]:
    """A raw connection as the app role, so a check is proved by the database and not by the service."""
    db = settings.DATABASES["default"]
    conn = psycopg.connect(
        host=db["HOST"], port=db["PORT"], dbname=db["NAME"], user=db["USER"], password=db["PASSWORD"]
    )
    try:
        conn.execute(
            "SELECT set_config('app.workspace_id', %s, false), set_config('app.user_id', %s, false)",
            [w.ws, str(w.user)],
        )
        conn.commit()
        yield conn
    finally:
        conn.rollback()
        conn.close()


def raw_insert(
    conn: psycopg.Connection,
    w: World,
    txn: str,
    invoice: str,
    amount: int,
    *,
    kind: str = "ALLOCATION",
    currency: str = "INR",
    reverses: str | None = None,
    overpayment: bool = False,
    note: str | None = None,
) -> str:
    row = conn.execute(
        "INSERT INTO payment_allocations (workspace_id, transaction_id, invoice_id, amount_minor, currency,"
        " kind, reverses_allocation_id, overpayment_confirmed, evidence_type, confirmed_by, note)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'STATEMENT_ROW', %s, %s) RETURNING id",
        [w.ws, txn, invoice, amount, currency, kind, reverses, overpayment, w.user, note],
    ).fetchone()
    assert row is not None
    return str(row[0])


def line(invoice: str, amount: int, **extra: Any) -> dict[str, Any]:
    return {"invoice_id": invoice, "amount_minor": amount, **extra}


def allocate(w: World, txn: str, *lines: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    return w.client.post(
        f"{API}/workspaces/{w.ws}/allocations",
        {"transaction_id": txn, "allocations": list(lines)},
        format="json",
        **(headers or idem()),
    )


def reverse(w: World, allocation: str, reason: str = "Allocated to the wrong invoice") -> Any:
    return w.client.post(
        f"{API}/workspaces/{w.ws}/allocations/{allocation}/reverse",
        {"reason": reason},
        format="json",
        **idem(),
    )


def state(w: World, invoice: str) -> tuple[Any, ...]:
    w.owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [w.ws])
    return w.owner_db.execute(
        "SELECT payment_status, paid_minor, outstanding_minor FROM invoice_state WHERE invoice_id = %s",
        [invoice],
    ).fetchone()


def scalar(w: World, sql: str, *params: Any) -> Any:
    w.owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [w.ws])
    return w.owner_db.execute(sql, list(params)).fetchone()[0]


def allocated_ok(w: World, txn: str, invoice: str, amount: int) -> str:
    response = allocate(w, txn, line(invoice, amount))
    assert response.status_code == 200, response.content
    return response.json()["allocations"][0]["id"]


def manual(w: World, amount: int = 10_000, currency: str = "INR", **extra: Any) -> Any:
    body = {
        "method": "BANK_TRANSFER",
        "amount": {"amount_minor": amount, "currency": currency},
        "value_date": "2026-10-20",
        **extra,
    }
    return w.client.post(f"{API}/workspaces/{w.ws}/payments", body, format="json", **idem())


# ---- the database itself, as the app role -------------------------------------------------------------


def test_update_delete_allocation_denied(owner_db: Any) -> None:
    """F-5: privileges stop the app role, and the trigger stops the owner."""
    w = world(owner_db, "db1@example.test")
    allocation = allocated_ok(w, w.txns[0], w.invoices["INV-1"], 4_000)
    for statement in (
        "UPDATE payment_allocations SET note = 'edited'",
        "UPDATE payment_allocations SET amount_minor = 1",
        "DELETE FROM payment_allocations",
        "TRUNCATE payment_allocations",
    ):
        with app_connection(w) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement)
    w.owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [w.ws])
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        w.owner_db.execute("UPDATE payment_allocations SET note = 'edited' WHERE id = %s", [allocation])
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        w.owner_db.execute("DELETE FROM payment_allocations WHERE id = %s", [allocation])
    assert scalar(w, "SELECT count(*) FROM payment_allocations") == 1


def test_trigger_rejects_over_transaction(owner_db: Any) -> None:
    """F-1, with the service out of the way."""
    w = world(
        owner_db,
        "db2@example.test",
        invoices=(("INV-1", "Acme", "100.00"), ("INV-2", "Zenith", "100.00")),
    )
    with app_connection(w) as conn:
        raw_insert(conn, w, w.txns[0], w.invoices["INV-1"], 7_000)
        raw_insert(conn, w, w.txns[0], w.invoices["INV-2"], 3_001)
        with pytest.raises(psycopg.errors.CheckViolation, match="F-1"):
            conn.commit()
    assert scalar(w, "SELECT count(*) FROM payment_allocations") == 0


def test_trigger_rejects_over_gross(owner_db: Any) -> None:
    """F-2: above the invoice total needs the explicit flag."""
    w = world(owner_db, "db3@example.test", payments=("100.00", "100.00"))
    with app_connection(w) as conn:
        raw_insert(conn, w, w.txns[0], w.invoices["INV-1"], 10_000)
        raw_insert(conn, w, w.txns[1], w.invoices["INV-1"], 1)
        with pytest.raises(psycopg.errors.CheckViolation, match="F-2"):
            conn.commit()
    with app_connection(w) as conn:
        raw_insert(conn, w, w.txns[0], w.invoices["INV-1"], 10_000)
        raw_insert(conn, w, w.txns[1], w.invoices["INV-1"], 1, overpayment=True)
        conn.commit()
    assert scalar(w, "SELECT count(*) FROM payment_allocations") == 2


def test_currency_mismatch_rejected(owner_db: Any) -> None:
    """F-3 in the database, then TS-013 through the service: no conversion, no balance change."""
    w = world(owner_db, "db4@example.test")
    with app_connection(w) as conn:
        raw_insert(conn, w, w.txns[0], w.invoices["INV-1"], 1_000, currency="USD")
        with pytest.raises(psycopg.errors.CheckViolation, match="F-3"):
            conn.commit()

    usd = manual(w, 1_000, "USD")
    assert usd.status_code == 201, usd.content
    refused = allocate(w, usd.json()["payment"]["id"], line(w.invoices["INV-1"], 1_000))
    assert refused.status_code == 422
    assert refused.json()["code"] == "VALIDATION_FAILED"
    assert state(w, w.invoices["INV-1"]) == ("OUTSTANDING", 0, 10_000)

    inline = manual(w, 1_000, "USD", allocations=[line(w.invoices["INV-1"], 1_000)])
    assert inline.status_code == 422
    # the refused manual entry left nothing behind
    assert scalar(w, "SELECT count(*) FROM payment_transactions WHERE source_type = 'MANUAL'") == 1


def test_second_reversal_rejected(owner_db: Any) -> None:
    """F-4: one reversal per allocation, never larger than the original."""
    w = world(owner_db, "db5@example.test")
    allocation = allocated_ok(w, w.txns[0], w.invoices["INV-1"], 4_000)
    with app_connection(w) as conn:
        raw_insert(
            conn, w, w.txns[0], w.invoices["INV-1"], -4_001, kind="REVERSAL", reverses=allocation, note="x"
        )
        with pytest.raises(psycopg.errors.CheckViolation, match="F-4"):
            conn.commit()
    assert reverse(w, allocation).status_code == 200
    with app_connection(w) as conn, pytest.raises(psycopg.errors.UniqueViolation):
        raw_insert(
            conn, w, w.txns[0], w.invoices["INV-1"], -4_000, kind="REVERSAL", reverses=allocation, note="x"
        )
    again = reverse(w, allocation)
    assert again.status_code == 409
    assert again.json()["code"] == "STATE_TRANSITION_INVALID"
    assert state(w, w.invoices["INV-1"]) == ("OUTSTANDING", 0, 10_000)


def test_reversal_must_match_its_original_and_carry_a_reason(owner_db: Any) -> None:
    w = world(
        owner_db,
        "db6@example.test",
        invoices=(("INV-1", "Acme", "100.00"), ("INV-2", "Zenith", "100.00")),
    )
    allocation = allocated_ok(w, w.txns[0], w.invoices["INV-1"], 4_000)
    with app_connection(w) as conn:
        raw_insert(
            conn, w, w.txns[0], w.invoices["INV-2"], -4_000, kind="REVERSAL", reverses=allocation, note="x"
        )
        with pytest.raises(psycopg.errors.CheckViolation, match="F-4"):
            conn.commit()
    with app_connection(w) as conn, pytest.raises(psycopg.errors.CheckViolation):
        raw_insert(conn, w, w.txns[0], w.invoices["INV-1"], -4_000, kind="REVERSAL", reverses=allocation)
    with app_connection(w) as conn, pytest.raises(psycopg.errors.CheckViolation):
        raw_insert(conn, w, w.txns[0], w.invoices["INV-1"], -1, kind="ALLOCATION")
    with app_connection(w) as conn, pytest.raises(psycopg.errors.CheckViolation):
        raw_insert(conn, w, w.txns[0], w.invoices["INV-1"], 1, kind="REVERSAL", reverses=allocation, note="x")


def test_evidence_types_exclude_any_ai_value(owner_db: Any) -> None:
    """INV-03: the database has no way to store an AI reading as payment evidence."""
    w = world(owner_db, "db7@example.test")
    with app_connection(w) as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO payment_transactions (workspace_id, source_type, method, amount_minor, currency,"
            " value_date, fingerprint, evidence_type, entered_by)"
            " VALUES (%s, 'MANUAL', 'OTHER', 100, 'INR', '2026-10-01', 'f', 'AI_INFERENCE', %s)",
            [w.ws, w.user],
        )
    with app_connection(w) as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO payment_allocations (workspace_id, transaction_id, invoice_id, amount_minor,"
            " currency, kind, evidence_type, confirmed_by)"
            " VALUES (%s, %s, %s, 100, 'INR', 'ALLOCATION', 'AI_INFERENCE', %s)",
            [w.ws, w.txns[0], w.invoices["INV-1"], w.user],
        )
    # the allocation carries the evidence type of its transaction, not one chosen by the caller
    with app_connection(w) as conn:
        conn.execute(
            "INSERT INTO payment_allocations (workspace_id, transaction_id, invoice_id, amount_minor,"
            " currency, kind, evidence_type, confirmed_by)"
            " VALUES (%s, %s, %s, 100, 'INR', 'ALLOCATION', 'USER_CONFIRMATION', %s)",
            [w.ws, w.txns[0], w.invoices["INV-1"], w.user],
        )
        with pytest.raises(psycopg.errors.CheckViolation, match="evidence"):
            conn.commit()


def test_transaction_with_live_allocations_cannot_be_retired_directly(owner_db: Any) -> None:
    w = world(owner_db, "db8@example.test")
    allocation = allocated_ok(w, w.txns[0], w.invoices["INV-1"], 4_000)
    with app_connection(w) as conn:
        conn.execute("UPDATE payment_transactions SET status = 'DUPLICATE' WHERE id = %s", [w.txns[0]])
        with pytest.raises(psycopg.errors.CheckViolation, match="live allocations"):
            conn.commit()
    with app_connection(w) as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("UPDATE payment_transactions SET status = 'VOID' WHERE id = %s", [w.txns[0]])
    assert reverse(w, allocation).status_code == 200
    with app_connection(w) as conn:
        conn.execute("UPDATE payment_transactions SET status = 'DUPLICATE' WHERE id = %s", [w.txns[0]])
        conn.commit()
    with app_connection(w) as conn:
        raw_insert(conn, w, w.txns[0], w.invoices["INV-1"], 100)
        with pytest.raises(psycopg.errors.CheckViolation, match="not active"):
            conn.commit()


def test_allocations_are_invisible_across_workspaces(owner_db: Any) -> None:
    w = world(owner_db, "db9@example.test")
    allocated_ok(w, w.txns[0], w.invoices["INV-1"], 4_000)
    outsider, other_ws = owner_workspace(owner_db, "db9b@example.test")
    assert outsider.get(f"{API}/workspaces/{other_ws}/payments").json()["items"] == []
    assert outsider.get(f"{API}/workspaces/{other_ws}/payments/{w.txns[0]}").status_code == 404
    assert outsider.get(f"{API}/workspaces/{w.ws}/payments").status_code in (403, 404)
    other_world = World(outsider, other_ws, w.user, {}, [], owner_db)
    assert allocate(other_world, w.txns[0], line(w.invoices["INV-1"], 1)).status_code == 404


# ---- the money paths --------------------------------------------------------------------------------


def test_ts011_partial_allocation_reports_the_remainder(owner_db: Any) -> None:
    w = world(owner_db, "t1@example.test")
    response = allocate(w, w.txns[0], line(w.invoices["INV-1"], 4_000))
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["payment"]["allocated_minor"] == 4_000 and body["payment"]["unallocated_minor"] == 6_000
    [invoice_state] = body["invoice_states"]
    assert invoice_state["payment_status"] == "PARTIALLY_PAID"
    assert invoice_state["outstanding_minor"] == 6_000
    assert state(w, w.invoices["INV-1"]) == ("PARTIALLY_PAID", 4_000, 6_000)


def test_ts012_sequence_then_overpayment_needs_confirmation(owner_db: Any) -> None:
    w = world(owner_db, "t2@example.test", payments=("60.00", "40.00", "5.00"))
    invoice = w.invoices["INV-1"]
    assert state(w, invoice)[0] == "OUTSTANDING"
    allocated_ok(w, w.txns[0], invoice, 6_000)
    assert state(w, invoice)[0] == "PARTIALLY_PAID"
    allocated_ok(w, w.txns[1], invoice, 4_000)
    assert state(w, invoice) == ("PAID_VERIFIED", 10_000, 0)

    blocked = allocate(w, w.txns[2], line(invoice, 500))
    assert blocked.status_code == 409
    assert blocked.json()["needs_overpayment_confirmation"] is True
    assert state(w, invoice) == ("PAID_VERIFIED", 10_000, 0)

    confirmed = allocate(w, w.txns[2], line(invoice, 500, overpayment_confirmed=True))
    assert confirmed.status_code == 200, confirmed.content
    assert confirmed.json()["invoice_states"][0]["overpayment_flag"] is True
    assert state(w, invoice) == ("PAID_VERIFIED", 10_500, 0)
    assert scalar(w, "SELECT count(*) FROM payment_allocations WHERE overpayment_confirmed") == 1


def test_overpayment_flag_is_stored_only_where_it_overpays(owner_db: Any) -> None:
    w = world(owner_db, "t3@example.test")
    response = allocate(w, w.txns[0], line(w.invoices["INV-1"], 4_000, overpayment_confirmed=True))
    assert response.status_code == 200
    assert scalar(w, "SELECT count(*) FROM payment_allocations WHERE overpayment_confirmed") == 0


def test_fr033_cannot_allocate_more_than_the_transaction(owner_db: Any) -> None:
    w = world(
        owner_db,
        "t4@example.test",
        invoices=(("INV-1", "Acme", "200.00"),),
    )
    refused = allocate(w, w.txns[0], line(w.invoices["INV-1"], 12_000))
    assert refused.status_code == 409 and refused.json()["code"] == "CONFLICT_VERSION"
    assert state(w, w.invoices["INV-1"]) == ("OUTSTANDING", 0, 20_000)
    assert allocate(w, w.txns[0], line(w.invoices["INV-1"], 7_000)).status_code == 200

    unmatched = w.client.get(f"{API}/workspaces/{w.ws}/transactions/unmatched").json()["items"]
    assert [(u["id"], u["remaining_minor"]) for u in unmatched] == [(w.txns[0], 3_000)]
    assert allocate(w, w.txns[0], line(w.invoices["INV-1"], 3_001)).status_code == 409
    assert allocate(w, w.txns[0], line(w.invoices["INV-1"], 3_000)).status_code == 200
    assert w.client.get(f"{API}/workspaces/{w.ws}/transactions/unmatched").json()["items"] == []


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(0, 422), (-5, 422), ("100", 422), (100.5, 422), (True, 422), (2**63, 422), (None, 422)],
)
def test_allocation_amount_must_be_a_positive_integer(owner_db: Any, amount: Any, expected: int) -> None:
    w = world(owner_db, f"t5{uuid.uuid4().hex[:6]}@example.test")
    response = allocate(w, w.txns[0], line(w.invoices["INV-1"], amount))
    assert response.status_code == expected, response.content
    assert scalar(w, "SELECT count(*) FROM payment_allocations") == 0


def test_lines_must_be_distinct_and_present(owner_db: Any) -> None:
    w = world(owner_db, "t6@example.test")
    invoice = w.invoices["INV-1"]
    assert allocate(w, w.txns[0]).status_code == 422
    assert allocate(w, w.txns[0], line(invoice, 1), line(invoice, 2)).status_code == 422
    assert allocate(w, w.txns[0], line(invoice, 1, surprise=True)).status_code == 422
    assert allocate(w, str(uuid.uuid4()), line(invoice, 1)).status_code == 404
    assert allocate(w, w.txns[0], line(str(uuid.uuid4()), 1)).status_code == 404


def test_split_across_invoices_is_atomic(owner_db: Any) -> None:
    w = world(
        owner_db,
        "t7@example.test",
        invoices=(("INV-1", "Acme", "40.00"), ("INV-2", "Zenith", "100.00")),
    )
    refused = allocate(w, w.txns[0], line(w.invoices["INV-2"], 5_000), line(w.invoices["INV-1"], 5_000))
    assert refused.status_code == 409 and refused.json()["needs_overpayment_confirmation"] is True
    assert scalar(w, "SELECT count(*) FROM payment_allocations") == 0
    split = allocate(w, w.txns[0], line(w.invoices["INV-2"], 6_000), line(w.invoices["INV-1"], 4_000))
    assert split.status_code == 200, split.content
    assert state(w, w.invoices["INV-1"])[0] == "PAID_VERIFIED"
    assert state(w, w.invoices["INV-2"])[0] == "PARTIALLY_PAID"


def test_fr035_allocation_records_the_person_and_evidence(owner_db: Any) -> None:
    w = world(owner_db, "t8@example.test")
    response = allocate(w, w.txns[0], line(w.invoices["INV-1"], 4_000))
    [allocation] = response.json()["allocations"]
    assert allocation["confirmed_by"] == str(w.user) and allocation["created_at"]
    assert allocation["evidence_type"] == "STATEMENT_ROW"
    actor = scalar(
        w,
        "SELECT actor_id FROM audit_events WHERE action = 'allocation.created' AND object_id = %s",
        allocation["id"],
    )
    assert str(actor) == str(w.user)


def test_retry_same_key_returns_original_allocation(owner_db: Any) -> None:
    w = world(owner_db, "t9@example.test")
    key = idem()
    first = allocate(w, w.txns[0], line(w.invoices["INV-1"], 4_000), headers=key)
    second = allocate(w, w.txns[0], line(w.invoices["INV-1"], 4_000), headers=key)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert scalar(w, "SELECT count(*) FROM payment_allocations") == 1
    assert state(w, w.invoices["INV-1"]) == ("PARTIALLY_PAID", 4_000, 6_000)
    changed = allocate(w, w.txns[0], line(w.invoices["INV-1"], 5_000), headers=key)
    assert changed.status_code == 422 and changed.json()["code"] == "IDEMPOTENCY_MISMATCH"


def test_duplicate_transaction_cannot_allocate_twice(owner_db: Any) -> None:
    """Critical negative 4: the same money, seen twice, pays once."""
    w = world(owner_db, "n4@example.test", payments=("100.00", "100.00"))
    first, duplicate = w.txns
    allocated_ok(w, first, w.invoices["INV-1"], 10_000)
    marked = w.client.post(
        f"{API}/workspaces/{w.ws}/transactions/{duplicate}/mark-duplicate",
        {"duplicate_of": first},
        format="json",
        **idem(),
    )
    assert marked.status_code == 200, marked.content
    assert marked.json()["payment"]["status"] == "DUPLICATE"
    assert marked.json()["payment"]["duplicate_of_transaction_id"] == first
    refused = allocate(w, duplicate, line(w.invoices["INV-1"], 1, overpayment_confirmed=True))
    assert refused.status_code == 409 and refused.json()["code"] == "STATE_TRANSITION_INVALID"
    assert state(w, w.invoices["INV-1"]) == ("PAID_VERIFIED", 10_000, 0)
    assert allocate(w, first, line(w.invoices["INV-1"], 1, overpayment_confirmed=True)).status_code == 409


def test_mark_duplicate_refuses_what_is_not_a_duplicate(owner_db: Any) -> None:
    w = world(owner_db, "n5@example.test", payments=("100.00", "90.00", "100.00"))
    one, other_amount, two = w.txns

    def mark(txn: str, target: str) -> Any:
        return w.client.post(
            f"{API}/workspaces/{w.ws}/transactions/{txn}/mark-duplicate",
            {"duplicate_of": target},
            format="json",
            **idem(),
        )

    assert mark(one, one).status_code == 422
    assert mark(one, other_amount).status_code == 422
    assert mark(one, str(uuid.uuid4())).status_code == 404
    allocation = allocated_ok(w, one, w.invoices["INV-1"], 1_000)
    assert mark(one, two).status_code == 409
    assert reverse(w, allocation).status_code == 200
    assert mark(one, two).status_code == 200
    assert mark(two, one).status_code == 409


def test_mark_duplicate_withdraws_its_proposals(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "n6@example.test")
    ids = load_invoices(client, ws, ("INV-7", "Northwind", "100.00"))
    rows = [("2026-10-20", "NEFT INV-7", "100.00"), ("2026-10-21", "IMPS INV-7", "100.00")]
    assert _post(client, ws, _account(client, ws), _statement(rows)).status_code == 201
    drain_jobs()
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    txns = [
        str(r[0])
        for r in owner_db.execute("SELECT id FROM payment_transactions ORDER BY value_date").fetchall()
    ]
    marked = client.post(
        f"{API}/workspaces/{ws}/transactions/{txns[1]}/mark-duplicate",
        {"duplicate_of": txns[0]},
        format="json",
        **idem(),
    )
    assert marked.status_code == 200
    items = client.get(f"{API}/workspaces/{ws}/reconciliation/proposals").json()["items"]
    assert [i["transaction"]["id"] for i in items] == [txns[0]]
    assert ids


def test_finance_role_without_permission_denied(owner_db: Any) -> None:
    """Critical negative 5: a role without ledger.write, and any non-person actor, are refused."""
    w = world(owner_db, "n7@example.test")
    lead, _ = add_member(owner_db, w.ws, "lead@example.test", "PROJECT_LEAD")
    body = {"transaction_id": w.txns[0], "allocations": [line(w.invoices["INV-1"], 1)]}
    assert lead.post(f"{API}/workspaces/{w.ws}/allocations", body, format="json", **idem()).status_code == 403

    finance, _ = add_member(owner_db, w.ws, "finance@example.test", "FINANCE_ADMIN")
    assert (
        finance.post(f"{API}/workspaces/{w.ws}/allocations", body, format="json", **idem()).status_code == 200
    )

    for actor in ("AI", "SYSTEM"):
        ctx = RequestContext(uuid.UUID(w.ws), w.user, "OWNER", str(uuid.uuid4()), actor)
        with pytest.raises(ProblemError) as refused:
            ledger.confirm_allocation(
                ctx, uuid.UUID(w.txns[0]), [ledger.Line(uuid.UUID(w.invoices["INV-1"]), 1)]
            )
        assert refused.value.status == 403
    assert scalar(w, "SELECT count(*) FROM payment_allocations") == 1


def test_reversal_of_partial_restores_the_balance(owner_db: Any) -> None:
    w = world(owner_db, "r1@example.test")
    invoice = w.invoices["INV-1"]
    allocation = allocated_ok(w, w.txns[0], invoice, 4_000)
    done = reverse(w, allocation)
    assert done.status_code == 200, done.content
    assert state(w, invoice) == ("OUTSTANDING", 0, 10_000)
    rows = w.owner_db.execute(
        "SELECT kind, amount_minor, reverses_allocation_id::text, note FROM payment_allocations ORDER BY kind"
    ).fetchall()
    assert rows == [
        ("ALLOCATION", 4_000, None, None),
        ("REVERSAL", -4_000, allocation, "Allocated to the wrong invoice"),
    ]
    assert scalar(w, "SELECT count(*) FROM audit_events WHERE action = 'allocation.reversed'") == 1
    # money released by the reversal can be allocated again
    assert allocate(w, w.txns[0], line(invoice, 10_000)).status_code == 200


def test_reversal_needs_a_reason(owner_db: Any) -> None:
    w = world(owner_db, "r2@example.test")
    allocation = allocated_ok(w, w.txns[0], w.invoices["INV-1"], 4_000)
    for body in ({}, {"reason": ""}, {"reason": "   "}):
        response = w.client.post(
            f"{API}/workspaces/{w.ws}/allocations/{allocation}/reverse", body, format="json", **idem()
        )
        assert response.status_code == 422, response.content
    assert state(w, w.invoices["INV-1"]) == ("PARTIALLY_PAID", 4_000, 6_000)
    assert reverse(w, str(uuid.uuid4())).status_code == 404


def test_a_reversal_row_cannot_itself_be_reversed(owner_db: Any) -> None:
    w = world(owner_db, "r3@example.test")
    allocation = allocated_ok(w, w.txns[0], w.invoices["INV-1"], 4_000)
    body = reverse(w, allocation).json()
    reversal = next(a["id"] for a in body["allocations"] if a["kind"] == "REVERSAL")
    assert reverse(w, reversal).status_code == 409


def test_reversal_of_paid_invoice_sets_followup_needs_review_not_auto_resume(owner_db: Any) -> None:
    """AC-14: `RESOLVED --> NEEDS_REVIEW`, and nothing starts contacting the customer again by itself."""
    w = world(owner_db, "r4@example.test")
    invoice = w.invoices["INV-1"]

    def reminder() -> str:
        return scalar(w, "SELECT reminder_status FROM invoice_state WHERE invoice_id = %s", invoice)

    assert reminder() == "NOT_CONTACTED"
    allocation = allocated_ok(w, w.txns[0], invoice, 10_000)
    assert state(w, invoice)[0] == "PAID_VERIFIED"
    assert reminder() == "RESOLVED"
    assert reverse(w, allocation).status_code == 200
    drain_jobs()
    assert state(w, invoice) == ("OUTSTANDING", 0, 10_000)
    assert reminder() == "NEEDS_REVIEW"


def test_reversal_of_partial_leaves_followup_alone(owner_db: Any) -> None:
    w = world(owner_db, "r5@example.test")
    invoice = w.invoices["INV-1"]
    allocation = allocated_ok(w, w.txns[0], invoice, 4_000)
    assert reverse(w, allocation).status_code == 200
    assert scalar(w, "SELECT reminder_status FROM invoice_state WHERE invoice_id = %s", invoice) == (
        "NOT_CONTACTED"
    )


# ---- proposals --------------------------------------------------------------------------------------


def _with_proposal(owner_db: Any, email: str) -> tuple[World, dict[str, Any]]:
    client, ws = owner_workspace(owner_db, email)
    ids = load_invoices(client, ws, ("INV-7", "Northwind", "100.00"))
    response = _post(
        client, ws, _account(client, ws), _statement([("2026-10-20", "NEFT Northwind INV-7", "100.00")])
    )
    assert response.status_code == 201
    drain_jobs()
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    txn = str(owner_db.execute("SELECT id FROM payment_transactions").fetchone()[0])
    user = owner_db.execute("SELECT user_id FROM workspace_memberships WHERE role = 'OWNER'").fetchone()[0]
    [proposal] = client.get(f"{API}/workspaces/{ws}/reconciliation/proposals").json()["items"]
    return World(client, ws, user, ids, [txn], owner_db), proposal


def _confirm(w: World, proposal: str, *lines: dict[str, Any]) -> Any:
    return w.client.post(
        f"{API}/workspaces/{w.ws}/reconciliation/proposals/{proposal}/confirm",
        {"allocations": list(lines)},
        format="json",
        **idem(),
    )


def test_confirming_a_proposal_allocates_and_records_the_decision(owner_db: Any) -> None:
    w, proposal = _with_proposal(owner_db, "p1@example.test")
    invoice = w.invoices["INV-7"]
    assert state(w, invoice)[0] == "AWAITING_VERIFICATION"
    done = _confirm(w, proposal["id"], line(invoice, 10_000))
    assert done.status_code == 200, done.content
    assert done.json()["allocations"][0]["match_id"] == proposal["id"]
    assert state(w, invoice) == ("PAID_VERIFIED", 10_000, 0)
    assert scalar(w, "SELECT status FROM reconciliation_matches") == "CONFIRMED"
    assert scalar(w, "SELECT decided_by FROM reconciliation_matches") == w.user
    assert scalar(w, "SELECT count(*) FROM audit_events WHERE action = 'match.confirmed'") == 1

    again = _confirm(w, proposal["id"], line(invoice, 10_000))
    assert again.status_code == 409 and again.json()["code"] == "STATE_TRANSITION_INVALID"
    assert state(w, invoice) == ("PAID_VERIFIED", 10_000, 0)


def test_confirm_needs_the_proposals_own_invoice(owner_db: Any) -> None:
    w, proposal = _with_proposal(owner_db, "p2@example.test")
    other = load_invoices(w.client, w.ws, ("INV-8", "Zenith", "100.00"))["INV-8"]
    assert _confirm(w, proposal["id"], line(other, 100)).status_code == 422
    assert _confirm(w, str(uuid.uuid4()), line(other, 100)).status_code == 404
    assert scalar(w, "SELECT count(*) FROM payment_allocations") == 0


def test_a_named_proposal_must_be_about_this_payment_and_still_open(owner_db: Any) -> None:
    w, proposal = _with_proposal(owner_db, "p3@example.test")
    invoice = uuid.UUID(w.invoices["INV-7"])
    other = ledger.record_payment(w.ctx(), "CASH", 10_000, "INR", clock.today())["payment"]["id"]
    match = uuid.UUID(proposal["id"])
    lines = [ledger.Line(invoice, 10_000)]
    refusals = [
        (uuid.UUID(other), match, 422),
        (uuid.UUID(w.txns[0]), uuid.uuid4(), 404),
    ]
    for txn, named, status in refusals:
        with pytest.raises(ProblemError) as refused:
            ledger.confirm_allocation(w.ctx(), txn, lines, match_id=named)
        assert refused.value.status == status
    assert scalar(w, "SELECT count(*) FROM payment_allocations") == 0

    done = ledger.confirm_allocation(w.ctx(), uuid.UUID(w.txns[0]), lines, match_id=match)
    assert done["allocations"][0]["match_id"] == proposal["id"]
    with pytest.raises(ProblemError) as decided:
        ledger.confirm_allocation(w.ctx(), uuid.UUID(w.txns[0]), lines, match_id=match)
    assert decided.value.code == "STATE_TRANSITION_INVALID"


def test_allocating_through_e059_settles_the_matching_proposal(owner_db: Any) -> None:
    w, _ = _with_proposal(owner_db, "p3@example.test")
    allocated_ok(w, w.txns[0], w.invoices["INV-7"], 10_000)
    assert scalar(w, "SELECT status FROM reconciliation_matches") == "CONFIRMED"
    assert w.client.get(f"{API}/workspaces/{w.ws}/reconciliation/proposals").json()["items"] == []


def test_settled_invoice_withdraws_rival_proposals(owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "p4@example.test")
    ids = load_invoices(client, ws, ("INV-7", "Northwind", "100.00"))
    rows = [("2026-10-20", "NEFT INV-7", "100.00"), ("2026-10-21", "IMPS INV-7", "100.00")]
    assert _post(client, ws, _account(client, ws), _statement(rows)).status_code == 201
    drain_jobs()
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    user = owner_db.execute("SELECT user_id FROM workspace_memberships WHERE role = 'OWNER'").fetchone()[0]
    txns = [
        str(r[0])
        for r in owner_db.execute("SELECT id FROM payment_transactions ORDER BY value_date").fetchall()
    ]
    w = World(client, ws, user, ids, txns, owner_db)
    allocation = allocated_ok(w, txns[0], ids["INV-7"], 10_000)
    assert client.get(f"{API}/workspaces/{ws}/reconciliation/proposals").json()["items"] == []

    # undoing the payment lets the rival transaction be proposed again, and never the declined pair
    assert reverse(w, allocation).status_code == 200
    drain_jobs()
    items = client.get(f"{API}/workspaces/{ws}/reconciliation/proposals").json()["items"]
    assert [i["transaction"]["id"] for i in items] == [txns[1]]


def test_reversal_does_not_repropose_the_same_pair(owner_db: Any) -> None:
    w, proposal = _with_proposal(owner_db, "p5@example.test")
    invoice = w.invoices["INV-7"]
    done = _confirm(w, proposal["id"], line(invoice, 10_000))
    allocation = done.json()["allocations"][0]["id"]
    assert reverse(w, allocation, "Belongs to another client").status_code == 200
    drain_jobs()
    assert state(w, invoice) == ("OUTSTANDING", 0, 10_000)
    assert w.client.get(f"{API}/workspaces/{w.ws}/reconciliation/proposals").json()["items"] == []
    assert scalar(w, "SELECT status FROM reconciliation_matches") == "REJECTED"
    assert scalar(w, "SELECT decision_reason FROM reconciliation_matches") == "Belongs to another client"


def test_partial_confirm_keeps_the_pair_from_being_proposed_again(owner_db: Any) -> None:
    w, proposal = _with_proposal(owner_db, "p6@example.test")
    assert _confirm(w, proposal["id"], line(w.invoices["INV-7"], 4_000)).status_code == 200
    with tenant_tx(w.ctx()):
        from collectiq.evidence import service_matching

        assert service_matching.reconcile(w.ctx(), [w.txns[0]]) == 0
    assert w.client.get(f"{API}/workspaces/{w.ws}/reconciliation/proposals").json()["items"] == []
    assert state(w, w.invoices["INV-7"]) == ("PARTIALLY_PAID", 4_000, 6_000)


def test_e058_reject_needs_no_reason_and_is_final(owner_db: Any) -> None:
    w, proposal = _with_proposal(owner_db, "p7@example.test")
    url = f"{API}/workspaces/{w.ws}/reconciliation/proposals/{proposal['id']}/reject"
    response = w.client.post(url, {}, format="json", **idem())
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "REJECTED"
    assert state(w, w.invoices["INV-7"])[0] == "OUTSTANDING"
    again = w.client.post(url, {"reason": "No"}, format="json", **idem())
    assert again.status_code == 409 and again.json()["code"] == "STATE_TRANSITION_INVALID"
    unknown = f"{API}/workspaces/{w.ws}/reconciliation/proposals/{uuid.uuid4()}/reject"
    assert w.client.post(unknown, {}, format="json", **idem()).status_code == 404


def test_new_money_follows_allocations_not_only_proposals(owner_db: Any) -> None:
    """A person's own E059 choice teaches the matcher, and reversing it unteaches."""
    w = world(owner_db, "p8@example.test")
    allocation = allocated_ok(w, w.txns[0], w.invoices["INV-1"], 4_000)
    with tenant_tx(w.ctx()):
        from collectiq.evidence import service_matching

        txn = {"payer_descriptor": None, "payment_account_id": None}
        client_id = scalar(w, "SELECT client_id FROM invoices WHERE id = %s", w.invoices["INV-1"])
        account = scalar(w, "SELECT payment_account_id FROM payment_transactions WHERE id = %s", w.txns[0])
        txn["payment_account_id"] = account
        assert service_matching._history(txn, client_id, {})[1] is True
    assert reverse(w, allocation).status_code == 200
    with tenant_tx(w.ctx()):
        assert service_matching._history(txn, client_id, {})[1] is False


# ---- manual payments --------------------------------------------------------------------------------


def test_e049_manual_payment_with_allocation(owner_db: Any) -> None:
    w = world(owner_db, "m1@example.test", payments=())
    invoice = w.invoices["INV-1"]
    response = manual(
        w,
        6_000,
        reference="INV-1",
        payer="Acme Pvt Ltd",
        notes="Told by phone, then seen in the bank app",
        allocations=[line(invoice, 6_000)],
    )
    assert response.status_code == 201, response.content
    body = response.json()
    payment = body["payment"]
    assert payment["evidence_type"] == "USER_CONFIRMATION" and payment["lower_assurance"] is True
    assert payment["source_type"] == "MANUAL" and payment["method"] == "BANK_TRANSFER"
    assert payment["entered_by"] == str(w.user) and payment["account_label"] is None
    assert payment["unallocated_minor"] == 0
    assert body["invoice_states"][0]["payment_status"] == "PARTIALLY_PAID"
    assert body["invoice_states"][0]["outstanding_minor"] == 4_000
    assert scalar(w, "SELECT count(*) FROM audit_events WHERE action = 'payment.recorded'") == 1
    assert body["allocations"][0]["evidence_type"] == "USER_CONFIRMATION"


def test_e049_keeps_identical_cash_entries_apart_and_replays_a_retry(owner_db: Any) -> None:
    w = world(owner_db, "m2@example.test", payments=())
    assert manual(w, 500).status_code == 201
    assert manual(w, 500).status_code == 201
    assert scalar(w, "SELECT count(*) FROM payment_transactions") == 2
    key = idem()
    body = {
        "method": "CASH",
        "amount": {"amount_minor": 500, "currency": "INR"},
        "value_date": "2026-10-20",
    }
    first = w.client.post(f"{API}/workspaces/{w.ws}/payments", body, format="json", **key)
    second = w.client.post(f"{API}/workspaces/{w.ws}/payments", body, format="json", **key)
    assert first.status_code == second.status_code == 201 and first.content == second.content
    assert scalar(w, "SELECT count(*) FROM payment_transactions") == 3


@pytest.mark.parametrize(
    "change",
    [
        {"method": "AI_GUESS"},
        {"method": "MARK_PAID"},
        {"value_date": "2026-10-31"},
        {"amount": {"amount_minor": 0, "currency": "INR"}},
        {"amount": {"amount_minor": -1, "currency": "INR"}},
        {"amount": {"amount_minor": "100", "currency": "INR"}},
        {"amount": {"amount_minor": 10.5, "currency": "INR"}},
        {"amount": {"amount_minor": 100, "currency": "XXQ"}},
        {"amount": {"amount_minor": 100, "currency": "INR", "extra": 1}},
        {"surprise": "x"},
    ],
)
def test_e049_validation(owner_db: Any, change: dict[str, Any]) -> None:
    w = world(owner_db, f"m3{uuid.uuid4().hex[:6]}@example.test", payments=())
    body = {
        "method": "CASH",
        "amount": {"amount_minor": 100, "currency": "INR"},
        "value_date": "2026-10-20",
        **change,
    }
    response = w.client.post(f"{API}/workspaces/{w.ws}/payments", body, format="json", **idem())
    assert response.status_code == 422, response.content
    assert scalar(w, "SELECT count(*) FROM payment_transactions") == 0


def test_e049_lines_above_the_amount_leave_nothing(owner_db: Any) -> None:
    w = world(owner_db, "m4@example.test", payments=())
    response = manual(w, 100, allocations=[line(w.invoices["INV-1"], 101)])
    assert response.status_code == 422
    assert scalar(w, "SELECT count(*) FROM payment_transactions") == 0
    assert state(w, w.invoices["INV-1"]) == ("OUTSTANDING", 0, 10_000)


def test_manual_payment_is_never_proposed_by_the_matcher(owner_db: Any) -> None:
    w = world(owner_db, "m5@example.test", payments=())
    created = manual(w, 10_000, reference="INV-1")
    with tenant_tx(w.ctx()):
        from collectiq.evidence import service_matching

        assert service_matching.reconcile(w.ctx(), [created.json()["payment"]["id"]]) == 0
    assert scalar(w, "SELECT count(*) FROM reconciliation_matches") == 0
    unmatched = w.client.get(f"{API}/workspaces/{w.ws}/transactions/unmatched").json()["items"]
    assert unmatched[0]["remaining_minor"] == 10_000 and unmatched[0]["account_label"] is None


def test_e052_void_undoes_a_mistaken_manual_entry(owner_db: Any) -> None:
    w = world(owner_db, "v1@example.test", payments=())
    invoice = w.invoices["INV-1"]
    created = manual(w, 10_000, allocations=[line(invoice, 10_000)])
    payment = created.json()["payment"]["id"]
    assert state(w, invoice) == ("PAID_VERIFIED", 10_000, 0)
    url = f"{API}/workspaces/{w.ws}/payments/{payment}/void"

    assert w.client.post(url, {}, format="json", **idem()).status_code == 422
    done = w.client.post(url, {"reason": "Entered twice"}, format="json", **idem())
    assert done.status_code == 200, done.content
    assert done.json()["payment"]["status"] == "VOID" and done.json()["payment"]["void_reason"]
    assert state(w, invoice) == ("OUTSTANDING", 0, 10_000)
    assert (
        scalar(w, "SELECT reminder_status FROM invoice_state WHERE invoice_id = %s", invoice)
        == "NEEDS_REVIEW"
    )
    assert scalar(w, "SELECT count(*) FROM payment_allocations WHERE kind = 'REVERSAL'") == 1
    assert scalar(w, "SELECT count(*) FROM audit_events WHERE action = 'payment.voided'") == 1

    again = w.client.post(url, {"reason": "Again"}, format="json", **idem())
    assert again.status_code == 409
    assert allocate(w, payment, line(invoice, 1)).status_code == 409
    unknown = f"{API}/workspaces/{w.ws}/payments/{uuid.uuid4()}/void"
    assert w.client.post(unknown, {"reason": "x"}, format="json", **idem()).status_code == 404


def test_e052_refuses_a_statement_row(owner_db: Any) -> None:
    w = world(owner_db, "v2@example.test")
    url = f"{API}/workspaces/{w.ws}/payments/{w.txns[0]}/void"
    response = w.client.post(url, {"reason": "Not ours"}, format="json", **idem())
    assert response.status_code == 409
    assert scalar(w, "SELECT status FROM payment_transactions") == "ACTIVE"


def test_e050_e051_list_and_detail(owner_db: Any) -> None:
    w = world(owner_db, "l1@example.test", payments=("100.00", "50.00"))
    allocation = allocated_ok(w, w.txns[0], w.invoices["INV-1"], 4_000)
    reverse(w, allocation)
    allocated_ok(w, w.txns[0], w.invoices["INV-1"], 3_000)

    page = w.client.get(f"{API}/workspaces/{w.ws}/payments?limit=1").json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    rest = w.client.get(f"{API}/workspaces/{w.ws}/payments?limit=1&cursor={page['next_cursor']}").json()
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None
    assert {page["items"][0]["id"], rest["items"][0]["id"]} == set(w.txns)
    assert w.client.get(f"{API}/workspaces/{w.ws}/payments?limit=0").status_code == 422

    detail = w.client.get(f"{API}/workspaces/{w.ws}/payments/{w.txns[0]}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["allocated_minor"] == 3_000 and body["unallocated_minor"] == 7_000
    assert sorted(a["amount_minor"] for a in body["allocations"]) == [-4_000, 3_000, 4_000]
    assert all(a["invoice_number"] == "INV-1" for a in body["allocations"])
    assert body["account_label"]
    assert w.client.get(f"{API}/workspaces/{w.ws}/payments/{uuid.uuid4()}").status_code == 404


def test_e051_matches_show_labels_not_scores(owner_db: Any) -> None:
    w, proposal = _with_proposal(owner_db, "l2@example.test")
    body = w.client.get(f"{API}/workspaces/{w.ws}/payments/{w.txns[0]}").json()
    [match] = body["matches"]
    assert match["id"] == proposal["id"] and match["label"] == "Strong" and match["status"] == "PROPOSED"
    assert "score" not in str(body).lower()


def test_lowered_total_below_paid_becomes_uncertain_not_paid(owner_db: Any) -> None:
    """Ruling: a corrected total below what is allocated is shown as a problem, not hidden by a trigger."""
    w = world(owner_db, "g1@example.test")
    invoice = w.invoices["INV-1"]
    allocated_ok(w, w.txns[0], invoice, 8_000)
    detail = w.client.get(f"{API}/workspaces/{w.ws}/invoices/{invoice}")
    response = w.client.patch(
        f"{API}/workspaces/{w.ws}/invoices/{invoice}",
        {"gross_minor": 5_000, "reason": "Credit note issued"},
        format="json",
        HTTP_IF_MATCH=detail["ETag"],
    )
    assert response.status_code == 200, response.content
    drain_jobs()
    status, paid, outstanding = state(w, invoice)
    assert (status, paid, outstanding) == ("UNCERTAIN", 8_000, 0)


# ---- F-7 over random ledger operations ------------------------------------------------------------

_OPS = st.lists(
    st.tuples(st.sampled_from(["allocate", "overpay", "reverse", "reverse_first"]), st.integers(1, 12_000)),
    max_size=8,
)


@pytest.fixture
def property_world(owner_db: Any) -> World:
    return world(owner_db, f"prop{uuid.uuid4().hex[:6]}@example.test", payments=())


def _assert_state_equals_derive(ctx: RequestContext, invoice: str) -> None:
    with tenant_tx(ctx):
        facts = service_state.load_facts(invoice)
        derived = derive(facts)
        stored = service_state.snapshot([uuid.UUID(invoice)])[0]
    assert stored["payment_status"] == derived.payment_status
    assert stored["paid_minor"] == derived.paid_minor
    assert stored["outstanding_minor"] == derived.outstanding_minor
    assert stored["overpayment_flag"] == derived.overpayment_flag


@hypothesis_settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(ops=_OPS)
def test_stored_state_equals_derive_over_random_ledger_operations(
    property_world: World, ops: list[tuple[str, int]]
) -> None:
    """Property for F-7 and F-1: any mix of allocations and reversals keeps the invariants."""
    w = property_world
    ctx = w.ctx()
    number = f"P-{uuid.uuid4().hex[:8]}"
    # a new client each time: the same client and total would be held by the import as a possible duplicate
    invoice = load_invoices(w.client, w.ws, (number, f"Acme {number}", "100.00"))[number]
    created = ledger.record_payment(ctx, "CASH", 40_000, "INR", clock.today())
    txn = uuid.UUID(created["payment"]["id"])
    live: list[uuid.UUID] = []
    for name, amount in ops:
        try:
            if name in ("allocate", "overpay"):
                result = ledger.confirm_allocation(
                    ctx,
                    txn,
                    [ledger.Line(uuid.UUID(invoice), amount)],
                    overpayment_confirmed=name == "overpay",
                )
                live.append(uuid.UUID(result["allocations"][0]["id"]))
            elif live:
                ledger.reverse_allocation(ctx, live.pop(0 if name == "reverse_first" else -1), "Corrected")
        except ProblemError as refused:
            assert refused.status == 409
        _assert_state_equals_derive(ctx, invoice)
        payment = ledger.get_payment(ctx, txn)
        assert 0 <= payment["allocated_minor"] <= payment["amount_minor"]
    with tenant_tx(ctx):
        drifted = service_state.check_integrity(ctx, repair=False)
    assert invoice not in drifted


# --- a confirmed allocation (FR-057): claim tasks close, an overpayment opens a review ---


def _claim_task(w: World, invoice: str) -> str:
    """A customer's payment claim, as a person's label leaves it: an open task counted on the invoice."""
    w.owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [w.ws])
    message = w.owner_db.execute(
        "INSERT INTO messages (workspace_id, source, received_at, body_enc, body_sha256, uploaded_by)"
        " VALUES (%s, 'PASTE', now(), %s, 'x', %s) RETURNING id",
        [w.ws, b"x", w.user],
    ).fetchone()[0]
    task = w.owner_db.execute(
        "INSERT INTO verification_tasks (workspace_id, invoice_id, message_id, kind)"
        " VALUES (%s, %s, %s, 'PAYMENT_CLAIM') RETURNING id",
        [w.ws, invoice, message],
    ).fetchone()[0]
    w.owner_db.execute("UPDATE invoice_state SET open_task_count = 1 WHERE invoice_id = %s", [invoice])
    return str(task)


def test_recording_a_payment_closes_the_open_payment_claim_task(owner_db: Any) -> None:
    w = world(owner_db, "t60@example.test")
    invoice = w.invoices["INV-1"]
    task = _claim_task(w, invoice)
    assert allocate(w, w.txns[0], line(invoice, 4_000)).status_code == 200
    drain_jobs()
    assert scalar(w, "SELECT status FROM verification_tasks WHERE id = %s", task) == "CLOSED"
    assert scalar(w, "SELECT open_task_count FROM invoice_state WHERE invoice_id = %s", invoice) == 0
    # The payment, not the customer's word, is what moved the status; the task only stops blocking.
    assert state(w, invoice) == ("PARTIALLY_PAID", 4_000, 6_000)
    assert scalar(w, "SELECT count(*) FROM audit_events WHERE action = 'verification_task.closed'") == 1


def test_a_confirmed_overpayment_opens_one_match_review_case(owner_db: Any) -> None:
    w = world(owner_db, "t61@example.test", payments=("100.00", "5.00", "2.00"))
    invoice = w.invoices["INV-1"]
    allocated_ok(w, w.txns[0], invoice, 10_000)
    assert allocate(w, w.txns[1], line(invoice, 500, overpayment_confirmed=True)).status_code == 200
    drain_jobs()
    cases = w.owner_db.execute(
        "SELECT type, status, opened_by_kind FROM cases WHERE invoice_id = %s", [invoice]
    ).fetchall()
    assert cases == [("MATCH_REVIEW", "OPEN", "SYSTEM")]
    # A second overpayment while the review is open adds nothing.
    assert allocate(w, w.txns[2], line(invoice, 200, overpayment_confirmed=True)).status_code == 200
    drain_jobs()
    assert scalar(w, "SELECT count(*) FROM cases WHERE invoice_id = %s", invoice) == 1
    # It does not mark a dispute: only reminders are held.
    assert scalar(w, "SELECT dispute_status FROM invoice_state WHERE invoice_id = %s", invoice) == "NONE"


def test_a_payment_that_does_not_overpay_opens_no_review(owner_db: Any) -> None:
    w = world(owner_db, "t62@example.test")
    allocated_ok(w, w.txns[0], w.invoices["INV-1"], 4_000)
    drain_jobs()
    assert scalar(w, "SELECT count(*) FROM cases") == 0
