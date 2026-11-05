"""Policy versions, emergency pause, persisted decisions, single use and approvals (E016-E020, E092, E101)."""

import dataclasses
import uuid
from datetime import timedelta
from typing import Any

import psycopg
import pytest
from django.db import DatabaseError
from rest_framework.test import APIClient

from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.policy import service
from collectiq.policy.authorized import AuthorizedAction
from collectiq.policy.domain import ActionRequest, ActionType, Actor, ActorKind, Outcome, StateSnapshot
from tests.support import API, add_member, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")


class Env:
    def __init__(self, owner_db: psycopg.Connection, email: str) -> None:
        self.owner_db = owner_db
        self.client, self.ws = owner_workspace(owner_db, email)
        owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [self.ws])
        self.user = owner_db.execute(
            "SELECT user_id FROM workspace_memberships WHERE role = 'OWNER'"
        ).fetchone()[0]
        self.ctx = RequestContext(uuid.UUID(self.ws), self.user, "OWNER", str(uuid.uuid4()), "USER")
        self.human = Actor(ActorKind.HUMAN, str(self.user), "OWNER")

    def url(self, tail: str) -> str:
        return f"{API}/workspaces/{self.ws}/{tail}"

    def request(
        self, action: ActionType = ActionType.SEND_REMINDER, actor: Actor | None = None
    ) -> ActionRequest:
        return ActionRequest(action, actor or self.human, f"invoice:{uuid.uuid4()}", {})

    def decide(self, req: ActionRequest | None = None, snap: StateSnapshot | None = None) -> dict[str, Any]:
        return service.decide(self.ctx, req or self.request(), snap or StateSnapshot())

    def put(self, **body: Any) -> Any:
        return self.client.put(self.url("policy"), body, format="json", **idem())

    def approvals(self) -> list[tuple[Any, ...]]:
        return self.owner_db.execute("SELECT id, status, decided_by FROM approval_requests").fetchall()


@pytest.fixture
def env(owner_db: psycopg.Connection) -> Env:
    return Env(owner_db, f"pol-{uuid.uuid4().hex[:8]}@example.test")


def _authorize(env: Env, decision_id: Any, req: ActionRequest, snap: StateSnapshot) -> AuthorizedAction:
    with tenant_tx(env.ctx):
        return service.authorize_execution(env.ctx, decision_id, req, snap)


def _blocked(env: Env, decision_id: Any, req: ActionRequest, snap: StateSnapshot) -> str:
    with pytest.raises(ProblemError) as raised:
        _authorize(env, decision_id, req, snap)
    assert raised.value.code == "POLICY_BLOCKED" and raised.value.status == 409
    return raised.value.detail


# --- E016 / E017 / E018: versioned policy ---


def test_new_workspace_starts_manual_unpaused_with_auto_snooze_unavailable(env: Env) -> None:
    body = env.client.get(env.url("policy")).json()
    assert body["version"] == 1 and body["mode"] == "MANUAL" and body["automation_paused"] is False
    assert body["auto_snooze_enabled"] is False and body["auto_snooze_available"] is False
    versions = env.client.get(env.url("policy/versions")).json()
    assert [v["version"] for v in versions["items"]] == [1]


def test_put_writes_a_new_immutable_version(env: Env) -> None:
    response = env.put(mode="ASSISTED", cadence={"first_after_days": 3}, limits={"max_contacts": 2})
    assert response.status_code == 200, response.content
    assert response.json()["version"] == 2 and response.json()["mode"] == "ASSISTED"
    assert env.client.get(env.url("policy")).json()["limits"] == {"max_contacts": 2}
    versions = env.client.get(env.url("policy/versions")).json()["items"]
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[1]["mode"] == "MANUAL"
    assert versions[0]["changed_by"] == str(env.user)
    audit = env.owner_db.execute("SELECT action FROM audit_events WHERE action = 'policy.changed'").fetchall()
    assert len(audit) == 1
    with pytest.raises(DatabaseError):  # versions are rows the app can only add
        with tenant_tx(env.ctx):
            from collectiq.platform.db import execute

            execute("UPDATE workspace_policies SET settings = '{}'::jsonb")


