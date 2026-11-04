"""Single-use email tokens. The address proves the claim, so only a hash is kept."""
import hashlib
import secrets
from datetime import timedelta
from uuid import UUID

from collectiq.platform.db import execute, fetch_one

VERIFY_EMAIL = "VERIFY_EMAIL"
PASSWORD_RESET = "PASSWORD_RESET"  # noqa: S105  # pragma: allowlist secret (a purpose, not a secret)


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue(user_id: UUID, purpose: str, ttl: timedelta) -> str:
    """A newer token replaces any older one for the same purpose."""
    execute(
        "UPDATE auth_tokens SET used_at = now() WHERE user_id = %s AND purpose = %s AND used_at IS NULL",
        [user_id, purpose],
    )
    raw = secrets.token_urlsafe(32)
    execute(
        "INSERT INTO auth_tokens (user_id, purpose, token_hash, expires_at) VALUES (%s, %s, %s, now() + %s)",
        [user_id, purpose, _digest(raw), ttl],
    )
    return raw


def peek(raw: str, purpose: str) -> UUID | None:
    row = fetch_one(
        "SELECT user_id FROM auth_tokens"
        " WHERE token_hash = %s AND purpose = %s AND used_at IS NULL AND expires_at > now()",
        [_digest(raw), purpose],
    )
    return row["user_id"] if row else None


def consume(raw: str, purpose: str) -> UUID | None:
    """One statement, so two concurrent uses cannot both succeed."""
    row = fetch_one(
        "UPDATE auth_tokens SET used_at = now()"
        " WHERE token_hash = %s AND purpose = %s AND used_at IS NULL AND expires_at > now()"
        " RETURNING user_id",
        [_digest(raw), purpose],
    )
    return row["user_id"] if row else None
