"""Rate limits and login lockout. Every key is hashed: this table must not become a list of addresses."""

import hashlib

from django.conf import settings

from collectiq.platform.db import execute, fetch_all, fetch_one
from collectiq.platform.errors import ProblemError

_IP_WINDOW_SECONDS = 60
_MAIL_WINDOW_SECONDS = 3600


def _digest(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def email_digest(email: str) -> str:
    return _digest(email)


def _rate_limited(retry_after: int) -> ProblemError:
    return ProblemError(
        "RATE_LIMITED",
        429,
        "Too many attempts. Wait a moment and try again.",
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _bump(key: str, window_seconds: int) -> tuple[int, int]:
    """One statement, so concurrent requests cannot lose a count. Returns the count and seconds remaining."""
    row = fetch_all(
        """
        INSERT INTO auth_throttles AS t (key, count) VALUES (%(key)s, 1)
        ON CONFLICT (key) DO UPDATE SET
            count = CASE WHEN t.window_started_at < now() - %(window)s * interval '1 second'
                         THEN 1 ELSE t.count + 1 END,
            window_started_at = CASE WHEN t.window_started_at < now() - %(window)s * interval '1 second'
                                     THEN now() ELSE t.window_started_at END
        RETURNING count,
            CEIL(EXTRACT(EPOCH FROM window_started_at + %(window)s * interval '1 second' - now()))::int
                AS remaining
        """,
        {"key": key, "window": window_seconds},
    )[0]
    return row["count"], row["remaining"]


def check_ip(address: str) -> None:
    count, remaining = _bump(f"ip:{_digest(address)}", _IP_WINDOW_SECONDS)
    if count > settings.AUTH_IP_RATE_LIMIT:
        raise _rate_limited(remaining)


def take_mail_slot(email: str) -> bool:
    """False over the hourly cap. Called inside the job's transaction, so a failed delivery gives it back."""
    count, _ = _bump(f"mail:{_digest(email)}", _MAIL_WINDOW_SECONDS)
    return count <= settings.AUTH_EMAIL_HOURLY_LIMIT


def _login_key(email: str) -> str:
    return f"login:{_digest(email)}"


def check_login_lock(email: str) -> None:
    row = fetch_one(
        "SELECT CEIL(EXTRACT(EPOCH FROM locked_until - now()))::int AS remaining FROM auth_throttles"
        " WHERE key = %s AND locked_until > now()",
        [_login_key(email)],
    )
    if row:
        raise _rate_limited(row["remaining"])


def record_login_failure(email: str) -> None:
    """Keyed on the address, not the user, so an unknown email locks exactly as a real one does."""
    execute(
        """
        INSERT INTO auth_throttles AS t (key, count, locked_until)
        VALUES (%(key)s, 1, CASE WHEN %(threshold)s <= 1 THEN now() + %(seconds)s * interval '1 second' END)
        ON CONFLICT (key) DO UPDATE SET
            count = CASE WHEN t.locked_until <= now()
                           OR t.window_started_at < now() - %(seconds)s * interval '1 second'
                         THEN 1 ELSE t.count + 1 END,
            window_started_at = CASE WHEN t.locked_until <= now()
                                       OR t.window_started_at < now() - %(seconds)s * interval '1 second'
                                     THEN now() ELSE t.window_started_at END,
            locked_until = CASE WHEN (CASE WHEN t.locked_until <= now()
                                       OR t.window_started_at < now() - %(seconds)s * interval '1 second'
                                     THEN 1 ELSE t.count + 1 END) >= %(threshold)s
                                THEN now() + %(seconds)s * interval '1 second' END
        """,
        {
            "key": _login_key(email),
            "threshold": settings.AUTH_LOCKOUT_THRESHOLD,
            "seconds": settings.AUTH_LOCKOUT_SECONDS,
        },
    )


def clear_login(email: str) -> None:
    execute("DELETE FROM auth_throttles WHERE key = %s", [_login_key(email)])
