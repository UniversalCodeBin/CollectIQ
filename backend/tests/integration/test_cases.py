"""Disputes and blockers (E076-E082): TS-006, TS-034, BR-60, critical negative 7."""

import uuid
from datetime import timedelta
from typing import Any

import psycopg
import pytest
from rest_framework.test import APIClient

from collectiq.cases import service
from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.policy import service as policy
from collectiq.policy.domain import ActionRequest, ActionType, Actor, ActorKind, Outcome
from tests.integration.test_accounts import _invoices
from tests.support import API, add_member, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")


class Env:
    def __init__(self, owner_db: psycopg.Connection, email: str) -> None:
        self.db = owner_db
        self.client, self.ws = owner_workspace(owner_db, email)
        owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [self.ws])
        self.user = owner_db.execute(
            "SELECT user_id FROM workspace_memberships WHERE role = 'OWNER'"
        ).fetchone()[0]
        self.ctx = RequestContext(uuid.UUID(self.ws), self.user, "OWNER", str(uuid.uuid4()), "USER")
        self.ai = RequestContext(uuid.UUID(self.ws), None, None, str(uuid.uuid4()), "AI")
        self.invoices = _invoices(self.client, self.ws, ("INV-1", "2026-10-01"), ("INV-2", "2026-10-02"))

    def url(self, tail: str) -> str:
        return f"{API}/workspaces/{self.ws}/{tail}"

    def open(self, invoice: str = "INV-1", type_: str = "DISPUTE", **extra: Any) -> Any:
        body = {
            "invoice_id": self.invoices[invoice],
            "type": type_,
            "summary": "Customer says the amount is wrong.",
        }
        return self.client.post(self.url("cases"), {**body, **extra}, format="json", **idem())

    def case(self, **kw: Any) -> dict[str, Any]:
        response = self.open(**kw)
        assert response.status_code == 201, response.content
        return response.json()

    def resolve(self, case_id: str, outcome: str = "NO_CHANGE", **extra: Any) -> Any:
        return self.client.post(
            self.url(f"cases/{case_id}/resolve"), {"outcome": outcome, **extra}, format="json", **idem()
        )

    def state(self, invoice: str = "INV-1") -> dict[str, Any]:
        cur = self.db.execute(
            "SELECT dispute_status, reminder_status, outstanding_minor, version FROM invoice_state"
            " WHERE invoice_id = %s",
            [self.invoices[invoice]],
        )
        return dict(zip([c.name for c in cur.description], cur.fetchone(), strict=True))

    def audit(self, action: str) -> list[Any]:
        return self.db.execute(
            "SELECT actor_type, actor_id, after_masked FROM audit_events WHERE action = %s", [action]
        ).fetchall()


@pytest.fixture
def env(owner_db: psycopg.Connection) -> Env:
    return Env(owner_db, f"case-{uuid.uuid4().hex[:8]}@example.test")


# --- TS-006: a dispute suppresses reminders ---


def test_opening_a_dispute_suppresses_reminders_and_leaves_the_balance(env: Env) -> None:
    before = env.state()
    case = env.case(dispute_type="AMOUNT")
    after = env.state()
    assert case["status"] == "OPEN" and case["type"] == "DISPUTE" and case["dispute_type"] == "AMOUNT"
    assert (after["dispute_status"], after["reminder_status"]) == ("OPEN", "SUPPRESSED")
    assert after["outstanding_minor"] == before["outstanding_minor"]
    assert after["version"] > before["version"]
    assert env.state("INV-2")["dispute_status"] == "NONE"
    assert [r[0] for r in env.audit("case.opened")] == ["USER"]
    event = env.db.execute("SELECT payload FROM outbox_events WHERE event_type = 'CaseOpened'").fetchone()
    assert event and event[0]["case_id"] == case["id"]


def test_second_open_dispute_on_the_invoice_is_a_duplicate(env: Env) -> None:
    env.case()
    response = env.open()
    assert response.status_code == 409 and response.json()["code"] == "DUPLICATE_RESOURCE"
    assert env.open("INV-2").status_code == 201


