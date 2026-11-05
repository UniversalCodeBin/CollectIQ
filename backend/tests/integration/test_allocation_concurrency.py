"""F-8: racing requests can never over-allocate, and the loser is told so. Real threads, real commits."""

import copy
import threading
import uuid
from collections.abc import Callable
from typing import Any

import psycopg
import pytest
from django.db import connection
from rest_framework.test import APIClient

from collectiq.evidence import service_state
from collectiq.evidence.domain.derive import derive
from collectiq.platform.db import tenant_tx
from tests.integration.test_allocation_db import (  # noqa: F401
    World,
    _frozen_clock,
    allocated_ok,
    app_connection,
    line,
    raw_insert,
    scalar,
    state,
    world,
)
from tests.support import API, idem

pytestmark = [pytest.mark.usefixtures("pg"), pytest.mark.concurrency]
TIMEOUT = 60


def _clone(client: APIClient) -> APIClient:
    twin = APIClient()
    twin.cookies = copy.copy(client.cookies)
    twin.defaults = dict(client.defaults)
    return twin


def _race(w: World, *calls: Callable[[APIClient], Any]) -> list[Any]:
    """Start every call at the same moment, each with its own client and database connection."""
    barrier = threading.Barrier(len(calls))
    results: list[Any] = [None] * len(calls)
    clients = [_clone(w.client) for _ in calls]

    def run(index: int, call: Callable[[APIClient], Any]) -> None:
        try:
            barrier.wait(timeout=30)
            results[index] = call(clients[index])
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(i, c)) for i, c in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=TIMEOUT)
    assert not any(thread.is_alive() for thread in threads), "a request is stuck"
    assert all(r is not None for r in results), "a request raised"
    return results


def _allocate(w: World, txn: str, *lines: dict[str, Any]) -> Callable[[APIClient], Any]:
    key = idem()

    def call(client: APIClient) -> Any:
        return client.post(
            f"{API}/workspaces/{w.ws}/allocations",
            {"transaction_id": txn, "allocations": list(lines)},
            format="json",
            **key,
        )

    return call


def _reverse(w: World, allocation: str) -> Callable[[APIClient], Any]:
    key = idem()

    def call(client: APIClient) -> Any:
        return client.post(
            f"{API}/workspaces/{w.ws}/allocations/{allocation}/reverse",
            {"reason": "Raced"},
            format="json",
            **key,
        )

    return call


def _assert_consistent(w: World, *invoices: str) -> None:
    ctx = w.ctx()
    for invoice in invoices:
        with tenant_tx(ctx):
            derived = derive(service_state.load_facts(invoice))
            stored = service_state.snapshot([uuid.UUID(invoice)])[0]
        assert stored["payment_status"] == derived.payment_status
        assert stored["paid_minor"] == derived.paid_minor
        assert stored["outstanding_minor"] == derived.outstanding_minor
    w.owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [w.ws])
    over = w.owner_db.execute(
        "SELECT t.id FROM payment_transactions t"
        " WHERE t.amount_minor < (SELECT coalesce(sum(a.amount_minor), 0) FROM payment_allocations a"
        "                          WHERE a.transaction_id = t.id)"
    ).fetchall()
    assert over == [], "F-1 broken"


def test_parallel_confirms_on_one_transaction_never_over_allocate(owner_db: Any) -> None:
    """F-8: 10,000 of money, eight invoices each asking for 4,000. Exactly two win, the rest get 409."""
    numbers = [f"INV-{n}" for n in range(8)]
    w = world(
        owner_db,
        "c1@example.test",
        invoices=tuple((n, f"Client {n}", "100.00") for n in numbers),
    )
    results = _race(w, *[_allocate(w, w.txns[0], line(w.invoices[n], 4_000)) for n in numbers])
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200] * 2 + [409] * 6, [r.content for r in results]
    assert {r.json()["code"] for r in results if r.status_code == 409} == {"CONFLICT_VERSION"}
    assert scalar(w, "SELECT sum(amount_minor) FROM payment_allocations") == 8_000
    _assert_consistent(w, *w.invoices.values())


def test_parallel_confirms_on_one_invoice_never_exceed_its_total(owner_db: Any) -> None:
    """Eight transactions race for one invoice of 10,000. One wins; the rest are told it needs a person."""
    w = world(owner_db, "c2@example.test", payments=tuple(["100.00"] * 8))
    invoice = w.invoices["INV-1"]
    assert len(w.txns) == 8
    results = _race(w, *[_allocate(w, t, line(invoice, 10_000)) for t in w.txns])
    assert sorted(r.status_code for r in results) == [200] + [409] * 7, [r.content for r in results]
    assert state(w, invoice) == ("PAID_VERIFIED", 10_000, 0)
    assert scalar(w, "SELECT count(*) FROM payment_allocations") == 1
    _assert_consistent(w, invoice)


