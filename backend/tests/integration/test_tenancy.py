"""Workspaces, membership and invitations through the real API (TSD M02, M03, TS-024)."""

import logging
import threading
import uuid

import psycopg
import pytest
from django.db import connection
from rest_framework.test import APIClient

from collectiq.platform import email as email_port
from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx
from tests.support import (
    API,
    WORKSPACE_BODY,
    add_member,
    drain_jobs,
    idem,
    logged_in,
    mailbox,
    make_user,
    owner_workspace,
    token_from,
)

OWNER = "owner@example.test"
INVITEE = "invitee@example.test"


@pytest.fixture(autouse=True)
def _empty_outbox() -> None:
    email_port.memory_outbox.clear()


def _ws(workspace_id: str) -> str:
    return f"{API}/workspaces/{workspace_id}"


def _audit_actions(owner_db: psycopg.Connection, workspace_id: str) -> list[str]:
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [workspace_id])
    return [row[0] for row in owner_db.execute("SELECT action FROM audit_events ORDER BY id").fetchall()]


# Create and read


def test_unverified_email_cannot_create_workspace(pg, owner_db) -> None:
    make_user(owner_db, OWNER, verified=False)
    client = logged_in(OWNER)
    response = client.post(f"{API}/workspaces", WORKSPACE_BODY, format="json", **idem())
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [str(uuid.uuid4())])
    assert owner_db.execute("SELECT count(*) FROM workspace_memberships").fetchone() == (0,)


def test_unverified_member_cannot_read_workspace_data(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    owner_db.execute("UPDATE users SET email_verified_at = NULL, status = 'UNVERIFIED'")
    assert client.get(_ws(workspace_id)).status_code == 403


def test_creator_becomes_owner_and_session_lists_the_workspace(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    body = client.get(f"{API}/auth/session").json()
    assert body["workspaces"] == [{"id": workspace_id, "name": "Acme Studio", "role": "OWNER"}]
    assert "workspace.created" in _audit_actions(owner_db, workspace_id)


def test_default_policy_has_automation_off(pg, owner_db) -> None:
    _, workspace_id = owner_workspace(owner_db, OWNER)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [workspace_id])
    version, settings, active = owner_db.execute(
        "SELECT p.version, p.settings, w.active_policy_id = p.id FROM workspace_policies p"
        " JOIN workspaces w ON w.id = p.workspace_id"
    ).fetchone()
    assert (version, active) == (1, True)
    assert settings["mode"] == "MANUAL"
    assert settings["auto_snooze_enabled"] is False
    assert settings["automation_paused"] is False


def test_workspace_creation_replays_for_the_same_key(pg, owner_db) -> None:
    make_user(owner_db, OWNER)
    client = logged_in(OWNER)
    key = idem()
    first = client.post(f"{API}/workspaces", WORKSPACE_BODY, format="json", **key)
    second = client.post(f"{API}/workspaces", WORKSPACE_BODY, format="json", **key)
    assert first.status_code == second.status_code == 201
    assert first.content == second.content
    assert len(client.get(f"{API}/auth/session").json()["workspaces"]) == 1


def test_expired_key_cannot_create_the_same_workspace_twice(pg, owner_db) -> None:
    make_user(owner_db, OWNER)
    client = logged_in(OWNER)
    key = idem()
    first = client.post(f"{API}/workspaces", WORKSPACE_BODY, format="json", **key)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [first.json()["id"]])
    owner_db.execute("DELETE FROM idempotency_keys")
    assert client.post(f"{API}/workspaces", WORKSPACE_BODY, format="json", **key).status_code == 409


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timezone", "Mars/Olympus"),
        ("default_currency", "XXZ"),
        ("default_currency", "inr"),
        ("country", "India"),
    ],
)
def test_invalid_workspace_fields_are_rejected(pg, owner_db, field: str, value: str) -> None:
    make_user(owner_db, OWNER)
    client = logged_in(OWNER)
    response = client.post(f"{API}/workspaces", {**WORKSPACE_BODY, field: value}, format="json", **idem())
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == field


# Tenant isolation


