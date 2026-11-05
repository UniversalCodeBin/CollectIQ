"""FR-056: an invoice shows every allocation and reversal that touched it, oldest first."""

from typing import Any

import pytest

from tests.integration.test_allocation_db import allocated_ok, reverse, world
from tests.support import API, add_member, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")


def _history(client: Any, ws: str, invoice: str) -> Any:
    return client.get(f"{API}/workspaces/{ws}/invoices/{invoice}/payments")


def test_history_lists_allocation_then_reversal(owner_db: Any) -> None:
    w = world(owner_db, "hist1@example.test")
    invoice = w.invoices["INV-1"]
    assert _history(w.client, w.ws, invoice).json() == {"items": []}
    allocation = allocated_ok(w, w.txns[0], invoice, 4_000)
    assert reverse(w, allocation).status_code == 200
    items = _history(w.client, w.ws, invoice).json()["items"]
    assert [(i["kind"], i["amount_minor"]) for i in items] == [("ALLOCATION", 4_000), ("REVERSAL", -4_000)]
    assert items[1]["reverses_allocation_id"] == allocation
    assert items[0]["transaction_id"] == w.txns[0]
    assert items[0]["invoice_number"] == "INV-1" and items[0]["currency"] == "INR"
    assert items[1]["note"] == "Allocated to the wrong invoice"


def test_history_is_private_to_the_workspace_and_to_finance_roles(owner_db: Any) -> None:
    w = world(owner_db, "hist2@example.test")
    invoice = w.invoices["INV-1"]
    allocated_ok(w, w.txns[0], invoice, 1_000)
    outsider, other_ws = owner_workspace(owner_db, "hist2b@example.test")
    assert _history(outsider, other_ws, invoice).status_code == 404
    assert _history(outsider, w.ws, invoice).status_code in (403, 404)
    lead, _ = add_member(owner_db, w.ws, "hist2p@example.test", "PROJECT_LEAD")
    assert _history(lead, w.ws, invoice).status_code == 403
    assert _history(w.client, w.ws, "00000000-0000-4000-8000-000000000000").status_code == 404
