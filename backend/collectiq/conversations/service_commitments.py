"""Customer promises and the snooze a person may approve because of one (E071-E075).

A promise is recorded by a person. It can propose a pause in follow-ups; only a person's approval
starts it, and any dispute, open check on a payment or contact limit stops it (FR-080, BR-60).
"""

from dataclasses import replace
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from collectiq.audit import record
from collectiq.cases import service as cases
from collectiq.invoices import state as invoice_state
from collectiq.platform import clock, outbox
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.policy import service as policy
from collectiq.policy.domain import ActionRequest, ActionType, Actor, ActorKind
from collectiq.tenancy.permissions import MESSAGES_READ, MESSAGES_WRITE, authorize

from .service import _lead_may_see, _not_found

STRENGTHS = ("EXPLICIT", "TENTATIVE")
HORIZON = timedelta(days=45)  # a pause never runs longer than this without a person looking again
_COLUMNS = (
    "id, invoice_id, source_message_id, strength, promised_date, window_start, window_end, status, note,"
    " created_by, version, created_at"
)


def _dto(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "id": str(row["id"]),
        "invoice_id": str(row["invoice_id"]),
        "source_message_id": str(row["source_message_id"]) if row["source_message_id"] else None,
        "created_by": str(row["created_by"]),
    }


def _refused(detail: str) -> ProblemError:
    return ProblemError("STATE_TRANSITION_INVALID", 409, detail)


def _today() -> date:
    return clock.now().date()


def _request(ctx: RequestContext, invoice_id: UUID, snooze_id: UUID, until: date) -> ActionRequest:
    return ActionRequest(
        ActionType.AUTO_SNOOZE,
        Actor(ActorKind.HUMAN, str(ctx.user_id), ctx.role),
        f"invoice:{invoice_id}",
        {"snooze_id": str(snooze_id), "until": until.isoformat()},
    )


def _snooze_dto(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "id": str(row["id"]),
        "invoice_id": str(row["invoice_id"]),
        "commitment_id": str(row["commitment_id"]) if row["commitment_id"] else None,
        "approval_id": str(row["approval_id"]),
    }


_SNOOZE = "id, invoice_id, commitment_id, until, status, approval_id, created_at, activated_at, ended_at"


# --- reads (E071) ---


def list_commitments(
    ctx: RequestContext, invoice_id: UUID, limit: int, cursor: UUID | None
) -> dict[str, Any]:
    authorize(ctx, MESSAGES_READ)
    with tenant_tx(ctx):
        if fetch_one("SELECT 1 AS ok FROM invoices WHERE id = %s", [invoice_id]) is None or not _lead_may_see(
            ctx, invoice_id
        ):
            raise _not_found()
        rows = fetch_all(
            f"SELECT {_COLUMNS} FROM commitments WHERE invoice_id = %(invoice)s"  # noqa: S608
            " AND (%(cursor)s::uuid IS NULL OR id > %(cursor)s::uuid) ORDER BY id LIMIT %(limit)s",
            {"invoice": invoice_id, "cursor": cursor, "limit": limit + 1},
        )
        page = rows[:limit]
        snoozes = fetch_all(
            f"SELECT {_SNOOZE} FROM snoozes WHERE invoice_id = %s AND status IN ('PROPOSED', 'ACTIVE')",  # noqa: S608
            [invoice_id],
        )
    return {
        "items": [_dto(r) for r in page],
        "snoozes": [_snooze_dto(s) for s in snoozes],
        "next_cursor": str(page[-1]["id"]) if len(rows) > limit else None,
    }


# --- record (E072) ---