def test_cross_tenant_is_404(pg, owner_db, caplog) -> None:
    _, workspace_id = owner_workspace(owner_db, OWNER)
    make_user(owner_db, "other@example.test")
    other = logged_in("other@example.test")
    with caplog.at_level(logging.WARNING, logger="collectiq.api.registry"):
        real = other.get(_ws(workspace_id))
    missing = other.get(_ws(str(uuid.uuid4())))
    assert real.status_code == missing.status_code == 404
    strip = lambda r: {k: v for k, v in r.json().items() if k != "correlation_id"}  # noqa: E731
    assert strip(real) == strip(missing)
    assert any("workspace_access_refused" in record.getMessage() for record in caplog.records)


def test_users_memberships_are_visible_only_to_them_or_the_tenant(pg, owner_db) -> None:
    _, first = owner_workspace(owner_db, OWNER)
    _, second = owner_workspace(owner_db, "other@example.test")
    ctx = RequestContext(uuid.UUID(second), uuid.uuid4(), "OWNER", "corr", "USER")
    with tenant_tx(ctx), connection.cursor() as cursor:
        cursor.execute("SELECT workspace_id::text FROM workspace_memberships")
        assert {row[0] for row in cursor.fetchall()} == {second}
        cursor.execute("SELECT id::text FROM workspaces")
        assert {row[0] for row in cursor.fetchall()} == {second}
    assert first != second


def test_deleted_workspace_is_404(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [workspace_id])
    owner_db.execute("UPDATE workspaces SET status = 'DELETED'")
    assert client.get(_ws(workspace_id)).status_code == 404


# Update


