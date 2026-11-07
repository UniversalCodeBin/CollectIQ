"""Customer replies: capture, timeline and what a person's reading of a reply sets in motion (E062-E066).

A reply is the customer's statement, kept as text. A label is a person's reading of it. Neither one
changes a balance, marks anything paid or sends anything (FR-055, INV-1).
"""

import hashlib
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from collectiq.audit import record
from collectiq.cases import service as cases
from collectiq.evidence import service_state
from collectiq.invoices import clients
from collectiq.invoices import state as invoice_state
from collectiq.platform import clock, outbox
from collectiq.platform.context import RequestContext
from collectiq.platform.crypto import get_cipher
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.tenancy.permissions import MESSAGES_LIST, MESSAGES_READ, MESSAGES_WRITE, authorize

from . import parsing

LABELS = (
    "PAYMENT_CLAIM",
    "COMMITMENT_EXPLICIT",
    "EXPECTATION_TENTATIVE",
    "DOCUMENT_REQUEST",
    "DISPUTE",
    "PAUSE_REQUEST",
    "CLARIFICATION_REQUEST",
    "PARTIAL_PAYMENT_PROPOSAL",
    "WRONG_RECIPIENT_OR_OPT_OUT",
    "UNRELATED_OR_AMBIGUOUS",
)
SOURCES = ("PASTE", "EML", "TXT")
_BLOCKERS = {
    "DOCUMENT_REQUEST": "MISSING_DOCUMENT",
    "CLARIFICATION_REQUEST": "QUESTION",
    "PARTIAL_PAYMENT_PROPOSAL": "PROPOSAL",
}
_COLUMNS = "id, source, sender, subject, received_at, uploaded_by, created_at"


def _not_found() -> ProblemError:
    return ProblemError("NOT_FOUND", 404, "We could not find that.")


def _aad(message_id: UUID | str) -> bytes:
    return f"message:{message_id}".encode()


def _body(ctx: RequestContext, row: dict[str, Any]) -> str:
    return get_cipher().decrypt(ctx, bytes(row["body_enc"]), _aad(row["id"])).decode()


def _dto(row: dict[str, Any], associations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "source": row["source"],
        "sender": row["sender"],
        "subject": row["subject"],
        "received_at": row["received_at"],
        "uploaded_by": str(row["uploaded_by"]),
        "created_at": row["created_at"],
        # Always the customer's own words, never a fact the product has checked.
        "is_customer_statement": True,
        "associations": associations,
    }


def _associations(message_ids: list[UUID]) -> dict[UUID, list[dict[str, Any]]]:
    rows = fetch_all(
        "SELECT mi.message_id, mi.invoice_id, mi.labels, i.invoice_number FROM message_invoices mi"
        "  JOIN invoices i ON i.id = mi.invoice_id AND i.workspace_id = mi.workspace_id"
        " WHERE mi.message_id = ANY(%s) ORDER BY mi.created_at, mi.invoice_id",
        [message_ids],
    )
    found: dict[UUID, list[dict[str, Any]]] = {m: [] for m in message_ids}
    for r in rows:
        found[r["message_id"]].append(
            {"invoice_id": str(r["invoice_id"]), "invoice_number": r["invoice_number"], "labels": r["labels"]}
        )
    return found


def _lead_may_see(ctx: RequestContext, invoice_id: UUID) -> bool:
    """A project lead sees the conversation of an invoice only when a case on it is assigned to them."""
    if ctx.role != "PROJECT_LEAD":
        return True
    row = fetch_one(
        "SELECT 1 AS ok FROM cases WHERE invoice_id = %s AND assignee_id = %s LIMIT 1",
        [invoice_id, ctx.user_id],
    )
    return row is not None


# --- capture (E062) ---


