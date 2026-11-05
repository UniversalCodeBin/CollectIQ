"""Disputes and blockers (E076-E082).

A person resolves a case and a person chooses to resume follow-ups; automation may only open or reopen.
Resolving never resumes reminders (BR-60, FR-126), and resuming never sends anything.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

from collectiq.audit import record
from collectiq.invoices import state as invoice_state
from collectiq.platform import clock, outbox
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.policy import service as policy_service
from collectiq.policy.domain import ActionRequest, ActionType, Actor, ActorKind, StateSnapshot
from collectiq.tenancy.permissions import CASE_NOTE, CASE_OPEN, CASE_RESOLVE, CASES_READ, authorize

BLOCKER_TYPES = ("MISSING_DOCUMENT", "QUESTION", "PROPOSAL")
CASE_TYPES = ("DISPUTE", *BLOCKER_TYPES)
OPEN_STATUSES = ("OPEN", "IN_REVIEW", "AWAITING_CUSTOMER")
OUTCOMES = ("NO_CHANGE", "INVOICE_CORRECTED", "ADJUSTMENT_AGREED", "WITHDRAWN_BY_CUSTOMER", "OTHER")
# TS-034: a proposed default, the owner's to change. The wait begins when a person resolves the dispute.
COOLING_OFF = timedelta(hours=24)

_COLUMNS = (
    "c.id, c.invoice_id, c.type, c.status, c.dispute_type, c.summary, c.source_message_id, c.assignee_id,"
    " c.opened_by_kind, c.opened_by, c.opened_at, c.resolution_outcome, c.resolution_note, c.resolved_by,"
    " c.resolved_at, c.reopen_count, c.version, i.invoice_number"
)
_FROM = " FROM cases c JOIN invoices i ON i.id = c.invoice_id AND i.workspace_id = c.workspace_id"


def _not_found() -> ProblemError:
    return ProblemError("NOT_FOUND", 404, "We could not find that.")


def _refused(detail: str) -> ProblemError:
    return ProblemError("STATE_TRANSITION_INVALID", 409, detail)


def _dto(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "id": str(row["id"]),
        "invoice_id": str(row["invoice_id"]),
        "assignee_id": str(row["assignee_id"]) if row["assignee_id"] else None,
        "opened_by": str(row["opened_by"]) if row["opened_by"] else None,
        "resolved_by": str(row["resolved_by"]) if row["resolved_by"] else None,
        "source_message_id": str(row["source_message_id"]) if row["source_message_id"] else None,
        # A summary typed by a person is theirs; one written for an automated opener is labelled as such.
        "summary_is_ai_derived": row["opened_by_kind"] == "AI",
    }


def _visible(ctx: RequestContext, row: dict[str, Any]) -> bool:
    return ctx.role != "PROJECT_LEAD" or row["assignee_id"] == ctx.user_id


def _get_row(case_id: UUID, lock: bool = False) -> dict[str, Any]:
    row = fetch_one(
        f"SELECT {_COLUMNS}{_FROM} WHERE c.id = %s" + (" FOR UPDATE OF c" if lock else ""),  # noqa: S608
        [case_id],
    )
    if row is None:
        raise _not_found()
    return row


def _notes(case_id: UUID) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id, author_id, kind, body, created_at FROM case_notes "
        "WHERE case_id = %s ORDER BY created_at, id",
        [case_id],
    )
    return [{**r, "id": str(r["id"]), "author_id": str(r["author_id"])} for r in rows]


def _lock_state(invoice_id: UUID) -> dict[str, Any]:
    row = fetch_one(
        "SELECT s.dispute_status, s.reminder_status, s.version, s.payment_status, i.status AS lifecycle"
        "  FROM invoice_state s JOIN invoices i ON i.id = s.invoice_id AND i.workspace_id = s.workspace_id"
        " WHERE s.invoice_id = %s FOR UPDATE OF s",
        [invoice_id],
    )
    if row is None:
        raise _not_found()
    return row


def _note(ctx: RequestContext, case_id: UUID, kind: str, body: str) -> None:
    if ctx.user_id is not None:  # a note has an author; an automated opener leaves the summary only
        execute(
            "INSERT INTO case_notes (workspace_id, case_id, author_id, kind, body, created_at) "
            "VALUES (%s, %s, %s, %s, %s, clock_timestamp())",
            [ctx.workspace_id, case_id, ctx.user_id, kind, body],
        )


def _open_count(invoice_id: UUID, kind: str) -> int:
    where = "type = 'DISPUTE'" if kind == "DISPUTE" else "type <> 'DISPUTE'"
    row = fetch_one(
        f"SELECT count(*) AS n FROM cases WHERE invoice_id = %s AND status <> 'RESOLVED' AND {where}",  # noqa: S608
        [invoice_id],
    )
    assert row
    return int(row["n"])


def _opener_kind(ctx: RequestContext) -> str:
    return ctx.actor_type if ctx.actor_type in ("USER", "SYSTEM", "AI") else "SYSTEM"


# --- reads (E076, E077) ---


def list_cases(
    ctx: RequestContext,
    limit: int,
    cursor: UUID | None,
    status: str | None = None,
    invoice_id: UUID | None = None,
) -> dict[str, Any]:
    authorize(ctx, CASES_READ)
    with tenant_tx(ctx):
        rows = fetch_all(
            f"SELECT {_COLUMNS}{_FROM}"  # noqa: S608
            " WHERE (%(cursor)s::uuid IS NULL OR c.id > %(cursor)s::uuid)"
            "   AND (%(status)s::text IS NULL OR c.status = %(status)s::text)"
            "   AND (%(invoice)s::uuid IS NULL OR c.invoice_id = %(invoice)s::uuid)"
            "   AND (%(limited)s::boolean IS FALSE OR c.assignee_id = %(user)s::uuid)"
            " ORDER BY c.id LIMIT %(limit)s",
            {
                "cursor": cursor,
                "status": status,
                "invoice": invoice_id,
                "limited": ctx.role == "PROJECT_LEAD",
                "user": ctx.user_id,
                "limit": limit + 1,
            },
        )
    page = rows[:limit]
    return {
        "items": [_dto(r) for r in page],
        "next_cursor": str(page[-1]["id"]) if len(rows) > limit else None,
    }


def get_case(ctx: RequestContext, case_id: UUID) -> dict[str, Any]:
    authorize(ctx, CASES_READ)
    with tenant_tx(ctx):
        row = _get_row(case_id)
        if not _visible(ctx, row):
            raise _not_found()  # INV: a limited member learns nothing about a case that is not theirs.
        return {**_dto(row), "notes": _notes(case_id)}


# --- open (E078) ---


def open_case(
    ctx: RequestContext,
    invoice_id: UUID,
    case_type: str,
    summary: str,
    dispute_type: str | None = None,
    source_message_id: UUID | None = None,
) -> dict[str, Any]:
    authorize(ctx, CASE_OPEN)
    if case_type not in CASE_TYPES:
        raise ProblemError("VALIDATION_FAILED", 422, "This kind of case is not recognised.")
    with tenant_tx(ctx):
        state = _lock_state(invoice_id)
        if state["lifecycle"] != "ACTIVE":
            raise _refused("A cancelled or archived invoice cannot have a case opened on it.")
        if case_type == "DISPUTE":
            dispute_type = dispute_type or "OTHER"
            if _open_count(invoice_id, "DISPUTE"):
                raise ProblemError("DUPLICATE_RESOURCE", 409, "This invoice already has an open dispute.")
        elif dispute_type is not None:
            raise ProblemError("VALIDATION_FAILED", 422, "Only a dispute has a dispute type.")
        row = fetch_one(
            "INSERT INTO cases (workspace_id, invoice_id, type, dispute_type, summary, source_message_id,"
            " opened_by_kind, opened_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            [
                ctx.workspace_id,
                invoice_id,
                case_type,
                dispute_type,
                summary,
                source_message_id,
                _opener_kind(ctx),
                ctx.user_id,
            ],
        )
        assert row
        case_id = row["id"]
        _suppress(invoice_id, state, case_type)
        record(
            ctx,
            "case.opened",
            "case",
            str(case_id),
            after={"type": case_type, "status": "OPEN", "invoice_id": str(invoice_id)},
            reason_codes=["DISPUTE_OPENED" if case_type == "DISPUTE" else "BLOCKER_OPENED"],
        )
        outbox.publish(
            ctx, "CaseOpened", {"case_id": str(case_id), "invoice_id": str(invoice_id), "type": case_type}
        )
        return {**_dto(_get_row(case_id)), "notes": _notes(case_id)}


def _suppress(invoice_id: UUID, state: dict[str, Any], case_type: str) -> None:
    """Routine reminders stop (G4/G5). Drafts and snoozes are cancelled by the subscribers of CaseOpened."""
    invoice_state.set_follow_up(
        invoice_id,
        dispute_status="OPEN" if case_type == "DISPUTE" else None,
        reminder_status="SUPPRESSED" if state["reminder_status"] != "RESOLVED" else None,
    )


# --- update (E079) ---

_MOVES = {"OPEN", "IN_REVIEW", "AWAITING_CUSTOMER"}


def update_case(
    ctx: RequestContext,
    case_id: UUID,
    version: int,
    assignee_id: UUID | None = None,
    status: str | None = None,
    note: str | None = None,
    assignee_given: bool = False,
) -> dict[str, Any]:
    authorize(ctx, CASE_NOTE)
    with tenant_tx(ctx):
        row = _get_row(case_id, lock=True)
        if not _visible(ctx, row):
            raise _not_found()
        if row["version"] != version:
            raise ProblemError("CONFLICT_VERSION", 409, "This case changed. Reload and try again.")
        if row["status"] == "RESOLVED":
            raise _refused("A resolved case is reopened before it can change.")
        if ctx.role == "PROJECT_LEAD" and (assignee_given or status is not None):
            # A project lead adds notes to the cases assigned to them; routing and status are finance's.
            raise ProblemError("FORBIDDEN", 403, "You can add notes to this case.")
        if status is not None and status not in _MOVES:
            raise ProblemError(
                "VALIDATION_FAILED", 422, "A case is resolved with its outcome, not by a status change."
            )
        if assignee_given and assignee_id is not None:
            member = fetch_one(
                "SELECT 1 AS ok FROM workspace_memberships WHERE user_id = %s AND status = 'ACTIVE'",
                [assignee_id],
            )
            if member is None:
                raise ProblemError("VALIDATION_FAILED", 422, "That person is not a member of this workspace.")
        before = {
            "status": row["status"],
            "assignee_id": str(row["assignee_id"]) if row["assignee_id"] else None,
        }
        new_status = status or row["status"]
        new_assignee = assignee_id if assignee_given else row["assignee_id"]
        if new_status != row["status"] or new_assignee != row["assignee_id"]:
            execute(
                "UPDATE cases SET status = %s, assignee_id = %s, version = version + 1, updated_at = now()"
                " WHERE id = %s",
                [new_status, new_assignee, case_id],
            )
        elif note is None:
            return {**_dto(row), "notes": _notes(case_id)}
        else:
            execute("UPDATE cases SET version = version + 1, updated_at = now() WHERE id = %s", [case_id])
        if new_status != row["status"]:
            _note(ctx, case_id, "STATUS", f"Status changed to {new_status}.")
            if row["type"] == "DISPUTE":
                invoice_state.set_follow_up(row["invoice_id"], dispute_status=new_status)
        if new_assignee != row["assignee_id"]:
            _note(ctx, case_id, "ASSIGNMENT", "Assignee changed.")
            if new_assignee is not None:
                outbox.publish(
                    ctx, "CaseAssigned", {"case_id": str(case_id), "assignee_id": str(new_assignee)}
                )
        if note:
            _note(ctx, case_id, "NOTE", note)
        record(
            ctx,
            "case.status_changed" if new_status != row["status"] else "case.updated",
            "case",
            str(case_id),
            before=before,
            after={"status": new_status, "assignee_id": str(new_assignee) if new_assignee else None},
        )
        return {**_dto(_get_row(case_id)), "notes": _notes(case_id)}


# --- resolve and reopen (E080, E081) ---


def resolve_case(ctx: RequestContext, case_id: UUID, outcome: str, note: str | None) -> dict[str, Any]:
    authorize(ctx, CASE_RESOLVE)
    if ctx.actor_type != "USER" or ctx.user_id is None:
        raise ProblemError("FORBIDDEN", 403, "Only a person can resolve a case.")  # INV: BR-60
    if outcome not in OUTCOMES:
        raise ProblemError("VALIDATION_FAILED", 422, "This outcome is not recognised.")
    with tenant_tx(ctx):
        row = _get_row(case_id, lock=True)
        if row["status"] == "RESOLVED":
            raise _refused("This case is already resolved.")
        state = _lock_state(row["invoice_id"])
        execute(
            "UPDATE cases SET status = 'RESOLVED', resolution_outcome = %s, resolution_note = %s,"
            " resolved_by = %s, resolved_at = %s, version = version + 1, updated_at = now() WHERE id = %s",
            [outcome, note, ctx.user_id, clock.now(), case_id],
        )
        _note(ctx, case_id, "RESOLUTION", note or f"Resolved: {outcome}.")
        if row["type"] == "DISPUTE":
            # The dispute is over, but reminders stay off until a person chooses to resume (FR-126).
            invoice_state.set_follow_up(row["invoice_id"], dispute_status="RESOLVED")
        elif not _open_count(row["invoice_id"], "BLOCKER") and state["dispute_status"] == "NONE":
            invoice_state.set_follow_up(row["invoice_id"], reminder_status="NOT_CONTACTED")
        record(
            ctx,
            "case.resolved",
            "case",
            str(case_id),
            before={"status": row["status"]},
            after={"status": "RESOLVED", "outcome": outcome},
            reason_codes=[outcome],
        )
        outbox.publish(ctx, "CaseResolved", {"case_id": str(case_id), "invoice_id": str(row["invoice_id"])})
        return {**_dto(_get_row(case_id)), "notes": _notes(case_id)}


def reopen_case(ctx: RequestContext, case_id: UUID, reason: str) -> dict[str, Any]:
    """A person reopens from the case; a later dispute-like message reopens through here as AI or SYSTEM."""
    authorize(ctx, CASE_RESOLVE if ctx.actor_type == "USER" else CASE_OPEN)
    with tenant_tx(ctx):
        row = _get_row(case_id, lock=True)
        if row["status"] != "RESOLVED":
            raise _refused("Only a resolved case can be reopened.")
        state = _lock_state(row["invoice_id"])
        if row["type"] == "DISPUTE" and _open_count(row["invoice_id"], "DISPUTE"):
            raise ProblemError("DUPLICATE_RESOURCE", 409, "This invoice already has an open dispute.")
        execute(
            "UPDATE cases SET status = 'OPEN', resolution_outcome = NULL, resolution_note = NULL,"
            " resolved_by = NULL, resolved_at = NULL, reopen_count = reopen_count + 1, version = version + 1,"
            " updated_at = now() WHERE id = %s",
            [case_id],
        )
        _note(ctx, case_id, "REOPEN", reason)
        _suppress(row["invoice_id"], state, row["type"])
        record(
            ctx,
            "case.reopened",
            "case",
            str(case_id),
            before={"status": "RESOLVED", "outcome": row["resolution_outcome"]},
            after={"status": "OPEN"},
            reason_codes=["CASE_REOPENED"],
        )
        outbox.publish(
            ctx,
            "CaseOpened",
            {"case_id": str(case_id), "invoice_id": str(row["invoice_id"]), "type": row["type"]},
        )
        return {**_dto(_get_row(case_id)), "notes": _notes(case_id)}


# --- resume follow-ups (E082) ---


def invoice_snapshot(invoice_id: UUID) -> StateSnapshot:
    """What the gates need to know about disputes and blockers, read under the caller's invoice lock."""
    state = fetch_one(
        "SELECT s.dispute_status, s.version, s.payment_status, i.status AS lifecycle"
        "  FROM invoice_state s JOIN invoices i ON i.id = s.invoice_id AND i.workspace_id = s.workspace_id"
        " WHERE s.invoice_id = %s",
        [invoice_id],
    )
    if state is None:
        raise _not_found()
    resolved = fetch_one(
        "SELECT max(resolved_at) AS at FROM cases WHERE invoice_id = %s AND type = 'DISPUTE'", [invoice_id]
    )
    assert resolved
    cooled = state["dispute_status"] != "RESOLVED" or (
        resolved["at"] is not None and resolved["at"] + COOLING_OFF <= clock.now()
    )
    return StateSnapshot(
        lifecycle=state["lifecycle"],
        payment_status=state["payment_status"],
        dispute_status=state["dispute_status"],
        dispute_cooled_off=cooled,
        open_blocker=_open_count(invoice_id, "BLOCKER") > 0,
        state_version=state["version"],
    )


