"""A date hint from a reply becomes a date only when it can mean one thing. Otherwise a person decides."""

from datetime import UTC, date, datetime

import pytest

from collectiq.ai.date_resolver import Ambiguous, BusinessCalendar, ResolvedDate, resolve_date


def at(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


def ok(hint, received, tz="UTC", cal=None):
    out = resolve_date(hint, received, tz, cal)
    assert isinstance(out, ResolvedDate), out
    return out.date


def amb(hint, received, tz="UTC"):
    out = resolve_date(hint, received, tz)
    assert isinstance(out, Ambiguous), out
    return out.reason


def test_the_15th_from_3_nov_is_15_nov():
    assert ok("the 15th", at(2026, 11, 3)) == date(2026, 11, 15)


def test_the_15th_from_20_nov_is_ambiguous():
    assert amb("the 15th", at(2026, 11, 20))


def test_the_31st_in_a_30_day_month_is_ambiguous():
    assert amb("the 31st", at(2026, 11, 3))


def test_31st_of_february_is_ambiguous():
    assert amb("31 February", at(2026, 1, 3))
    assert amb("February 31", at(2026, 1, 3))


def test_leap_day():
    assert ok("29 Feb", at(2028, 1, 3)) == date(2028, 2, 29)
    assert amb("29 Feb", at(2027, 1, 3))


@pytest.mark.parametrize(
    "hint,expected",
    [
        ("15 Nov", date(2026, 11, 15)),
        ("Nov 15", date(2026, 11, 15)),
        ("15th of November", date(2026, 11, 15)),
        ("November 15, 2026", date(2026, 11, 15)),
        ("2026-11-20", date(2026, 11, 20)),
        ("tomorrow", date(2026, 11, 4)),
        ("today", date(2026, 11, 3)),
        ("in 3 days", date(2026, 11, 6)),
        ("in 2 weeks", date(2026, 11, 17)),
        ("end of the month", date(2026, 11, 30)),
        ("end of next month", date(2026, 12, 31)),
        ("by Friday", date(2026, 11, 6)),
        ("friday", date(2026, 11, 6)),
        ("next monday", date(2026, 11, 9)),
        ("  THE 15TH ", date(2026, 11, 15)),
        ("the 3rd", date(2026, 11, 3)),
    ],
)
def test_grammar(hint, expected):
    assert ok(hint, at(2026, 11, 3)) == expected  # 3 Nov 2026 is a Tuesday


def test_named_month_rolls_into_next_year_when_near():
    assert ok("15 Jan", at(2026, 12, 20)) == date(2027, 1, 15)


def test_named_month_in_the_recent_past_is_ambiguous():
    assert amb("15 Nov", at(2026, 11, 20))


def test_explicit_past_year_is_ambiguous():
    assert amb("2025-01-01", at(2026, 11, 3))
    assert amb("yesterday", at(2026, 11, 3))


def test_bare_weekday_on_that_weekday_is_ambiguous():
    assert amb("friday", at(2026, 11, 6))


def test_next_weekday_still_ahead_this_week_is_ambiguous():
    assert amb("next friday", at(2026, 11, 3))
    assert ok("next friday", at(2026, 11, 8)) == date(2026, 11, 13)  # Sunday: this week's Friday has passed


def test_local_date_decides_not_utc():
    # 23:30 UTC on 4 Nov is already 5 Nov in Auckland, so "tomorrow" is 6 Nov there.
    assert ok("tomorrow", at(2026, 11, 4, 23, 30), "Pacific/Auckland") == date(2026, 11, 6)
    assert ok("tomorrow", at(2026, 11, 4, 23, 30), "UTC") == date(2026, 11, 5)
    # 03:00 UTC on 4 Nov is still 3 Nov in Los Angeles.
    assert ok("today", at(2026, 11, 4, 3, 0), "America/Los_Angeles") == date(2026, 11, 3)


def test_dst_change_does_not_shift_the_day():
    # US clocks go back on 1 Nov 2026; adding days works on dates, not hours.
    assert ok("in 3 days", at(2026, 10, 30, 5, 0), "America/New_York") == date(2026, 11, 2)
    assert ok("in 1 week", at(2026, 3, 4, 12), "America/New_York") == date(2026, 3, 11)


def test_unknown_timezone_is_ambiguous_not_a_crash():
    assert isinstance(resolve_date("tomorrow", at(2026, 11, 3), "Mars/Base", None), Ambiguous)


def test_naive_received_at_is_treated_as_utc():
    assert ok("tomorrow", datetime(2026, 11, 3, 12)) == date(2026, 11, 4)


@pytest.mark.parametrize(
    "hint", ["", "   ", "soon", "when I can", "03/04", "some day", "next", "31st of never"]
)
def test_unreadable_hints_are_ambiguous(hint):
    assert amb(hint, at(2026, 11, 3))


def test_hint_that_is_not_text_is_ambiguous():
    assert isinstance(resolve_date(None, at(2026, 11, 3), "UTC", None), Ambiguous)  # type: ignore[arg-type]


def test_huge_offsets_are_ambiguous():
    assert amb("in 9999 days", at(2026, 11, 3))
    assert amb("in 0 days", at(2026, 11, 3))


def test_business_days_use_the_calendar():
    cal = BusinessCalendar(holidays=frozenset({date(2026, 11, 5)}))
    # Tue 3 Nov + 2 business days, skipping the Thursday holiday: Wed 4 (1), Fri 6 (2)
    assert ok("in 2 business days", at(2026, 11, 3), "UTC", cal) == date(2026, 11, 6)
    assert ok("in 2 business days", at(2026, 11, 3), "UTC", None) == date(2026, 11, 5)


def test_result_reports_whether_it_is_a_business_day():
    cal = BusinessCalendar(holidays=frozenset({date(2026, 11, 30)}))
    out = resolve_date("end of the month", at(2026, 11, 3), "UTC", cal)
    assert isinstance(out, ResolvedDate) and out.business_day is False
    out = resolve_date("the 15th", at(2026, 11, 3), "UTC", cal)
    assert isinstance(out, ResolvedDate) and out.business_day is False  # a Sunday
    out = resolve_date("the 16th", at(2026, 11, 3), "UTC", cal)
    assert isinstance(out, ResolvedDate) and out.business_day is True


def test_december_end_of_next_month_crosses_the_year():
    assert ok("end of next month", at(2026, 12, 10)) == date(2027, 1, 31)
    assert ok("15 Jan", at(2026, 12, 20)) == date(2027, 1, 15)
