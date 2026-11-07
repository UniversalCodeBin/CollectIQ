"""Reminders and manual handoff (E083-E089).

The system drafts from a fixed template; a person edits, approves, sends it by hand somewhere else, and then
records that they did. Approving never sends, and nothing reaches MARKED_SENT except `mark_sent`. There is
no scheduler and no send path (INV-13). Every approval and every hand-off re-reads the invoice under its
lock and runs the gates again, so what was true when the draft was made is never taken on trust (TOCTOU).
"""

import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from collectiq.audit import record
from collectiq.cases import service as cases
from collectiq.invoices import state as invoice_state
from collectiq.platform import clock, outbox
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.platform.money import currency_exponent
from collectiq.policy import service as policy
from collectiq.policy.domain import (
    ActionRequest,
    ActionType,
    Actor,
    ActorKind,
    Outcome,
    PolicyDecision,
    StateSnapshot,
    evaluate,
)
from collectiq.tenancy.permissions import DRAFT_APPROVE, DRAFT_CREATE, DRAFT_READ, authorize

from . import service_pause
from .domain.linter import lint_reminder

DEFAULT_CADENCE_DAYS = (3, 10, 17)  # after the due date: the first, second and third reminder
CONTACT_WINDOW = timedelta(days=7)
METHODS = ("EMAIL", "WHATSAPP", "PHONE", "OTHER")
LIVE = ("DRAFT", "APPROVED")
CASE_OPENED = "CaseOpened"
INVOICE_CHANGED = "InvoiceChanged"
ALLOCATION_CONFIRMED = "AllocationConfirmed"
ALLOCATION_REVERSED = "AllocationReversed"
SNOOZE_STARTED = "SnoozeStarted"

_COLUMNS = (
    "r.id, r.invoice_id, r.contact_id, r.sequence, r.intended_date, r.status, r.subject, r.body,"
    " r.fact_block,"
    " r.approved_by, r.approved_at, r.sent_at, r.method, r.marked_by, r.reason, r.version, r.created_at,"
    " i.invoice_number, c.email AS recipient"
)
_FROM = (
    " FROM reminders r JOIN invoices i ON i.id = r.invoice_id AND i.workspace_id = r.workspace_id"
    " JOIN client_contacts c ON c.id = r.contact_id AND c.workspace_id = r.workspace_id"
)


def _not_found() -> ProblemError:
    return ProblemError("NOT_FOUND", 404, "We could not find that.")


def _refused(detail: str) -> ProblemError:
    return ProblemError("POLICY_BLOCKED", 409, detail)


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _dto(row: dict[str, Any]) -> dict[str, Any]:
    facts = _json(row["fact_block"])
    return {
        "id": row["id"],
        "invoice_id": row["invoice_id"],
        "invoice_number": row["invoice_number"],
        "contact_id": row["contact_id"],
        "recipient": row["recipient"],
        "sequence": row["sequence"],
        "intended_date": row["intended_date"],
        "status": row["status"],
        "subject": row["subject"],
        "body": row["body"],
        "fact_block": facts,
        "approved_by": row["approved_by"],
        "approved_at": row["approved_at"],
        "sent_at": row["sent_at"],
        "method": row["method"],
        "marked_by": row["marked_by"],
        "reason": row["reason"],
        "version": row["version"],
        "created_at": row["created_at"],
    }


# ---- facts, template, key ---------------------------------------------------------------------------


def _facts(invoice_id: UUID | str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT i.invoice_number, i.currency, i.due_date, s.outstanding_minor"
        "  FROM invoices i JOIN invoice_state s ON s.invoice_id = i.id AND s.workspace_id = i.workspace_id"
        " WHERE i.id = %s",
        [invoice_id],
    )
    if row is None:
        raise _not_found()
    exponent = currency_exponent(row["currency"])
    amount = row["outstanding_minor"] / (10**exponent)
    plain = f"{amount:.{exponent}f}"
    return {
        "invoice_number": row["invoice_number"],
        "outstanding_minor": row["outstanding_minor"],
        "currency": row["currency"],
        "due_date": row["due_date"].isoformat(),
        "amount_plain": plain,
        "amount_text": f"{row['currency']} {amount:,.{exponent}f}",
    }


