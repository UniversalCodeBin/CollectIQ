"""evaluate(): authorization -> pause -> gates -> action rules -> approval. Any exception denies (TSD §13)."""

import hashlib
import json
from dataclasses import asdict

from .gates import GATES, SEVERITY
from .model import (
    ActionRequest,
    ActionType,
    Actor,
    ActorKind,
    GateResult,
    Outcome,
    PolicyDecision,
    PolicyVersion,
    StateSnapshot,
)

# Only a person can do these. An AI or system origin is refused, whatever the snapshot says.
HUMAN_ONLY = frozenset(
    {
        ActionType.CONFIRM_ALLOCATION,
        ActionType.REVERSE_ALLOCATION,
        ActionType.CHANGE_STATUS,
        ActionType.CHANGE_RECIPIENT,
        ActionType.RESOLVE_CASE,
        ActionType.CHANGE_POLICY,
        ActionType.CHANGE_INTEGRATION,
        ActionType.EXPORT,
        ActionType.DELETE,
    }
)
_HUMAN_ROLES = {"OWNER", "FINANCE_ADMIN"}
# Never gated: they only make things safer or add work for a person.
PROTECTIVE = frozenset({ActionType.PROTECTIVE_SUPPRESS, ActionType.CREATE_CASE})
APPROVAL_REQUIRED = frozenset(
    {ActionType.APPROVE_DRAFT, ActionType.SEND_REMINDER, ActionType.MARK_SENT, ActionType.RESUME_FOLLOWUPS}
)
_AI_ACTORS = {ActorKind.AI, ActorKind.SYSTEM}

# Bump on any change to gates or rules; every decision records it.
RULES_VERSION = hashlib.sha256(
    json.dumps(
        {
            "gates": [(g.gate, g.on_fail.value, g.reason) for g in GATES],
            "human_only": sorted(a.value for a in HUMAN_ONLY),
            "approval": sorted(a.value for a in APPROVAL_REQUIRED),
            "protective": sorted(a.value for a in PROTECTIVE),
        },
        sort_keys=True,
    ).encode()
).hexdigest()[:12]


def _inputs_hash(req: ActionRequest, snap: StateSnapshot, policy: PolicyVersion) -> str:
    body = {
        "action": str(req.action),
        "actor": [req.actor.kind.value, req.actor.user_id, req.actor.role],
        "subject": req.subject,
        "params": dict(req.params),
        "snapshot": asdict(snap),
        "policy": asdict(policy),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def _decision(
    outcome: Outcome,
    reasons: list[str],
    gates: list[GateResult],
    req: ActionRequest,
    snap: StateSnapshot,
    policy: PolicyVersion,
) -> PolicyDecision:
    return PolicyDecision(
        outcome=outcome,
        gate_results=tuple(gates),
        reasons=tuple(reasons),
        rules_version=RULES_VERSION,
        policy_version=policy.version,
        state_version=snap.state_version,
        inputs_hash=_inputs_hash(req, snap, policy),
    )


def _deny(reason: str, req: ActionRequest, snap: StateSnapshot, policy: PolicyVersion) -> PolicyDecision:
    return _decision(Outcome.DENY, [reason], [], req, snap, policy)


def _failsafe(req: ActionRequest, snap: object, policy: PolicyVersion) -> PolicyDecision:
    version = getattr(snap, "state_version", 0)
    return PolicyDecision(
        Outcome.DENY,
        (),
        ("POLICY_ENGINE_ERROR",),
        RULES_VERSION,
        getattr(policy, "version", 0),
        version if isinstance(version, int) else 0,
        "",
    )


fail_closed = _failsafe


def _authorized(actor: Actor) -> bool:
    if actor.kind is ActorKind.HUMAN:
        return bool(actor.user_id)
    return actor.kind in _AI_ACTORS


def _run_gates(
    action: ActionType, snap: StateSnapshot, policy: PolicyVersion, automatic: bool
) -> list[GateResult]:
    results = []
    for gate in GATES:
        applies = gate.applies_to is None or action in gate.applies_to
        ok = (not applies) or gate.check(snap, policy, automatic)
        results.append(GateResult(gate.gate, ok, None if ok else gate.reason))
    return results


def _worst(gates: list[GateResult]) -> Outcome | None:
    failing = {g.gate for g in gates if not g.passed}
    hit = {gate.on_fail for gate in GATES if gate.gate in failing}
    return next((o for o in SEVERITY if o in hit), None)


def evaluate(req: ActionRequest, snap: StateSnapshot, policy: PolicyVersion) -> PolicyDecision:
    try:
        return _evaluate(req, snap, policy)
    except Exception:  # fail closed: a bug in a rule must never allow an action
        return _failsafe(req, snap, policy)


def _evaluate(req: ActionRequest, snap: StateSnapshot, policy: PolicyVersion) -> PolicyDecision:
    try:
        action = ActionType(req.action)
    except ValueError:
        return _deny("FORBIDDEN_ACTION", req, snap, policy)
    if not _authorized(req.actor):
        return _deny("HUMAN_ONLY_ACTOR_UNKNOWN", req, snap, policy)
    automatic = req.actor.kind in _AI_ACTORS

    if action in HUMAN_ONLY:
        if automatic or req.actor.role not in _HUMAN_ROLES:
            return _deny("HUMAN_ONLY", req, snap, policy)
        return _decision(Outcome.ALLOW_AUTOMATIC, [], [], req, snap, policy)

    if action in PROTECTIVE:
        return _decision(Outcome.ALLOW_AUTOMATIC, [], [], req, snap, policy)

    gates = _run_gates(action, snap, policy, automatic)
    reasons = [g.reason for g in gates if not g.passed and g.reason]
    worst = _worst(gates)
    if worst is not None:
        return _decision(worst, reasons, gates, req, snap, policy)

    if action is ActionType.AUTO_SNOOZE:
        if snap.injection_flag:
            return _decision(Outcome.DENY, ["INJECTION_SUSPECTED"], gates, req, snap, policy)
        if not (policy.auto_snooze_enabled and policy.auto_snooze_available):
            return _decision(Outcome.REQUIRE_APPROVAL, ["APPROVAL_REQUIRED"], gates, req, snap, policy)
        if snap.ai_confidence != "HIGH":
            return _decision(Outcome.REQUIRE_APPROVAL, ["AI_CONFIDENCE_TOO_LOW"], gates, req, snap, policy)
        return _decision(Outcome.ALLOW_AUTOMATIC, [], gates, req, snap, policy)

    if action in APPROVAL_REQUIRED:
        return _decision(Outcome.REQUIRE_APPROVAL, ["APPROVAL_REQUIRED"], gates, req, snap, policy)
    return _decision(Outcome.ALLOW_AUTOMATIC, [], gates, req, snap, policy)
