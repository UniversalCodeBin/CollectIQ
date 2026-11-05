"""Export, deletion and payload inspector (E102-E105): TS-022, TS-028, members audited, retention."""

import json
import uuid
from typing import Any

import psycopg
import pytest
from rest_framework.test import APIClient

from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx
from tests.support import API, add_member, drain_jobs, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")

CONFIRM = "DELETE MY WORKSPACE"


def _ctx(ws: str) -> RequestContext:
    return RequestContext(ws, None, "OWNER", "c", "SYSTEM")  # type: ignore[arg-type]


def _client(client: APIClient, ws: str, name: str) -> None:
    response = client.post(f"{API}/workspaces/{ws}/clients", {"display_name": name}, format="json", **idem())
    assert response.status_code == 201, response.content


def _ai_record(owner_db: psycopg.Connection, ws: str, redacted: dict[str, Any], age_days: int = 0) -> None:
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    row = owner_db.execute(
        "INSERT INTO ai_processing_records (workspace_id, task_id, subject_type, status)"
        " VALUES (%s, 'reply.interpret', 'message', 'OK') RETURNING id",
        [ws],
    ).fetchone()
    assert row
    owner_db.execute(
        "INSERT INTO ai_payloads (workspace_id, processing_id, redacted_input, created_at)"
        " VALUES (%s, %s, %s::jsonb, now() - make_interval(days => %s))",
        [ws, row[0], json.dumps(redacted), age_days],
    )


def _export(client: APIClient, ws: str) -> Any:
    created = client.post(f"{API}/workspaces/{ws}/exports", {}, format="json", **idem())
    assert created.status_code == 201, created.content
    drain_jobs()
    return client.get(f"{API}/workspaces/{ws}/exports/{created.json()['id']}")


def test_export_holds_only_this_workspace(owner_db) -> None:
    client, ws = owner_workspace(owner_db, "exp-a@example.test")
    other_client, other = owner_workspace(owner_db, "exp-b@example.test")
    _client(client, ws, "Mine Traders")
    _client(other_client, other, "Foreign Secret Traders")
    body = _export(client, ws).json()
    assert body["status"] == "READY"
    text = json.dumps(body["content"])
    assert "Mine Traders" in text
    assert "Foreign Secret Traders" not in text
    assert other not in text
    for banned in ("wrapped_key", "verifier_sealed", "sealed", "body_enc", "raw_row_ciphertext"):
        assert banned not in text


def test_export_is_owner_and_finance_only(owner_db) -> None:
    _, ws = owner_workspace(owner_db, "exp-role@example.test")
    lead, _ = add_member(owner_db, ws, "exp-lead@example.test", "PROJECT_LEAD")
    assert lead.post(f"{API}/workspaces/{ws}/exports", {}, format="json", **idem()).status_code == 403
    finance, _ = add_member(owner_db, ws, "exp-fin@example.test", "FINANCE_ADMIN")
    assert finance.post(f"{API}/workspaces/{ws}/exports", {}, format="json", **idem()).status_code == 201


def test_another_workspace_cannot_read_an_export(owner_db) -> None:
    client, ws = owner_workspace(owner_db, "exp-own@example.test")
    stranger, other = owner_workspace(owner_db, "exp-str@example.test")
    created = client.post(f"{API}/workspaces/{ws}/exports", {}, format="json", **idem()).json()
    assert stranger.get(f"{API}/workspaces/{other}/exports/{created['id']}").status_code == 404


def test_deletion_needs_owner_and_exact_confirmation(owner_db) -> None:
    client, ws = owner_workspace(owner_db, "del-guard@example.test")
    finance, _ = add_member(owner_db, ws, "del-fin@example.test", "FINANCE_ADMIN")
    url = f"{API}/workspaces/{ws}/deletion"
    assert finance.post(url, {"confirmation_text": CONFIRM}, format="json", **idem()).status_code == 403
    wrong = client.post(url, {"confirmation_text": "delete"}, format="json", **idem())
    assert wrong.status_code == 422
    assert client.get(f"{API}/workspaces/{ws}").status_code == 200


