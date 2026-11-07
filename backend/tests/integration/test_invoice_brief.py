"""Invoice brief (E120): a bounded agent over one invoice. Facts stay verified; the brief stays AI-derived.

The agent may read two minimised views and suggest a pause. It changes nothing, sends nothing, and a
draft wording only survives the same linter that guards reminders.
"""

import json
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from collectiq.ai.gateway import AIConfig, Gateway
from collectiq.ai.providers.fake import FakeProvider
from collectiq.ai.runtime import use_gateway
from tests.integration.test_conversations import Env
from tests.support import add_member, idem

pytestmark = pytest.mark.usefixtures("pg")

WORDING = "Hello, invoice {invoice_number} for {amount} was due on {due_date}. When can we expect payment?"


def tool(name: str, **args: Any) -> str:
    return json.dumps({"tool": name, "args": args})


def final(**kw: Any) -> str:
    body = {"summary": "Overdue, no reply yet.", "next_step": "SEND_REMINDER", "draft_wording": WORDING}
    return json.dumps({"final": {**body, **kw}})


@pytest.fixture
def script() -> Iterator[Any]:
    def install(*responses: str | Exception) -> FakeProvider:
        provider = FakeProvider(list(responses))
        use_gateway(Gateway(provider, AIConfig()))
        return provider

    yield install
    use_gateway(None)


@pytest.fixture
def env(owner_db: psycopg.Connection) -> Env:
    e = Env(owner_db, f"brief-{uuid.uuid4().hex[:8]}@example.test")
    owner_db.execute(
        "INSERT INTO workspace_ai_settings (workspace_id, invoice_brief_enabled) VALUES (%s, true)", [e.ws]
    )
    return e


def brief(env: Env, invoice: str = "INV-1", client: Any = None) -> Any:
    return (client or env.client).post(
        env.url(f"invoices/{env.invoices[invoice]}/ai/brief"), {}, format="json"
    )


def count(env: Env, sql: str) -> int:
    row = env.db.execute(sql).fetchone()
    assert row
    return int(row[0])


def test_brief_returns_verified_facts_apart_from_the_ai_reading(env: Env, script: Any) -> None:
    provider = script(tool("get_invoice_status"), tool("get_recent_activity"), final())
    state_before = env.state()
    response = brief(env)
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "COMPLETED" and body["ai_derived"] is True
    assert body["facts"]["invoice_number"] == "INV-1" and body["derived"]["outstanding_minor"] > 0
    assert body["brief"]["next_step"] == "SEND_REMINDER"
    assert "INV-1" in body["brief"]["draft_wording"] and "{amount}" not in body["brief"]["draft_wording"]
    assert "verified" not in body["brief"]  # nothing in the reading claims to be verified
    # minimum necessary: the model never saw the invoice number, client name or any message text
    seen = json.dumps([r.input for r in provider.requests])
    assert "INV-1" not in seen and "Acme" not in seen
    # nothing changed, nothing was sent, and the run is auditable
    assert env.state() == state_before
    assert count(env, "SELECT count(*) FROM reminders") == 0
    assert count(env, "SELECT count(*) FROM audit_events WHERE action = 'invoice.brief_generated'") == 1
    assert count(env, "SELECT count(*) FROM ai_processing_records WHERE task_id = 'agent.invoice_brief'") == 1
    assert count(env, "SELECT count(*) FROM ai_payloads") == 1


def test_off_by_default_and_no_model_call(owner_db: psycopg.Connection, script: Any) -> None:
    env = Env(owner_db, f"brief-off-{uuid.uuid4().hex[:8]}@example.test")
    provider = script(final())
    body = brief(env).json()
    assert body["status"] == "NOT_ENABLED" and body["brief"] is None and body["facts"]["invoice_number"]
    assert provider.requests == []


def test_kill_switch_wins_over_the_opt_in(env: Env, script: Any) -> None:
    env.db.execute("UPDATE workspace_ai_settings SET kill_switch = true WHERE workspace_id = %s", [env.ws])
    provider = script(final())
    assert brief(env).json()["status"] == "NOT_ENABLED"
    assert provider.requests == []


def test_forbidden_wording_is_dropped_not_shown(env: Env, script: Any) -> None:
    script(final(draft_wording="Pay {amount} for {invoice_number} by {due_date} or face legal action."))
    body = brief(env).json()
    assert body["brief"]["draft_wording"] is None
    assert "NO_LEGAL_THREATS" in body["wording_rejected"]


def test_a_pause_suggestion_is_only_a_suggestion(env: Env, script: Any) -> None:
    script(tool("suggest_pause", reason="Customer says they will pay Friday"), final(draft_wording=""))
    body = brief(env).json()
    assert body["status"] == "AWAITING_APPROVAL"
    assert body["suggestions"] == [
        {"action": "PAUSE_REMINDERS", "reason": "Customer says they will pay Friday"}
    ]
    assert body["brief"]["draft_wording"] is None
    assert env.state()["reminder_status"] == env.state("INV-2")["reminder_status"]  # nothing was paused


def test_provider_failure_still_returns_the_facts(env: Env, script: Any) -> None:
    script(TimeoutError("down"))
    body = brief(env).json()
    assert body["status"] == "PROVIDER_ERROR" and body["brief"] is None
    assert body["facts"]["invoice_number"] == "INV-1"


def test_bad_tool_calls_and_garbage_end_safely(env: Env, script: Any) -> None:
    script(tool("mark_paid"), "not json", "still not json")
    body = brief(env).json()
    assert body["status"] == "INVALID_OUTPUT" and body["brief"] is None
    assert count(env, "SELECT count(*) FROM payment_allocations") == 0


def test_another_workspaces_invoice_is_not_found_and_not_sent(
    owner_db: psycopg.Connection, script: Any
) -> None:
    other = Env(owner_db, f"brief-other-{uuid.uuid4().hex[:8]}@example.test")
    mine = Env(owner_db, f"brief-mine-{uuid.uuid4().hex[:8]}@example.test")
    owner_db.execute(
        "INSERT INTO workspace_ai_settings (workspace_id, invoice_brief_enabled) VALUES (%s, true)", [mine.ws]
    )
    provider = script(final())
    response = mine.client.post(mine.url(f"invoices/{other.invoices['INV-1']}/ai/brief"), {}, format="json")
    assert response.status_code == 404
    assert provider.requests == []


def test_only_roles_that_can_draft_may_ask(env: Env, script: Any) -> None:
    lead, _ = add_member(env.db, env.ws, f"lead-{uuid.uuid4().hex[:6]}@example.test", "PROJECT_LEAD")
    provider = script(final())
    assert brief(env, client=lead).status_code == 403
    assert provider.requests == []


def test_the_opt_in_is_part_of_the_settings(env: Env) -> None:
    url = env.url("ai/settings")
    assert env.client.get(url).json()["invoice_brief_enabled"] is True
    response = env.client.put(url, {"invoice_brief_enabled": False}, format="json", **idem())
    assert response.status_code == 200 and response.json()["invoice_brief_enabled"] is False
