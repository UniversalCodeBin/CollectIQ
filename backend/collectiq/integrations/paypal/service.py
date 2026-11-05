"""PayPal webhook intake. Events are kept as evidence only; nothing here allocates or marks anything paid."""

import json
import uuid
from collections.abc import Mapping
from uuid import UUID

from django.conf import settings

from collectiq.audit import record
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError

from .verify import get_verifier


def receive(headers: Mapping[str, str], body: bytes) -> None:
    if not settings.FEATURE_PAYPAL_WEBHOOK:
        raise ProblemError("NOT_FOUND", 404, "We could not find that.")
    if not get_verifier().verify(headers, body):
        raise ProblemError("AUTH_REQUIRED", 401, "The signature could not be verified.")
    try:
        event = json.loads(body)
        event_id = str(event["id"])
        event_type = str(event["event_type"])
        merchant = str(event["resource"]["payee"]["merchant_id"])
    except (ValueError, KeyError, TypeError):
        raise ProblemError("VALIDATION_FAILED", 422, "The event is not in the expected shape.") from None
    row = fetch_one("SELECT paypal_workspace_for(%s) AS ws", [merchant])
    workspace_id: UUID | None = row["ws"] if row else None
    if workspace_id is None:
        return  # not ours; acknowledge so the sender stops retrying, keep nothing
    ctx = RequestContext(workspace_id, None, None, str(uuid.uuid4()), "SYSTEM")
    with tenant_tx(ctx):
        inserted = execute(
            "INSERT INTO webhook_events (workspace_id, provider, event_id, event_type, status, payload)"
            " VALUES (%s, 'PAYPAL', %s, %s, 'EVIDENCE_ONLY', %s::jsonb) ON CONFLICT DO NOTHING",
            [workspace_id, event_id, event_type, json.dumps(event)],
        )
        if inserted:
            record(
                ctx,
                "webhook.received",
                "webhook_event",
                event_id,
                after={"provider": "PAYPAL", "event_type": event_type, "status": "EVIDENCE_ONLY"},
            )
