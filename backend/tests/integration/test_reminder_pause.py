"""Per-client and per-invoice pause (E121-E123): enforced by the policy engine, kept as history."""

import uuid
from typing import Any

import psycopg
import pytest

from tests.integration.test_reminders import Env
from tests.support import add_member, idem

pytestmark = pytest.mark.usefixtures("pg")


@pytest.fixture
def env(owner_db: psycopg.Connection) -> Env:
    return Env(owner_db, f"pause-{uuid.uuid4().hex[:8]}@example.test")


def pause(env: Env, scope: str, target: str, reason: str | None = "Customer asked us to wait") -> Any:
    body: dict[str, Any] = {"scope": scope, "target_id": target}
    if reason is not None:
        body["reason"] = reason
    return env.client.post(env.url("reminder-pauses"), body, format="json", **idem())


def client_id(env: Env) -> str:
    row = env.db.execute("SELECT client_id FROM invoices WHERE id = %s", [env.invoices["INV-1"]]).fetchone()
    assert row
    return str(row[0])


def audit_actions(env: Env) -> list[str]:
    rows = env.db.execute(
        "SELECT action FROM audit_events WHERE action LIKE 'reminders.%' ORDER BY id"
    ).fetchall()
    return [r[0] for r in rows]


def test_invoice_pause_blocks_drafting_and_resume_allows_it(env: Env) -> None:
    made = pause(env, "INVOICE", env.invoices["INV-1"])
    assert made.status_code == 201, made.content
    body = env.evaluate().json()
    assert body["outcome"] == "PAUSE_FOR_REVIEW" and body["reminder"] is None
    assert "G13_AUTOMATION_PAUSED" in body["reasons"] or any(
        g["gate"] == "G13" and not g["passed"] for g in body["gate_results"]
    )
    # the other invoice of the same client is untouched by an invoice-level pause
    assert env.evaluate("INV-2").json()["reminder"] is not None
    resumed = env.client.post(env.url(f"reminder-pauses/{made.json()['id']}/resume"), **idem())
    assert resumed.status_code == 200 and resumed.json()["status"] == "RESUMED"
    assert env.evaluate().json()["reminder"] is not None


def test_client_pause_covers_every_invoice_of_that_client(env: Env) -> None:
    assert pause(env, "CLIENT", client_id(env)).status_code == 201
    for number in ("INV-1", "INV-2"):
        body = env.evaluate(number).json()
        assert body["outcome"] == "PAUSE_FOR_REVIEW" and body["reminder"] is None


def test_pause_after_drafting_stops_approval_and_hand_off(env: Env) -> None:
    reminder = env.draft()
    made = pause(env, "INVOICE", env.invoices["INV-1"])
    assert made.status_code == 201
    approved = env.approve(reminder["id"])
    assert approved.status_code in (409, 422), approved.content
    assert env.get(reminder["id"])["status"] == "DRAFT"
    env.client.post(env.url(f"reminder-pauses/{made.json()['id']}/resume"), **idem())
    assert env.approve(reminder["id"]).status_code == 200


def test_pause_cannot_be_applied_twice_or_resumed_twice(env: Env) -> None:
    first = pause(env, "INVOICE", env.invoices["INV-1"])
    assert first.status_code == 201
    assert pause(env, "INVOICE", env.invoices["INV-1"]).status_code == 409
    url = env.url(f"reminder-pauses/{first.json()['id']}/resume")
    assert env.client.post(url, **idem()).status_code == 200
    assert env.client.post(url, **idem()).status_code == 409
    # after a resume the target can be paused again
    assert pause(env, "INVOICE", env.invoices["INV-1"]).status_code == 201


def test_foreign_or_unknown_targets_are_not_found(env: Env, owner_db: psycopg.Connection) -> None:
    other = Env(owner_db, f"pause-{uuid.uuid4().hex[:8]}@example.test")
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [env.ws])
    assert pause(env, "INVOICE", other.invoices["INV-1"]).status_code == 404
    assert pause(env, "CLIENT", str(uuid.uuid4())).status_code == 404
    unknown = env.client.post(env.url(f"reminder-pauses/{uuid.uuid4()}/resume"), **idem())
    assert unknown.status_code == 404


def test_list_shows_active_and_history_and_the_audit_trail(env: Env) -> None:
    made = pause(env, "INVOICE", env.invoices["INV-1"], reason="Dispute under review")
    env.client.post(env.url(f"reminder-pauses/{made.json()['id']}/resume"), **idem())
    pause(env, "CLIENT", client_id(env), reason=None)
    active = env.client.get(env.url("reminder-pauses")).json()["items"]
    assert [p["scope"] for p in active] == ["CLIENT"] and active[0]["reason"] is None
    history = env.client.get(env.url("reminder-pauses?history=true")).json()["items"]
    assert {p["status"] for p in history} == {"ACTIVE", "RESUMED"}
    resumed = next(p for p in history if p["status"] == "RESUMED")
    assert resumed["reason"] == "Dispute under review" and resumed["resumed_by"]
    narrowed = env.client.get(env.url(f"reminder-pauses?invoice_id={env.invoices['INV-2']}")).json()["items"]
    assert [p["scope"] for p in narrowed] == ["CLIENT"]  # the client's pause covers this invoice too
    assert audit_actions(env) == ["reminders.paused", "reminders.resumed", "reminders.paused"]


def test_only_people_who_may_pause_can_pause(env: Env, owner_db: psycopg.Connection) -> None:
    lead, _ = add_member(owner_db, env.ws, f"lead-{uuid.uuid4().hex[:6]}@example.test", "PROJECT_LEAD")
    body = {"scope": "INVOICE", "target_id": env.invoices["INV-1"]}
    assert lead.post(env.url("reminder-pauses"), body, format="json", **idem()).status_code == 403
    assert env.db.execute("SELECT count(*) FROM reminder_pauses").fetchone()[0] == 0


def test_invalid_scope_is_rejected(env: Env) -> None:
    assert pause(env, "WORKSPACE", env.invoices["INV-1"]).status_code == 422