def capture(
    ctx: RequestContext,
    source: str,
    *,
    text: str | None = None,
    filename: str | None = None,
    data: bytes | None = None,
    sender: str | None = None,
    subject: str | None = None,
    received_at: datetime | None = None,
    associations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    authorize(ctx, MESSAGES_WRITE)
    if ctx.user_id is None:
        raise ProblemError("FORBIDDEN", 403, "Only a person can add a customer reply.")
    if source not in SOURCES:
        raise ProblemError("VALIDATION_FAILED", 422, "This kind of source is not recognised.")
    if source == "PASTE":
        parsed = parsing.parse_paste(text or "")
    elif data is not None:
        parsed = parsing.parse_upload(filename or "", data)
    else:
        parsed = parsing.Parsed("")
    if not parsed.text:
        raise ProblemError("VALIDATION_FAILED", 422, "There is no text in this reply.")
    message_id = uuid.uuid4()
    body = parsed.text
    sender = (sender or parsed.sender or "").strip()[:320] or None
    subject = (subject or parsed.subject or "").strip()[:500] or None
    when = received_at or parsed.received_at or clock.now()
    with tenant_tx(ctx):
        execute(
            "INSERT INTO messages (id, workspace_id, source, sender, subject, received_at, body_enc,"
            " body_sha256, uploaded_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                message_id,
                ctx.workspace_id,
                source,
                sender,
                subject,
                when,
                get_cipher().encrypt(ctx, body.encode(), _aad(message_id)),
                hashlib.sha256(body.encode()).hexdigest(),
                ctx.user_id,
            ],
        )
        record(
            ctx,
            "message.captured",
            "message",
            str(message_id),
            after={"source": source, "associated": len(associations or [])},
        )
        effects = associate_in_tx(ctx, message_id, associations or [])
        return {**_read(ctx, message_id), "effects": effects}


# --- reads (E063, E064, E065) ---


def _read(ctx: RequestContext, message_id: UUID, with_body: bool = True) -> dict[str, Any]:
    row = fetch_one(
        f"SELECT {_COLUMNS}, body_enc FROM messages WHERE id = %s",  # noqa: S608
        [message_id],
    )
    if row is None:
        raise _not_found()
    out = _dto(row, _associations([message_id])[message_id])
    if with_body:
        out["body"] = _body(ctx, row)
    return out


def get_message(ctx: RequestContext, message_id: UUID) -> dict[str, Any]:
    authorize(ctx, MESSAGES_READ)
    with tenant_tx(ctx):
        message = _read(ctx, message_id)
        if ctx.role == "PROJECT_LEAD" and not any(
            _lead_may_see(ctx, UUID(a["invoice_id"])) for a in message["associations"]
        ):
            raise _not_found()  # INV: a lead learns nothing about a conversation that is not theirs.
        return message


def list_messages(ctx: RequestContext, limit: int, cursor: UUID | None) -> dict[str, Any]:
    authorize(ctx, MESSAGES_LIST)
    with tenant_tx(ctx):
        rows = fetch_all(
            f"SELECT {_COLUMNS}, body_enc FROM messages"  # noqa: S608
            " WHERE (%(cursor)s::uuid IS NULL OR id > %(cursor)s::uuid) ORDER BY id LIMIT %(limit)s",
            {"cursor": cursor, "limit": limit + 1},
        )
        page = rows[:limit]
        found = _associations([r["id"] for r in page])
        items = []
        for r in page:
            item = _dto(r, found[r["id"]])
            item["preview"] = _body(ctx, r)[:160]
            items.append(item)
    return {"items": items, "next_cursor": str(page[-1]["id"]) if len(rows) > limit else None}