def test_put_keeps_the_pause_flag_and_rejects_bad_input(env: Env) -> None:
    assert env.client.post(env.url("automation/pause"), {}, format="json", **idem()).status_code == 200
    assert env.put(mode="ASSISTED").json()["automation_paused"] is True
    assert env.put(mode="AUTO_SEND").status_code == 422
    assert env.put(mode="ASSISTED", surprise=1).status_code == 422
    assert env.put(limits={"max_contacts": 0}).status_code == 422
    assert env.put(limits={"max_contacts": "many"}).status_code == 422


def test_auto_snooze_cannot_be_switched_on_until_it_is_evaluated(env: Env) -> None:
    response = env.put(mode="ASSISTED", auto_snooze_enabled=True)
    assert response.status_code == 422
    assert "evaluat" in response.content.decode().lower()
    assert env.client.get(env.url("policy")).json()["version"] == 1


def test_policy_roles_and_isolation(env: Env, owner_db: psycopg.Connection) -> None:
    lead, _ = add_member(owner_db, env.ws, "pol-lead@example.test", "PROJECT_LEAD")
    admin, _ = add_member(owner_db, env.ws, "pol-fin@example.test", "FINANCE_ADMIN")
    assert lead.get(env.url("policy")).status_code == 403
    assert lead.get(env.url("policy/versions")).status_code == 403
    assert lead.put(env.url("policy"), {"mode": "ASSISTED"}, format="json", **idem()).status_code == 403
    assert lead.post(env.url("automation/pause"), {}, format="json", **idem()).status_code == 403
    assert admin.get(env.url("policy")).status_code == 200
    assert admin.put(env.url("policy"), {"mode": "ASSISTED"}, format="json", **idem()).status_code == 200
    stranger, other_ws = owner_workspace(owner_db, "pol-stranger@example.test")
    assert stranger.get(env.url("policy")).status_code in (403, 404)
    assert stranger.get(f"{API}/workspaces/{other_ws}/policy").json()["version"] == 1


# --- E019 / E020: emergency pause ---


def test_pause_and_resume_are_versions_with_audit(env: Env) -> None:
    paused = env.client.post(env.url("automation/pause"), {"reason": "Bank holiday"}, format="json", **idem())
    assert paused.status_code == 200 and paused.json()["automation_paused"] is True
    again = env.client.post(env.url("automation/pause"), {}, format="json", **idem())
    assert again.json()["version"] == paused.json()["version"]  # already paused: no new version
    resumed = env.client.post(env.url("automation/resume"), {}, format="json", **idem())
    assert resumed.json()["automation_paused"] is False
    assert resumed.json()["version"] == paused.json()["version"] + 1
    actions = [r[0] for r in env.owner_db.execute("SELECT action FROM audit_events ORDER BY id").fetchall()]
    assert "automation.paused" in actions and "automation.resumed" in actions


def test_pause_holds_outbound_decisions_and_resume_does_not_release_them(env: Env) -> None:
    env.client.post(env.url("automation/pause"), {}, format="json", **idem())
    held = env.decide()
    assert held["outcome"] == Outcome.PAUSE_FOR_REVIEW
    assert env.approvals() == []
    env.client.post(env.url("automation/resume"), {}, format="json", **idem())
    assert _blocked(env, held["id"], env.request(), StateSnapshot())  # a held decision never authorizes later


# --- decide(): persisted, explained decisions ---


def test_decide_persists_the_decision_with_versions_and_gate_results(env: Env) -> None:
    decision = env.decide(snap=StateSnapshot(state_version=4))
    row = env.owner_db.execute(
        "SELECT action_type, outcome, state_version, policy_version, rules_version, inputs_hash, consumed_at,"
        " jsonb_array_length(gate_results) FROM policy_decisions WHERE id = %s",
        [decision["id"]],
    ).fetchone()
    assert row[:3] == ("SEND_REMINDER", "REQUIRE_APPROVAL", 4)
    assert row[3] == 1 and row[4] and len(row[5]) == 64 and row[6] is None and row[7] == 15
    assert len(env.approvals()) == 1 and env.approvals()[0][1] == "PENDING"


def test_a_denied_or_cancelled_decision_creates_no_approval(env: Env) -> None:
    assert env.decide(snap=StateSnapshot(payment_status="PAID_VERIFIED"))["outcome"] == Outcome.CANCEL
    ai = Actor(ActorKind.AI, None, None)
    assert env.decide(env.request(ActionType.CONFIRM_ALLOCATION, ai))["outcome"] == Outcome.DENY
    assert env.approvals() == []


