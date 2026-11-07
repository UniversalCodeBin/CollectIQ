"""Gates G1-G15 (PRD §5.3, TSD §13). Each gate is a pure check with a fixed outcome when it fails."""

from collections.abc import Callable
from dataclasses import dataclass

from .model import ActionType, Outcome, PolicyVersion, StateSnapshot

_DEAD_LIFECYCLES = {"CANCELLED", "WRITTEN_OFF", "ARCHIVED"}
_OPEN_PAYMENT = {"OUTSTANDING", "PARTIALLY_PAID"}
_CONTACT_ACTIONS = {ActionType.SEND_REMINDER, ActionType.MARK_SENT, ActionType.APPROVE_DRAFT}
_DRAFT_ACTIONS = _CONTACT_ACTIONS


@dataclass(frozen=True)
class Gate:
    gate: str
    on_fail: Outcome
    reason: str
    applies_to: frozenset[ActionType] | None  # None: every gated action
    check: Callable[[StateSnapshot, PolicyVersion, bool], bool]  # (snapshot, policy, automatic_actor)


def _dispute_clear(s: StateSnapshot, *_: object) -> bool:
    return s.dispute_status == "NONE" or (s.dispute_status == "RESOLVED" and s.dispute_cooled_off)


def _automation_permits(s: StateSnapshot, p: PolicyVersion, automatic: bool) -> bool:
    if p.paused or s.hold_scope or not s.sensitivity_satisfied:
        return False
    return not (automatic and p.mode == "MANUAL")


GATES: tuple[Gate, ...] = (
    Gate("G1", Outcome.CANCEL, "G1_INVOICE_NOT_ACTIVE", None, lambda s, p, a: s.lifecycle == "ACTIVE"),
    Gate("G2", Outcome.CANCEL, "G2_ALREADY_PAID", None, lambda s, p, a: s.payment_status != "PAID_VERIFIED"),
    Gate(
        "G3", Outcome.CANCEL, "G3_INVOICE_CLOSED", None, lambda s, p, a: s.lifecycle not in _DEAD_LIFECYCLES
    ),
    Gate("G4", Outcome.PAUSE_FOR_REVIEW, "G4_DISPUTE", None, lambda s, p, a: _dispute_clear(s)),
    Gate("G5", Outcome.PAUSE_FOR_REVIEW, "G5_OPEN_BLOCKER", None, lambda s, p, a: not s.open_blocker),
    Gate(
        "G6",
        Outcome.PAUSE_FOR_REVIEW,
        "G6_EVIDENCE_NOT_SUPPORTED",
        None,
        lambda s, p, a: s.coverage == "SUPPORTED",
    ),
    Gate(
        "G7",
        Outcome.PAUSE_FOR_REVIEW,
        "G7_PAYMENT_STATUS",
        None,
        lambda s, p, a: s.payment_status in _OPEN_PAYMENT,
    ),
    Gate("G8", Outcome.DEFER, "G8_SNOOZED", None, lambda s, p, a: not s.snooze_active),
    Gate(
        "G9",
        Outcome.PAUSE_FOR_REVIEW,
        "G9_RECIPIENT",
        frozenset(_CONTACT_ACTIONS),
        lambda s, p, a: s.recipient_approved and not s.recipient_suppressed,
    ),
    Gate(
        "G10",
        Outcome.DEFER,
        "G10_CONTACT_LIMIT",
        frozenset(_CONTACT_ACTIONS),
        lambda s, p, a: s.contacts_in_window < p.max_contacts,
    ),
    Gate(
        "G11",
        Outcome.DEFER,
        "G11_OUTSIDE_HOURS",
        frozenset(_CONTACT_ACTIONS),
        lambda s, p, a: s.in_business_hours,
    ),
    Gate(
        "G12",
        Outcome.PAUSE_FOR_REVIEW,
        "G12_DRAFT_FACTS",
        frozenset(_DRAFT_ACTIONS),
        lambda s, p, a: s.draft_facts_valid,
    ),
    Gate("G13", Outcome.PAUSE_FOR_REVIEW, "G13_AUTOMATION", None, _automation_permits),
    Gate(
        "G14",
        Outcome.DENY,
        "G14_ALREADY_USED",
        frozenset({ActionType.SEND_REMINDER, ActionType.MARK_SENT}),
        lambda s, p, a: not s.idempotency_key_used,
    ),
    Gate("G15", Outcome.PAUSE_FOR_REVIEW, "G15_INTEGRATION", None, lambda s, p, a: s.integration_healthy),
)

# Most severe first. A cancelled invoice is not "deferred" just because it was also snoozed.
SEVERITY = (Outcome.CANCEL, Outcome.DENY, Outcome.PAUSE_FOR_REVIEW, Outcome.DEFER)