def _resume_request(ctx: RequestContext, invoice_id: UUID) -> ActionRequest:
    return ActionRequest(
        ActionType.RESUME_FOLLOWUPS,
        Actor(ActorKind.HUMAN, str(ctx.user_id), ctx.role),
        f"invoice:{invoice_id}",
        {},
    )


def request_resume(ctx: RequestContext, invoice_id: UUID) -> dict[str, Any]:
    """Asks the policy engine whether follow-ups may resume. A person still approves, then calls resume."""
    authorize(ctx, CASE_RESOLVE)
    with tenant_tx(ctx):
        _lock_state(invoice_id)
        snap = invoice_snapshot(invoice_id)
        if snap.dispute_status != "RESOLVED":
            raise _refused("Follow-ups can resume once the dispute has been resolved.")
        return policy_service.decide(ctx, _resume_request(ctx, invoice_id), snap)


def resume_followups(ctx: RequestContext, invoice_id: UUID, approval_id: UUID) -> dict[str, Any]:
    authorize(ctx, CASE_RESOLVE)
    if ctx.actor_type != "USER" or ctx.user_id is None:
        raise ProblemError("FORBIDDEN", 403, "Only a person can resume follow-ups.")
    with tenant_tx(ctx):
        state = _lock_state(invoice_id)
        approval = fetch_one(
            "SELECT a.decision_id, a.status, d.action_type, d.subject FROM approval_requests a"
            "  JOIN policy_decisions d ON d.id = a.decision_id AND d.workspace_id = a.workspace_id"
            " WHERE a.id = %s",
            [approval_id],
        )
        if approval is None:
            raise _not_found()
        if (
            approval["action_type"] != ActionType.RESUME_FOLLOWUPS
            or approval["subject"] != f"invoice:{invoice_id}"
        ):
            raise _refused("This approval is for something else.")
        if state["dispute_status"] != "RESOLVED":
            raise _refused("Follow-ups can resume once the dispute has been resolved.")
        snap = invoice_snapshot(invoice_id)
        # Re-checks everything under the lock, then spends the decision. Fails closed with POLICY_BLOCKED.
        policy_service.authorize_execution(
            ctx, approval["decision_id"], _resume_request(ctx, invoice_id), snap
        )
        invoice_state.set_follow_up(invoice_id, dispute_status="NONE", reminder_status="NOT_CONTACTED")
        record(
            ctx,
            "followups.resumed",
            "invoice",
            str(invoice_id),
            before={"dispute_status": "RESOLVED", "reminder_status": state["reminder_status"]},
            after={"dispute_status": "NONE", "reminder_status": "NOT_CONTACTED"},
            reason_codes=["RESUMED_BY_PERSON"],
            policy_decision_id=approval["decision_id"],
        )
        outbox.publish(ctx, "FollowupsResumed", {"invoice_id": str(invoice_id)})
        return {"invoice_id": str(invoice_id), "dispute_status": "NONE", "reminder_status": "NOT_CONTACTED"}