def test_decide_stores_a_forbidden_action_as_a_denial(env: Env) -> None:
    decision = service.decide(
        env.ctx, ActionRequest("MARK_PAID", env.human, "invoice:x", {}), StateSnapshot()
    )
    assert decision["outcome"] == Outcome.DENY
    stored = env.owner_db.execute("SELECT action_type, outcome FROM policy_decisions").fetchone()
    assert stored == ("MARK_PAID", "DENY")


def test_engine_failure_is_stored_as_a_denial(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: Any) -> Any:
        raise RuntimeError("db lost")

    monkeypatch.setattr(service, "active_policy", boom)
    decision = env.decide()
    assert decision["outcome"] == Outcome.DENY and decision["reasons"] == ["POLICY_ENGINE_ERROR"]


# --- single use and re-check ---


def _approved(
    env: Env, snap: StateSnapshot | None = None
) -> tuple[dict[str, Any], ActionRequest, StateSnapshot]:
    req, snap = env.request(), snap or StateSnapshot()
    decision = env.decide(req, snap)
    approval = env.approvals()[-1][0]
    response = env.client.post(
        env.url(f"approvals/{approval}/decide"),
        {"decision": "APPROVED", "note": "Looks right"},
        format="json",
        **idem(),
    )
    assert response.status_code == 200, response.content
    return decision, req, snap


def test_an_allowed_decision_authorizes_once(env: Env) -> None:
    req = env.request(ActionType.CREATE_DRAFT)
    decision = env.decide(req)
    assert decision["outcome"] == Outcome.ALLOW_AUTOMATIC
    authorized = _authorize(env, decision["id"], req, StateSnapshot())
    assert isinstance(authorized, AuthorizedAction)
    assert authorized.action == "CREATE_DRAFT" and str(authorized.decision_id) == str(decision["id"])
    assert "already" in _blocked(env, decision["id"], req, StateSnapshot()).lower()


def test_decision_cannot_be_consumed_twice(env: Env) -> None:
    req = env.request(ActionType.CREATE_DRAFT)
    decision = env.decide(req)
    _authorize(env, decision["id"], req, StateSnapshot())
    for sql in (
        "UPDATE policy_decisions SET consumed_at = now() WHERE id = %s",
        "UPDATE policy_decisions SET consumed_at = NULL WHERE id = %s",
        "UPDATE policy_decisions SET outcome = 'ALLOW_AUTOMATIC', consumed_at = NULL WHERE id = %s",
        "DELETE FROM policy_decisions WHERE id = %s",
    ):
        with pytest.raises(DatabaseError):
            with tenant_tx(env.ctx):
                from collectiq.platform.db import execute

                execute(sql, [decision["id"]])


def test_only_consumed_at_may_ever_change_even_for_the_owner_role(env: Env) -> None:
    decision = env.decide(env.request(ActionType.CREATE_DRAFT))
    with pytest.raises(psycopg.Error):
        env.owner_db.execute("UPDATE policy_decisions SET outcome = 'DENY' WHERE id = %s", [decision["id"]])
    env.owner_db.execute("UPDATE policy_decisions SET consumed_at = now() WHERE id = %s", [decision["id"]])
    with pytest.raises(psycopg.Error):
        env.owner_db.execute(
            "UPDATE policy_decisions SET consumed_at = now() WHERE id = %s", [decision["id"]]
        )


def test_authorize_needs_the_same_request_and_state(env: Env) -> None:
    req = env.request(ActionType.CREATE_DRAFT)
    decision = env.decide(req, StateSnapshot(state_version=3))
    assert "changed" in _blocked(env, decision["id"], req, StateSnapshot(state_version=4)).lower()
    other = dataclasses.replace(req, subject="invoice:somebody-else")
    _blocked(env, decision["id"], other, StateSnapshot(state_version=3))
    _blocked(env, decision["id"], req, StateSnapshot(state_version=3, open_blocker=True))
    assert _authorize(env, decision["id"], req, StateSnapshot(state_version=3))


