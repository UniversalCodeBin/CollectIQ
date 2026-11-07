"""Confirmed allocations, reversals and manual payments (SAD 6.6). A person always decides.

Locks are always taken in one order: transaction rows by id, then `invoice_state` rows by invoice id, then
anything else. Every check runs after the locks, so the loser of a race sees the winner's rows and gets a
useful answer. The deferred triggers in `0004_ledger_triggers` are the backstop for any path but this one.
"""

from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

from django.db import IntegrityError, OperationalError

from collectiq.audit import record
from collectiq.platform import clock, outbox
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.tenancy.permissions import FINANCE_READ, LEDGER_WRITE, authorize

from . import service_state
from .service_matching import ALLOCATION_REVERSED, BAND_LABELS

ALLOCATION_CONFIRMED = "AllocationConfirmed"
_MAX_LINES = 100
_DEADLOCK = "40P01"
_METHODS = ("BANK_TRANSFER", "UPI", "CASH", "PAYPAL_MANUAL", "OTHER")
_PAYMENT_COLUMNS = (
    "t.id, t.source_type, t.method, t.amount_minor, t.currency, t.value_date, t.reference,"
    " t.payer_descriptor, t.notes, t.status, t.evidence_type, t.entered_by, t.created_at, t.void_reason,"
    " t.duplicate_of_transaction_id, a.label AS account_label,"
    " sf.file_name AS attachment_name, sf.size_bytes AS attachment_size, pat.content_type AS attachment_type,"
    " (SELECT COALESCE(sum(pa.amount_minor), 0)::bigint FROM payment_allocations pa"
    "   WHERE pa.transaction_id = t.id AND pa.workspace_id = t.workspace_id) AS allocated_minor"
)
_PAYMENT_FROM = (
    "payment_transactions t LEFT JOIN payment_accounts a"
    " ON a.id = t.payment_account_id AND a.workspace_id = t.workspace_id"
    " LEFT JOIN payment_attachments pat ON pat.transaction_id = t.id AND pat.workspace_id = t.workspace_id"
    " LEFT JOIN stored_files sf ON sf.id = pat.file_id AND sf.workspace_id = pat.workspace_id"
    "  AND sf.deleted_at IS NULL"
)
_ALLOCATION_COLUMNS = (
    "id, invoice_id, amount_minor, kind, reverses_allocation_id, match_id, overpayment_confirmed,"
    " evidence_type, confirmed_by, note, created_at"
)


@dataclass(frozen=True)
class Line:
    invoice_id: UUID
    amount_minor: int
    overpayment_confirmed: bool = False


@contextmanager
def _ledger_tx(ctx: RequestContext) -> Iterator[None]:
    """One ledger change. The triggers fire here, so a violation is an answer rather than a failed commit."""
    try:
        with tenant_tx(ctx):
            yield
            execute(
                "SET CONSTRAINTS payment_allocations_invariants, payment_transactions_status_guard IMMEDIATE"
            )
    except IntegrityError as error:
        raise ProblemError(
            "CONFLICT_VERSION", 409, "Another change to this money came first. Reload and try again."
        ) from error
    except OperationalError as error:
        if getattr(error.__cause__, "sqlstate", None) != _DEADLOCK:
            raise
        raise ProblemError(
            "CONFLICT_VERSION", 409, "Another change to this money came first. Reload and try again."
        ) from error


def _invalid(field: str, message: str) -> ProblemError:
    return ProblemError(
        "VALIDATION_FAILED",
        422,
        "Some fields are invalid.",
        {"errors": [{"field": field, "message": message}]},
    )


def _state_refused(detail: str) -> ProblemError:
    return ProblemError("STATE_TRANSITION_INVALID", 409, detail)


def _check_lines(lines: Sequence[Line]) -> None:
    if not lines:
        raise _invalid("allocations", "Give at least one invoice and amount.")
    if len(lines) > _MAX_LINES:
        raise _invalid("allocations", f"Give at most {_MAX_LINES} invoices at once.")
    if len({line.invoice_id for line in lines}) != len(lines):
        raise _invalid("allocations", "Name each invoice once.")
    for line in lines:
        if line.amount_minor <= 0:
            raise _invalid("amount_minor", "Use a whole amount above zero, in minor units.")


