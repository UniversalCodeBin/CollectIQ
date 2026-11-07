"""In-app notifications (E106, E107). A notification only points at work; the work itself lives at its source,
so a dropped notification never loses an item (the review inbox is derived from the source tables)."""

import json
from typing import Any
from uuid import UUID

from collectiq.audit import record
from collectiq.platform import outbox
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError

from .routes import target

CASE_OPENED = "CaseOpened"
REMINDER_DRAFTED = "ReminderDrafted"
_APPROVERS = ("OWNER", "FINANCE_ADMIN")


def _dto(row: dict[str, Any]) -> dict[str, Any]:
    ref = row["subject_ref"]
    ref = json.loads(ref) if isinstance(ref, str) else ref
    route, action = target(row["type"], ref)
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "subject_ref": ref,
        "target_route": route,
        "action": action,
        "created_at": row["created_at"],
        "read_at": row["read_at"],
    }


def list_notifications(ctx: RequestContext, limit: int, cursor: UUID | None) -> dict[str, Any]:
    with tenant_tx(ctx):
        rows = fetch_all(
            "SELECT n.id, n.type, n.subject_ref, n.created_at, n.read_at FROM notifications n"
            " WHERE n.user_id = %(user)s"
            "   AND (%(cursor)s::uuid IS NULL OR (n.created_at, n.id) <"
            "        (SELECT c.created_at, c.id FROM notifications c WHERE c.id = %(cursor)s::uuid"
            "         AND c.user_id = %(user)s))"
            " ORDER BY n.created_at DESC, n.id DESC LIMIT %(limit)s",
            {"user": ctx.user_id, "cursor": cursor, "limit": limit + 1},
        )
    page = rows[:limit]
    return {
        "items": [_dto(r) for r in page],
        "next_cursor": str(page[-1]["id"]) if len(rows) > limit else None,
    }


def mark_read(ctx: RequestContext, notification_id: UUID) -> None:
    with tenant_tx(ctx):
        row = fetch_one(
            "SELECT id FROM notifications WHERE id = %s AND user_id = %s FOR UPDATE",
            [notification_id, ctx.user_id],
        )
        if row is None:
            raise ProblemError("NOT_FOUND", 404, "We could not find that.")
        execute(
            "UPDATE notifications SET read_at = now() WHERE id = %s AND read_at IS NULL", [notification_id]
        )


KINDS = ("CASE_OPENED", "REMINDER_DRAFT_READY")
RETENTION_DAYS = 90  # FR-146 / retention: notifications only point at work, so old ones are safe to drop


def get_preferences(ctx: RequestContext) -> dict[str, Any]:
    with tenant_tx(ctx):
        rows = fetch_all(
            "SELECT type, in_app FROM notification_preferences WHERE user_id = %s", [ctx.user_id]
        )
    chosen = {r["type"]: r["in_app"] for r in rows}
    return {"in_app": {kind: chosen.get(kind, True) for kind in KINDS}}


def put_preferences(ctx: RequestContext, in_app: dict[str, bool]) -> dict[str, Any]:
    """Personal and partial: only the kinds named change. Never hides work; the review inbox ignores this."""
    unknown = sorted(set(in_app) - set(KINDS))
    if unknown:
        raise ProblemError("VALIDATION_FAILED", 422, "That kind of notification is not recognised.")
    with tenant_tx(ctx):
        for kind, on in in_app.items():
            execute(
                "INSERT INTO notification_preferences (workspace_id, user_id, type, in_app)"
                " VALUES (%s, %s, %s, %s) ON CONFLICT (workspace_id, user_id, type)"
                " DO UPDATE SET in_app = EXCLUDED.in_app, updated_at = now()",
                [ctx.workspace_id, ctx.user_id, kind, on],
            )
        record(
            ctx,
            "notification_preferences.changed",
            "user",
            str(ctx.user_id),
            after={"in_app": dict(sorted(in_app.items()))},
        )
    return get_preferences(ctx)


def delete_expired(ctx: RequestContext) -> int:
    """Inside a tenant transaction. Removes notifications older than the retention window."""
    return execute(
        "DELETE FROM notifications"
        " WHERE workspace_id = %s AND created_at < now() - make_interval(days => %s)",
        [ctx.workspace_id, RETENTION_DAYS],
    )


def notify_approvers(ctx: RequestContext, type_: str, subject_ref: dict[str, str]) -> int:
    """One notification per owner and finance admin, once per subject. Safe to run again.

    People who turned this kind off are skipped; the work still shows in the review inbox."""
    recipients = fetch_all(
        "SELECT m.user_id FROM workspace_memberships m WHERE m.status = 'ACTIVE' AND m.role = ANY(%s)"
        " AND NOT EXISTS (SELECT 1 FROM notification_preferences p WHERE p.user_id = m.user_id"
        "                 AND p.type = %s AND NOT p.in_app)",
        [list(_APPROVERS), type_],
    )
    for member in recipients:
        execute(
            "INSERT INTO notifications (workspace_id, user_id, type, subject_ref)"
            " VALUES (%s, %s, %s, %s::jsonb) ON CONFLICT (user_id, type, subject_ref) DO NOTHING",
            [ctx.workspace_id, member["user_id"], type_, json.dumps(subject_ref, sort_keys=True)],
        )
    return len(recipients)


@outbox.subscriber(CASE_OPENED)
def _on_case_opened(ctx: RequestContext, payload: dict[str, Any]) -> None:
    notify_approvers(ctx, "CASE_OPENED", {"case_id": payload["case_id"], "invoice_id": payload["invoice_id"]})


@outbox.subscriber(REMINDER_DRAFTED)
def _on_reminder_drafted(ctx: RequestContext, payload: dict[str, Any]) -> None:
    notify_approvers(
        ctx,
        "REMINDER_DRAFT_READY",
        {"reminder_id": payload["reminder_id"], "invoice_id": payload["invoice_id"]},
    )