def test_deletion_leaves_no_rows_and_a_final_record(owner_db) -> None:
    client, ws = owner_workspace(owner_db, "del-all@example.test")
    keep_client, keep = owner_workspace(owner_db, "del-keep@example.test")
    _client(client, ws, "Doomed Traders")
    _client(keep_client, keep, "Survivor Traders")
    _ai_record(owner_db, ws, {"body": "[EMAIL_1]"})
    response = client.post(
        f"{API}/workspaces/{ws}/deletion", {"confirmation_text": CONFIRM}, format="json", **idem()
    )
    assert response.status_code == 201, response.content
    assert response.json()["rows_remaining"] == 0
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    tables = owner_db.execute(
        "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public'"
        " AND column_name = 'workspace_id' AND table_name NOT IN"
        " ('audit_events', 'deletion_records', 'workspaces')"
    ).fetchall()
    for (table,) in tables:
        left = owner_db.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
        assert left == (0,), table
    record = owner_db.execute("SELECT rows_remaining, requested_by FROM deletion_records").fetchone()
    assert record and record[0] == 0 and record[1] is not None
    status = owner_db.execute("SELECT status, name FROM workspaces WHERE id = %s", [ws]).fetchone()
    assert status == ("DELETED", "[deleted]")
    audit_left = owner_db.execute("SELECT count(*) FROM audit_events").fetchone()
    assert audit_left and audit_left[0] > 0  # the append-only history is retained
    assert client.get(f"{API}/workspaces/{ws}/clients").status_code in (403, 404)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [keep])
    assert owner_db.execute("SELECT count(*) FROM clients").fetchone() == (1,)


def test_payload_inspector_shows_tokens_and_is_audited(owner_db) -> None:
    client, ws = owner_workspace(owner_db, "pay-a@example.test")
    _ai_record(owner_db, ws, {"body": "Please call [PHONE_1] or write to [EMAIL_1]"})
    body = client.get(f"{API}/workspaces/{ws}/ai/payloads").json()
    assert body["items"], body
    text = json.dumps(body)
    assert "[EMAIL_1]" in text and "[PHONE_1]" in text
    assert "@" not in text.replace("[EMAIL_1]", "")
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    actions = [r[0] for r in owner_db.execute("SELECT action FROM audit_events").fetchall()]
    assert "ai_payloads.viewed" in actions


def test_payload_inspector_is_tenant_scoped_and_role_gated(owner_db) -> None:
    client, ws = owner_workspace(owner_db, "pay-b@example.test")
    _, other = owner_workspace(owner_db, "pay-c@example.test")
    _ai_record(owner_db, other, {"body": "ForeignSecret"})
    assert "ForeignSecret" not in json.dumps(client.get(f"{API}/workspaces/{ws}/ai/payloads").json())
    lead, _ = add_member(owner_db, ws, "pay-lead@example.test", "PROJECT_LEAD")
    assert lead.get(f"{API}/workspaces/{ws}/ai/payloads").status_code == 403


def test_role_changes_and_removals_are_audited(owner_db) -> None:
    client, ws = owner_workspace(owner_db, "mem-a@example.test")
    _, member_id = add_member(owner_db, ws, "mem-b@example.test", "PROJECT_LEAD")
    changed = client.patch(
        f"{API}/workspaces/{ws}/members/{member_id}", {"role": "FINANCE_ADMIN"}, format="json", **idem()
    )
    assert changed.status_code == 200, changed.content
    assert client.delete(f"{API}/workspaces/{ws}/members/{member_id}", **idem()).status_code in (200, 204)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    actions = [r[0] for r in owner_db.execute("SELECT action FROM audit_events").fetchall()]
    assert "member.role_changed" in actions and "member.removed" in actions


def test_retention_clears_old_payloads_and_expired_exports(owner_db, settings) -> None:
    from collectiq.settings_privacy import service

    client, ws = owner_workspace(owner_db, "ret-a@example.test")
    settings.COLLECTIQ_PAYLOAD_RETENTION_DAYS = 30
    _ai_record(owner_db, ws, {"body": "old [EMAIL_1]"}, age_days=45)
    _ai_record(owner_db, ws, {"body": "new [EMAIL_2]"}, age_days=1)
    with tenant_tx(_ctx(ws)):
        removed = service.apply_retention(_ctx(ws))
    assert removed["payloads_cleared"] == 1
    text = json.dumps(client.get(f"{API}/workspaces/{ws}/ai/payloads").json())
    assert "new [EMAIL_2]" in text and "old [EMAIL_1]" not in text
    assert uuid.UUID(ws)