def _reason(reason: str) -> str:
    cleaned = reason.strip()
    if not cleaned:
        raise _invalid("reason", "Say why.")
    return cleaned


def _lock_transaction(transaction_id: UUID) -> dict[str, Any]:
    row = fetch_one(
        "SELECT id, status, direction, amount_minor, currency, evidence_type, source_type"
        "  FROM payment_transactions WHERE id = %s FOR NO KEY UPDATE",
        [transaction_id],
    )
    if row is None:
        raise ProblemError("NOT_FOUND", 404, "That payment does not exist.")
    return row


def _lock_invoices(invoice_ids: Iterable[UUID | str]) -> None:
    """Sorted by the database, so two requests naming the same invoices in any order cannot deadlock."""
    execute_ids = sorted({str(i) for i in invoice_ids})
    if execute_ids:
        fetch_all(
            "SELECT invoice_id FROM invoice_state WHERE invoice_id = ANY(%s::uuid[])"
            " ORDER BY invoice_id FOR UPDATE",
            [execute_ids],
        )


def _proposed_invoices(transaction_id: UUID) -> list[str]:
    rows = fetch_all(
        "SELECT invoice_id FROM reconciliation_matches WHERE transaction_id = %s AND status = 'PROPOSED'",
        [transaction_id],
    )
    return [str(r["invoice_id"]) for r in rows]


def _allocated(transaction_id: UUID | str) -> int:
    row = fetch_one(
        "SELECT COALESCE(sum(amount_minor), 0)::bigint AS total FROM payment_allocations"
        " WHERE transaction_id = %s",
        [transaction_id],
    )
    assert row is not None
    return int(row["total"])


def _allocated_on_invoice(invoice_id: UUID | str) -> int:
    row = fetch_one(
        "SELECT COALESCE(sum(amount_minor), 0)::bigint AS total FROM payment_allocations"
        " WHERE invoice_id = %s",
        [invoice_id],
    )
    assert row is not None
    return int(row["total"])


def _apply_lines(
    ctx: RequestContext,
    txn: dict[str, Any],
    lines: Sequence[Line],
    overpayment_confirmed: bool,
) -> list[dict[str, Any]]:
    """The checks and inserts of SAD 6.6, in the caller's transaction, with the transaction row locked."""
    transaction_id = txn["id"]
    if txn["status"] != "ACTIVE" or txn["direction"] != "CREDIT":
        raise _state_refused("This payment is no longer active, so nothing can be allocated from it.")

    wanted = [line.invoice_id for line in lines]
    _lock_invoices([*wanted, *_proposed_invoices(transaction_id)])
    invoices = {
        str(r["id"]): r
        for r in fetch_all(
            "SELECT id, invoice_number, gross_minor, currency, status FROM invoices"
            " WHERE id = ANY(%s::uuid[])",
            [wanted],
        )
    }
    for invoice_id in wanted:
        if str(invoice_id) not in invoices:
            raise ProblemError("NOT_FOUND", 404, "That invoice does not exist.")
    for invoice in invoices.values():
        if invoice["currency"] != txn["currency"]:
            raise _invalid("invoice_id", f"Invoice {invoice['invoice_number']} is in {invoice['currency']}.")
        if invoice["status"] != "ACTIVE":
            raise _state_refused(f"Invoice {invoice['invoice_number']} is not active.")

    total_new = sum(line.amount_minor for line in lines)
    if _allocated(transaction_id) + total_new > txn["amount_minor"]:
        raise ProblemError(
            "CONFLICT_VERSION",
            409,
            "This is more than what remains of the payment. Reload and try again.",
            {"errors": [{"field": "allocations", "message": "More than the payment has left."}]},
        )

    created = []
    for line in sorted(lines, key=lambda item: str(item.invoice_id)):
        invoice = invoices[str(line.invoice_id)]
        over = _allocated_on_invoice(line.invoice_id) + line.amount_minor > invoice["gross_minor"]
        confirmed = line.overpayment_confirmed or overpayment_confirmed
        if over and not confirmed:
            raise ProblemError(
                "CONFLICT_VERSION",
                409,
                f"This pays more than invoice {invoice['invoice_number']} is for. Confirm the overpayment.",
                {
                    "needs_overpayment_confirmation": True,
                    "errors": [{"field": "overpayment_confirmed", "message": "Confirm the overpayment."}],
                },
            )
        created.append(_insert_allocation(ctx, txn, line, over))
    return created