def test_authorize_blocks_when_the_gates_now_fail(env: Env) -> None:
    req = env.request(ActionType.CREATE_DRAFT)
    decision = env.decide(req)
    paid = StateSnapshot(payment_status="PAID_VERIFIED")
    _blocked(env, decision["id"], req, paid)


def test_authorize_blocks_after_a_new_policy_version(env: Env) -> None:
    req = env.request(ActionType.CREATE_DRAFT)
    decision = env.decide(req)
    assert env.put(mode="ASSISTED").status_code == 200
    assert "polic" in _blocked(env, decision["id"], req, StateSnapshot()).lower()


def test_authorize_blocks_an_expired_decision(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    req = env.request(ActionType.CREATE_DRAFT)
    decision = env.decide(req)
    real = clock.now
    monkeypatch.setattr(clock, "now", lambda: real() + timedelta(hours=2))
    assert "expired" in _blocked(env, decision["id"], req, StateSnapshot()).lower()


@pytest.mark.parametrize(
    "outcome_snap", [{"open_blocker": True}, {"snooze_active": True}, {"idempotency_key_used": True}]
)
def test_a_held_or_denied_decision_never_authorizes(env: Env, outcome_snap: dict[str, Any]) -> None:
    req, snap = env.request(), StateSnapshot(**outcome_snap)
    decision = env.decide(req, snap)
    assert decision["outcome"] != Outcome.ALLOW_AUTOMATIC
    _blocked(env, decision["id"], req, snap)


def test_authorize_must_run_inside_the_executors_transaction(env: Env) -> None:
    req = env.request(ActionType.CREATE_DRAFT)
    decision = env.decide(req)
    with pytest.raises(RuntimeError):
        service.authorize_execution(env.ctx, decision["id"], req, StateSnapshot())


def test_authorized_action_cannot_be_built_outside_the_policy_package() -> None:
    with pytest.raises(TypeError):
        AuthorizedAction(decision_id=uuid.uuid4(), action="SEND_REMINDER", subject="x", approved_by=None)  # type: ignore[call-arg]


def test_unknown_decision_is_not_found_and_other_workspaces_cannot_use_it(
    env: Env, owner_db: psycopg.Connection
) -> None:
    req = env.request(ActionType.CREATE_DRAFT)
    decision = env.decide(req)
    with pytest.raises(ProblemError) as raised:
        _authorize(env, uuid.uuid4(), req, StateSnapshot())
    assert raised.value.status == 404
    other = Env(owner_db, "pol-other@example.test")
    with pytest.raises(ProblemError) as theirs:
        with tenant_tx(other.ctx):
            service.authorize_execution(other.ctx, decision["id"], req, StateSnapshot())
    assert theirs.value.status == 404


# --- approvals (E092) ---


def test_send_needs_an_approval_before_it_authorizes(env: Env) -> None:
    req, snap = env.request(), StateSnapshot()
    decision = env.decide(req, snap)
    assert decision["outcome"] == Outcome.REQUIRE_APPROVAL
    assert "approv" in _blocked(env, decision["id"], req, snap).lower()


def test_an_approved_send_authorizes_once_and_names_the_approver(env: Env) -> None:
    decision, req, snap = _approved(env)
    authorized = _authorize(env, decision["id"], req, snap)
    assert authorized.approved_by == env.user
    _blocked(env, decision["id"], req, snap)


def test_a_rejected_approval_never_authorizes(env: Env) -> None:
    req, snap = env.request(), StateSnapshot()
    decision = env.decide(req, snap)
    approval = env.approvals()[0][0]
    rejected = env.client.post(
        env.url(f"approvals/{approval}/decide"),
        {"decision": "REJECTED", "note": "Wrong tone"},
        format="json",
        **idem(),
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
    _blocked(env, decision["id"], req, snap)


def test_an_approval_is_decided_once(env: Env) -> None:
    _approved(env)
    approval = env.approvals()[0][0]
    again = env.client.post(
        env.url(f"approvals/{approval}/decide"), {"decision": "REJECTED"}, format="json", **idem()
    )
    assert again.status_code == 409
    with pytest.raises(psycopg.Error):
        env.owner_db.execute("UPDATE approval_requests SET status = 'PENDING' WHERE id = %s", [approval])


def test_approval_roles_validation_and_isolation(env: Env, owner_db: psycopg.Connection) -> None:
    env.decide()
    approval = env.approvals()[0][0]
    path = env.url(f"approvals/{approval}/decide")
    lead, _ = add_member(owner_db, env.ws, "pol-lead2@example.test", "PROJECT_LEAD")
    assert lead.post(path, {"decision": "APPROVED"}, format="json", **idem()).status_code == 403
    assert env.client.post(path, {"decision": "MAYBE"}, format="json", **idem()).status_code == 422
    assert env.client.post(path, {}, format="json", **idem()).status_code == 422
    stranger, _ = owner_workspace(owner_db, "pol-stranger2@example.test")
    assert stranger.post(path, {"decision": "APPROVED"}, format="json", **idem()).status_code in (403, 404)
    missing = env.url(f"approvals/{uuid.uuid4()}/decide")
    assert env.client.post(missing, {"decision": "APPROVED"}, format="json", **idem()).status_code == 404
    assert env.approvals()[0][1] == "PENDING"


def test_approving_an_expired_decision_is_refused(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    env.decide()
    approval = env.approvals()[0][0]
    real = clock.now
    monkeypatch.setattr(clock, "now", lambda: real() + timedelta(hours=2))
    response = env.client.post(
        env.url(f"approvals/{approval}/decide"), {"decision": "APPROVED"}, format="json", **idem()
    )
    assert response.status_code == 409
    assert env.approvals()[0][1] == "PENDING"


def test_approval_decisions_are_audited_with_the_decision_id(env: Env) -> None:
    decision, _, _ = _approved(env)
    row = env.owner_db.execute(
        "SELECT action, policy_decision_id FROM audit_events WHERE action LIKE 'approval.%'"
    ).fetchone()
    assert row == ("approval.approved", decision["id"])


# --- E101: why-view ---


def test_why_view_explains_in_plain_words(env: Env) -> None:
    decision = env.decide(snap=StateSnapshot(dispute_status="OPEN", recipient_suppressed=True))
    body = env.client.get(env.url(f"policy-decisions/{decision['id']}")).json()
    assert body["outcome"] == "PAUSE_FOR_REVIEW" and body["action_type"] == "SEND_REMINDER"
    assert any("dispute" in line.lower() for line in body["explanation"])
    gates = {g["gate"]: g for g in body["gates"]}
    assert len(gates) == 15 and gates["G4"]["passed"] is False and gates["G1"]["passed"] is True
    assert all(g["text"] for g in gates.values())
    assert body["policy_version"] == 1 and body["rules_version"] and body["consumed_at"] is None
    assert body["approval"] is None


def test_why_view_shows_the_approval_and_consumption(env: Env) -> None:
    decision, req, snap = _approved(env)
    _authorize(env, decision["id"], req, snap)
    body = env.client.get(env.url(f"policy-decisions/{decision['id']}")).json()
    assert body["approval"]["status"] == "APPROVED" and body["approval"]["decided_by"] == str(env.user)
    assert body["consumed_at"] is not None


def test_why_view_roles_and_isolation(env: Env, owner_db: psycopg.Connection) -> None:
    decision = env.decide()
    lead, _ = add_member(owner_db, env.ws, "pol-lead3@example.test", "PROJECT_LEAD")
    path = env.url(f"policy-decisions/{decision['id']}")
    assert lead.get(path).status_code == 403
    stranger, other_ws = owner_workspace(owner_db, "pol-stranger3@example.test")
    assert stranger.get(f"{API}/workspaces/{other_ws}/policy-decisions/{decision['id']}").status_code == 404
    assert env.client.get(env.url(f"policy-decisions/{uuid.uuid4()}")).status_code == 404


def test_decisions_and_approvals_are_invisible_across_workspaces(
    env: Env, owner_db: psycopg.Connection
) -> None:
    env.decide()
    other = Env(owner_db, "pol-iso@example.test")
    with tenant_tx(other.ctx):
        from collectiq.platform.db import fetch_all

        assert fetch_all("SELECT id FROM policy_decisions") == []
        assert fetch_all("SELECT id FROM approval_requests") == []


def test_unauthenticated_requests_are_refused(env: Env) -> None:
    anonymous = APIClient()
    assert anonymous.get(env.url("policy")).status_code == 401
    assert anonymous.post(env.url("automation/pause"), {}, format="json", **idem()).status_code == 401