def invoice_timeline(
    ctx: RequestContext, invoice_id: UUID, limit: int, cursor: UUID | None = None
) -> dict[str, Any]:
    """Everything said or decided on one invoice, newest first, one entry per event.

    The cursor is the id of the last entry already seen. An invoice's events are few, so the merged list is
    ordered in memory and the page starts after that entry.
    """
    authorize(ctx, MESSAGES_READ)
    with tenant_tx(ctx):
        if fetch_one("SELECT 1 AS ok FROM invoices WHERE id = %s", [invoice_id]) is None or not _lead_may_see(
            ctx, invoice_id
        ):
            raise _not_found()
        events: list[dict[str, Any]] = []
        for r in fetch_all(
            "SELECT m.id, m.source, m.sender, m.subject, m.received_at, m.uploaded_by, m.body_enc, mi.labels"
            "  FROM message_invoices mi JOIN messages m"
            "    ON m.id = mi.message_id AND m.workspace_id = mi.workspace_id"
            " WHERE mi.invoice_id = %s",
            [invoice_id],
        ):
            events.append(
                {
                    "type": "MESSAGE",
                    "id": str(r["id"]),
                    "at": r["received_at"],
                    "title": r["subject"] or "Customer reply",
                    "sender": r["sender"],
                    "excerpt": _body(ctx, r)[:240],
                    "labels": r["labels"],
                    "uploaded_by": str(r["uploaded_by"]),
                    "is_customer_statement": True,
                }
            )
        for r in fetch_all(
            "SELECT id, strength, promised_date, window_start, window_end, status, created_at, created_by"
            "  FROM commitments WHERE invoice_id = %s",
            [invoice_id],
        ):
            events.append(
                {
                    "type": "COMMITMENT",
                    "id": str(r["id"]),
                    "at": r["created_at"],
                    "title": "Customer promise recorded",
                    "strength": r["strength"],
                    "date": r["promised_date"],
                    "status": r["status"],
                    "recorded_by": str(r["created_by"]),
                }
            )
        for r in fetch_all(
            "SELECT id, type, status, summary, opened_at FROM cases WHERE invoice_id = %s", [invoice_id]
        ):
            events.append(
                {
                    "type": "CASE",
                    "id": str(r["id"]),
                    "at": r["opened_at"],
                    "title": "Dispute opened" if r["type"] == "DISPUTE" else "Question or request opened",
                    "case_type": r["type"],
                    "status": r["status"],
                }
            )
        for r in fetch_all(
            "SELECT id, until, status, created_at FROM snoozes WHERE invoice_id = %s", [invoice_id]
        ):
            events.append(
                {
                    "type": "SNOOZE",
                    "id": str(r["id"]),
                    "at": r["created_at"],
                    "title": "Follow-ups paused by a person",
                    "until": r["until"],
                    "status": r["status"],
                }
            )
        for r in fetch_all(
            "SELECT id, status, created_at FROM verification_tasks WHERE invoice_id = %s", [invoice_id]
        ):
            events.append(
                {
                    "type": "VERIFICATION_TASK",
                    "id": str(r["id"]),
                    "at": r["created_at"],
                    "title": "Payment not verified",
                    "status": r["status"],
                }
            )
    events.sort(key=lambda e: (e["at"], e["id"]), reverse=True)
    if cursor is not None:
        seen = next((n for n, e in enumerate(events) if e["id"] == str(cursor)), None)
        if seen is None:
            raise ProblemError(
                "VALIDATION_FAILED", 422, "This cursor is not valid. Start again from the first page."
            )
        events = events[seen + 1 :]
    page = events[:limit]
    return {"items": page, "next_cursor": page[-1]["id"] if len(events) > limit else None}


# --- association and what a label sets in motion (E066) ---