def _pair_match(transaction_id: UUID, invoice_id: UUID) -> dict[str, Any] | None:
    """The open proposal on this pair, if any. One at most (partial unique index)."""
    return fetch_one(
        "SELECT id FROM reconciliation_matches WHERE transaction_id = %s AND invoice_id = %s"
        " AND status = 'PROPOSED'",
        [transaction_id, invoice_id],
    )


def _insert_allocation(ctx: RequestContext, txn: dict[str, Any], line: Line, over: bool) -> dict[str, Any]:
    proposal = _pair_match(txn["id"], line.invoice_id)
    row = fetch_one(
        "INSERT INTO payment_allocations (workspace_id, transaction_id, invoice_id, amount_minor, currency,"  # noqa: S608
        " kind, match_id, overpayment_confirmed, evidence_type, confirmed_by)"
        " VALUES (%s, %s, %s, %s, %s, 'ALLOCATION', %s, %s, %s, %s)"
        f" RETURNING {_ALLOCATION_COLUMNS}",
        [
            ctx.workspace_id,
            txn["id"],
            line.invoice_id,
            line.amount_minor,
            txn["currency"],
            proposal["id"] if proposal else None,
            over,
            txn["evidence_type"],
            ctx.user_id,
        ],
    )
    assert row is not None
    if proposal:
        execute(
            "UPDATE reconciliation_matches SET status = 'CONFIRMED', decided_by = %s, decided_at = now()"
            " WHERE id = %s",
            [ctx.user_id, proposal["id"]],
        )
        record(
            ctx,
            "match.confirmed",
            "reconciliation_match",
            str(proposal["id"]),
            after={"transaction_id": str(txn["id"]), "invoice_id": str(line.invoice_id)},
            reason_codes=["USER_CONFIRMATION"],
        )
    record(
        ctx,
        "allocation.created",
        "payment_allocation",
        str(row["id"]),
        after={
            "transaction_id": str(txn["id"]),
            "invoice_id": str(line.invoice_id),
            "amount_minor": line.amount_minor,
            "currency": txn["currency"],
            "evidence_type": txn["evidence_type"],
            "overpayment_confirmed": over,
        },
        reason_codes=["USER_CONFIRMATION", *(["OVERPAYMENT_CONFIRMED"] if over else [])],
    )
    return row


def _settle_proposals(txn: dict[str, Any], invoice_ids: Iterable[UUID | str]) -> list[str]:
    """Withdraw what this decision made moot. Returns every invoice whose open proposals changed."""
    touched: list[str] = []
    if _allocated(txn["id"]) >= txn["amount_minor"]:
        rows = fetch_all(
            "UPDATE reconciliation_matches SET status = 'SUPERSEDED', decided_at = now()"
            " WHERE transaction_id = %s AND status = 'PROPOSED' RETURNING invoice_id",
            [txn["id"]],
        )
        touched += [str(r["invoice_id"]) for r in rows]
    for invoice_id in invoice_ids:
        gross = fetch_one("SELECT gross_minor FROM invoices WHERE id = %s", [invoice_id])
        assert gross is not None
        if _allocated_on_invoice(invoice_id) >= gross["gross_minor"]:
            execute(
                "UPDATE reconciliation_matches SET status = 'SUPERSEDED', decided_at = now()"
                " WHERE invoice_id = %s AND status = 'PROPOSED'",
                [invoice_id],
            )
    return touched