def _propose_snooze(
    ctx: RequestContext, invoice_id: UUID, commitment_id: UUID, until: date
) -> dict[str, Any]:
    """Asks the policy engine. Whatever it says is shown; only an approval can start a snooze."""
    snap = cases.invoice_snapshot(invoice_id)
    active = fetch_one(
        "SELECT 1 AS ok FROM snoozes WHERE invoice_id = %s AND status = 'ACTIVE'", [invoice_id]
    )
    snap = replace(snap, snooze_active=active is not None, ai_confidence=None)
    proposal_id = fetch_one("SELECT gen_random_uuid() AS id")
    assert proposal_id
    decision = policy.decide(ctx, _request(ctx, invoice_id, proposal_id["id"], until), snap)
    result = {
        "outcome": decision["outcome"],
        "reasons": decision["reasons"],
        "approval_id": str(decision["approval_id"]) if decision["approval_id"] else None,
        "until": until,
    }
    if decision["approval_id"]:
        execute(
            "INSERT INTO snoozes (id, workspace_id, invoice_id, commitment_id, until, approval_id,"
            " proposed_by)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [
                proposal_id["id"],
                ctx.workspace_id,
                invoice_id,
                commitment_id,
                until,
                decision["approval_id"],
                ctx.user_id,
            ],
        )
    return result


def record_commitment(
    ctx: RequestContext,
    invoice_id: UUID,
    strength: str,
    promised: date | None = None,
    window_start: date | None = None,
    window_end: date | None = None,
    note: str | None = None,
    source_message_id: UUID | None = None,
) -> dict[str, Any]:
    authorize(ctx, MESSAGES_WRITE)
    if ctx.user_id is None:
        raise ProblemError("FORBIDDEN", 403, "Only a person can record a customer promise.")
    if strength not in STRENGTHS:
        raise ProblemError("VALIDATION_FAILED", 422, "A promise is explicit or tentative.")
    if strength == "EXPLICIT" and promised is None and window_end is None:
        raise ProblemError(
            "VALIDATION_FAILED", 422, "An explicit promise needs a date or the end of a window."
        )
    if window_start and window_end and window_start > window_end:
        raise ProblemError("VALIDATION_FAILED", 422, "The window ends before it starts.")
    with tenant_tx(ctx):
        if fetch_one("SELECT 1 AS ok FROM invoices WHERE id = %s", [invoice_id]) is None:
            raise ProblemError("VALIDATION_FAILED", 422, "That invoice could not be found.")
        state = fetch_one("SELECT 1 AS ok FROM invoice_state WHERE invoice_id = %s FOR UPDATE", [invoice_id])
        assert state
        row = fetch_one(
            f"INSERT INTO commitments (workspace_id, invoice_id, source_message_id, strength, promised_date,"  # noqa: S608
            " window_start, window_end, note, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            f" RETURNING {_COLUMNS}",
            [
                ctx.workspace_id,
                invoice_id,
                source_message_id,
                strength,
                promised,
                window_start,
                window_end,
                note,
                ctx.user_id,
            ],
        )
        assert row
        record(
            ctx,
            "commitment.recorded",
            "commitment",
            str(row["id"]),
            after={"invoice_id": str(invoice_id), "strength": strength, "date": str(promised or window_end)},
            reason_codes=["RECORDED_BY_PERSON"],
        )
        outbox.publish(
            ctx, "CommitmentRecorded", {"commitment_id": str(row["id"]), "invoice_id": str(invoice_id)}
        )
        target = promised or window_end
        snooze: dict[str, Any] | None = None
        note_out: str | None = None
        if strength != "EXPLICIT":
            note_out = "A tentative promise does not pause follow-ups."
        elif target is None or target < _today() or target > _today() + HORIZON:
            note_out = "The date is outside the next 45 days, so no pause is proposed."
        else:
            snooze = _propose_snooze(ctx, invoice_id, row["id"], target)
        return {**_dto(row), "snooze": snooze, "snooze_note": note_out}


# --- update (E073) ---