def _claim(ctx: RequestContext, message_id: UUID, invoice_id: UUID, state: dict[str, Any]) -> str:
    if state["payment_status"] == "PAID_VERIFIED":
        return "CLAIM_NOTED_ALREADY_VERIFIED"
    row = fetch_one(
        "INSERT INTO verification_tasks (workspace_id, invoice_id, message_id, kind)"
        " VALUES (%s, %s, %s, 'PAYMENT_CLAIM') ON CONFLICT (message_id, invoice_id, kind) DO NOTHING"
        " RETURNING id",
        [ctx.workspace_id, invoice_id, message_id],
    )
    if row is None:
        return "VERIFICATION_TASK_EXISTS"
    execute(
        "UPDATE invoice_state SET open_task_count = open_task_count + 1, version = version + 1,"
        " updated_at = now() WHERE invoice_id = %s",
        [invoice_id],
    )
    if state["reminder_status"] != "RESOLVED":
        invoice_state.set_follow_up(invoice_id, reminder_status="SUPPRESSED")
    service_state.recompute(ctx, invoice_id)  # derives AWAITING_VERIFICATION; the balance is untouched
    record(
        ctx,
        "verification_task.opened",
        "invoice",
        str(invoice_id),
        after={"kind": "PAYMENT_CLAIM", "message_id": str(message_id)},
        reason_codes=["PAYMENT_CLAIMED_BY_CUSTOMER"],
    )
    outbox.publish(ctx, "VerificationTaskOpened", {"invoice_id": str(invoice_id), "task_id": str(row["id"])})
    return "VERIFICATION_TASK_OPENED"


def close_ai_verification_tasks(ctx: RequestContext, message_id: UUID) -> int:
    """Closes tasks a model's reading opened when a person says it was wrong. A person's own task stays."""
    closed = 0
    for task in fetch_all(
        "SELECT t.id, t.invoice_id FROM verification_tasks t WHERE t.message_id = %s AND t.status = 'OPEN'"
        " AND NOT EXISTS (SELECT 1 FROM message_invoices mi WHERE mi.message_id = t.message_id"
        " AND mi.invoice_id = t.invoice_id AND 'PAYMENT_CLAIM' = ANY (mi.labels)) FOR UPDATE",
        [message_id],
    ):
        _close_task(ctx, task["id"], task["invoice_id"], message_id, "READING_REJECTED_BY_PERSON")
        closed += 1
    return closed


@outbox.subscriber("AllocationConfirmed")
def _on_allocation_confirmed(ctx: RequestContext, payload: dict[str, Any]) -> None:
    """A payment a person recorded answers a customer's claim of payment: the task has done its job.

    The money, not the claim, is what moves the invoice status. Closing only stops the task blocking it.
    """
    for invoice_id in payload["invoice_ids"]:
        for task in fetch_all(
            "SELECT id, message_id FROM verification_tasks"
            " WHERE invoice_id = %s AND status = 'OPEN' FOR UPDATE",
            [invoice_id],
        ):
            _close_task(ctx, task["id"], UUID(invoice_id), task["message_id"], "PAYMENT_RECORDED_BY_PERSON")


def _close_task(ctx: RequestContext, task_id: UUID, invoice_id: UUID, message_id: UUID, reason: str) -> None:
    execute(
        "UPDATE verification_tasks SET status = 'CLOSED', closed_by = %s, closed_at = now() WHERE id = %s",
        [ctx.user_id, task_id],
    )
    execute(
        "UPDATE invoice_state SET open_task_count = GREATEST(open_task_count - 1, 0), version = version + 1,"
        " updated_at = now() WHERE invoice_id = %s",
        [invoice_id],
    )
    service_state.recompute(ctx, invoice_id)
    record(
        ctx,
        "verification_task.closed",
        "invoice",
        str(invoice_id),
        after={"kind": "PAYMENT_CLAIM", "message_id": str(message_id)},
        reason_codes=[reason],
    )


def _opt_out(ctx: RequestContext, message_id: UUID, invoice_id: UUID, state: dict[str, Any]) -> str:
    message = fetch_one("SELECT sender FROM messages WHERE id = %s", [message_id])
    assert message
    contact = (
        fetch_one(
            "SELECT c.id FROM client_contacts c JOIN invoices i ON i.client_id = c.client_id"
            " AND i.workspace_id = c.workspace_id WHERE i.id = %s AND c.email = %s AND c.status = 'ACTIVE'",
            [invoice_id, message["sender"]],
        )
        if message["sender"]
        else None
    )
    if state["reminder_status"] != "RESOLVED":
        invoice_state.set_follow_up(invoice_id, reminder_status="SUPPRESSED")
    if contact is None:
        return "REMINDERS_SUPPRESSED_NO_CONTACT_MATCHED"
    clients.suppress_contact(ctx, contact["id"], "Asked not to be contacted, or the wrong recipient.")
    return "CONTACT_SUPPRESSED"


