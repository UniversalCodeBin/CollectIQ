"""Types of the policy engine. Pure: no database, no clock, no framework (TSD §13)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Outcome(StrEnum):
    ALLOW_AUTOMATIC = "ALLOW_AUTOMATIC"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"
    DEFER = "DEFER"
    PAUSE_FOR_REVIEW = "PAUSE_FOR_REVIEW"
    CANCEL = "CANCEL"


class ActorKind(StrEnum):
    HUMAN = "HUMAN"
    AI = "AI"
    SYSTEM = "SYSTEM"


# INV-13: there is no AUTO_SEND, MARK_PAID or AUTO_ALLOCATE member, and there must never be one.
class ActionType(StrEnum):
    PROTECTIVE_SUPPRESS = "PROTECTIVE_SUPPRESS"
    CREATE_CASE = "CREATE_CASE"
    CREATE_DRAFT = "CREATE_DRAFT"
    AUTO_SNOOZE = "AUTO_SNOOZE"
    APPROVE_DRAFT = "APPROVE_DRAFT"
    SEND_REMINDER = "SEND_REMINDER"
    MARK_SENT = "MARK_SENT"
    RESUME_FOLLOWUPS = "RESUME_FOLLOWUPS"
    CONFIRM_ALLOCATION = "CONFIRM_ALLOCATION"
    REVERSE_ALLOCATION = "REVERSE_ALLOCATION"
    CHANGE_STATUS = "CHANGE_STATUS"
    CHANGE_RECIPIENT = "CHANGE_RECIPIENT"
    RESOLVE_CASE = "RESOLVE_CASE"
    CHANGE_POLICY = "CHANGE_POLICY"
    CHANGE_INTEGRATION = "CHANGE_INTEGRATION"
    EXPORT = "EXPORT"
    DELETE = "DELETE"


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    user_id: str | None
    role: str | None


@dataclass(frozen=True)
class ActionRequest:
    action: Any
    actor: Actor
    subject: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StateSnapshot:
    """What the caller read, under the invoice lock, about the subject. Defaults: a healthy invoice."""

    lifecycle: str = "ACTIVE"
    payment_status: str = "OUTSTANDING"
    dispute_status: str = "NONE"
    dispute_cooled_off: bool = True
    open_blocker: bool = False
    coverage: str = "SUPPORTED"
    snooze_active: bool = False
    hold_scope: str | None = None  # "CLIENT" or "INVOICE" when a person paused reminders for it
    recipient_approved: bool = True
    recipient_suppressed: bool = False
    contacts_in_window: int = 0
    in_business_hours: bool = True
    draft_facts_valid: bool = True
    idempotency_key_used: bool = False
    integration_healthy: bool = True
    sensitivity_satisfied: bool = True
    injection_flag: bool = False
    ai_confidence: str | None = None
    state_version: int = 1


@dataclass(frozen=True)
class PolicyVersion:
    version: int
    mode: str = "MANUAL"
    paused: bool = False
    auto_snooze_enabled: bool = False
    auto_snooze_available: bool = False
    max_contacts: int = 3


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    reason: str | None = None


@dataclass(frozen=True)
class PolicyDecision:
    outcome: Outcome
    gate_results: tuple[GateResult, ...]
    reasons: tuple[str, ...]
    rules_version: str
    policy_version: int
    state_version: int
    inputs_hash: str
    expires_at: datetime | None = None