def update_commitment(
    ctx: RequestContext, commitment_id: UUID, version: int, status: str | None, note: str | None
) -> dict[str, Any]:
    authorize(ctx, MESSAGES_WRITE)
    if ctx.user_id is None:
        raise ProblemError("FORBIDDEN", 403, "Only a person can change a customer promise.")
    if status is not None and status not in ("WITHDRAWN", "BROKEN"):
        raise ProblemError("VALIDATION_FAILED", 422, "A promise can be marked withdrawn or broken.")
    with tenant_tx(ctx):
        row = fetch_one(f"SELECT {_COLUMNS} FROM commitments WHERE id = %s FOR UPDATE", [commitment_id])  # noqa: S608
        if row is None:
            raise _not_found()
        if row["version"] != version:
            raise ProblemError("CONFLICT_VERSION", 409, "This promise changed. Reload and try again.")
        if row["status"] != "ACTIVE" and status is not None:
            raise _refused("This promise is already closed.")
        if status is not None:
            invoice_state_row = fetch_one(
                "SELECT 1 AS ok FROM invoice_state WHERE invoice_id = %s FOR UPDATE", [row["invoice_id"]]
            )
            assert invoice_state_row
            for pending in fetch_all(
                "SELECT id FROM snoozes WHERE commitment_id = %s AND status = 'PROPOSED' FOR UPDATE",
                [commitment_id],
            ):
                execute(
                    "UPDATE snoozes SET status = 'DISCARDED', ended_at = now() WHERE id = %s", [pending["id"]]
                )
            if fetch_one(
                "SELECT 1 AS ok FROM snoozes WHERE commitment_id = %s AND status = 'ACTIVE'", [commitment_id]
            ):
                _end_snooze(ctx, row["invoice_id"], f"Promise {status.lower()}")
        updated = fetch_one(
            f"UPDATE commitments SET status = COALESCE(%s, status), note = COALESCE(%s, note),"  # noqa: S608
            f" version = version + 1, updated_at = now() WHERE id = %s RETURNING {_COLUMNS}",
            [status, note, commitment_id],
        )
        assert updated
        record(
            ctx,
            "commitment.updated",
            "commitment",
            str(commitment_id),
            before={"status": row["status"]},
            after={"status": updated["status"]},
        )
        return _dto(updated)


# --- snooze (E074, E075) ---


def approve_snooze(ctx: RequestContext, invoice_id: UUID, approval_id: UUID) -> dict[str, Any]:
    authorize(ctx, MESSAGES_WRITE)
    if ctx.actor_type != "USER" or ctx.user_id is None:
        raise ProblemError("FORBIDDEN", 403, "Only a person can start a pause in follow-ups.")
    with tenant_tx(ctx):
        state = fetch_one(
            "SELECT reminder_status FROM invoice_state WHERE invoice_id = %s FOR UPDATE", [invoice_id]
        )
        if state is None:
            raise _not_found()
        proposal = fetch_one(
            f"SELECT {_SNOOZE} FROM snoozes WHERE approval_id = %s AND invoice_id = %s FOR UPDATE",  # noqa: S608
            [approval_id, invoice_id],
        )
        if proposal is None:
            raise _not_found()
        if proposal["status"] != "PROPOSED":
            raise _refused("This pause was already used or withdrawn.")
        approval = fetch_one(
            "SELECT a.decision_id, d.action_type, d.subject FROM approval_requests a"
            "  JOIN policy_decisions d ON d.id = a.decision_id AND d.workspace_id = a.workspace_id"
            " WHERE a.id = %s",
            [approval_id],
        )
        if (
            approval is None
            or approval["action_type"] != ActionType.AUTO_SNOOZE
            or approval["subject"] != f"invoice:{invoice_id}"
        ):
            raise _refused("This approval is for something else.")
        until = proposal["until"]
        if until < _today() or until > _today() + HORIZON:
            raise _refused(
                "The promised date has passed or is more than 45 days away. Record the promise again."
            )
        snap = cases.invoice_snapshot(invoice_id)
        active = fetch_one(
            "SELECT 1 AS ok FROM snoozes WHERE invoice_id = %s AND status = 'ACTIVE'", [invoice_id]
        )
        snap = replace(snap, snooze_active=active is not None)
        # Re-checks every gate under the lock, then spends the approval once. Fails closed.
        policy.authorize_execution(
            ctx, approval["decision_id"], _request(ctx, invoice_id, proposal["id"], until), snap
        )
        execute(
            "UPDATE snoozes SET status = 'ACTIVE', prior_reminder_status = %s, approved_by = %s,"
            " activated_at = now() WHERE id = %s",
            [state["reminder_status"], ctx.user_id, proposal["id"]],
        )
        invoice_state.set_follow_up(invoice_id, reminder_status="SNOOZED")
        record(
            ctx,
            "snooze.started",
            "invoice",
            str(invoice_id),
            before={"reminder_status": state["reminder_status"]},
            after={"reminder_status": "SNOOZED", "until": str(until)},
            reason_codes=["APPROVED_BY_PERSON"],
            policy_decision_id=approval["decision_id"],
        )
        outbox.publish(
            ctx, "SnoozeStarted", {"invoice_id": str(invoice_id), "snooze_id": str(proposal["id"])}
        )
        return {"invoice_id": str(invoice_id), "reminder_status": "SNOOZED", "until": until}