@pytest.mark.parametrize("round_number", [1, 2, 3])
def test_reverse_vs_confirm_race_stays_consistent(owner_db: Any, round_number: int) -> None:
    w = world(
        owner_db,
        f"c3{round_number}@example.test",
        invoices=(("INV-1", "Acme", "100.00"), ("INV-2", "Zenith", "100.00")),
    )
    first = allocated_ok(w, w.txns[0], w.invoices["INV-1"], 10_000)
    reversal, confirm = _race(
        w, _reverse(w, first), _allocate(w, w.txns[0], line(w.invoices["INV-2"], 10_000))
    )
    assert reversal.status_code == 200, reversal.content
    assert confirm.status_code in (200, 409), confirm.content
    paid_second = 10_000 if confirm.status_code == 200 else 0
    assert state(w, w.invoices["INV-1"])[1] == 0
    assert state(w, w.invoices["INV-2"])[1] == paid_second
    _assert_consistent(w, w.invoices["INV-1"], w.invoices["INV-2"])


def test_two_reversals_of_one_allocation_leave_one(owner_db: Any) -> None:
    w = world(owner_db, "c4@example.test")
    allocation = allocated_ok(w, w.txns[0], w.invoices["INV-1"], 4_000)
    results = _race(w, _reverse(w, allocation), _reverse(w, allocation))
    assert sorted(r.status_code for r in results) == [200, 409], [r.content for r in results]
    assert scalar(w, "SELECT count(*) FROM payment_allocations WHERE kind = 'REVERSAL'") == 1
    assert state(w, w.invoices["INV-1"]) == ("OUTSTANDING", 0, 10_000)


def test_crossing_splits_do_not_deadlock(owner_db: Any) -> None:
    """The same two invoices named in opposite orders. Locks are taken in id order, so both complete."""
    w = world(
        owner_db,
        "c5@example.test",
        invoices=(("INV-1", "Acme", "100.00"), ("INV-2", "Zenith", "100.00")),
        payments=("20.00", "20.00"),
    )
    one, two = w.invoices["INV-1"], w.invoices["INV-2"]
    results = _race(
        w,
        _allocate(w, w.txns[0], line(one, 1_000), line(two, 1_000)),
        _allocate(w, w.txns[1], line(two, 1_000), line(one, 1_000)),
    )
    assert [r.status_code for r in results] == [200, 200], [r.content for r in results]
    assert state(w, one)[1] == 2_000 and state(w, two)[1] == 2_000
    _assert_consistent(w, one, two)


def test_retry_racing_itself_applies_once(owner_db: Any) -> None:
    w = world(owner_db, "c6@example.test")
    same = _allocate(w, w.txns[0], line(w.invoices["INV-1"], 4_000))
    results = _race(w, same, same)
    assert [r.status_code for r in results] == [200, 200], [r.content for r in results]
    assert results[0].content == results[1].content
    assert scalar(w, "SELECT count(*) FROM payment_allocations") == 1


def test_backstop_holds_when_both_commits_race_past_the_service(owner_db: Any) -> None:
    """The deferred trigger alone, in sequence: each insert passes alone, and the later commit fails."""
    w = world(
        owner_db,
        "c7@example.test",
        invoices=(("INV-1", "Acme", "100.00"), ("INV-2", "Zenith", "100.00")),
    )
    with app_connection(w) as first, app_connection(w) as second:
        raw_insert(first, w, w.txns[0], w.invoices["INV-1"], 7_000)
        raw_insert(second, w, w.txns[0], w.invoices["INV-2"], 7_000)
        first.commit()
        with pytest.raises(psycopg.errors.CheckViolation, match="F-1"):
            second.commit()
    assert scalar(w, "SELECT sum(amount_minor) FROM payment_allocations") == 7_000


def test_backstop_holds_when_commits_truly_overlap(owner_db: Any) -> None:
    """Both commits at once, on both invariants: the row locks in the trigger make them take turns."""
    w = world(owner_db, "c8@example.test", payments=("100.00", "100.00"))
    invoice = w.invoices["INV-1"]
    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def commit_one(txn: str) -> None:
        with app_connection(w) as conn:
            raw_insert(conn, w, txn, invoice, 10_000)
            barrier.wait(timeout=30)
            try:
                conn.commit()
                outcomes.append("committed")
            except psycopg.errors.CheckViolation as error:
                outcomes.append("F-2" if "F-2" in str(error) else str(error))

    threads = [threading.Thread(target=commit_one, args=(t,)) for t in w.txns]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=TIMEOUT)
    assert not any(thread.is_alive() for thread in threads)
    assert sorted(outcomes) == ["F-2", "committed"]
    assert scalar(w, "SELECT sum(amount_minor) FROM payment_allocations") == 10_000
