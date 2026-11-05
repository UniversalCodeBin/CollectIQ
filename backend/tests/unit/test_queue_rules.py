"""BR-40 tiers and BR-41 actions as a table. The queue is rules over state, never a score."""

from dataclasses import fields
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from collectiq.invoices.domain.queue import (
    ACTIONS,
    QueueFacts,
    aging_bucket,
    due_bucket,
    effective_coverage,
    exception_order,
    queue_entry,
)

TODAY = date(2026, 7, 15)
NOW = datetime(2026, 7, 15, 6, 0, tzinfo=UTC)
FRESH = NOW - timedelta(days=1)
OLD = NOW - timedelta(days=8)


def _facts(**changes: Any) -> QueueFacts:
    values: dict[str, Any] = {
        "invoice_id": "11111111-1111-1111-1111-111111111111",
        "status": "ACTIVE",
        "payment_status": "OUTSTANDING",
        "coverage_as_of": FRESH,
        "dispute_status": "NONE",
        "reminder_status": "NOT_CONTACTED",
        "snooze_until": None,
        "due_date": date(2026, 8, 1),
        "outstanding_minor": 1000,
        "overpayment": False,
    }
    return QueueFacts(**{**values, **changes})


OVERDUE = date(2026, 7, 1)


@pytest.mark.parametrize(
    ("changes", "tier", "action", "reason"),
    [
        ({"payment_status": "AWAITING_VERIFICATION"}, 1, "VERIFY_PAYMENT", "PAYMENT_CLAIMED"),
        (
            {"payment_status": "AWAITING_VERIFICATION", "match_candidates": 1},
            1,
            "REVIEW_MATCH",
            "PAYMENT_CLAIMED",
        ),
        ({"payment_status": "UNCERTAIN"}, 1, "REVIEW_MATCH", "PAYMENT_UNCERTAIN"),
        ({"payment_status": "UNCERTAIN", "match_candidates": 2}, 1, "REVIEW_MATCH", "POSSIBLE_MATCHES"),
        ({"coverage_as_of": OLD, "due_date": OVERDUE}, 1, "VERIFY_PAYMENT", "EVIDENCE_STALE"),
        ({"coverage_as_of": OLD, "due_date": TODAY}, 1, "VERIFY_PAYMENT", "EVIDENCE_STALE"),
        ({"coverage_as_of": None, "due_date": OVERDUE}, 1, "VERIFY_PAYMENT", "EVIDENCE_MISSING"),
        ({"dispute_status": "OPEN"}, 1, "REVIEW_DISPUTE", "DISPUTE_OPEN"),
        ({"dispute_status": "IN_REVIEW"}, 1, "REVIEW_DISPUTE", "DISPUTE_OPEN"),
        ({"dispute_status": "AWAITING_CUSTOMER"}, 1, "REVIEW_DISPUTE", "DISPUTE_OPEN"),
        ({"association_pending": True}, 1, "CONFIRM_ASSOCIATION", "ASSOCIATION_PENDING"),
        ({"classification_pending": True}, 1, "REVIEW_CLASSIFICATION", "CLASSIFICATION_PENDING"),
        ({"status": "PENDING_REVIEW"}, 1, "REVIEW_CLASSIFICATION", "INVOICE_PENDING_REVIEW"),
        ({"snooze_proposed": True}, 1, "APPROVE_SNOOZE", "SNOOZE_PROPOSED"),
        ({"reminder_status": "NEEDS_REVIEW"}, 1, "REVIEW_CLASSIFICATION", "REMINDER_NEEDS_REVIEW"),
        ({"reminder_status": "DRAFT_READY"}, 2, "APPROVE_DRAFT", "DRAFT_READY"),
        ({"due_date": OVERDUE}, 3, "CONTACT_MANUALLY", "OVERDUE"),
        (
            {"reminder_status": "SNOOZED", "snooze_until": TODAY, "due_date": OVERDUE},
            4,
            "RESUME_FOLLOWUPS",
            "SNOOZE_ENDED",
        ),
        ({"dispute_status": "RESOLVED"}, 4, "RESUME_FOLLOWUPS", "DISPUTE_RESOLVED"),
        ({"payment_status": "PARTIALLY_PAID"}, 5, "WAIT", "PARTLY_PAID"),
        ({"overpayment": True}, 5, "WAIT", "POSSIBLE_OVERPAYMENT"),
        ({"coverage_as_of": OLD}, 5, "VERIFY_PAYMENT", "EVIDENCE_STALE"),
        ({"reminder_status": "SCHEDULED", "due_date": OVERDUE}, 5, "WAIT", "REMINDER_SCHEDULED"),
        ({"reminder_status": "WAITING_FOR_CUSTOMER", "due_date": OVERDUE}, 5, "WAIT", "WAITING_FOR_CUSTOMER"),
    ],
)
def test_each_rule_gives_its_tier_action_and_reason(
    changes: dict[str, Any], tier: int, action: str, reason: str
) -> None:
    entry = queue_entry(_facts(**changes), TODAY, NOW)
    assert (entry.tier, entry.action) == (tier, action)
    assert entry.reasons[0].code == reason


def test_a_first_rule_wins_when_several_apply_and_every_reason_is_listed() -> None:
    entry = queue_entry(
        _facts(payment_status="UNCERTAIN", dispute_status="OPEN", due_date=OVERDUE), TODAY, NOW
    )
    assert entry.action == "REVIEW_MATCH"
    assert {reason.code for reason in entry.reasons} >= {"PAYMENT_UNCERTAIN", "DISPUTE_OPEN", "OVERDUE"}