def _recompute(ctx: RequestContext, invoice_ids: Iterable[UUID | str]) -> None:
    for invoice_id in sorted({str(i) for i in invoice_ids}):
        service_state.recompute(ctx, invoice_id)


def _confirm(
    ctx: RequestContext, txn: dict[str, Any], lines: Sequence[Line], overpayment_confirmed: bool = False
) -> list[dict[str, Any]]:
    created = _apply_lines(ctx, txn, lines, overpayment_confirmed)
    invoice_ids = [line.invoice_id for line in lines]
    touched = _settle_proposals(txn, invoice_ids)
    _recompute(ctx, [*invoice_ids, *touched])
    outbox.publish(
        ctx,
        ALLOCATION_CONFIRMED,
        {
            "transaction_id": str(txn["id"]),
            "allocation_ids": [str(row["id"]) for row in created],
            "invoice_ids": sorted(str(i) for i in invoice_ids),
            "overpaid_invoice_ids": sorted(
                {str(row["invoice_id"]) for row in created if row["overpayment_confirmed"]}
            ),
        },
    )
    return created


def _check_proposal(match_id: UUID, transaction_id: UUID, lines: Sequence[Line]) -> None:
    """Runs with the transaction locked and the invoices about to be, so its status cannot change under it."""
    _lock_invoices([*(line.invoice_id for line in lines), *_proposed_invoices(transaction_id)])
    found = fetch_one(
        "SELECT transaction_id, invoice_id, status FROM reconciliation_matches WHERE id = %s", [match_id]
    )
    if found is None:
        raise ProblemError("NOT_FOUND", 404, "That proposal does not exist.")
    if found["transaction_id"] != transaction_id:
        raise _invalid("match_id", "That proposal is about a different payment.")
    if found["invoice_id"] not in {line.invoice_id for line in lines}:
        raise _invalid("allocations", "Include the invoice this proposal is about.")
    if found["status"] != "PROPOSED":
        raise _state_refused("That proposal has already been decided.")


def confirm_allocation(
    ctx: RequestContext,
    transaction_id: UUID,
    lines: Sequence[Line],
    match_id: UUID | None = None,
    overpayment_confirmed: bool = False,
) -> dict[str, Any]:
    """Allocate received money to invoices. Each line going over an invoice's total must say so."""
    authorize(ctx, LEDGER_WRITE)
    _check_lines(lines)
    with _ledger_tx(ctx):
        txn = _lock_transaction(transaction_id)
        if match_id is not None:
            _check_proposal(match_id, transaction_id, lines)
        created = _confirm(ctx, txn, lines, overpayment_confirmed)
        return _result(transaction_id, created, [line.invoice_id for line in lines])


def confirm_proposal(ctx: RequestContext, match_id: UUID, lines: Sequence[Line]) -> dict[str, Any]:
    """A person accepts a proposal, and may split the money across other invoices at the same time."""
    authorize(ctx, LEDGER_WRITE)
    with tenant_tx(ctx):
        found = fetch_one("SELECT transaction_id FROM reconciliation_matches WHERE id = %s", [match_id])
    if found is None:
        raise ProblemError("NOT_FOUND", 404, "That proposal does not exist.")
    return confirm_allocation(ctx, found["transaction_id"], lines, match_id=match_id)


