"""Cross-module reactions (INV-10). An event commits with the change that caused it, then reaches subscribers
through a job in the same workspace, so it needs no second path across tenants. Subscribers must be
idempotent.
"""
import json
from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection

from . import jobs
from .context import RequestContext

_DISPATCH_KIND = "outbox.dispatch"

_subscribers: defaultdict[str, list[jobs.Handler]] = defaultdict(list)


def subscriber(event_type: str) -> Callable[[jobs.Handler], jobs.Handler]:
    def register(handler: jobs.Handler) -> jobs.Handler:
        _subscribers[event_type].append(handler)
        return handler

    return register


def publish(ctx: RequestContext, event_type: str, payload: Mapping[str, Any]) -> UUID:
    if not connection.in_atomic_block:
        raise RuntimeError("publish must run inside the transaction of the change it announces")
    jobs.require_ids_only(payload)
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO outbox_events (workspace_id, event_type, payload, correlation_id)"
            " VALUES (%s, %s, %s::jsonb, %s) RETURNING id",
            [ctx.workspace_id, event_type, json.dumps(payload, cls=DjangoJSONEncoder), ctx.correlation_id],
        )
        event_id = cursor.fetchone()[0]
    jobs.enqueue(ctx, _DISPATCH_KIND, {"event_id": event_id}, dedupe_key=str(event_id))
    return event_id


@jobs.job_handler(_DISPATCH_KIND)
def _dispatch(ctx: RequestContext, payload: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT event_type, payload FROM outbox_events WHERE id = %s AND published_at IS NULL FOR UPDATE",
            [payload["event_id"]],
        )
        row = cursor.fetchone()
        if row is None:
            return
        event_type, event_payload = row
        for handler in _subscribers[event_type]:
            handler(ctx, json.loads(event_payload))
        cursor.execute("UPDATE outbox_events SET published_at = now() WHERE id = %s", [payload["event_id"]])