def _fact_hash(facts: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()


def _sign_off(ctx: RequestContext) -> str:
    """Who the note is from: the sender name, else the workspace name, with the legal name beneath."""
    row = fetch_one("SELECT name, legal_name, sender_name FROM workspaces WHERE id = %s", [ctx.workspace_id])
    if row is None:
        return "Thank you."
    lines = [row["sender_name"] or row["name"]]
    if row["legal_name"] and row["legal_name"] != lines[0]:
        lines.append(row["legal_name"])
    return "Thank you,\n" + "\n".join(lines)


def _template(
    facts: dict[str, Any], contact_name: str | None, overdue_days: int, sign_off: str = "Thank you."
) -> tuple[str, str]:
    subject = f"Payment reminder: invoice {facts['invoice_number']}"
    late = f"{overdue_days} days past" if overdue_days > 0 else "at"
    body = (
        f"Hello {contact_name or 'there'},\n\n"
        f"This is a friendly reminder that invoice {facts['invoice_number']} for {facts['amount_text']} "
        f"was due on {facts['due_date']} and is now {late} its due date.\n\n"
        "If you have already arranged payment, please ignore this note, or reply with the details so we can "
        "check our records. If anything about the invoice is unclear, tell us and we will help.\n\n"
        f"{sign_off}"
    )
    return subject, body


def _idempotency_key(workspace_id: UUID | str, invoice_id: UUID | str, sequence: int, intended: date) -> str:
    raw = f"{workspace_id}|{invoice_id}|{ActionType.SEND_REMINDER}|{sequence}|{intended.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ---- the snapshot the gates read --------------------------------------------------------------------


def _in_business_hours(ctx: RequestContext, config: Any) -> bool:
    """An empty or unreadable configuration means no restriction; a reading that is clear is applied."""
    if not isinstance(config, dict) or not config:
        return True
    try:
        start = time.fromisoformat(str(config["start"]))
        end = time.fromisoformat(str(config["end"]))
        workspace = fetch_one("SELECT timezone FROM workspaces WHERE id = %s", [ctx.workspace_id])
        local = clock.now().astimezone(ZoneInfo(workspace["timezone"] if workspace else "UTC"))
        days = config.get("days")
        if isinstance(days, list) and days and local.isoweekday() not in days:
            return False
        return start <= local.time() < end
    except (KeyError, ValueError, TypeError):
        return True


def _recipient_ok(contact_id: UUID | None) -> bool:
    if contact_id is None:
        return False
    row = fetch_one("SELECT email, status FROM client_contacts WHERE id = %s", [contact_id])
    if row is None or row["status"] != "ACTIVE":
        return False
    blocked = fetch_one(
        "SELECT 1 AS blocked FROM client_contacts WHERE email = %s AND status = 'SUPPRESSED' LIMIT 1",
        [row["email"]],
    )
    return blocked is None


def _lock_invoice(invoice_id: UUID | str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT s.evidence_coverage, s.reminder_status, i.client_id, i.due_date"
        "  FROM invoice_state s JOIN invoices i ON i.id = s.invoice_id AND i.workspace_id = s.workspace_id"
        " WHERE s.invoice_id = %s FOR UPDATE OF s",
        [invoice_id],
    )
    if row is None:
        raise _not_found()
    return row


def _snapshot(
    ctx: RequestContext,
    invoice_id: UUID | str,
    invoice: dict[str, Any],
    contact_id: UUID | None,
    *,
    key: str | None,
    facts_valid: bool,
    contact_checks: bool,
) -> StateSnapshot:
    snap = cases.invoice_snapshot(UUID(str(invoice_id)))
    snoozed = fetch_one(
        "SELECT 1 AS ok FROM snoozes WHERE invoice_id = %s AND status = 'ACTIVE'", [invoice_id]
    )
    sent = fetch_one(
        "SELECT count(*) AS n FROM reminders r JOIN invoices i ON i.id = r.invoice_id"
        " WHERE i.client_id = %s AND r.status IN ('MARKED_SENT', 'SUBMITTED')"
        " AND COALESCE(r.sent_at, r.submitted_at) >= %s",
        [invoice["client_id"], clock.now() - CONTACT_WINDOW],
    )
    used = (
        fetch_one(
            "SELECT 1 AS ok FROM reminders WHERE idempotency_key = %s"
            " AND status IN ('MARKED_SENT', 'SUBMITTED', 'SUBMISSION_UNKNOWN')",
            [key],
        )
        if key
        else None
    )
    hours = policy.active_settings(ctx).get("business_hours")
    assert sent
    return replace(
        snap,
        coverage=invoice["evidence_coverage"],
        snooze_active=snoozed is not None,
        hold_scope=service_pause.hold_scope(invoice_id, invoice["client_id"]),
        recipient_approved=_recipient_ok(contact_id),
        recipient_suppressed=False,
        contacts_in_window=sent["n"] if contact_checks else 0,
        in_business_hours=_in_business_hours(ctx, hours) if contact_checks else True,
        draft_facts_valid=facts_valid,
        idempotency_key_used=used is not None,
    )


def _request(ctx: RequestContext, action: ActionType, invoice_id: UUID | str) -> ActionRequest:
    return ActionRequest(
        action, Actor(ActorKind.HUMAN, str(ctx.user_id), ctx.role), f"invoice:{invoice_id}", {}
    )


def _decision_dto(decision: PolicyDecision) -> dict[str, Any]:
    return {
        "outcome": decision.outcome,
        "reasons": list(decision.reasons),
        "gate_results": [
            {"gate": g.gate, "passed": g.passed, "reason": g.reason} for g in decision.gate_results
        ],
    }


def _gate(
    ctx: RequestContext, action: ActionType, invoice_id: UUID | str, snap: StateSnapshot
) -> PolicyDecision:
    return evaluate(_request(ctx, action, invoice_id), snap, policy.active_policy(ctx))


def _require_clear(decision: PolicyDecision) -> None:
    """A person is the approver here; every gate must be clear, which the engine reports as this outcome."""
    if decision.outcome != Outcome.REQUIRE_APPROVAL:
        raise _refused(
            "This reminder cannot go ahead now: " + ", ".join(decision.reasons or ["see the gates"])
        )


# ---- reads ------------------------------------------------------------------------------------------


def list_reminders(ctx: RequestContext, limit: int, cursor: UUID | None) -> dict[str, Any]:
    authorize(ctx, DRAFT_READ)
    with tenant_tx(ctx):
        rows = fetch_all(
            f"SELECT {_COLUMNS}{_FROM}"  # noqa: S608
            " WHERE (%(cursor)s::uuid IS NULL OR r.id > %(cursor)s::uuid)"
            "   AND (%(limited)s::boolean IS FALSE OR FALSE)"
            " ORDER BY r.id LIMIT %(limit)s",
            {"cursor": cursor, "limited": ctx.role == "PROJECT_LEAD", "limit": limit + 1},
        )
    page = rows[:limit]
    return {
        "items": [_dto(r) for r in page],
        "next_cursor": str(page[-1]["id"]) if len(rows) > limit else None,
    }


def _get_row(reminder_id: UUID, lock: bool = False) -> dict[str, Any]:
    row = fetch_one(
        f"SELECT {_COLUMNS}{_FROM} WHERE r.id = %s" + (" FOR UPDATE OF r" if lock else ""),  # noqa: S608
        [reminder_id],
    )
    if row is None:
        raise _not_found()
    return row


def get_reminder(ctx: RequestContext, reminder_id: UUID) -> dict[str, Any]:
    authorize(ctx, DRAFT_READ)
    with tenant_tx(ctx):
        row = _get_row(reminder_id)
        if ctx.role == "PROJECT_LEAD":
            raise _not_found()  # A limited member learns nothing about a reminder.
        invoice = _lock_invoice(row["invoice_id"]) if row["status"] in LIVE else None
        gates = None
        if invoice is not None:
            facts = _facts(row["invoice_id"])
            snap = _snapshot(
                ctx,
                row["invoice_id"],
                invoice,
                row["contact_id"],
                key=None,
                facts_valid=_fact_hash(facts) == _fact_hash(_json(row["fact_block"])),
                contact_checks=True,
            )
            gates = _decision_dto(_gate(ctx, ActionType.SEND_REMINDER, row["invoice_id"], snap))
        return {**_dto(row), "gates": gates}


# ---- evaluate (E085) --------------------------------------------------------------------------------


def _next_sequence(invoice_id: UUID | str) -> int:
    row = fetch_one(
        "SELECT count(*) AS n FROM reminders WHERE invoice_id = %s AND status = 'MARKED_SENT'", [invoice_id]
    )
    assert row
    return row["n"] + 1


def _cadence(ctx: RequestContext) -> tuple[int, ...]:
    raw = policy.active_settings(ctx).get("cadence", {}).get("days_after_due")
    if isinstance(raw, list) and raw and all(isinstance(d, int) and d >= 0 for d in raw):
        return tuple(raw)
    return DEFAULT_CADENCE_DAYS


def _first_contact(client_id: UUID) -> dict[str, Any] | None:
    return fetch_one(
        "SELECT id, name FROM client_contacts WHERE client_id = %s AND status = 'ACTIVE'"
        " ORDER BY created_at, id LIMIT 1",
        [client_id],
    )


def _record_evaluated(ctx: RequestContext, invoice_id: UUID, decision: PolicyDecision, result: str) -> None:
    """An evaluation that makes no draft still leaves a trace: what the policy said and why."""
    record(
        ctx,
        "reminder.evaluated",
        "invoice",
        str(invoice_id),
        after={"outcome": str(decision.outcome), "result": result},
        reason_codes=list(decision.reasons or [])[:10],
    )


def evaluate_invoice(ctx: RequestContext, invoice_id: UUID) -> dict[str, Any]:
    authorize(ctx, DRAFT_CREATE)
    with tenant_tx(ctx):
        invoice = _lock_invoice(invoice_id)
        sequence = _next_sequence(invoice_id)
        cadence = _cadence(ctx)
        offset = cadence[min(sequence, len(cadence)) - 1]
        intended = invoice["due_date"] + timedelta(days=offset)
        key = _idempotency_key(ctx.workspace_id, invoice_id, sequence, intended)
        existing = fetch_one(
            "SELECT id FROM reminders WHERE idempotency_key = %s AND status IN ('DRAFT', 'APPROVED')", [key]
        )
        contact = _first_contact(invoice["client_id"])
        facts = _facts(invoice_id)
        snap = _snapshot(
            ctx,
            invoice_id,
            invoice,
            contact["id"] if contact else None,
            key=key,
            facts_valid=True,
            contact_checks=True,
        )
        decision = _gate(ctx, ActionType.SEND_REMINDER, invoice_id, snap)
        result: dict[str, Any] = {**_decision_dto(decision), "invoice_id": invoice_id, "reminder": None}
        if existing is not None:  # TS-014: a retry returns the record that is already there
            result["reminder"] = _dto(_get_row(existing["id"]))
            _record_evaluated(ctx, invoice_id, decision, "EXISTING")
            return result
        if decision.outcome != Outcome.REQUIRE_APPROVAL or contact is None:
            _record_evaluated(ctx, invoice_id, decision, "NO_DRAFT")
            return result
        overdue = max((clock.today() - invoice["due_date"]).days, 0)
        subject, body = _template(facts, contact["name"], overdue, _sign_off(ctx))
        row = fetch_one(
            "INSERT INTO reminders (workspace_id, invoice_id, contact_id, sequence, intended_date, subject,"
            " body,"
            " fact_block, fact_hash, idempotency_key, state_version, created_by)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s) RETURNING id",
            [
                ctx.workspace_id,
                invoice_id,
                contact["id"],
                sequence,
                intended,
                subject,
                body,
                json.dumps(facts),
                _fact_hash(facts),
                key,
                snap.state_version,
                ctx.user_id,
            ],
        )
        assert row
        if invoice["reminder_status"] in ("NOT_CONTACTED", "WAITING_FOR_CUSTOMER"):
            invoice_state.set_follow_up(invoice_id, reminder_status="DRAFT_READY")
        created = _dto(_get_row(row["id"]))
        record(
            ctx,
            "reminder.drafted",
            "reminder",
            str(row["id"]),
            after={"invoice_id": str(invoice_id), "sequence": sequence, "status": "DRAFT"},
            reason_codes=["TEMPLATE_DRAFT"],
        )
        outbox.publish(
            ctx, "ReminderDrafted", {"reminder_id": str(row["id"]), "invoice_id": str(invoice_id)}
        )
        result["reminder"] = created
        return result


# ---- edit, approve, reject, mark-sent ---------------------------------------------------------------


def _settle_status(invoice_id: UUID | str) -> None:
    """The draft is gone. The invoice goes back to waiting if a reminder was sent, else to not contacted."""
    state = fetch_one("SELECT reminder_status FROM invoice_state WHERE invoice_id = %s", [invoice_id])
    if state is None or state["reminder_status"] != "DRAFT_READY":
        return  # a dispute, a pause or a payment claim has already moved it; that stays
    sent = fetch_one(
        "SELECT 1 AS ok FROM reminders WHERE invoice_id = %s AND status = 'MARKED_SENT' LIMIT 1", [invoice_id]
    )
    invoice_state.set_follow_up(
        invoice_id, reminder_status="WAITING_FOR_CUSTOMER" if sent else "NOT_CONTACTED"
    )


def _key_of(reminder_id: UUID) -> str:
    key = fetch_one("SELECT idempotency_key FROM reminders WHERE id = %s", [reminder_id])
    assert key
    return str(key["idempotency_key"])


def _live_row(reminder_id: UUID) -> dict[str, Any]:
    return _get_row(reminder_id, lock=True)


def edit_reminder(ctx: RequestContext, reminder_id: UUID, version: int, body: str) -> dict[str, Any]:
    authorize(ctx, DRAFT_CREATE)
    with tenant_tx(ctx):
        row = _live_row(reminder_id)
        if row["version"] != version:
            raise ProblemError("CONFLICT_VERSION", 409, "This reminder changed. Reload and try again.")
        if row["status"] != "DRAFT":
            raise _refused("Only a draft can be edited.")
        findings = lint_reminder(body, _json(row["fact_block"]))
        if findings:
            raise ProblemError(
                "VALIDATION_FAILED",
                422,
                "; ".join(f.message for f in findings),
                {"errors": [{"field": "body", "code": f.code, "message": f.message} for f in findings]},
            )
        execute(
            "UPDATE reminders SET body = %s, version = version + 1, updated_at = now() WHERE id = %s",
            [body.strip(), reminder_id],
        )
        record(
            ctx,
            "reminder.edited",
            "reminder",
            str(reminder_id),
            before={"version": row["version"]},
            after={"version": row["version"] + 1},
            reason_codes=["TEXT_EDITED"],
        )
        return _dto(_get_row(reminder_id))


def _live_facts_valid(row: dict[str, Any]) -> bool:
    return _fact_hash(_facts(row["invoice_id"])) == _fact_hash(_json(row["fact_block"]))


def approve_reminder(ctx: RequestContext, reminder_id: UUID) -> dict[str, Any]:
    authorize(ctx, DRAFT_APPROVE)
    if ctx.user_id is None:
        raise ProblemError("FORBIDDEN", 403, "Only a person can approve a reminder.")
    with tenant_tx(ctx):
        row = _live_row(reminder_id)
        if row["status"] == "APPROVED":
            return _dto(row)
        if row["status"] != "DRAFT":
            raise _refused("Only a draft can be approved.")
        invoice = _lock_invoice(row["invoice_id"])
        snap = _snapshot(
            ctx,
            row["invoice_id"],
            invoice,
            row["contact_id"],
            key=None,
            facts_valid=_live_facts_valid(row),
            contact_checks=True,
        )
        decision = _gate(ctx, ActionType.APPROVE_DRAFT, row["invoice_id"], snap)
        _require_clear(decision)
        findings = lint_reminder(row["body"], _json(row["fact_block"]))
        if findings:
            raise ProblemError("VALIDATION_FAILED", 422, "; ".join(f.message for f in findings))
        execute(
            "UPDATE reminders SET status = 'APPROVED', approved_by = %s, approved_at = now(),"
            " version = version + 1, updated_at = now() WHERE id = %s",
            [ctx.user_id, reminder_id],
        )
        record(
            ctx,
            "reminder.approved",
            "reminder",
            str(reminder_id),
            before={"status": "DRAFT"},
            after={"status": "APPROVED"},
            reason_codes=["HUMAN_APPROVED", *decision.reasons],
        )
        return _dto(_get_row(reminder_id))


def reject_reminder(ctx: RequestContext, reminder_id: UUID, reason: str | None) -> dict[str, Any]:
    authorize(ctx, DRAFT_APPROVE)
    with tenant_tx(ctx):
        row = _live_row(reminder_id)
        if row["status"] not in LIVE:
            raise _refused("Only a draft or an approved reminder that has not been sent can be rejected.")
        execute(
            "UPDATE reminders SET status = 'REJECTED', rejected_by = %s, reason = %s, version = version + 1,"
            " updated_at = now() WHERE id = %s",
            [ctx.user_id, reason, reminder_id],
        )
        _settle_status(row["invoice_id"])
        record(
            ctx,
            "reminder.rejected",
            "reminder",
            str(reminder_id),
            before={"status": row["status"]},
            after={"status": "REJECTED"},
            reason_codes=["HUMAN_REJECTED"],
        )
        return _dto(_get_row(reminder_id))


def mark_sent(ctx: RequestContext, reminder_id: UUID, sent_at: datetime, method: str) -> dict[str, Any]:
    """Records that a person sent the approved text themselves. Only this moves a reminder to MARKED_SENT."""
    authorize(ctx, DRAFT_APPROVE)
    if ctx.user_id is None:
        raise ProblemError("FORBIDDEN", 403, "Only a person can record a reminder as sent.")
    if method not in METHODS:
        raise ProblemError("VALIDATION_FAILED", 422, "Choose how it was sent.")
    if sent_at > clock.now() + timedelta(minutes=5):
        raise ProblemError("VALIDATION_FAILED", 422, "The time it was sent cannot be in the future.")
    with tenant_tx(ctx):
        row = _live_row(reminder_id)
        if row["status"] != "APPROVED":
            raise _refused("Approve the reminder before recording it as sent.")
        invoice = _lock_invoice(row["invoice_id"])
        key = fetch_one("SELECT idempotency_key FROM reminders WHERE id = %s", [reminder_id])
        assert key
        snap = _snapshot(
            ctx,
            row["invoice_id"],
            invoice,
            row["contact_id"],
            key=key["idempotency_key"],
            facts_valid=_live_facts_valid(row),
            contact_checks=False,  # recording a send that already happened is not a new contact
        )
        decision = _gate(ctx, ActionType.MARK_SENT, row["invoice_id"], snap)
        _require_clear(decision)
        execute(
            "UPDATE reminders SET status = 'MARKED_SENT', sent_at = %s, method = %s, marked_by = %s,"
            " marked_at = now(), version = version + 1, updated_at = now() WHERE id = %s",
            [sent_at, method, ctx.user_id, reminder_id],
        )
        if invoice["reminder_status"] == "DRAFT_READY":
            invoice_state.set_follow_up(row["invoice_id"], reminder_status="WAITING_FOR_CUSTOMER")
        record(
            ctx,
            "reminder.marked_sent",
            "reminder",
            str(reminder_id),
            before={"status": "APPROVED"},
            after={"status": "MARKED_SENT", "method": method},
            reason_codes=["HUMAN_RECORDED_SEND"],
        )
        outbox.publish(
            ctx, "ReminderMarkedSent", {"reminder_id": str(reminder_id), "invoice_id": str(row["invoice_id"])}
        )
        return _dto(_get_row(reminder_id))


# ---- cancellation when the world changes ------------------------------------------------------------


def _cancel_pending(ctx: RequestContext, invoice_id: str, reason: str, only_stale: bool = False) -> int:
    rows = fetch_all(
        f"SELECT {_COLUMNS}{_FROM} WHERE r.invoice_id = %s AND r.status IN ('DRAFT', 'APPROVED')"  # noqa: S608
        " FOR UPDATE OF r",
        [invoice_id],
    )
    cancelled = 0
    for row in rows:
        if only_stale and _live_facts_valid(row):
            continue
        execute(
            "UPDATE reminders SET status = 'CANCELLED', reason = %s, version = version + 1,"
            " updated_at = now()"
            " WHERE id = %s",
            [reason, row["id"]],
        )
        record(
            ctx,
            "reminder.cancelled",
            "reminder",
            str(row["id"]),
            before={"status": row["status"]},
            after={"status": "CANCELLED"},
            reason_codes=["CANCELLED_BY_CHANGE"],
        )
        cancelled += 1
    if cancelled:
        _settle_status(invoice_id)
    return cancelled


@outbox.subscriber(CASE_OPENED)
def _on_case_opened(ctx: RequestContext, payload: dict[str, Any]) -> None:
    """A dispute or a blocker stops routine follow-up: drafts are cancelled and a pause no longer applies."""
    _cancel_pending(ctx, payload["invoice_id"], "A case was opened on this invoice.")
    from collectiq.conversations import service_commitments  # noqa: PLC0415

    service_commitments.end_active_snooze(ctx, UUID(payload["invoice_id"]), "A case was opened.")


@outbox.subscriber(INVOICE_CHANGED)
def _on_invoice_changed(ctx: RequestContext, payload: dict[str, Any]) -> None:
    _cancel_pending(
        ctx, payload["invoice_id"], "The invoice changed after this was drafted.", only_stale=True
    )


@outbox.subscriber(ALLOCATION_CONFIRMED)
def _on_allocation_confirmed(ctx: RequestContext, payload: dict[str, Any]) -> None:
    for invoice_id in payload["invoice_ids"]:
        _cancel_pending(ctx, invoice_id, "A payment was recorded against this invoice.", only_stale=False)


@outbox.subscriber(ALLOCATION_REVERSED)
def _on_allocation_reversed(ctx: RequestContext, payload: dict[str, Any]) -> None:
    _cancel_pending(
        ctx, payload["invoice_id"], "A payment was reversed after this was drafted.", only_stale=True
    )
