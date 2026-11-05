"""Turns a date phrase from a reply into a date, or says it cannot.

The model only quotes the phrase. The date is worked out here, on the workspace's own calendar, and
anything that could mean two dates is returned as Ambiguous for a person to settle (BR-52).
"""

import calendar
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_DAYS_AHEAD = 366
_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
_DAYS = {name.lower(): i for i, name in enumerate(calendar.day_name)}
_DAYS.update({name.lower(): i for i, name in enumerate(calendar.day_abbr)})
_MON = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DOW = "|".join(sorted(_DAYS, key=len, reverse=True))
_ORD = r"(\d{1,2})(?:st|nd|rd|th)?"


@dataclass(frozen=True)
class BusinessCalendar:
    holidays: frozenset[date] = field(default_factory=frozenset)

    def is_business_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.holidays


_DEFAULT = BusinessCalendar()


@dataclass(frozen=True)
class ResolvedDate:
    date: date
    business_day: bool


@dataclass(frozen=True)
class Ambiguous:
    reason: str


def _make(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(today: date, months: int) -> tuple[int, int]:
    index = today.year * 12 + today.month - 1 + months
    return index // 12, index % 12 + 1


def _named(today: date, month: int, day: int) -> date | Ambiguous:
    for year in (today.year, today.year + 1):
        candidate = _make(year, month, day)
        if candidate is None:
            continue
        if candidate >= today:
            if (candidate - today).days > 183:
                return Ambiguous("That date is too far from the message to read safely.")
            return candidate
    if _make(today.year, month, day) is None and _make(today.year + 1, month, day) is None:
        return Ambiguous("That day does not exist in that month.")
    return Ambiguous("That date has already passed or is too far away to read safely.")


def _business_days(start: date, count: int, calendar_: BusinessCalendar) -> date:
    day = start
    while count > 0:
        day += timedelta(days=1)
        if calendar_.is_business_day(day):
            count -= 1
    return day


def _weekday(today: date, name: str, nxt: bool) -> date | Ambiguous:
    target = _DAYS[name]
    ahead = (target - today.weekday()) % 7
    if not nxt:
        return today + timedelta(days=ahead) if ahead else Ambiguous("That weekday is today; say a date.")
    if today.weekday() < target:
        return Ambiguous('"Next" that weekday could mean this week or the following one.')
    return today - timedelta(days=today.weekday()) + timedelta(days=7 + target)


def _local_today(received_at: datetime, tz: str) -> date | None:
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return None
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=UTC)
    return received_at.astimezone(zone).date()


def _parse(text: str, today: date, cal: BusinessCalendar) -> date | Ambiguous:  # noqa: PLR0911, PLR0912
    text = re.sub(r"^(?:by|on|before|until|around|about)\s+", "", text)
    text = (
        re.sub(r"^the\s+(?=\d)", "", text) if re.fullmatch(r"the\s+\d{1,2}(?:st|nd|rd|th)?", text) else text
    )
    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if text == "yesterday":
        return Ambiguous("That date is in the past.")
    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text):
        found = _make(int(m[1]), int(m[2]), int(m[3]))
        return found if found else Ambiguous("That day does not exist.")
    if m := re.fullmatch(r"in (\d{1,4}) (day|week|business day)s?", text):
        n = int(m[1])
        if n == 0 or n * (7 if m[2] == "week" else 1) > MAX_DAYS_AHEAD:
            return Ambiguous("That is not a usable number of days.")
        if m[2] == "business day":
            return _business_days(today, n, cal)
        return today + timedelta(days=n * (7 if m[2] == "week" else 1))
    if m := re.fullmatch(r"end of (?:the |this )?month", text):
        return _month_end(today.year, today.month)
    if re.fullmatch(r"end of next month", text):
        return _month_end(*_add_months(today, 1))
    if m := re.fullmatch(rf"(next )?({_DOW})", text):
        return _weekday(today, m[2], bool(m[1]))
    if m := re.fullmatch(rf"{_ORD}", text):
        found = _make(today.year, today.month, int(m[1]))
        if found is None:
            return Ambiguous("That day does not exist in this month.")
        return found if found >= today else Ambiguous("That day has passed this month; say the month.")
    if m := re.fullmatch(rf"{_ORD} (?:of )?({_MON})(?: (\d{{4}}))?", text) or re.fullmatch(
        rf"({_MON}) {_ORD}(?:,? (\d{{4}}))?", text
    ):
        groups = m.groups()
        day, month = (
            (int(groups[0]), _MONTHS[groups[1]])
            if groups[0].isdigit()
            else (int(groups[1]), _MONTHS[groups[0]])
        )
        if groups[2]:
            found = _make(int(groups[2]), month, day)
            if found is None:
                return Ambiguous("That day does not exist in that month.")
            return found if found >= today else Ambiguous("That date is in the past.")
        return _named(today, month, day)
    return Ambiguous("That could not be read as one date.")


def resolve_date(
    hint: str, received_at: datetime, workspace_tz: str, business_calendar: BusinessCalendar | None = None
) -> ResolvedDate | Ambiguous:
    if not isinstance(hint, str) or not hint.strip():
        return Ambiguous("There is no date to read.")
    today = _local_today(received_at, workspace_tz)
    if today is None:
        return Ambiguous("The workspace time zone is not recognised.")
    cal = business_calendar or _DEFAULT
    text = re.sub(r"\s+", " ", hint.strip().lower().rstrip(".!"))
    result = _parse(text, today, cal)
    if isinstance(result, Ambiguous):
        return result
    if result < today:
        return Ambiguous("That date is in the past.")
    if (result - today).days > MAX_DAYS_AHEAD:
        return Ambiguous("That date is too far away to read safely.")
    return ResolvedDate(result, cal.is_business_day(result))