def test_a_cancelled_invoice_takes_no_case(env: Env) -> None:
    env.db.execute("UPDATE invoices SET status = 'CANCELLED' WHERE id = %s", [env.invoices["INV-1"]])
    assert env.open().status_code == 409


def test_blocker_fails_g5_without_touching_the_dispute_status(env: Env) -> None:
    case = env.case(type_="MISSING_DOCUMENT")
    assert env.state()["dispute_status"] == "NONE" and env.state()["reminder_status"] == "SUPPRESSED"
    with tenant_tx(env.ctx):
        snap = service.invoice_snapshot(uuid.UUID(env.invoices["INV-1"]))
    assert snap.open_blocker is True and snap.dispute_status == "NONE"
    assert env.resolve(case["id"], "OTHER").status_code == 200
    assert env.state()["reminder_status"] == "NOT_CONTACTED"
    with tenant_tx(env.ctx):
        assert service.invoice_snapshot(uuid.UUID(env.invoices["INV-1"])).open_blocker is False


def test_dispute_type_only_belongs_to_a_dispute(env: Env) -> None:
    assert env.open(type_="QUESTION", dispute_type="AMOUNT").status_code == 422


def test_unknown_field_is_refused(env: Env) -> None:
    assert env.open(severity="HIGH").status_code == 422


# --- critical negative 7: an open dispute blocks approval ---


def test_open_dispute_blocks_approval(env: Env) -> None:
    env.case()
    with tenant_tx(env.ctx):
        snap = service.invoice_snapshot(uuid.UUID(env.invoices["INV-1"]))
    req = ActionRequest(
        ActionType.SEND_REMINDER,
        Actor(ActorKind.HUMAN, str(env.user), "OWNER"),
        f"invoice:{env.invoices['INV-1']}",
        {},
    )
    decision = policy.decide(env.ctx, req, snap)
    assert decision["outcome"] != Outcome.REQUIRE_APPROVAL and decision["approval_id"] is None
    assert any(g["gate"] == "G4" and not g["passed"] for g in decision["gate_results"])
    assert env.db.execute("SELECT count(*) FROM approval_requests").fetchone()[0] == 0


# --- BR-60: only a person resolves ---


def test_ai_cannot_resolve_case(env: Env) -> None:
    case = env.case()
    with pytest.raises(ProblemError) as raised:
        service.resolve_case(env.ai, uuid.UUID(case["id"]), "NO_CHANGE", None)
    assert raised.value.status == 403
    assert env.state()["dispute_status"] == "OPEN"


def test_database_refuses_a_resolved_case_without_a_person(env: Env) -> None:
    case = env.case()
    with pytest.raises(psycopg.errors.CheckViolation):
        env.db.execute("UPDATE cases SET status = 'RESOLVED' WHERE id = %s", [case["id"]])


def test_project_lead_and_unassigned_roles_cannot_resolve_or_open(
    env: Env, owner_db: psycopg.Connection
) -> None:
    case = env.case()
    lead, _ = add_member(owner_db, env.ws, "case-lead@example.test", "PROJECT_LEAD")
    assert (
        lead.post(
            env.url(f"cases/{case['id']}/resolve"), {"outcome": "OTHER"}, format="json", **idem()
        ).status_code
        == 403
    )
    assert (
        lead.post(
            env.url("cases"),
            {"invoice_id": env.invoices["INV-2"], "type": "QUESTION", "summary": "x"},
            format="json",
            **idem(),
        ).status_code
        == 403
    )


def test_resolution_records_outcome_actor_and_audit(env: Env) -> None:
    case = env.case()
    response = env.resolve(case["id"], "ADJUSTMENT_AGREED", note="Agreed 5% off; credit note to follow.")
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "RESOLVED" and body["resolution_outcome"] == "ADJUSTMENT_AGREED"
    assert body["resolved_by"] == str(env.user) and body["resolved_at"]
    assert body["resolution_note"].startswith("Agreed 5%")
    rows = env.audit("case.resolved")
    assert len(rows) == 1 and rows[0][0] == "USER" and rows[0][2]["outcome"] == "ADJUSTMENT_AGREED"
    again = env.resolve(case["id"])
    assert again.status_code == 409


