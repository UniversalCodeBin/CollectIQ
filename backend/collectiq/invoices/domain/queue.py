"""Why an invoice needs attention and what to do next (BR-40, BR-41). Rules over state, never a score."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

ACTIONS = (
    "VERIFY_PAYMENT",
    "REVIEW_MATCH",
    "CONFIRM_ASSOCIATION",
    "REVIEW_CLASSIFICATION",
    "REVIEW_DISPUTE",
    "APPROVE_DRAFT",
    "APPROVE_SNOOZE",
    "RESUME_FOLLOWUPS",
    "WAIT",
    "CONTACT_MANUALLY",
)
ACTION_LABELS = {
    "VERIFY_PAYMENT": "Check whether this was paid",
    "REVIEW_MATCH": "Review the possible payment match",
    "CONFIRM_ASSOCIATION": "Confirm which invoice this belongs to",
    "REVIEW_CLASSIFICATION": "Review what needs classifying",
    "REVIEW_DISPUTE": "Review the dispute",
    "APPROVE_DRAFT": "Approve the reminder draft",
    "APPROVE_SNOOZE": "Approve the request for more time",
    "RESUME_FOLLOWUPS": "Resume follow-ups",
    "WAIT": "Nothing to do yet",
    "CONTACT_MANUALLY": "Contact the client",
}
OPEN_DISPUTES = frozenset({"OPEN", "IN_REVIEW", "AWAITING_CUSTOMER"})
ENDED_STATUSES = frozenset({"CANCELLED", "WRITTEN_OFF", "ARCHIVED"})
DEFAULT_FRESHNESS_DAYS = 7
DUE_SOON_DAYS = 7
AGING_BUCKETS = ("not_due", "1-30", "31-60", "61-90", "90+")
TILES = ("outstanding", "overdue", "due_soon", "partially_paid", "needs_verification", "disputed", "snoozed")
_ENDED_WHY = {
    "CANCELLED": ("INVOICE_CANCELLED", "This invoice was cancelled."),
    "WRITTEN_OFF": ("INVOICE_WRITTEN_OFF", "This invoice was written off."),
    "ARCHIVED": ("INVOICE_ARCHIVED", "This invoice was archived."),
}
_EVIDENCE, _DISPUTE, _FOLLOW_UPS, _FACTS = "payment-evidence", "dispute", "follow-ups", "facts"


@dataclass(frozen=True, slots=True)
class QueueFacts:
    invoice_id: str
    status: str
    payment_status: str
    coverage_as_of: datetime | None
    dispute_status: str
    reminder_status: str
    snooze_until: date | None
    due_date: date
    outstanding_minor: int
    overpayment: bool
    match_candidates: int = 0
    association_pending: bool = False
    classification_pending: bool = False
    snooze_proposed: bool = False


@dataclass(frozen=True, slots=True)
class Reason:
    code: str
    label: str
    link: str


@dataclass(frozen=True, slots=True)
class WhyNot:
    code: str
    label: str


@dataclass(frozen=True, slots=True)
class QueueEntry:
    tier: int | None
    action: str | None
    reasons: tuple[Reason, ...]
    why_not: tuple[WhyNot, ...]
    coverage: str
    days_overdue: int
    due_bucket: str
    aging: str


def effective_coverage(as_of: datetime | None, now: datetime, freshness_days: int) -> str:
    """SAD 6.8: judged when read, because time alone makes evidence stale."""
    if as_of is None:
        return "MISSING"
    return "SUPPORTED" if now - as_of <= timedelta(days=freshness_days) else "STALE"


def due_bucket(due: date, today: date) -> str:
    if due > today:
        return "UPCOMING"
    return "DUE_TODAY" if due == today else "OVERDUE"


def aging_bucket(due: date, today: date) -> str:
    days = (today - due).days
    if days <= 0:
        return "not_due"
    if days <= 30:
        return "1-30"
    if days <= 60:
        return "31-60"
    return "61-90" if days <= 90 else "90+"


def exception_order(tier: int | None, days_overdue: int, outstanding_minor: int) -> tuple[int, int, int]:
    """FR-022. The invoice id is the caller's last tiebreak. Amounts compare within one currency's sort."""
    return (tier if tier is not None else 9, -days_overdue, -outstanding_minor)


def _decision_rules(facts: QueueFacts, coverage: str, today: date) -> list[tuple[int, str, str, str, str]]:
    """Rows of (tier, action, code, label, anchor) in BR-41 order. The first decides; all are shown."""
    rules: list[tuple[int, str, str, str, str]] = []
    due_or_late = facts.due_date <= today
    if facts.payment_status == "AWAITING_VERIFICATION":
        action = "REVIEW_MATCH" if facts.match_candidates > 0 else "VERIFY_PAYMENT"
        rules.append((1, action, "PAYMENT_CLAIMED", "Customer claims payment: unverified", _EVIDENCE))
    if facts.payment_status == "UNCERTAIN":
        if facts.match_candidates >= 2:
            rules.append(
                (1, "REVIEW_MATCH", "POSSIBLE_MATCHES", "Two or more possible bank matches", _EVIDENCE)
            )
        else:
            rules.append((1, "REVIEW_MATCH", "PAYMENT_UNCERTAIN", "Payment evidence is uncertain", _EVIDENCE))
    if due_or_late and coverage == "STALE":
        rules.append((1, "VERIFY_PAYMENT", "EVIDENCE_STALE", "Evidence stale", _EVIDENCE))
    if due_or_late and coverage == "MISSING":
        rules.append((1, "VERIFY_PAYMENT", "EVIDENCE_MISSING", "No payment evidence yet", _EVIDENCE))
    if facts.dispute_status in OPEN_DISPUTES:
        rules.append((1, "REVIEW_DISPUTE", "DISPUTE_OPEN", "Dispute open", _DISPUTE))
    if facts.association_pending:
        rules.append(
            (
                1,
                "CONFIRM_ASSOCIATION",
                "ASSOCIATION_PENDING",
                "A message needs linking to an invoice",
                _FOLLOW_UPS,
            )
        )
    if facts.classification_pending:
        rules.append(
            (1, "REVIEW_CLASSIFICATION", "CLASSIFICATION_PENDING", "A reply needs classifying", _FOLLOW_UPS)
        )
    if facts.status == "PENDING_REVIEW":
        rules.append(
            (1, "REVIEW_CLASSIFICATION", "INVOICE_PENDING_REVIEW", "This invoice needs review", _FACTS)
        )
    if facts.reminder_status == "NEEDS_REVIEW":
        rules.append(
            (1, "REVIEW_CLASSIFICATION", "REMINDER_NEEDS_REVIEW", "A follow-up needs review", _FOLLOW_UPS)
        )
    if facts.snooze_proposed:
        rules.append(
            (
                1,
                "APPROVE_SNOOZE",
                "SNOOZE_PROPOSED",
                "Customer asked for more time: needs approval",
                _FOLLOW_UPS,
            )
        )
    if facts.reminder_status == "DRAFT_READY":
        rules.append((2, "APPROVE_DRAFT", "DRAFT_READY", "A reminder draft is ready", _FOLLOW_UPS))
    if facts.dispute_status == "RESOLVED":
        rules.append((4, "RESUME_FOLLOWUPS", "DISPUTE_RESOLVED", "The dispute was resolved", _DISPUTE))
    if facts.reminder_status == "SNOOZED" and facts.snooze_until is not None and facts.snooze_until <= today:
        rules.append((4, "RESUME_FOLLOWUPS", "SNOOZE_ENDED", "The snooze has ended", _FOLLOW_UPS))
    return rules


def _waiting_rules(facts: QueueFacts, coverage: str, today: date) -> list[tuple[int, str, str, str, str]]:
    """What applies only when no decision is waiting: overdue and informational rows."""
    rules: list[tuple[int, str, str, str, str]] = []
    if facts.due_date < today:
        if facts.reminder_status == "SCHEDULED":
            rules.append((5, "WAIT", "REMINDER_SCHEDULED", "A reminder is scheduled", _FOLLOW_UPS))
        elif facts.reminder_status == "WAITING_FOR_CUSTOMER":
            rules.append(
                (5, "WAIT", "WAITING_FOR_CUSTOMER", "Waiting for the customer to reply", _FOLLOW_UPS)
            )
        else:
            rules.append((3, "CONTACT_MANUALLY", "OVERDUE", "Overdue", _FOLLOW_UPS))
    if facts.due_date > today and coverage == "STALE":
        rules.append((5, "VERIFY_PAYMENT", "EVIDENCE_STALE", "Evidence stale", _EVIDENCE))
    if facts.payment_status == "PARTIALLY_PAID":
        rules.append((5, "WAIT", "PARTLY_PAID", "Partly paid", _EVIDENCE))
    if facts.overpayment:
        rules.append((5, "WAIT", "POSSIBLE_OVERPAYMENT", "Possible overpayment", _EVIDENCE))
    return rules


def _why_not(facts: QueueFacts) -> list[WhyNot]:
    items: list[WhyNot] = []
    if facts.dispute_status in OPEN_DISPUTES:
        items.append(WhyNot("FOLLOW_UPS_HELD_BY_DISPUTE", "Follow-ups are paused while a dispute is open."))
    if facts.reminder_status == "SUPPRESSED":
        items.append(WhyNot("CONTACT_SUPPRESSED", "Reminders are off because the contact is suppressed."))
    return items


def _snooze_label(until: date | None) -> str:
    return f"Follow-ups are snoozed until {until.isoformat()}." if until else "Follow-ups are snoozed."


def queue_entry(
    facts: QueueFacts, today: date, now: datetime, freshness_days: int = DEFAULT_FRESHNESS_DAYS
) -> QueueEntry:
    coverage = effective_coverage(facts.coverage_as_of, now, freshness_days)
    overdue = max(0, (today - facts.due_date).days)
    bucket, aging = due_bucket(facts.due_date, today), aging_bucket(facts.due_date, today)

    def entry(
        tier: int | None, action: str | None, reasons: tuple[Reason, ...], why_not: tuple[WhyNot, ...]
    ) -> QueueEntry:
        return QueueEntry(tier, action, reasons, why_not, coverage, overdue, bucket, aging)

    if facts.status in ENDED_STATUSES:
        return entry(None, None, (), (WhyNot(*_ENDED_WHY[facts.status]),))
    if facts.payment_status == "PAID_VERIFIED":
        return entry(None, None, (), (WhyNot("PAID_VERIFIED", "Payment on this invoice is verified."),))

    decisions = _decision_rules(facts, coverage, today)
    waiting = _waiting_rules(facts, coverage, today)
    why_not = _why_not(facts)
    running_snooze = facts.reminder_status == "SNOOZED" and (
        facts.snooze_until is None or facts.snooze_until > today
    )
    if running_snooze:
        why_not.insert(0, WhyNot("SNOOZED", _snooze_label(facts.snooze_until)))
        if not decisions:
            return entry(None, "WAIT", (), tuple(why_not))
    # Every reason is listed under the row, including those that do not decide its action.
    rules = decisions if running_snooze else decisions + waiting
    if not rules:
        return entry(None, None, (), tuple(why_not))
    first = rules[0]
    seen: dict[str, Reason] = {}
    for _tier, _action, code, label, anchor in rules:
        seen.setdefault(code, Reason(code, label, f"/invoices/{facts.invoice_id}#{anchor}"))
    return entry(first[0], first[1], tuple(seen.values()), tuple(why_not))


def is_open(status: str, payment_status: str) -> bool:
    """Counted as money still owed: active, and not verified paid."""
    return status == "ACTIVE" and payment_status != "PAID_VERIFIED"


def tile_matches(
    tile: str,
    status: str,
    payment_status: str,
    dispute_status: str,
    reminder_status: str,
    due: date,
    today: date,
) -> bool:
    """One definition per tile, so a tile's count is always what its filter lists (FR-019)."""
    if not is_open(status, payment_status):
        return False
    if tile == "outstanding":
        return True
    if tile == "overdue":
        return due < today
    if tile == "due_soon":
        return today <= due <= today + timedelta(days=DUE_SOON_DAYS)
    if tile == "partially_paid":
        return payment_status == "PARTIALLY_PAID"
    if tile == "needs_verification":
        return payment_status in {"AWAITING_VERIFICATION", "UNCERTAIN"}
    if tile == "disputed":
        return dispute_status in OPEN_DISPUTES
    if tile == "snoozed":
        return reminder_status == "SNOOZED"
    raise ValueError(tile)