@pytest.mark.parametrize(
    "changes",
    [
        {"payment_status": "PAID_VERIFIED", "outstanding_minor": 0},
        {"status": "CANCELLED"},
        {"status": "WRITTEN_OFF"},
        {"status": "ARCHIVED"},
    ],
)
def test_finished_invoices_are_not_in_the_queue_and_say_why(changes: dict[str, Any]) -> None:
    entry = queue_entry(_facts(due_date=OVERDUE, **changes), TODAY, NOW)
    assert entry.tier is None
    assert entry.action is None
    assert entry.why_not


def test_an_invoice_with_nothing_to_do_is_not_in_the_queue() -> None:
    entry = queue_entry(_facts(), TODAY, NOW)
    assert (entry.tier, entry.action, entry.reasons) == (None, None, ())


def test_a_snooze_still_running_keeps_an_overdue_invoice_out_and_explains() -> None:
    entry = queue_entry(
        _facts(reminder_status="SNOOZED", snooze_until=date(2026, 7, 20), due_date=OVERDUE), TODAY, NOW
    )
    assert (entry.tier, entry.action) == (None, "WAIT")
    assert [item.code for item in entry.why_not] == ["SNOOZED"]
    assert "2026-07-20" in entry.why_not[0].label


def test_a_snooze_does_not_hide_a_decision_the_owner_must_make() -> None:
    entry = queue_entry(
        _facts(reminder_status="SNOOZED", snooze_until=date(2026, 7, 20), dispute_status="OPEN"), TODAY, NOW
    )
    assert (entry.tier, entry.action) == (1, "REVIEW_DISPUTE")


def test_an_open_dispute_says_why_follow_ups_are_held() -> None:
    entry = queue_entry(_facts(dispute_status="OPEN", due_date=OVERDUE), TODAY, NOW)
    assert "FOLLOW_UPS_HELD_BY_DISPUTE" in {item.code for item in entry.why_not}


def test_a_suppressed_contact_is_named_as_the_blocking_rule() -> None:
    entry = queue_entry(_facts(reminder_status="SUPPRESSED", due_date=OVERDUE), TODAY, NOW)
    assert entry.action == "CONTACT_MANUALLY"
    assert "CONTACT_SUPPRESSED" in {item.code for item in entry.why_not}


def test_every_queued_row_has_a_reason_with_a_link_and_an_action_from_the_fixed_list() -> None:
    combinations = [
        _facts(
            payment_status=payment,
            dispute_status=dispute,
            reminder_status=reminder,
            due_date=due,
            coverage_as_of=seen,
        )
        for payment in (
            "OUTSTANDING",
            "PARTIALLY_PAID",
            "AWAITING_VERIFICATION",
            "UNCERTAIN",
            "PAID_VERIFIED",
        )
        for dispute in ("NONE", "OPEN", "IN_REVIEW", "AWAITING_CUSTOMER", "RESOLVED")
        for reminder in ("NOT_CONTACTED", "DRAFT_READY", "SCHEDULED", "SNOOZED", "SUPPRESSED", "RESOLVED")
        for due in (OVERDUE, TODAY, date(2026, 8, 1))
        for seen in (FRESH, OLD, None)
    ]
    queued = 0
    for facts in combinations:
        entry = queue_entry(facts, TODAY, NOW)
        if entry.tier is None:
            continue
        queued += 1
        assert entry.reasons, facts
        assert entry.action in ACTIONS, facts
        assert all(reason.label and "#" in reason.link for reason in entry.reasons)
    assert queued > 500


def test_no_field_of_the_entry_is_a_score() -> None:
    entry = queue_entry(_facts(due_date=OVERDUE), TODAY, NOW)
    names = {field.name for field in fields(entry)}
    assert not {
        name for name in names if any(word in name for word in ("risk", "score", "probab", "confidence"))
    }


def test_actions_are_exactly_the_fixed_enumeration() -> None:
    assert set(ACTIONS) == {
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
    }


def test_exception_order_is_tier_then_most_overdue_then_largest() -> None:
    assert exception_order(1, 5, 100) < exception_order(2, 90, 900)
    assert exception_order(3, 30, 100) < exception_order(3, 5, 900)
    assert exception_order(3, 5, 900) < exception_order(3, 5, 100)


@pytest.mark.parametrize(
    ("as_of", "expected"),
    [
        (None, "MISSING"),
        (NOW - timedelta(days=7), "SUPPORTED"),
        (NOW - timedelta(days=7, seconds=1), "STALE"),
        (NOW, "SUPPORTED"),
    ],
)
def test_coverage_is_judged_against_the_freshness_window(as_of: datetime | None, expected: str) -> None:
    assert effective_coverage(as_of, NOW, 7) == expected


@pytest.mark.parametrize(
    ("due", "bucket", "aging"),
    [
        (date(2026, 7, 16), "UPCOMING", "not_due"),
        (TODAY, "DUE_TODAY", "not_due"),
        (date(2026, 7, 14), "OVERDUE", "1-30"),
        (date(2026, 6, 15), "OVERDUE", "1-30"),
        (date(2026, 6, 14), "OVERDUE", "31-60"),
        (date(2026, 5, 16), "OVERDUE", "31-60"),
        (date(2026, 5, 15), "OVERDUE", "61-90"),
        (date(2026, 4, 16), "OVERDUE", "61-90"),
        (date(2026, 4, 15), "OVERDUE", "90+"),
    ],
)
def test_due_date_buckets_and_aging_edges(due: date, bucket: str, aging: str) -> None:
    assert due_bucket(due, TODAY) == bucket
    assert aging_bucket(due, TODAY) == aging
