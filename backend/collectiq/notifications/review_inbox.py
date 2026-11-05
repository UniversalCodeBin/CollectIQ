"""The review inbox (E108): everything waiting for a person, read straight from the tables that hold it.

This is a read model. It writes nothing and keeps no copy, so resolving an item at its source is what removes
it. A project lead sees only the cases assigned to them.
"""

from typing import Any

from collectiq.platform.context import RequestContext
from collectiq.platform.db import fetch_all, tenant_tx
from collectiq.tenancy.permissions import REVIEW_INBOX, authorize

from .routes import ROUTES, target

KINDS = frozenset({"CASE", "REMINDER_DRAFT", "MATCH_PROPOSAL", "PAYMENT_CLAIM", "APPROVAL"})
PER_SOURCE = 100


def _item(
    kind: str, subject_ref: dict[str, str], created_at: Any, action: str | None = None
) -> dict[str, Any]:
    route, default_action = target(kind, subject_ref)
    return {
        "kind": kind,
        "subject_ref": subject_ref,
        "target_route": route,
        "action": action or default_action,
        "created_at": created_at,
    }


def _cases(ctx: RequestContext) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id, invoice_id, opened_at FROM cases WHERE status <> 'RESOLVED'"
        " AND (%(limited)s::boolean IS FALSE OR assignee_id = %(user)s::uuid)"
        " ORDER BY opened_at DESC LIMIT %(n)s",
        {"limited": ctx.role == "PROJECT_LEAD", "user": ctx.user_id, "n": PER_SOURCE},
    )
    return [
        _item("CASE", {"case_id": str(r["id"]), "invoice_id": str(r["invoice_id"])}, r["opened_at"])
        for r in rows
    ]


def _drafts() -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id, invoice_id, status, created_at FROM reminders WHERE status IN ('DRAFT', 'APPROVED')"
        " ORDER BY created_at DESC LIMIT %s",
        [PER_SOURCE],
    )
    return [
        _item(
            "REMINDER_DRAFT",
            {"reminder_id": str(r["id"]), "invoice_id": str(r["invoice_id"])},
            r["created_at"],
            "Mark as sent" if r["status"] == "APPROVED" else None,
        )
        for r in rows
    ]


def _matches() -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id, transaction_id, invoice_id, created_at FROM reconciliation_matches"
        " WHERE status = 'PROPOSED' ORDER BY created_at DESC LIMIT %s",
        [PER_SOURCE],
    )
    return [
        _item(
            "MATCH_PROPOSAL",
            {
                "match_id": str(r["id"]),
                "transaction_id": str(r["transaction_id"]),
                "invoice_id": str(r["invoice_id"]),
            },
            r["created_at"],
        )
        for r in rows
    ]


def _claims() -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id, invoice_id, message_id, created_at FROM verification_tasks WHERE status = 'OPEN'"
        " ORDER BY created_at DESC LIMIT %s",
        [PER_SOURCE],
    )
    return [
        _item(
            "PAYMENT_CLAIM",
            {"task_id": str(r["id"]), "invoice_id": str(r["invoice_id"]), "message_id": str(r["message_id"])},
            r["created_at"],
        )
        for r in rows
    ]


def _approvals() -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id, decision_id, requested_at FROM approval_requests WHERE status = 'PENDING'"
        " ORDER BY requested_at DESC LIMIT %s",
        [PER_SOURCE],
    )
    return [
        _item(
            "APPROVAL", {"approval_id": str(r["id"]), "decision_id": str(r["decision_id"])}, r["requested_at"]
        )
        for r in rows
    ]


def review_inbox(ctx: RequestContext) -> dict[str, Any]:
    authorize(ctx, REVIEW_INBOX)
    with tenant_tx(ctx):
        items = _cases(ctx)
        if ctx.role != "PROJECT_LEAD":
            items += _drafts() + _matches() + _claims() + _approvals()
    items.sort(key=lambda item: item["created_at"], reverse=True)
    counts = {kind: sum(1 for i in items if i["kind"] == kind) for kind in sorted(KINDS)}
    assert set(ROUTES) >= KINDS
    return {"items": items, "counts": counts}
