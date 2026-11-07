"""The pure policy engine (TSD §13): gates G1-G15, outcomes, fail-closed, and the actions that never exist."""

import dataclasses
from typing import Any

import pytest

from collectiq.policy.domain import (
    GATE_TEXT,
    ActionRequest,
    ActionType,
    Actor,
    ActorKind,
    Outcome,
    PolicyVersion,
    StateSnapshot,
    evaluate,
    explain,
)

HUMAN = Actor(ActorKind.HUMAN, "11111111-1111-4111-8111-111111111111", "OWNER")
AI = Actor(ActorKind.AI, None, None)
SYSTEM = Actor(ActorKind.SYSTEM, None, None)
POLICY = PolicyVersion(version=1, mode="ASSISTED")


def ask(action: Any, actor: Actor = HUMAN, **params: Any) -> ActionRequest:
    return ActionRequest(action, actor, "invoice:abc", params)


def run(action: Any = ActionType.SEND_REMINDER, snapshot: StateSnapshot | None = None, **policy: Any) -> Any:
    return evaluate(ask(action), snapshot or StateSnapshot(), dataclasses.replace(POLICY, **policy))


def failed(decision: Any) -> list[str]:
    return [g.gate for g in decision.gate_results if not g.passed]


def test_clean_send_requires_approval_and_passes_every_gate() -> None:
    decision = run()
    assert decision.outcome is Outcome.REQUIRE_APPROVAL
    assert [g.gate for g in decision.gate_results] == [f"G{i}" for i in range(1, 16)]
    assert failed(decision) == []
    assert decision.policy_version == 1 and decision.rules_version


