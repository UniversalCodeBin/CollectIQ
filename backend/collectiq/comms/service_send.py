"""Provider submission of an approved reminder (E090, E091). Three steps so a crash or a dropped connection
never turns into a silent second send:

1. `begin` commits SUBMITTING after every gate is clear. Only an APPROVED reminder can begin.
2. The caller hands the text to the provider outside any transaction.
3. `finish` records SUBMITTED, back to APPROVED on a definite rejection, or SUBMISSION_UNKNOWN when the
   outcome cannot be known. Unknown is never retried by the system; a person resolves it with
   `resolve_unknown`.
"""

from typing import Any
from uuid import UUID

from collectiq.audit import record
from collectiq.invoices import state as invoice_state
from collectiq.platform import clock, outbox
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.policy.domain import ActionType
from collectiq.tenancy.permissions import DRAFT_APPROVE, authorize

from . import service_reminders as base

OUTCOMES = ("WAS_SENT", "NOT_SENT")


def _human(ctx: RequestContext) -> None:
    authorize(ctx, DRAFT_APPROVE)
    if ctx.user_id is None:
        raise ProblemError("FORBIDDEN", 403, "Only a person can send a reminder.")


def begin(ctx: RequestContext, reminder_id: UUID) -> dict[str, Any]:
    """Returns what to hand the provider. The text is exactly what the person approved."""
    _human(ctx)
    with tenant_tx(ctx):
        row = base._live_row(reminder_id)
        if row["status"] != "APPROVED":
            raise base._refused("Only an approved reminder can be sent.")
        invoice = base._lock_invoice(row["invoice_id"])
        key = base._key_of(reminder_id)
        snap = base._snapshot(
            ctx,
            row["invoice_id"],
            invoice,
            row["contact_id"],
            key=key,
            facts_valid=base._live_facts_valid(row),
            contact_checks=True,
        )
        base._require_clear(base._gate(ctx, ActionType.SEND_REMINDER, row["invoice_id"], snap))
        execute(
            "UPDATE reminders SET status = 'SUBMITTING', version = version + 1, updated_at = now()"
            " WHERE id = %s",
            [reminder_id],
        )
        record(
            ctx,
            "reminder.submitting",
            "reminder",
            str(reminder_id),
            before={"status": "APPROVED"},
            after={"status": "SUBMITTING"},
            reason_codes=["HUMAN_REQUESTED_SEND"],
        )
        return {"to": row["recipient"], "subject": row["subject"], "body": row["body"]}


def finish(
    ctx: RequestContext,
    reminder_id: UUID,
    outcome: str,
    message_id: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """outcome: SUBMITTED | REJECTED | UNKNOWN."""
    with tenant_tx(ctx):
        row = base._live_row(reminder_id)
        if row["status"] != "SUBMITTING":
            raise base._refused("This reminder is not being submitted.")
        if outcome == "SUBMITTED":
            execute(
                "UPDATE reminders SET status = 'SUBMITTED', provider_message_id = %s, submitted_at = %s,"
                " send_error = NULL, version = version + 1, updated_at = now() WHERE id = %s",
                [message_id, clock.now(), reminder_id],
            )
            _mark_waiting(row)
            action, after = "reminder.submitted", "SUBMITTED"
        elif outcome == "REJECTED":
            execute(
                "UPDATE reminders SET status = 'APPROVED', send_error = %s, version = version + 1,"
                " updated_at = now() WHERE id = %s",
                [error, reminder_id],
            )
            action, after = "reminder.submission_rejected", "APPROVED"
        elif outcome == "UNKNOWN":
            execute(
                "UPDATE reminders SET status = 'SUBMISSION_UNKNOWN', send_error = %s, version = version + 1,"
                " updated_at = now() WHERE id = %s",
                [error, reminder_id],
            )
            action, after = "reminder.submission_unknown", "SUBMISSION_UNKNOWN"
        else:
            raise ValueError(outcome)
        record(
            ctx,
            action,
            "reminder",
            str(reminder_id),
            before={"status": "SUBMITTING"},
            after={"status": after},
        )
        if outcome == "SUBMITTED":
            outbox.publish(
                ctx,
                "ReminderSubmitted",
                {"reminder_id": str(reminder_id), "invoice_id": str(row["invoice_id"])},
            )
        return base._dto(base._get_row(reminder_id))


def _mark_waiting(row: dict[str, Any]) -> None:
    invoice = base._lock_invoice(row["invoice_id"])
    if invoice["reminder_status"] == "DRAFT_READY":
        invoice_state.set_follow_up(row["invoice_id"], reminder_status="WAITING_FOR_CUSTOMER")


def resolve_unknown(ctx: RequestContext, reminder_id: UUID, outcome: str) -> dict[str, Any]:
    _human(ctx)
    if outcome not in OUTCOMES:
        raise ProblemError("VALIDATION_FAILED", 422, "Say whether the message was sent.")
    with tenant_tx(ctx):
        row = base._live_row(reminder_id)
        if row["status"] != "SUBMISSION_UNKNOWN":
            raise base._refused("Only a submission with an unknown result can be resolved this way.")
        if outcome == "WAS_SENT":
            execute(
                "UPDATE reminders SET status = 'SUBMITTED', submitted_at = COALESCE(submitted_at, %s),"
                " version = version + 1, updated_at = now() WHERE id = %s",
                [clock.now(), reminder_id],
            )
            _mark_waiting(row)
            after = "SUBMITTED"
        else:
            execute(
                "UPDATE reminders SET status = 'APPROVED', version = version + 1, updated_at = now()"
                " WHERE id = %s",
                [reminder_id],
            )
            after = "APPROVED"
        record(
            ctx,
            "reminder.unknown_resolved",
            "reminder",
            str(reminder_id),
            before={"status": "SUBMISSION_UNKNOWN"},
            after={"status": after, "outcome": outcome},
            reason_codes=["HUMAN_RESOLVED_UNKNOWN"],
        )
        return base._dto(base._get_row(reminder_id))
