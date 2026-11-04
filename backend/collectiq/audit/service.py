"""Writes audit events in the caller's transaction, so a rollback removes them with the change."""
import json
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection

from collectiq.platform.context import RequestContext

# SEC-12: credentials, bank data and message or document content. A key containing any of these is removed.
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "private_key",
    "account_number",
    "iban",
    "routing_number",
    "sort_code",
    "bank",
    "body",
    "email_content",
    "raw_text",
    "raw_payload",
)


def _is_sensitive(key: object) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _mask(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _mask(item) for key, item in value.items() if not _is_sensitive(key)}
    if isinstance(value, list | tuple):
        return [_mask(item) for item in value]
    return value


def _masked_json(value: Mapping[str, Any] | None) -> str | None:
    return None if value is None else json.dumps(_mask(value), cls=DjangoJSONEncoder)


def record(
    ctx: RequestContext,
    action: str,
    object_type: str,
    object_id: str,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    reason_codes: Iterable[str] = (),
    evidence_refs: Mapping[str, Any] | None = None,
    policy_decision_id: UUID | None = None,
) -> None:
    if not connection.in_atomic_block:
        raise RuntimeError("audit.record must run inside the transaction of the change it records")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO audit_events (
              workspace_id, actor_type, actor_id, action, object_type, object_id, before_masked,
              after_masked, reason_codes, evidence_refs, policy_decision_id, correlation_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::text[], %s::jsonb, %s, %s)
            """,
            [
                ctx.workspace_id,
                ctx.actor_type,
                ctx.user_id,
                action,
                object_type,
                object_id,
                _masked_json(before),
                _masked_json(after),
                list(reason_codes),
                _masked_json(evidence_refs),
                policy_decision_id,
                ctx.correlation_id,
            ],
        )
