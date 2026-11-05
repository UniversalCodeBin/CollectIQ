"""The current time, in one place so a test can move it. Services call `now()`, never `datetime.now`."""

from datetime import UTC, date, datetime


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return now().date()