def _insert_reversal(ctx: RequestContext, original: dict[str, Any], reason: str) -> dict[str, Any]:
    row = fetch_one(
        "INSERT INTO payment_allocations (workspace_id, transaction_id, invoice_id, amount_minor, currency,"  # noqa: S608
        " kind, reverses_allocation_id, evidence_type, confirmed_by, note)"
        " VALUES (%s, %s, %s, %s, %s, 'REVERSAL', %s, %s, %s, %s)"
        f" RETURNING {_ALLOCATION_COLUMNS}",
        [
            ctx.workspace_id,
            original["transaction_id"],
            original["invoice_id"],
            -original["amount_minor"],
            original["currency"],
            original["id"],
            original["evidence_type"],
            ctx.user_id,
            reason,
        ],
    )
    assert row is not None
    live = fetch_one(
        "SELECT 1 AS live FROM payment_allocations a WHERE a.transaction_id = %s AND a.invoice_id = %s"
        " AND a.kind = 'ALLOCATION' AND NOT EXISTS (SELECT 1 FROM payment_allocations r"
        "   WHERE r.reverses_allocation_id = a.id)",
        [original["transaction_id"], original["invoice_id"]],
    )
    if live is None:
        # A person has now said no to this pair, so it is declined and not proposed on the same inputs again.
        execute(
            "UPDATE reconciliation_matches SET status = 'REJECTED', decided_by = %s, decided_at = now(),"
            " decision_reason = %s WHERE transaction_id = %s AND invoice_id = %s AND status = 'CONFIRMED'",
            [ctx.user_id, reason, original["transaction_id"], original["invoice_id"]],
        )
    record(
        ctx,
        "allocation.reversed",
        "payment_allocation",
        str(original["id"]),
        after={
            "reversal_id": str(row["id"]),
            "transaction_id": str(original["transaction_id"]),
            "invoice_id": str(original["invoice_id"]),
            "amount_minor": row["amount_minor"],
            "reason": reason,
        },
        reason_codes=["USER_REVERSAL"],
    )
    return row


def reverse_allocation(ctx: RequestContext, allocation_id: UUID, reason: str) -> dict[str, Any]:
    """Undo one allocation by adding its opposite (F-4). The original row stays as it was (F-5)."""
    authorize(ctx, LEDGER_WRITE)
    note = _reason(reason)
    with _ledger_tx(ctx):
        original = fetch_one(
            "SELECT id, transaction_id, invoice_id, amount_minor, currency, kind, evidence_type"
            "  FROM payment_allocations WHERE id = %s",
            [allocation_id],
        )
        if original is None:
            raise ProblemError("NOT_FOUND", 404, "That allocation does not exist.")
        if original["kind"] != "ALLOCATION":
            raise _state_refused("A reversal cannot itself be reversed. Allocate the money again instead.")
        _lock_transaction(original["transaction_id"])
        _lock_invoices([original["invoice_id"]])
        done = fetch_one(
            "SELECT 1 AS done FROM payment_allocations WHERE reverses_allocation_id = %s", [allocation_id]
        )
        if done is not None:
            raise _state_refused("This allocation has already been reversed.")
        reversal = _insert_reversal(ctx, original, note)
        _recompute(ctx, [original["invoice_id"]])
        outbox.publish(
            ctx,
            ALLOCATION_REVERSED,
            {
                "allocation_id": str(allocation_id),
                "transaction_id": str(original["transaction_id"]),
                "invoice_id": str(original["invoice_id"]),
            },
        )
        return _result(original["transaction_id"], [reversal], [original["invoice_id"]])


def record_payment(
    ctx: RequestContext,
    method: str,
    amount_minor: int,
    currency: str,
    value_date: date,
    reference: str | None = None,
    payer: str | None = None,
    notes: str | None = None,
    lines: Sequence[Line] = (),
) -> dict[str, Any]:
    """Money a person says they received (FR-036). It stays marked as lower assurance than a statement row."""
    authorize(ctx, LEDGER_WRITE)
    if method not in _METHODS:
        raise _invalid("method", "Use one of the listed payment methods.")
    if amount_minor <= 0:
        raise _invalid("amount.amount_minor", "Use a whole amount above zero, in minor units.")
    if value_date > clock.today():
        raise _invalid("value_date", "A payment cannot be dated in the future.")
    if lines:
        _check_lines(lines)
        if sum(line.amount_minor for line in lines) > amount_minor:
            raise _invalid("allocations", "These add up to more than the payment.")
    with _ledger_tx(ctx):
        created = fetch_one(
            "INSERT INTO payment_transactions (workspace_id, source_type, method, amount_minor, currency,"
            " value_date, reference, payer_descriptor, notes, fingerprint, evidence_type, entered_by)"
            " VALUES (%s, 'MANUAL', %s, %s, %s, %s, %s, %s, %s, %s, 'USER_CONFIRMATION', %s) RETURNING id",
            [
                ctx.workspace_id,
                method,
                amount_minor,
                currency,
                value_date,
                reference,
                payer,
                notes,
                f"manual:{uuid4()}",
                ctx.user_id,
            ],
        )
        assert created is not None
        record(
            ctx,
            "payment.recorded",
            "payment_transaction",
            str(created["id"]),
            after={
                "method": method,
                "amount_minor": amount_minor,
                "currency": currency,
                "value_date": value_date.isoformat(),
            },
            reason_codes=["USER_CONFIRMATION"],
        )
        allocations: list[dict[str, Any]] = []
        if lines:
            txn = _lock_transaction(created["id"])
            allocations = _confirm(ctx, txn, lines)
        return _result(created["id"], allocations, [line.invoice_id for line in lines])