def _apply(ctx: RequestContext, message_id: UUID, invoice_id: UUID, label: str) -> str | None:
    state = fetch_one(
        "SELECT payment_status, reminder_status FROM invoice_state WHERE invoice_id = %s FOR UPDATE",
        [invoice_id],
    )
    if state is None:
        raise _not_found()
    if label == "PAYMENT_CLAIM":
        return _claim(ctx, message_id, invoice_id, state)
    if label == "WRONG_RECIPIENT_OR_OPT_OUT":
        return _opt_out(ctx, message_id, invoice_id, state)
    kind = "DISPUTE" if label == "DISPUTE" else _BLOCKERS.get(label)
    if kind is None:
        return None
    try:
        cases.open_case(
            ctx,
            invoice_id,
            kind,
            "Raised in a customer reply. Open the conversation to read it.",
            source_message_id=message_id,
        )
    except ProblemError as problem:
        if problem.code != "DUPLICATE_RESOURCE":
            raise
        return "DISPUTE_ALREADY_OPEN"
    return "DISPUTE_OPENED" if kind == "DISPUTE" else "CASE_OPENED"


def associate_in_tx(
    ctx: RequestContext, message_id: UUID, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    for item in items:
        invoice_id = UUID(str(item["invoice_id"]))
        labels = list(dict.fromkeys(item.get("labels") or []))
        unknown = [label for label in labels if label not in LABELS]
        if unknown:
            raise ProblemError("VALIDATION_FAILED", 422, "This kind of reading is not recognised.")
        if fetch_one("SELECT 1 AS ok FROM invoices WHERE id = %s", [invoice_id]) is None:
            raise ProblemError("VALIDATION_FAILED", 422, "One of those invoices could not be found.")
        existing = fetch_one(
            "SELECT labels FROM message_invoices WHERE message_id = %s AND invoice_id = %s FOR UPDATE",
            [message_id, invoice_id],
        )
        had = list(existing["labels"]) if existing else []
        new = [label for label in labels if label not in had]
        if existing is None:
            execute(
                "INSERT INTO message_invoices (workspace_id, message_id, invoice_id, labels, associated_by)"
                " VALUES (%s, %s, %s, %s, %s)",
                [ctx.workspace_id, message_id, invoice_id, new, ctx.user_id],
            )
        elif new:
            execute(
                "UPDATE message_invoices SET labels = %s WHERE message_id = %s AND invoice_id = %s",
                [[*had, *new], message_id, invoice_id],
            )
        record(
            ctx,
            "message.associated",
            "message",
            str(message_id),
            after={"invoice_id": str(invoice_id), "labels": [*had, *new]},
            reason_codes=["CONFIRMED_BY_PERSON"],
        )
        for label in new:
            effect = _apply(ctx, message_id, invoice_id, label)
            effects.append({"invoice_id": str(invoice_id), "label": label, "effect": effect})
    return effects


def associate(ctx: RequestContext, message_id: UUID, items: list[dict[str, Any]]) -> dict[str, Any]:
    authorize(ctx, MESSAGES_WRITE)
    if ctx.user_id is None:
        raise ProblemError("FORBIDDEN", 403, "Only a person can confirm what a reply is about.")
    with tenant_tx(ctx):
        if fetch_one("SELECT 1 AS ok FROM messages WHERE id = %s FOR UPDATE", [message_id]) is None:
            raise _not_found()
        effects = associate_in_tx(ctx, message_id, items)
        return {**_read(ctx, message_id), "effects": effects}
