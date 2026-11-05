"""In-app notifications (E106, E107). A notification only points at work; the work itself lives at its source,
so a dropped notification never loses an item (the review inbox is derived from the source tables)."""

import json
from typing import Any
from uuid import UUID

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


def notify_approvers(ctx: RequestContext, type_: str, subject_ref: dict[str, str]) -> int:
    """One notification per owner and finance admin, once per subject. Safe to run again."""
    recipients = fetch_all(
        "SELECT user_id FROM workspace_memberships WHERE status = 'ACTIVE' AND role = ANY(%s)",
        [list(_APPROVERS)],
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