def test_resolution_needs_a_known_outcome(env: Env) -> None:
    case = env.case()
    assert env.resolve(case["id"], "PAID").status_code == 422
    assert (
        env.client.post(env.url(f"cases/{case['id']}/resolve"), {}, format="json", **idem()).status_code
        == 422
    )


def test_ai_resolution_never_marks_the_invoice_paid(env: Env) -> None:
    case = env.case()
    env.resolve(case["id"], "WITHDRAWN_BY_CUSTOMER")
    cur = env.db.execute(
        "SELECT payment_status FROM invoice_state WHERE invoice_id = %s", [env.invoices["INV-1"]]
    )
    assert cur.fetchone()[0] == "OUTSTANDING"


# --- TS-034: resolving does not resume; resume needs cooling-off and a person ---


def test_resolving_keeps_reminders_suppressed(env: Env) -> None:
    case = env.case()
    env.resolve(case["id"])
    state = env.state()
    assert (state["dispute_status"], state["reminder_status"]) == ("RESOLVED", "SUPPRESSED")


def _request_resume(env: Env) -> dict[str, Any]:
    return service.request_resume(env.ctx, uuid.UUID(env.invoices["INV-1"]))


def _resume(env: Env, approval_id: Any) -> Any:
    return env.client.post(
        env.url(f"invoices/{env.invoices['INV-1']}/followups/resume"),
        {"approval_id": str(approval_id)},
        format="json",
        **idem(),
    )


