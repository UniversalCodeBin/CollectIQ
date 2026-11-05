"""Audit history (E099, E100): scoped search, neutralised CSV export, audited export, chain check."""

import csv
import io
from typing import Any

import pytest
from rest_framework.test import APIClient

from collectiq import audit
from collectiq.audit import history
from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx
from tests.support import API, add_member, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")


def _ctx(ws: str) -> RequestContext:
    return RequestContext(
        workspace_id=ws,
        user_id=None,
        role="OWNER",
        correlation_id="c",
        actor_type="SYSTEM",  # type: ignore[arg-type]
    )


def _seed(ws: str, action: str, object_id: str = "x", after: dict[str, Any] | None = None) -> None:
    ctx = _ctx(ws)
    with tenant_tx(ctx):
        audit.record(ctx, action, "invoice", object_id, after=after)


def _search(client: APIClient, ws: str, query: str = "") -> Any:
    return client.get(f"{API}/workspaces/{ws}/audit-events{query}")


def test_search_is_tenant_scoped_and_filterable(owner_db) -> None:
    client, ws = owner_workspace(owner_db, "a-hist@example.test")
    _, other = owner_workspace(owner_db, "b-hist@example.test")
    _seed(ws, "invoice.updated", "one")
    _seed(other, "invoice.secret_other_tenant", "two")
    body = _search(client, ws).json()
    actions = [e["action"] for e in body["items"]]
    assert "invoice.updated" in actions
    assert "invoice.secret_other_tenant" not in actions
    only = _search(client, ws, "?action=invoice.updated").json()["items"]
    assert only and all(e["action"] == "invoice.updated" for e in only)
    assert _search(client, ws, "?bogus=1").status_code == 422


def test_search_pages_newest_first(owner_db) -> None:
    client, ws = owner_workspace(owner_db, "page-hist@example.test")
    for n in range(5):
        _seed(ws, "invoice.updated", f"p{n}")
    first = _search(client, ws, "?limit=2").json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = _search(client, ws, f"?limit=2&cursor={first['next_cursor']}").json()
    assert second["items"][0]["id"] < first["items"][-1]["id"]


def test_search_permission_and_copy(owner_db) -> None:
    client, ws = owner_workspace(owner_db, "perm-hist@example.test")
    outsider, _ = owner_workspace(owner_db, "outsider-hist@example.test")
    assert _search(outsider, ws).status_code in (403, 404)
    assert _search(APIClient(), ws).status_code in (401, 403)
    copy = _search(client, ws).json()["notice"]
    assert "append-only by database permissions" in copy
    assert "not tamper-resistant against a database superuser" in copy


def test_export_neutralises_csv_formula_cells(owner_db) -> None:
    client, ws = owner_workspace(owner_db, "csv-hist@example.test")
    _seed(ws, "invoice.updated", "=HYPERLINK(1)", {"note": "ok"})
    response = client.post(
        f"{API}/workspaces/{ws}/audit-events/exports", {"format": "CSV"}, format="json", **idem()
    )
    assert response.status_code == 200, response.content
    rows = list(csv.DictReader(io.StringIO(response.json()["content"])))
    target = [r for r in rows if r["action"] == "invoice.updated"]
    assert target and target[0]["object_id"] == "'=HYPERLINK(1)"
    assert not any(c[:1] in "=+-@" for r in rows for c in r.values() if c)


def test_export_is_audited_and_restricted(owner_db) -> None:
    client, ws = owner_workspace(owner_db, "exp-hist@example.test")
    lead, _ = add_member(owner_db, ws, "lead-hist@example.test", "PROJECT_LEAD")
    denied = lead.post(f"{API}/workspaces/{ws}/audit-events/exports", {}, format="json", **idem())
    assert denied.status_code == 403
    ok = client.post(
        f"{API}/workspaces/{ws}/audit-events/exports", {"format": "JSON"}, format="json", **idem()
    )
    assert ok.status_code == 200
    actions = [e["action"] for e in _search(client, ws).json()["items"]]
    assert "audit.exported" in actions


def test_chain_check_detects_seeded_break(owner_db) -> None:
    _, ws = owner_workspace(owner_db, "chain-hist@example.test")
    for n in range(3):
        _seed(ws, "invoice.updated", f"c{n}")
    ctx = _ctx(ws)
    assert history.verify_chain(ctx)["intact"] is True
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    owner_db.execute("ALTER TABLE audit_events DISABLE TRIGGER audit_events_append_only")
    try:
        owner_db.execute(
            "UPDATE audit_events SET action = 'edited' WHERE id = ("
            "SELECT id FROM audit_events WHERE workspace_id = %s AND object_id = 'c1')",
            [ws],
        )
    finally:
        owner_db.execute("ALTER TABLE audit_events ENABLE TRIGGER audit_events_append_only")
    result = history.verify_chain(ctx)
    assert result["intact"] is False and result["first_bad_id"]
    with tenant_tx(ctx):
        found = [e["action"] for e in history.search(ctx, {}, None, 50)["items"]]
    assert "audit.chain_break_detected" in found
