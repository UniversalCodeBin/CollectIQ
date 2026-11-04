"""Clients, contacts and suppression (E021-E028): TSD M07, FR-149, FR-097."""

import uuid
from typing import Any

import psycopg
import pytest
from rest_framework.test import APIClient

from collectiq.invoices import clients as client_service
from collectiq.platform.context import RequestContext
from collectiq.platform.errors import ProblemError
from tests.support import API, add_member, idem, owner_workspace


def _audit(owner_db: psycopg.Connection, workspace_id: str, action: str) -> list[dict[str, Any]]:
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [workspace_id])
    cursor = owner_db.execute(
        "SELECT object_type, object_id, before_masked, after_masked, reason_codes"
        " FROM audit_events WHERE action = %s ORDER BY id",
        [action],
    )
    names = [column.name for column in cursor.description or []]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def _new_client(client: APIClient, ws: str, name: str = "Northwind Traders", **extra: Any) -> dict[str, Any]:
    response = client.post(
        f"{API}/workspaces/{ws}/clients", {"display_name": name, **extra}, format="json", **idem()
    )
    assert response.status_code == 201, response.content
    return response.json()


def _new_contact(
    client: APIClient, ws: str, client_id: str, email: str = "ap@northwind.example.test"
) -> dict[str, Any]:
    response = client.post(
        f"{API}/workspaces/{ws}/clients/{client_id}/contacts",
        {"email": email, "name": "Accounts Payable"},
        format="json",
        **idem(),
    )
    assert response.status_code == 201, response.content
    return response.json()


def _suppress(client: APIClient, ws: str, contact_id: str, reason: str = "Asked us to stop") -> Any:
    return client.post(
        f"{API}/workspaces/{ws}/contacts/{contact_id}/suppression",
        {"reason": reason},
        format="json",
        **idem(),
    )


def _ctx(ws: str) -> RequestContext:
    return RequestContext(
        workspace_id=uuid.UUID(ws),
        user_id=None,
        role="OWNER",
        correlation_id=str(uuid.uuid4()),
        actor_type="USER",
    )


