"""Opaque server-side sessions: revocable, and only a hash is stored (FR-155, SEC-07)."""

import hashlib
import secrets
from dataclasses import dataclass
from uuid import UUID

from django.conf import settings

from collectiq.platform.db import execute, fetch_all, fetch_one

_TOUCH_EVERY_SECONDS = 60


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    email: str
    verified: bool
    session_id: UUID
    idle: bool


def token_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue(user_id: UUID) -> str:
    raw = secrets.token_urlsafe(32)
    execute(
        "INSERT INTO user_sessions (user_id, token_hash, expires_at) VALUES (%s, %s, now() + %s)",
        [user_id, token_digest(raw), settings.SESSION_ABSOLUTE_TTL],
    )
    return raw


def authenticate(raw: str) -> Principal | None:
    rows = fetch_all(
        """
        SELECT s.id AS session_id, u.id AS user_id, u.email::text AS email,
               u.email_verified_at IS NOT NULL AS verified,
               s.last_seen_at < now() - %s AS idle
        FROM user_sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = %s AND s.revoked_at IS NULL AND s.expires_at > now() AND u.status <> 'DISABLED'
        """,
        [settings.SESSION_IDLE_SENSITIVE, token_digest(raw)],
    )
    return Principal(**rows[0]) if rows else None


def touch(session_id: UUID) -> None:
    """Written at most once a minute, so reads do not turn into a write per request."""
    execute(
        "UPDATE user_sessions SET last_seen_at = now()"
        " WHERE id = %s AND last_seen_at < now() - %s * interval '1 second'",
        [session_id, _TOUCH_EVERY_SECONDS],
    )


def revoke_token(raw: str) -> UUID | None:
    row = fetch_one(
        "UPDATE user_sessions SET revoked_at = now() WHERE token_hash = %s AND revoked_at IS NULL"
        " RETURNING user_id",
        [token_digest(raw)],
    )
    return row["user_id"] if row else None


def revoke_all(user_id: UUID) -> None:
    execute(
        "UPDATE user_sessions SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL", [user_id]
    )