def void_payment(ctx: RequestContext, transaction_id: UUID, reason: str) -> dict[str, Any]:
    """Withdraw a mistaken manual entry and everything allocated from it. Statement rows are never voided."""
    authorize(ctx, LEDGER_WRITE)
    note = _reason(reason)
    with _ledger_tx(ctx):
        txn = _lock_transaction(transaction_id)
        if txn["source_type"] != "MANUAL":
            raise _state_refused(
                "Only a manual entry can be voided. Mark a statement row as a duplicate instead."
            )
        if txn["status"] != "ACTIVE":
            raise _state_refused("This payment is no longer active.")
        live = fetch_all(
            "SELECT id, transaction_id, invoice_id, amount_minor, currency, kind, evidence_type"
            "  FROM payment_allocations a WHERE a.transaction_id = %s AND a.kind = 'ALLOCATION'"
            "   AND NOT EXISTS (SELECT 1 FROM payment_allocations r WHERE r.reverses_allocation_id = a.id)"
            " ORDER BY a.id",
            [transaction_id],
        )
        invoice_ids = [row["invoice_id"] for row in live]
        _lock_invoices(invoice_ids)
        reversals = [_insert_reversal(ctx, row, note) for row in live]
        execute(
            "UPDATE payment_transactions SET status = 'VOID', void_reason = %s WHERE id = %s",
            [note, transaction_id],
        )
        touched = _supersede_on_transaction(transaction_id)
        _recompute(ctx, [*invoice_ids, *touched])
        record(
            ctx,
            "payment.voided",
            "payment_transaction",
            str(transaction_id),
            before={"status": "ACTIVE"},
            after={"status": "VOID", "reason": note},
            reason_codes=["USER_VOID"],
        )
        for row in live:
            outbox.publish(
                ctx,
                ALLOCATION_REVERSED,
                {
                    "allocation_id": str(row["id"]),
                    "transaction_id": str(transaction_id),
                    "invoice_id": str(row["invoice_id"]),
                },
            )
        return _result(transaction_id, reversals, invoice_ids)


def _supersede_on_transaction(transaction_id: UUID) -> list[str]:
    rows = fetch_all(
        "UPDATE reconciliation_matches SET status = 'SUPERSEDED', decided_at = now()"
        " WHERE transaction_id = %s AND status = 'PROPOSED' RETURNING invoice_id",
        [transaction_id],
    )
    return [str(r["invoice_id"]) for r in rows]