def test_update_uses_the_version(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    first = client.get(_ws(workspace_id))
    assert first["ETag"] == '"1"'
    assert first.json()["version"] == 1
    url, body = _ws(workspace_id), {"name": "Renamed"}
    updated = client.patch(url, body, format="json", HTTP_IF_MATCH='"1"')
    assert updated.status_code == 200
    assert (updated.json()["name"], updated.json()["version"]) == ("Renamed", 2)
    assert updated["ETag"] == '"2"'
    stale = client.patch(url, {"name": "Lost"}, format="json", HTTP_IF_MATCH='"1"')
    assert stale.status_code == 409
    assert stale.json()["code"] == "CONFLICT_VERSION"
    assert client.get(url).json()["name"] == "Renamed"
    assert "workspace.updated" in _audit_actions(owner_db, workspace_id)


def test_update_needs_if_match(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    assert client.patch(_ws(workspace_id), {"name": "x"}, format="json").status_code == 422


# Members


def test_members_list_paginates(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    add_member(owner_db, workspace_id, "finance@example.test", "FINANCE_ADMIN")
    add_member(owner_db, workspace_id, "second@example.test", "OWNER")
    seen: list[str] = []
    url: str | None = f"{_ws(workspace_id)}/members?limit=2"
    while url:
        page = client.get(url).json()
        assert len(page["items"]) <= 2
        seen += [item["email"] for item in page["items"]]
        cursor = page["next_cursor"]
        url = f"{_ws(workspace_id)}/members?limit=2&cursor={cursor}" if cursor else None
    assert sorted(seen) == ["finance@example.test", OWNER, "second@example.test"]


def test_members_list_rejects_bad_paging(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    assert client.get(f"{_ws(workspace_id)}/members?limit=0").status_code == 422
    assert client.get(f"{_ws(workspace_id)}/members?limit=201").status_code == 422
    assert client.get(f"{_ws(workspace_id)}/members?cursor=nope").status_code == 422


def _own_member_id(client: APIClient, workspace_id: str, email: str) -> str:
    items = client.get(f"{_ws(workspace_id)}/members").json()["items"]
    return next(item["id"] for item in items if item["email"] == email)


def test_last_owner_cannot_be_removed_or_demoted(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    member_id = _own_member_id(client, workspace_id, OWNER)
    url = f"{_ws(workspace_id)}/members/{member_id}"
    removed = client.delete(url, **idem())
    assert removed.status_code == 409
    assert removed.json()["code"] == "STATE_TRANSITION_INVALID"
    demoted = client.patch(url, {"role": "FINANCE_ADMIN"}, format="json")
    assert demoted.status_code == 409
    assert client.get(_ws(workspace_id)).status_code == 200


def test_owner_can_be_removed_when_another_remains(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    add_member(owner_db, workspace_id, "second@example.test", "OWNER")
    member_id = _own_member_id(client, workspace_id, OWNER)
    assert client.delete(f"{_ws(workspace_id)}/members/{member_id}", **idem()).status_code == 204
    assert client.get(_ws(workspace_id)).status_code == 404


@pytest.mark.concurrency
def test_two_owners_removing_each_other_leaves_one(pg, owner_db) -> None:
    first, workspace_id = owner_workspace(owner_db, OWNER)
    second, second_member = add_member(owner_db, workspace_id, "second@example.test", "OWNER")
    first_member = _own_member_id(first, workspace_id, OWNER)
    barrier = threading.Barrier(2)
    statuses: list[int] = []

    def remove(client: APIClient, member_id: str) -> None:
        try:
            barrier.wait(timeout=30)
            statuses.append(client.delete(f"{_ws(workspace_id)}/members/{member_id}", **idem()).status_code)
        finally:
            connection.close()

    threads = [
        threading.Thread(target=remove, args=(first, second_member)),
        threading.Thread(target=remove, args=(second, first_member)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert sorted(statuses) == [204, 409]
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [workspace_id])
    assert owner_db.execute(
        "SELECT count(*) FROM workspace_memberships WHERE role = 'OWNER' AND status = 'ACTIVE'"
    ).fetchone() == (1,)


def test_removed_member_loses_access_on_the_next_request(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    member, member_id = add_member(owner_db, workspace_id, "finance@example.test", "FINANCE_ADMIN")
    assert member.get(_ws(workspace_id)).status_code == 200
    assert client.delete(f"{_ws(workspace_id)}/members/{member_id}", **idem()).status_code == 204
    assert member.get(_ws(workspace_id)).status_code == 404
    assert "member.removed" in _audit_actions(owner_db, workspace_id)


def test_role_change_applies_on_the_next_request(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    member, member_id = add_member(owner_db, workspace_id, "finance@example.test", "FINANCE_ADMIN")
    assert (
        member.patch(_ws(workspace_id), {"name": "x"}, format="json", HTTP_IF_MATCH='"1"').status_code == 403
    )
    url = f"{_ws(workspace_id)}/members/{member_id}"
    assert client.patch(url, {"role": "OWNER"}, format="json").status_code == 200
    assert (
        member.patch(_ws(workspace_id), {"name": "x"}, format="json", HTTP_IF_MATCH='"1"').status_code == 200
    )
    assert "member.role_changed" in _audit_actions(owner_db, workspace_id)


def test_sensitive_denial_is_audited(pg, owner_db) -> None:
    _, workspace_id = owner_workspace(owner_db, OWNER)
    member, _ = add_member(owner_db, workspace_id, "finance@example.test", "FINANCE_ADMIN")
    body = {"email": INVITEE, "role": "OWNER"}
    url = f"{_ws(workspace_id)}/invitations"
    assert member.post(url, body, format="json", **idem()).status_code == 403
    assert "authz.denied" in _audit_actions(owner_db, workspace_id)


# Invitations


def _invite(client: APIClient, workspace_id: str, email: str = INVITEE, role: str = "FINANCE_ADMIN"):
    return client.post(
        f"{_ws(workspace_id)}/invitations", {"email": email, "role": role}, format="json", **idem()
    )


def _accept(client: APIClient, token: str):
    return client.post(f"{API}/invitations/accept", {"token": token}, format="json")


def _invited_token(client: APIClient, workspace_id: str, email: str = INVITEE) -> str:
    assert _invite(client, workspace_id, email).status_code == 201
    drain_jobs()
    return token_from(mailbox(email)[-1])


def test_invitation_flow_grants_the_invited_role(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    token = _invited_token(client, workspace_id)
    assert token not in str(client.get(f"{_ws(workspace_id)}/members").content)
    make_user(owner_db, INVITEE)
    invitee = logged_in(INVITEE)
    assert invitee.get(_ws(workspace_id)).status_code == 404
    accepted = _accept(invitee, token)
    assert accepted.status_code == 200
    assert accepted.json() == {"workspace_id": workspace_id, "role": "FINANCE_ADMIN"}
    assert invitee.get(_ws(workspace_id)).status_code == 200
    assert "member.invited" in _audit_actions(owner_db, workspace_id)


def test_invitation_token_is_single_use(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    token = _invited_token(client, workspace_id)
    make_user(owner_db, INVITEE)
    invitee = logged_in(INVITEE)
    assert _accept(invitee, token).status_code == 200
    assert _accept(invitee, token).status_code == 422


def test_invitation_for_another_address_is_404(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    token = _invited_token(client, workspace_id)
    make_user(owner_db, "stranger@example.test")
    stranger = logged_in("stranger@example.test")
    assert _accept(stranger, token).status_code == 404
    assert stranger.get(_ws(workspace_id)).status_code == 404


def test_invitation_needs_a_verified_email(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    token = _invited_token(client, workspace_id)
    make_user(owner_db, INVITEE, verified=False)
    assert _accept(logged_in(INVITEE), token).status_code == 403


def test_expired_or_malformed_invitation_is_rejected(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    token = _invited_token(client, workspace_id)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [workspace_id])
    owner_db.execute("UPDATE workspace_invitations SET expires_at = now() - interval '1 second'")
    make_user(owner_db, INVITEE)
    invitee = logged_in(INVITEE)
    assert _accept(invitee, token).status_code == 422
    assert _accept(invitee, "not-a-token").status_code == 422
    assert _accept(invitee, f"{uuid.uuid4()}.secret").status_code == 422


@pytest.mark.parametrize("role", ["SUPERADMIN", "PROJECT_LEAD", ""])
def test_invitation_with_unavailable_role_is_rejected(pg, owner_db, role: str) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    assert _invite(client, workspace_id, role=role).status_code == 422


def test_pending_invitation_can_be_listed_and_revoked(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    token = _invited_token(client, workspace_id)
    items = client.get(f"{_ws(workspace_id)}/members").json()["items"]
    pending = next(item for item in items if item["email"] == INVITEE)
    assert pending["status"] == "INVITED"
    assert client.delete(f"{_ws(workspace_id)}/members/{pending['id']}", **idem()).status_code == 204
    make_user(owner_db, INVITEE)
    assert _accept(logged_in(INVITEE), token).status_code == 422


def test_inviting_an_active_member_conflicts(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    response = _invite(client, workspace_id, OWNER)
    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE_RESOURCE"


def test_reinviting_replaces_the_pending_invitation(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    first = _invited_token(client, workspace_id)
    second = _invited_token(client, workspace_id)
    make_user(owner_db, INVITEE)
    invitee = logged_in(INVITEE)
    assert _accept(invitee, first).status_code == 422
    assert _accept(invitee, second).status_code == 200


def test_removed_member_can_rejoin_through_a_new_invitation(pg, owner_db) -> None:
    client, workspace_id = owner_workspace(owner_db, OWNER)
    member, member_id = add_member(owner_db, workspace_id, "finance@example.test", "FINANCE_ADMIN")
    client.delete(f"{_ws(workspace_id)}/members/{member_id}", **idem())
    token = _invited_token(client, workspace_id, "finance@example.test")
    assert _accept(member, token).status_code == 200
    assert member.get(_ws(workspace_id)).status_code == 200


# Health


def test_live_exposes_nothing_sensitive(pg) -> None:
    response = APIClient().get(f"{API}/health/live")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_ready_reports_ok(pg) -> None:
    response = APIClient().get(f"{API}/health/ready")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_ready_hides_the_failure(pg, monkeypatch) -> None:
    monkeypatch.setattr("collectiq.api.identity_views.check_ready", lambda: False)
    response = APIClient().get(f"{API}/health/ready")
    assert (response.status_code, response.json()) == (503, {"status": "unavailable"})