# (gate, snapshot change, policy change, expected outcome). One case per gate and outcome class (TSD §13).
GATE_CASES = [
    ("G1", {"lifecycle": "VOID"}, {}, Outcome.CANCEL),
    ("G2", {"payment_status": "PAID_VERIFIED"}, {}, Outcome.CANCEL),
    ("G3", {"lifecycle": "CANCELLED"}, {}, Outcome.CANCEL),
    ("G3", {"lifecycle": "WRITTEN_OFF"}, {}, Outcome.CANCEL),
    ("G3", {"lifecycle": "ARCHIVED"}, {}, Outcome.CANCEL),
    ("G4", {"dispute_status": "OPEN"}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G4", {"dispute_status": "RESOLVED", "dispute_cooled_off": False}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G5", {"open_blocker": True}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G6", {"coverage": "STALE"}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G6", {"coverage": "MISSING"}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G7", {"payment_status": "AWAITING_VERIFICATION"}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G7", {"payment_status": "UNCERTAIN"}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G8", {"snooze_active": True}, {}, Outcome.DEFER),
    ("G9", {"recipient_approved": False}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G9", {"recipient_suppressed": True}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G10", {"contacts_in_window": 3}, {}, Outcome.DEFER),
    ("G11", {"in_business_hours": False}, {}, Outcome.DEFER),
    ("G12", {"draft_facts_valid": False}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G13", {}, {"paused": True}, Outcome.PAUSE_FOR_REVIEW),
    ("G13", {"sensitivity_satisfied": False}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G13", {"hold_scope": "CLIENT"}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G13", {"hold_scope": "INVOICE"}, {}, Outcome.PAUSE_FOR_REVIEW),
    ("G14", {"idempotency_key_used": True}, {}, Outcome.DENY),
    ("G15", {"integration_healthy": False}, {}, Outcome.PAUSE_FOR_REVIEW),
]


@pytest.mark.parametrize(("gate", "snap", "policy", "outcome"), GATE_CASES)
def test_each_gate_fails_closed_to_its_outcome(gate: str, snap: dict, policy: dict, outcome: Outcome) -> None:
    decision = run(snapshot=StateSnapshot(**snap), **policy)
    assert gate in failed(decision)
    assert decision.outcome is outcome
    assert any(r.startswith(gate) for r in decision.reasons)


def test_resolved_dispute_after_cooling_off_passes_g4() -> None:
    decision = run(snapshot=StateSnapshot(dispute_status="RESOLVED", dispute_cooled_off=True))
    assert "G4" not in failed(decision)


def test_partially_paid_passes_g7() -> None:
    assert "G7" not in failed(run(snapshot=StateSnapshot(payment_status="PARTIALLY_PAID")))


def test_most_severe_outcome_wins() -> None:
    snap = StateSnapshot(payment_status="PAID_VERIFIED", snooze_active=True, open_blocker=True)
    assert run(snapshot=snap).outcome is Outcome.CANCEL
    snap = StateSnapshot(idempotency_key_used=True, open_blocker=True, snooze_active=True)
    assert run(snapshot=snap).outcome is Outcome.DENY
    snap = StateSnapshot(open_blocker=True, snooze_active=True)
    assert run(snapshot=snap).outcome is Outcome.PAUSE_FOR_REVIEW


def test_g15_is_priority_one_but_still_blocks_when_unhealthy() -> None:
    assert GATE_TEXT["G15"]
    assert run(snapshot=StateSnapshot(integration_healthy=False)).outcome is Outcome.PAUSE_FOR_REVIEW


def test_every_gate_has_plain_words() -> None:
    assert set(GATE_TEXT) == {f"G{i}" for i in range(1, 16)}
    assert all(len(text) > 10 for text in GATE_TEXT.values())


def test_pause_stops_outbound_actions_but_not_protective_ones() -> None:
    assert run(ActionType.SEND_REMINDER, paused=True).outcome is Outcome.PAUSE_FOR_REVIEW
    assert run(ActionType.CREATE_DRAFT, paused=True).outcome is Outcome.PAUSE_FOR_REVIEW
    assert run(ActionType.PROTECTIVE_SUPPRESS, paused=True).outcome is Outcome.ALLOW_AUTOMATIC
    assert run(ActionType.CREATE_CASE, paused=True).outcome is Outcome.ALLOW_AUTOMATIC


def test_protective_actions_ignore_the_send_gates() -> None:
    snap = StateSnapshot(dispute_status="OPEN", snooze_active=True, recipient_suppressed=True)
    assert run(ActionType.PROTECTIVE_SUPPRESS, snapshot=snap).outcome is Outcome.ALLOW_AUTOMATIC
    assert run(ActionType.CREATE_CASE, snapshot=snap).outcome is Outcome.ALLOW_AUTOMATIC


@pytest.mark.parametrize(
    "action",
    [ActionType.APPROVE_DRAFT, ActionType.SEND_REMINDER, ActionType.MARK_SENT, ActionType.RESUME_FOLLOWUPS],
)
def test_outbound_actions_always_need_a_person_to_approve(action: ActionType) -> None:
    assert run(action).outcome is Outcome.REQUIRE_APPROVAL
    ai = evaluate(ask(action, AI), StateSnapshot(), POLICY)
    assert ai.outcome in (Outcome.REQUIRE_APPROVAL, Outcome.DENY)
    assert ai.outcome is not Outcome.ALLOW_AUTOMATIC


def test_creating_a_draft_is_automatic_but_sending_never_is() -> None:
    assert run(ActionType.CREATE_DRAFT).outcome is Outcome.ALLOW_AUTOMATIC
    for action in ActionType:
        if action in (ActionType.SEND_REMINDER, ActionType.MARK_SENT):
            assert run(action).outcome is not Outcome.ALLOW_AUTOMATIC


@pytest.mark.parametrize(
    "action", ["MARK_PAID", "AUTO_ALLOCATE", "AUTO_SEND", "mark_paid", "NOT_AN_ACTION", "", None]
)
def test_mark_paid_and_auto_allocate_always_deny(action: Any) -> None:
    for actor in (HUMAN, AI, SYSTEM):
        for snap in (StateSnapshot(), StateSnapshot(payment_status="PAID_VERIFIED")):
            decision = evaluate(ask(action, actor), snap, POLICY)
            assert decision.outcome is Outcome.DENY
            assert decision.reasons


def test_no_auto_send_enum_exists() -> None:
    names = {a.name for a in ActionType} | {a.value for a in ActionType}
    assert not {n for n in names if "AUTO_SEND" in n or "MARK_PAID" in n or "AUTO_ALLOCATE" in n}
    assert {o.value for o in Outcome} == {
        "ALLOW_AUTOMATIC",
        "REQUIRE_APPROVAL",
        "DENY",
        "DEFER",
        "PAUSE_FOR_REVIEW",
        "CANCEL",
    }


@pytest.mark.parametrize(
    "action",
    [
        ActionType.CONFIRM_ALLOCATION,
        ActionType.REVERSE_ALLOCATION,
        ActionType.CHANGE_STATUS,
        ActionType.CHANGE_RECIPIENT,
        ActionType.CHANGE_POLICY,
        ActionType.RESOLVE_CASE,
        ActionType.CHANGE_INTEGRATION,
        ActionType.EXPORT,
        ActionType.DELETE,
    ],
)
def test_ai_origin_denied_for_ledger_status_recipient_policy(action: ActionType) -> None:
    for actor in (AI, SYSTEM):
        decision = evaluate(ask(action, actor), StateSnapshot(), POLICY)
        assert decision.outcome is Outcome.DENY
        assert any("HUMAN_ONLY" in r for r in decision.reasons)
    assert evaluate(ask(action, HUMAN), StateSnapshot(), POLICY).outcome is Outcome.ALLOW_AUTOMATIC


def test_a_human_actor_needs_a_user_id() -> None:
    nameless = Actor(ActorKind.HUMAN, None, "OWNER")
    assert evaluate(ask(ActionType.CHANGE_POLICY, nameless), StateSnapshot(), POLICY).outcome is Outcome.DENY


def test_project_lead_cannot_change_policy_or_confirm_money() -> None:
    lead = Actor(ActorKind.HUMAN, "22222222-2222-4222-8222-222222222222", "PROJECT_LEAD")
    for action in (ActionType.CHANGE_POLICY, ActionType.CONFIRM_ALLOCATION, ActionType.REVERSE_ALLOCATION):
        assert evaluate(ask(action, lead), StateSnapshot(), POLICY).outcome is Outcome.DENY


def test_auto_snooze_needs_opt_in_and_the_evaluation_gate() -> None:
    base = StateSnapshot(ai_confidence="HIGH")
    off = evaluate(ask(ActionType.AUTO_SNOOZE, AI), base, POLICY)
    assert off.outcome is Outcome.REQUIRE_APPROVAL
    enabled_only = dataclasses.replace(POLICY, auto_snooze_enabled=True)
    assert evaluate(ask(ActionType.AUTO_SNOOZE, AI), base, enabled_only).outcome is Outcome.REQUIRE_APPROVAL
    both = dataclasses.replace(POLICY, auto_snooze_enabled=True, auto_snooze_available=True)
    assert evaluate(ask(ActionType.AUTO_SNOOZE, AI), base, both).outcome is Outcome.ALLOW_AUTOMATIC
    low = StateSnapshot(ai_confidence="MEDIUM")
    assert evaluate(ask(ActionType.AUTO_SNOOZE, AI), low, both).outcome is Outcome.REQUIRE_APPROVAL
    injected = StateSnapshot(ai_confidence="HIGH", injection_flag=True)
    assert evaluate(ask(ActionType.AUTO_SNOOZE, AI), injected, both).outcome is Outcome.DENY


def test_auto_snooze_respects_the_gates() -> None:
    both = dataclasses.replace(POLICY, auto_snooze_enabled=True, auto_snooze_available=True)
    snap = StateSnapshot(ai_confidence="HIGH", dispute_status="OPEN")
    assert evaluate(ask(ActionType.AUTO_SNOOZE, AI), snap, both).outcome is Outcome.PAUSE_FOR_REVIEW


def test_manual_mode_blocks_automatic_actors_but_not_people() -> None:
    manual = dataclasses.replace(POLICY, mode="MANUAL")
    auto = evaluate(ask(ActionType.CREATE_DRAFT, SYSTEM), StateSnapshot(), manual)
    assert auto.outcome is Outcome.PAUSE_FOR_REVIEW and "G13" in failed(auto)
    assert (
        evaluate(ask(ActionType.CREATE_DRAFT, HUMAN), StateSnapshot(), manual).outcome
        is Outcome.ALLOW_AUTOMATIC
    )


def test_exception_inside_evaluate_denies() -> None:
    # A count that is not a number makes the limit comparison raise inside the engine.
    decision = evaluate(ask(ActionType.SEND_REMINDER), StateSnapshot(contacts_in_window=None), POLICY)  # type: ignore[arg-type]
    assert decision.outcome is Outcome.DENY
    assert decision.reasons == ("POLICY_ENGINE_ERROR",)
    broken = evaluate(ask(ActionType.SEND_REMINDER), None, POLICY)  # type: ignore[arg-type]
    assert broken.outcome is Outcome.DENY


def test_decisions_are_deterministic_and_carry_the_state_version() -> None:
    snap = StateSnapshot(state_version=7)
    a = run(snapshot=snap)
    b = run(snapshot=snap)
    assert a == b
    assert a.state_version == 7 and a.inputs_hash == b.inputs_hash
    other = run(snapshot=StateSnapshot(state_version=7, open_blocker=True))
    assert other.inputs_hash != a.inputs_hash


def test_explain_reads_in_plain_words_and_names_no_internals() -> None:
    decision = run(snapshot=StateSnapshot(dispute_status="OPEN", recipient_suppressed=True))
    lines = explain(decision)
    assert any("dispute" in line.lower() for line in lines)
    assert any("suppress" in line.lower() for line in lines)
    assert not any("Traceback" in line or "G4" in line for line in lines)


@pytest.mark.parametrize("value", [HUMAN, ask(ActionType.SEND_REMINDER), StateSnapshot(), POLICY])
def test_the_inputs_to_a_decision_cannot_be_changed_after_the_fact(value: Any) -> None:
    field = dataclasses.fields(value)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, field, None)


def test_a_decision_cannot_be_edited_after_it_is_made() -> None:
    decision = run()
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.outcome = Outcome.DENY  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.gate_results[0].passed = False  # type: ignore[misc]


def test_defaults_are_the_cautious_ones() -> None:
    assert StateSnapshot().dispute_cooled_off is True
    assert PolicyVersion(version=1, mode="MANUAL").auto_snooze_enabled is False


def test_the_inputs_hash_does_not_depend_on_parameter_order() -> None:
    a = evaluate(ask(ActionType.SEND_REMINDER, x=1, y=2), StateSnapshot(), POLICY)
    b = evaluate(ask(ActionType.SEND_REMINDER, y=2, x=1), StateSnapshot(), POLICY)
    assert a.inputs_hash == b.inputs_hash