def _end_snooze(
    ctx: RequestContext, invoice_id: UUID, reason: str, *, expired: bool = False
) -> dict[str, Any]:
    snooze = fetch_one(
        "SELECT id, prior_reminder_status FROM snoozes"
        " WHERE invoice_id = %s AND status = 'ACTIVE' FOR UPDATE",
        [invoice_id],
    )
    if snooze is None:
        raise _refused("There is no pause to undo on this invoice.")
    state = fetch_one("SELECT reminder_status FROM invoice_state WHERE invoice_id = %s", [invoice_id])
    assert state
    execute(
        "UPDATE snoozes SET status = %s, ended_at = now() WHERE id = %s",
        ["ENDED" if expired else "UNDONE", snooze["id"]],
    )
    restored = state["reminder_status"]
    if restored == "SNOOZED":  # a dispute or a payment claim may have suppressed it since; that stays
        restored = snooze["prior_reminder_status"]
        invoice_state.set_follow_up(invoice_id, reminder_status=restored)
    record(
        ctx,
        "snooze.expired" if expired else "snooze.undone",
        "invoice",
        str(invoice_id),
        before={"reminder_status": state["reminder_status"]},
        after={"reminder_status": restored, "reason": reason},
        reason_codes=["PAUSE_DATE_PASSED" if expired else "UNDONE_BY_PERSON"],
    )
    outbox.publish(ctx, "SnoozeEnded", {"invoice_id": str(invoice_id), "snooze_id": str(snooze["id"])})
    return {"invoice_id": str(invoice_id), "reminder_status": restored}


def end_active_snooze(ctx: RequestContext, invoice_id: UUID, reason: str) -> bool:
    """Ends a running pause if there is one, in the caller's transaction. Used when a case makes it moot."""
    active = fetch_one(
        "SELECT 1 AS ok FROM snoozes WHERE invoice_id = %s AND status = 'ACTIVE'", [invoice_id]
    )
    if active is None:
        return False
    _end_snooze(ctx, invoice_id, reason)
    return True


def end_expired_snoozes(ctx: RequestContext) -> int:
    """Nightly: a pause is in force through its last day, then reminders resume. Returns how many ended."""
    with tenant_tx(ctx):
        due = fetch_all(
            "SELECT invoice_id FROM snoozes WHERE status = 'ACTIVE' AND until < %s ORDER BY until, id",
            [clock.today()],
        )
        for row in due:
            fetch_one(
                "SELECT 1 AS ok FROM invoice_state WHERE invoice_id = %s FOR UPDATE", [row["invoice_id"]]
            )
            _end_snooze(ctx, row["invoice_id"], "The pause date passed.", expired=True)
        return len(due)


def undo_snooze(ctx: RequestContext, invoice_id: UUID, reason: str | None = None) -> dict[str, Any]:
    authorize(ctx, MESSAGES_WRITE)
    if ctx.user_id is None:
        raise ProblemError("FORBIDDEN", 403, "Only a person can undo a pause.")
    with tenant_tx(ctx):
        if (
            fetch_one("SELECT 1 AS ok FROM invoice_state WHERE invoice_id = %s FOR UPDATE", [invoice_id])
            is None
        ):
            raise _not_found()
        return _end_snooze(ctx, invoice_id, reason or "Undone by a person")