def test_create_client_defaults_and_audit(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    response = owner.post(
        f"{API}/workspaces/{ws}/clients", {"display_name": "  Northwind  Traders "}, format="json", **idem()
    )
    assert response.status_code == 201, response.content
    assert response.headers["ETag"] == '"1"'
    body = response.json()
    assert body["display_name"] == "Northwind Traders"
    assert body["sensitivity"] == "STANDARD"
    assert body["version"] == 1

    events = _audit(owner_db, ws, "client.created")
    assert [event["object_id"] for event in events] == [body["id"]]


def test_client_names_are_normalised_for_later_matching(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    created = _new_client(owner, ws, "  NORTHWIND   Traders ")
    assert created["normalized_name"] == "northwind traders"


def test_sensitivity_is_user_entered_and_validated(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    assert _new_client(owner, ws, sensitivity="SENSITIVE")["sensitivity"] == "SENSITIVE"
    refused = owner.post(
        f"{API}/workspaces/{ws}/clients",
        {"display_name": "Bad", "sensitivity": "VIP"},
        format="json",
        **idem(),
    )
    assert refused.status_code == 422
    assert refused.json()["errors"][0]["field"] == "sensitivity"


def test_list_clients_pages(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    ids = {_new_client(owner, ws, f"Client {index}")["id"] for index in range(3)}

    first = owner.get(f"{API}/workspaces/{ws}/clients?limit=2").json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = owner.get(f"{API}/workspaces/{ws}/clients?limit=2&cursor={first['next_cursor']}").json()
    assert second["next_cursor"] is None
    assert {row["id"] for row in first["items"] + second["items"]} == ids


def test_update_client_requires_current_version_and_audits(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    created = _new_client(owner, ws)
    url = f"{API}/workspaces/{ws}/clients/{created['id']}"

    updated = owner.patch(
        url, {"display_name": "Northwind Ltd", "tone": "FORMAL"}, format="json", HTTP_IF_MATCH='"1"'
    )
    assert updated.status_code == 200, updated.content
    assert updated.headers["ETag"] == '"2"'
    assert updated.json()["normalized_name"] == "northwind ltd"
    assert updated.json()["tone"] == "FORMAL"

    stale = owner.patch(url, {"display_name": "Again"}, format="json", HTTP_IF_MATCH='"1"')
    assert stale.status_code == 409
    assert stale.json()["code"] == "CONFLICT_VERSION"

    events = _audit(owner_db, ws, "client.updated")
    assert len(events) == 1
    assert events[0]["before_masked"]["display_name"] == "Northwind Traders"
    assert events[0]["after_masked"]["display_name"] == "Northwind Ltd"


def test_update_without_a_change_does_not_bump_or_audit(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    created = _new_client(owner, ws)
    response = owner.patch(
        f"{API}/workspaces/{ws}/clients/{created['id']}",
        {"display_name": created["display_name"]},
        format="json",
        HTTP_IF_MATCH='"1"',
    )
    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert _audit(owner_db, ws, "client.updated") == []


def test_add_contact_audits(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    client = _new_client(owner, ws)
    contact = _new_contact(owner, ws, client["id"])
    assert contact["status"] == "ACTIVE"
    assert contact["client_id"] == client["id"]
    assert [e["object_id"] for e in _audit(owner_db, ws, "contact.added")] == [contact["id"]]


def test_duplicate_contact_rejected(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    client = _new_client(owner, ws)
    _new_contact(owner, ws, client["id"], "ap@northwind.example.test")

    duplicate = owner.post(
        f"{API}/workspaces/{ws}/clients/{client['id']}/contacts",
        {"email": "AP@Northwind.Example.Test"},
        format="json",
        **idem(),
    )
    assert duplicate.status_code == 409, duplicate.content
    assert duplicate.json()["code"] == "DUPLICATE_RESOURCE"

    assert len(_audit(owner_db, ws, "contact.added")) == 1


def test_same_email_may_serve_two_clients(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    first = _new_client(owner, ws, "First")
    second = _new_client(owner, ws, "Second")
    _new_contact(owner, ws, first["id"], "shared@example.test")
    assert _new_contact(owner, ws, second["id"], "shared@example.test")["client_id"] == second["id"]


def test_edit_contact_audits_and_refuses_a_duplicate(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    client = _new_client(owner, ws)
    first = _new_contact(owner, ws, client["id"], "first@example.test")
    _new_contact(owner, ws, client["id"], "second@example.test")
    url = f"{API}/workspaces/{ws}/clients/{client['id']}/contacts/{first['id']}"

    edited = owner.patch(url, {"name": "Priya"}, format="json")
    assert edited.status_code == 200, edited.content
    assert edited.json()["name"] == "Priya"
    assert len(_audit(owner_db, ws, "contact.updated")) == 1

    clash = owner.patch(url, {"email": "second@example.test"}, format="json")
    assert clash.status_code == 409
    assert clash.json()["code"] == "DUPLICATE_RESOURCE"
    assert len(_audit(owner_db, ws, "contact.updated")) == 1


def test_a_contact_cannot_be_reached_through_another_client(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    first = _new_client(owner, ws, "First")
    second = _new_client(owner, ws, "Second")
    contact = _new_contact(owner, ws, first["id"])
    response = owner.patch(
        f"{API}/workspaces/{ws}/clients/{second['id']}/contacts/{contact['id']}",
        {"name": "Wrong client"},
        format="json",
    )
    assert response.status_code == 404


def test_suppression_requires_a_reason(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    client = _new_client(owner, ws)
    contact = _new_contact(owner, ws, client["id"])
    url = f"{API}/workspaces/{ws}/contacts/{contact['id']}/suppression"

    for body in ({}, {"reason": "   "}):
        refused = owner.post(url, body, format="json", **idem())
        assert refused.status_code == 422, refused.content
        assert refused.json()["errors"][0]["field"] == "reason"
    assert _audit(owner_db, ws, "contact.suppressed") == []


def test_suppress_then_clear_are_audited_with_reasons(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    client = _new_client(owner, ws)
    contact = _new_contact(owner, ws, client["id"])
    url = f"{API}/workspaces/{ws}/contacts/{contact['id']}/suppression"

    suppressed = _suppress(owner, ws, contact["id"], "Wrong person")
    assert suppressed.status_code == 200, suppressed.content
    assert suppressed.json()["status"] == "SUPPRESSED"
    assert suppressed.json()["suppression_reason"] == "Wrong person"
    events = _audit(owner_db, ws, "contact.suppressed")
    assert [e["object_id"] for e in events] == [contact["id"]]
    assert events[0]["before_masked"] == {"status": "ACTIVE"}
    assert events[0]["after_masked"]["status"] == "SUPPRESSED"

    cleared = owner.delete(url, {"reason": "Confirmed correct"}, format="json", **idem())
    assert cleared.status_code == 204, cleared.content
    profile = owner.get(f"{API}/workspaces/{ws}/clients/{client['id']}").json()
    assert profile["contacts"][0]["status"] == "ACTIVE"
    assert profile["contacts"][0]["suppression_reason"] is None
    events = _audit(owner_db, ws, "contact.suppression_cleared")
    assert [e["object_id"] for e in events] == [contact["id"]]
    assert events[0]["after_masked"]["reason"] == "Confirmed correct"


def test_invalid_suppression_transitions_conflict(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    client = _new_client(owner, ws)
    contact = _new_contact(owner, ws, client["id"])
    url = f"{API}/workspaces/{ws}/contacts/{contact['id']}/suppression"

    not_suppressed = owner.delete(url, format="json", **idem())
    assert not_suppressed.status_code == 409
    assert not_suppressed.json()["code"] == "STATE_TRANSITION_INVALID"

    assert _suppress(owner, ws, contact["id"]).status_code == 200
    again = _suppress(owner, ws, contact["id"])
    assert again.status_code == 409
    assert again.json()["code"] == "STATE_TRANSITION_INVALID"
    assert len(_audit(owner_db, ws, "contact.suppressed")) == 1


def test_contact_edit_cannot_change_suppression(pg, owner_db) -> None:
    """TSD M07: suppression moves through its explicit endpoints only."""
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    client = _new_client(owner, ws)
    contact = _new_contact(owner, ws, client["id"])
    refused = owner.patch(
        f"{API}/workspaces/{ws}/clients/{client['id']}/contacts/{contact['id']}",
        {"status": "SUPPRESSED"},
        format="json",
    )
    assert refused.status_code == 422


def test_suppressed_contact_cannot_be_approved_recipient(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    client = _new_client(owner, ws)
    contact = _new_contact(owner, ws, client["id"])
    ctx = _ctx(ws)

    assert client_service.approved_recipient(ctx, uuid.UUID(contact["id"]))["email"] == contact["email"]

    assert _suppress(owner, ws, contact["id"], "Asked us to stop").status_code == 200
    with pytest.raises(ProblemError) as refused:
        client_service.approved_recipient(ctx, uuid.UUID(contact["id"]))
    assert refused.value.code == "POLICY_BLOCKED"
    assert refused.value.status == 409

    url = f"{API}/workspaces/{ws}/contacts/{contact['id']}/suppression"
    assert owner.delete(url, format="json", **idem()).status_code == 204
    assert client_service.approved_recipient(ctx, uuid.UUID(contact["id"]))["id"] == contact["id"]


def test_unknown_or_foreign_contact_is_not_an_approved_recipient(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    other, other_ws = owner_workspace(owner_db, "other@example.test")
    foreign = _new_contact(other, other_ws, _new_client(other, other_ws)["id"])
    for contact_id in (uuid.uuid4(), uuid.UUID(foreign["id"])):
        with pytest.raises(ProblemError) as refused:
            client_service.approved_recipient(_ctx(ws), contact_id)
        assert refused.value.code == "NOT_FOUND"
    assert owner.get(f"{API}/workspaces/{ws}/clients").json()["items"] == []


def test_client_profile_returns_derived_summary(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    client = _new_client(owner, ws, sensitivity="LONG_TERM")
    first = _new_contact(owner, ws, client["id"], "first@example.test")
    _new_contact(owner, ws, client["id"], "second@example.test")

    profile = owner.get(f"{API}/workspaces/{ws}/clients/{client['id']}")
    assert profile.status_code == 200
    assert profile.headers["ETag"] == '"1"'
    body = profile.json()
    assert body["sensitivity"] == "LONG_TERM"
    assert body["summary"] == {"contacts_total": 2, "contacts_active": 2, "contacts_suppressed": 0}
    assert {row["email"] for row in body["contacts"]} == {"first@example.test", "second@example.test"}
    assert body["aliases"] == []

    assert _suppress(owner, ws, first["id"]).status_code == 200
    summary = owner.get(f"{API}/workspaces/{ws}/clients/{client['id']}").json()["summary"]
    assert summary == {"contacts_total": 2, "contacts_active": 1, "contacts_suppressed": 1}


def test_other_workspace_cannot_see_or_change_a_client(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    client = _new_client(owner, ws)
    contact = _new_contact(owner, ws, client["id"])
    other, other_ws = owner_workspace(owner_db, "other@example.test")

    base = f"{API}/workspaces/{other_ws}"
    assert other.get(f"{base}/clients/{client['id']}").status_code == 404
    assert (
        other.patch(
            f"{base}/clients/{client['id']}", {"display_name": "X"}, format="json", HTTP_IF_MATCH='"1"'
        ).status_code
        == 404
    )
    assert (
        other.post(
            f"{base}/clients/{client['id']}/contacts", {"email": "x@example.test"}, format="json", **idem()
        ).status_code
        == 404
    )
    assert _suppress(other, other_ws, contact["id"]).status_code == 404


def test_project_lead_reads_but_cannot_change(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    client = _new_client(owner, ws)
    contact = _new_contact(owner, ws, client["id"])
    lead, _ = add_member(owner_db, ws, "lead@example.test", "PROJECT_LEAD")

    assert lead.get(f"{API}/workspaces/{ws}/clients").status_code == 200
    assert lead.get(f"{API}/workspaces/{ws}/clients/{client['id']}").status_code == 200
    assert _suppress(lead, ws, contact["id"]).status_code == 403
    assert (
        lead.post(
            f"{API}/workspaces/{ws}/clients", {"display_name": "X"}, format="json", **idem()
        ).status_code
        == 403
    )


def test_idempotent_create_replays(pg, owner_db) -> None:
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    key = idem()
    url = f"{API}/workspaces/{ws}/clients"
    first = owner.post(url, {"display_name": "Once"}, format="json", **key)
    second = owner.post(url, {"display_name": "Once"}, format="json", **key)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(_audit(owner_db, ws, "client.created")) == 1


def test_a_suppressed_contact_keeps_its_address(pg, owner_db) -> None:
    """Moving the address away would let the old one be added again as an active contact."""
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    client = _new_client(owner, ws)
    contact = _new_contact(owner, ws, client["id"])
    assert _suppress(owner, ws, contact["id"]).status_code == 200
    url = f"{API}/workspaces/{ws}/clients/{client['id']}/contacts/{contact['id']}"

    refused = owner.patch(url, {"email": "new@example.test"}, format="json")
    assert refused.status_code == 409
    assert refused.json()["code"] == "STATE_TRANSITION_INVALID"

    renamed = owner.patch(url, {"name": "Renamed"}, format="json")
    assert renamed.status_code == 200
    assert renamed.json()["status"] == "SUPPRESSED"


def test_suppressing_an_address_blocks_it_for_every_client(pg, owner_db) -> None:
    """FR-072: reminders to that address are blocked, whichever client it is listed under."""
    owner, ws = owner_workspace(owner_db, "owner@example.test")
    first = _new_contact(owner, ws, _new_client(owner, ws, "First")["id"], "shared@example.test")
    second = _new_contact(owner, ws, _new_client(owner, ws, "Second")["id"], "SHARED@example.test")
    assert _suppress(owner, ws, first["id"]).status_code == 200
    with pytest.raises(ProblemError) as refused:
        client_service.approved_recipient(_ctx(ws), uuid.UUID(second["id"]))
    assert refused.value.code == "POLICY_BLOCKED"