def test_resume_waits_for_the_cooling_off_then_needs_a_person(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = env.case()
    env.resolve(case["id"])
    too_soon = _request_resume(env)
    assert too_soon["outcome"] != Outcome.REQUIRE_APPROVAL and too_soon["approval_id"] is None
    assert any(g["gate"] == "G4" and not g["passed"] for g in too_soon["gate_results"])

    real = clock.now
    monkeypatch.setattr(clock, "now", lambda: real() + timedelta(hours=25))
    ready = _request_resume(env)
    assert ready["outcome"] == Outcome.REQUIRE_APPROVAL and ready["approval_id"]
    blocked = _resume(env, ready["approval_id"])
    assert blocked.status_code == 409 and blocked.json()["code"] == "POLICY_BLOCKED"  # not yet approved
    assert env.state()["dispute_status"] == "RESOLVED"

    approved = env.client.post(
        env.url(f"approvals/{ready['approval_id']}/decide"), {"decision": "APPROVED"}, format="json", **idem()
    )
    assert approved.status_code == 200, approved.content
    done = _resume(env, ready["approval_id"])
    assert done.status_code == 200, done.content
    state = env.state()
    assert (state["dispute_status"], state["reminder_status"]) == ("NONE", "NOT_CONTACTED")
    assert len(env.audit("followups.resumed")) == 1
    # INV: resuming sends nothing and drafts nothing.
    assert (
        env.db.execute("SELECT count(*) FROM outbox_events WHERE event_type LIKE '%Send%'").fetchone()[0] == 0
    )
    assert _resume(env, ready["approval_id"]).status_code in (409,)


def test_resume_is_refused_while_the_dispute_is_open(env: Env) -> None:
    env.case()
    with pytest.raises(ProblemError) as raised:
        _request_resume(env)
    assert raised.value.status == 409


def test_resume_refuses_an_approval_for_another_invoice(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("INV-1", "INV-2"):
        env.resolve(env.case(invoice=name)["id"])
    real = clock.now
    monkeypatch.setattr(clock, "now", lambda: real() + timedelta(hours=25))
    ready = service.request_resume(env.ctx, uuid.UUID(env.invoices["INV-2"]))
    env.client.post(
        env.url(f"approvals/{ready['approval_id']}/decide"), {"decision": "APPROVED"}, format="json", **idem()
    )
    assert _resume(env, ready["approval_id"]).status_code == 409
    assert env.state("INV-1")["dispute_status"] == "RESOLVED"


def test_resume_is_refused_when_a_new_dispute_opened_after_approval(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = env.case()
    env.resolve(case["id"])
    real = clock.now
    monkeypatch.setattr(clock, "now", lambda: real() + timedelta(hours=25))
    ready = _request_resume(env)
    env.client.post(
        env.url(f"approvals/{ready['approval_id']}/decide"), {"decision": "APPROVED"}, format="json", **idem()
    )
    assert (
        env.client.post(
            env.url(f"cases/{case['id']}/reopen"),
            {"reason": "Customer wrote again."},
            format="json",
            **idem(),
        ).status_code
        == 200
    )
    blocked = _resume(env, ready["approval_id"])
    assert blocked.status_code == 409
    assert env.state()["dispute_status"] == "OPEN"


# --- FR-130: reopen ---


def test_reopen_resuppresses_and_may_come_from_automation(env: Env) -> None:
    case = env.case()
    env.resolve(case["id"])
    reopened = service.reopen_case(
        env.ai, uuid.UUID(case["id"]), "A later message disputes the invoice again."
    )
    assert reopened["status"] == "OPEN" and reopened["reopen_count"] == 1
    assert reopened["resolved_by"] is None and reopened["resolution_outcome"] is None
    state = env.state()
    assert (state["dispute_status"], state["reminder_status"]) == ("OPEN", "SUPPRESSED")
    rows = env.audit("case.reopened")
    assert len(rows) == 1 and rows[0][0] == "AI"


def test_only_a_resolved_case_reopens(env: Env) -> None:
    case = env.case()
    response = env.client.post(
        env.url(f"cases/{case['id']}/reopen"), {"reason": "again"}, format="json", **idem()
    )
    assert response.status_code == 409


# --- E079: update ---


def _patch(env: Env, client: APIClient, case: dict[str, Any], version: Any = None, **body: Any) -> Any:
    return client.patch(
        env.url(f"cases/{case['id']}"), body, format="json", HTTP_IF_MATCH=f'"{version or case["version"]}"'
    )


def test_status_change_follows_to_the_dispute_status(env: Env) -> None:
    case = env.case()
    moved = _patch(env, env.client, case, status="IN_REVIEW", note="Looking at the PO.")
    assert moved.status_code == 200, moved.content
    assert env.state()["dispute_status"] == "IN_REVIEW"
    assert moved.json()["version"] == case["version"] + 1
    assert [n["kind"] for n in moved.json()["notes"]] == ["STATUS", "NOTE"]
    waiting = _patch(env, env.client, moved.json(), status="AWAITING_CUSTOMER")
    assert waiting.status_code == 200 and env.state()["dispute_status"] == "AWAITING_CUSTOMER"
    assert env.audit("case.status_changed")


def test_a_status_change_cannot_resolve(env: Env) -> None:
    case = env.case()
    assert _patch(env, env.client, case, status="RESOLVED").status_code == 422
    assert env.state()["dispute_status"] == "OPEN"


def test_stale_version_is_a_conflict(env: Env) -> None:
    case = env.case()
    assert _patch(env, env.client, case, note="one").status_code == 200
    stale = _patch(env, env.client, case, note="two")
    assert stale.status_code == 409 and stale.json()["code"] == "CONFLICT_VERSION"
    assert env.client.patch(env.url(f"cases/{case['id']}"), {"note": "x"}, format="json").status_code == 422


def test_resolved_case_cannot_be_edited(env: Env) -> None:
    case = env.case()
    resolved = env.resolve(case["id"]).json()
    assert _patch(env, env.client, resolved, note="late").status_code == 409


def test_assignment_must_be_a_member_and_notifies(env: Env, owner_db: psycopg.Connection) -> None:
    case = env.case()
    stranger = uuid.uuid4()
    assert _patch(env, env.client, case, assignee_id=str(stranger)).status_code == 422
    lead, _ = add_member(owner_db, env.ws, "case-lead2@example.test", "PROJECT_LEAD")
    lead_id = owner_db.execute("SELECT id FROM users WHERE email = 'case-lead2@example.test'").fetchone()[0]
    assigned = _patch(env, env.client, case, assignee_id=str(lead_id))
    assert assigned.status_code == 200 and assigned.json()["assignee_id"] == str(lead_id)
    assert (
        owner_db.execute("SELECT count(*) FROM outbox_events WHERE event_type = 'CaseAssigned'").fetchone()[0]
        == 1
    )
    cleared = _patch(env, env.client, assigned.json(), assignee_id=None)
    assert cleared.json()["assignee_id"] is None


def test_project_lead_sees_and_notes_only_assigned_cases(env: Env, owner_db: psycopg.Connection) -> None:
    mine, other = env.case(), env.case(invoice="INV-2")
    lead, _ = add_member(owner_db, env.ws, "case-lead3@example.test", "PROJECT_LEAD")
    lead_id = owner_db.execute("SELECT id FROM users WHERE email = 'case-lead3@example.test'").fetchone()[0]
    mine = _patch(env, env.client, mine, assignee_id=str(lead_id)).json()
    listed = lead.get(env.url("cases")).json()["items"]
    assert [c["id"] for c in listed] == [mine["id"]]
    assert lead.get(env.url(f"cases/{other['id']}")).status_code == 404
    assert _patch(env, lead, other, note="peek").status_code == 404
    assert _patch(env, lead, mine, note="Sent the PO copy.").status_code == 200
    assert _patch(env, lead, _refresh(env, mine), status="IN_REVIEW").status_code == 403
    assert _patch(env, lead, _refresh(env, mine), assignee_id=None).status_code == 403


def _refresh(env: Env, case: dict[str, Any]) -> dict[str, Any]:
    return env.client.get(env.url(f"cases/{case['id']}")).json()


# --- E076 / E077 ---


def test_list_filters_and_pages(env: Env) -> None:
    first, second = env.case(), env.case(invoice="INV-2", type_="QUESTION")
    env.resolve(second["id"])
    page = env.client.get(env.url("cases?limit=1")).json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    rest = env.client.get(env.url(f"cases?limit=1&cursor={page['next_cursor']}")).json()
    assert {page["items"][0]["id"], rest["items"][0]["id"]} == {first["id"], second["id"]} and rest[
        "next_cursor"
    ] is None
    open_ = env.client.get(env.url("cases?status=OPEN")).json()["items"]
    assert [c["id"] for c in open_] == [first["id"]]
    by_invoice = env.client.get(env.url(f"cases?invoice_id={env.invoices['INV-2']}")).json()["items"]
    assert [c["id"] for c in by_invoice] == [second["id"]]
    assert env.client.get(env.url("cases?colour=red")).status_code == 422
    assert env.client.get(env.url("cases?invoice_id=nope")).status_code == 422


def test_automation_opened_summary_is_labelled_ai_derived(env: Env) -> None:
    opened = service.open_case(
        env.ai, uuid.UUID(env.invoices["INV-1"]), "DISPUTE", "Customer disputes the total."
    )
    assert opened["summary_is_ai_derived"] is True and opened["opened_by"] is None
    assert env.case(invoice="INV-2")["summary_is_ai_derived"] is False


def test_cases_are_tenant_isolated(env: Env, owner_db: psycopg.Connection) -> None:
    case = env.case()
    other_client, other_ws = owner_workspace(owner_db, "case-other@example.test")
    assert other_client.get(f"{API}/workspaces/{other_ws}/cases/{case['id']}").status_code == 404
    assert other_client.get(f"{API}/workspaces/{other_ws}/cases").json()["items"] == []
    forged = other_client.post(
        f"{API}/workspaces/{other_ws}/cases",
        {"invoice_id": env.invoices["INV-2"], "type": "DISPUTE", "summary": "x"},
        format="json",
        **idem(),
    )
    assert forged.status_code == 404