def mark_duplicate(ctx: RequestContext, transaction_id: UUID, duplicate_of: UUID) -> dict[str, Any]:
    """The same money seen twice pays once (FR-032). A person says which row is the copy."""
    authorize(ctx, LEDGER_WRITE)
    if transaction_id == duplicate_of:
        raise _invalid("duplicate_of", "A payment cannot be a duplicate of itself.")
    with _ledger_tx(ctx):
        found = {}
        for one in sorted((transaction_id, duplicate_of), key=str):
            row = fetch_one(
                "SELECT id, status, amount_minor, currency FROM payment_transactions"
                " WHERE id = %s FOR NO KEY UPDATE",
                [one],
            )
            if row is None:
                raise ProblemError("NOT_FOUND", 404, "That payment does not exist.")
            found[one] = row
        txn, target = found[transaction_id], found[duplicate_of]
        if (txn["currency"], txn["amount_minor"]) != (target["currency"], target["amount_minor"]):
            raise _invalid("duplicate_of", "A duplicate has the same amount and currency.")
        if txn["status"] != "ACTIVE" or target["status"] != "ACTIVE":
            raise _state_refused("Both payments must still be active.")
        proposed = _proposed_invoices(transaction_id)
        _lock_invoices(proposed)
        if _allocated(transaction_id) != 0:
            raise _state_refused("Reverse this payment's allocations before marking it as a duplicate.")
        execute(
            "UPDATE payment_transactions SET status = 'DUPLICATE', duplicate_of_transaction_id = %s"
            " WHERE id = %s",
            [duplicate_of, transaction_id],
        )
        touched = _supersede_on_transaction(transaction_id)
        _recompute(ctx, touched)
        record(
            ctx,
            "payment.marked_duplicate",
            "payment_transaction",
            str(transaction_id),
            before={"status": "ACTIVE"},
            after={"status": "DUPLICATE", "duplicate_of": str(duplicate_of)},
            reason_codes=["USER_CONFIRMATION"],
        )
        return _result(transaction_id, [], touched)


# ---- what a person reads ----------------------------------------------------------------------------


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _allocation_dto(row: dict[str, Any]) -> dict[str, Any]:
    """Plain JSON values, so a replayed response is the same bytes as the original."""
    dto = {
        "id": str(row["id"]),
        "invoice_id": str(row["invoice_id"]),
        "amount_minor": row["amount_minor"],
        "kind": row["kind"],
        "reverses_allocation_id": _text(row["reverses_allocation_id"]),
        "match_id": _text(row["match_id"]),
        "overpayment_confirmed": row["overpayment_confirmed"],
        "evidence_type": row["evidence_type"],
        "confirmed_by": str(row["confirmed_by"]),
        "note": row["note"],
        "created_at": row["created_at"].isoformat(),
    }
    if "invoice_number" in row:
        dto["invoice_number"] = row["invoice_number"]
    return dto


def _payment_dto(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "source_type": row["source_type"],
        "method": row["method"],
        "amount_minor": row["amount_minor"],
        "currency": row["currency"],
        "allocated_minor": row["allocated_minor"],
        "unallocated_minor": row["amount_minor"] - row["allocated_minor"],
        "value_date": row["value_date"].isoformat(),
        "reference": row["reference"],
        "payer_descriptor": row["payer_descriptor"],
        "notes": row["notes"],
        "status": row["status"],
        "evidence_type": row["evidence_type"],
        "lower_assurance": row["evidence_type"] == "USER_CONFIRMATION",
        "account_label": row["account_label"],
        "entered_by": str(row["entered_by"]),
        "created_at": row["created_at"].isoformat(),
        "void_reason": row["void_reason"],
        "duplicate_of_transaction_id": _text(row["duplicate_of_transaction_id"]),
        "attachment": None
        if row["attachment_name"] is None
        else {
            "file_name": row["attachment_name"],
            "size_bytes": row["attachment_size"],
            "content_type": row["attachment_type"],
        },
    }


def _load_payment(transaction_id: UUID | str) -> dict[str, Any] | None:
    return fetch_one(
        f"SELECT {_PAYMENT_COLUMNS} FROM {_PAYMENT_FROM} WHERE t.id = %s",  # noqa: S608
        [transaction_id],
    )


def _result(
    transaction_id: UUID | str, allocations: Sequence[dict[str, Any]], invoice_ids: Iterable[UUID | str]
) -> dict[str, Any]:
    payment = _load_payment(transaction_id)
    assert payment is not None
    return {
        "payment": _payment_dto(payment),
        "allocations": [_allocation_dto(row) for row in allocations],
        "invoice_states": service_state.snapshot(invoice_ids),
    }


