"""Pause reminders for one client or one invoice (E121-E123), with history.

A pause is a person's decision, never the AI's: the brief agent may only suggest one. While a pause is
active the policy engine refuses reminder drafting, approval and hand-off for that target (gate G13, see
`hold_scope`), so nothing slips through between a pause and the next reminder. Resuming closes the row but
keeps it, and both steps are audited with who and why. Drafts that already exist are left alone; they
simply cannot be approved or recorded as sent until the pause is lifted.
"""

from typing import Any
from uuid import UUID

from collectiq.audit import record
from collectiq.platform.context import RequestContext
from collectiq.platform.db import fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.tenancy.permissions import AUTOMATION_PAUSE, INVOICES_READ, authorize

SCOPES = ("CLIENT", "INVOICE")
_COLUMNS = "id, scope, client_id, invoice_id, reason, status, paused_by, paused_at, resumed_by, resumed_at"


def hold_scope(invoice_id: UUID | str, client_id: UUID | str) -> str | None:
    """'INVOICE' or 'CLIENT' when an active pause covers this invoice; the invoice's own wins."""
    row = fetch_one(
        "SELECT scope FROM reminder_pauses WHERE status = 'ACTIVE' AND (invoice_id = %s OR client_id = %s)"
        " ORDER BY (scope = 'INVOICE') DESC LIMIT 1",
        [invoice_id, client_id],
    )
    return row["scope"] if row else None


def _target_exists(scope: str, target_id: UUID) -> bool:
    table = "clients" if scope == "CLIENT" else "invoices"
    # Row security hides other workspaces, so a foreign id is simply "not found".
    return fetch_one(f"SELECT 1 AS ok FROM {table} WHERE id = %s", [target_id]) is not None  # noqa: S608


def pause(ctx: RequestContext, scope: str, target_id: UUID, reason: str | None) -> dict[str, Any]:
    authorize(ctx, AUTOMATION_PAUSE)
    with tenant_tx(ctx):
        if scope not in SCOPES or not _target_exists(scope, target_id):
            raise ProblemError("NOT_FOUND", 404, "We could not find that.")
        column = "client_id" if scope == "CLIENT" else "invoice_id"
        if fetch_one(
            f"SELECT 1 AS ok FROM reminder_pauses WHERE {column} = %s AND status = 'ACTIVE'",  # noqa: S608
            [target_id],
        ):
            raise ProblemError("STATE_TRANSITION_INVALID", 409, "Reminders are already paused here.")
        row = fetch_one(
            f"INSERT INTO reminder_pauses (workspace_id, scope, {column}, reason, paused_by)"  # noqa: S608
            f" VALUES (%s, %s, %s, %s, %s) RETURNING {_COLUMNS}",
            [ctx.workspace_id, scope, target_id, (reason or "").strip() or None, ctx.user_id],
        )
        assert row
        record(
            ctx,
            "reminders.paused",
            scope.lower(),
            str(target_id),
            after={"scope": scope, "pause_id": str(row["id"])},
            reason_codes=["PERSON_PAUSED"],
        )
        return row


def resume(ctx: RequestContext, pause_id: UUID) -> dict[str, Any]:
    authorize(ctx, AUTOMATION_PAUSE)
    with tenant_tx(ctx):
        current = fetch_one(
            "SELECT scope, client_id, invoice_id, status FROM reminder_pauses WHERE id = %s FOR UPDATE",
            [pause_id],
        )
        if current is None:
            raise ProblemError("NOT_FOUND", 404, "We could not find that.")
        if current["status"] != "ACTIVE":
            raise ProblemError("STATE_TRANSITION_INVALID", 409, "This pause has already ended.")
        row = fetch_one(
            "UPDATE reminder_pauses SET status = 'RESUMED', resumed_by = %s, resumed_at = now()"  # noqa: S608
            f" WHERE id = %s RETURNING {_COLUMNS}",
            [ctx.user_id, pause_id],
        )
        assert row
        target = current["client_id"] or current["invoice_id"]
        record(
            ctx,
            "reminders.resumed",
            current["scope"].lower(),
            str(target),
            before={"pause_id": str(pause_id)},
            after={"status": "RESUMED"},
            reason_codes=["PERSON_RESUMED"],
        )
        return row


def list_pauses(
    ctx: RequestContext, invoice_id: UUID | None, client_id: UUID | None, history: bool
) -> dict[str, Any]:
    """Active pauses by default; `history` adds the ended ones. Optionally narrowed to one target."""
    authorize(ctx, INVOICES_READ)
    clauses, args = [], []
    if not history:
        clauses.append("status = 'ACTIVE'")
    if invoice_id:
        clauses.append("(invoice_id = %s OR client_id = (SELECT client_id FROM invoices WHERE id = %s))")
        args += [invoice_id, invoice_id]
    if client_id:
        clauses.append("client_id = %s")
        args.append(client_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with tenant_tx(ctx):
        rows = fetch_all(
            f"SELECT {_COLUMNS} FROM reminder_pauses{where} ORDER BY paused_at DESC LIMIT 200",  # noqa: S608
            args,
        )
    return {"items": rows}


# FILE GUIDE
# hold_scope: read by comms.service_reminders._snapshot so gate G13 sees pauses. pause/resume: E122/E123.
# list_pauses: E121. Table `reminder_pauses` (migration comms 0003) keeps ended pauses as history.