def list_payments(ctx: RequestContext, limit: int, cursor: UUID | None) -> dict[str, Any]:
    authorize(ctx, FINANCE_READ)
    with tenant_tx(ctx):
        rows = fetch_all(
            f"SELECT {_PAYMENT_COLUMNS} FROM {_PAYMENT_FROM}"  # noqa: S608
            " WHERE t.direction = 'CREDIT' AND (%(cursor)s::uuid IS NULL OR t.id > %(cursor)s::uuid)"
            " ORDER BY t.id LIMIT %(limit)s",
            {"cursor": cursor, "limit": limit + 1},
        )
    page = rows[:limit]
    return {
        "items": [_payment_dto(row) for row in page],
        "next_cursor": str(page[-1]["id"]) if len(rows) > limit else None,
    }


def invoice_payment_history(ctx: RequestContext, invoice_id: UUID) -> dict[str, Any]:
    """Every allocation and reversal on one invoice, oldest first, with its payment (FR-056)."""
    authorize(ctx, FINANCE_READ)
    with tenant_tx(ctx):
        if fetch_one("SELECT 1 FROM invoices WHERE id = %s", [invoice_id]) is None:
            raise ProblemError("NOT_FOUND", 404, "That invoice does not exist.")
        rows = fetch_all(
            "SELECT a.id, a.invoice_id, a.amount_minor, a.kind, a.reverses_allocation_id, a.match_id,"
            "       a.overpayment_confirmed, a.evidence_type, a.confirmed_by, a.note, a.created_at,"
            "       i.invoice_number, t.id AS transaction_id, t.value_date, t.payer_descriptor, t.currency"
            "  FROM payment_allocations a"
            "  JOIN invoices i ON i.id = a.invoice_id AND i.workspace_id = a.workspace_id"
            "  JOIN payment_transactions t ON t.id = a.transaction_id AND t.workspace_id = a.workspace_id"
            " WHERE a.invoice_id = %s ORDER BY a.created_at, a.id",
            [invoice_id],
        )
    return {
        "items": [
            {
                **_allocation_dto(row),
                "transaction_id": str(row["transaction_id"]),
                "value_date": row["value_date"].isoformat(),
                "payer_descriptor": row["payer_descriptor"],
                "currency": row["currency"],
            }
            for row in rows
        ]
    }


def get_payment(ctx: RequestContext, transaction_id: UUID) -> dict[str, Any]:
    authorize(ctx, FINANCE_READ)
    with tenant_tx(ctx):
        payment = _load_payment(transaction_id)
        if payment is None:
            raise ProblemError("NOT_FOUND", 404, "That payment does not exist.")
        allocations = fetch_all(
            "SELECT a.id, a.invoice_id, a.amount_minor, a.kind, a.reverses_allocation_id, a.match_id,"
            "       a.overpayment_confirmed, a.evidence_type, a.confirmed_by, a.note, a.created_at,"
            "       i.invoice_number"
            "  FROM payment_allocations a JOIN invoices i"
            "    ON i.id = a.invoice_id AND i.workspace_id = a.workspace_id"
            " WHERE a.transaction_id = %s ORDER BY a.created_at, a.id",
            [transaction_id],
        )
        matches = fetch_all(
            "SELECT id, invoice_id, status, band, ambiguous, decided_at, decision_reason"
            "  FROM reconciliation_matches WHERE transaction_id = %s ORDER BY created_at, id",
            [transaction_id],
        )
    return {
        **_payment_dto(payment),
        "allocations": [_allocation_dto(row) for row in allocations],
        "matches": [
            {
                "id": str(m["id"]),
                "invoice_id": str(m["invoice_id"]),
                "status": m["status"],
                "label": BAND_LABELS[m["band"]],
                "ambiguous": m["ambiguous"],
                "decided_at": m["decided_at"].isoformat() if m["decided_at"] else None,
                "decision_reason": m["decision_reason"],
            }
            for m in matches
        ],
    }
