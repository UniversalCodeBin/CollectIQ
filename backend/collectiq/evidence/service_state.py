"""Keeps `invoice_state` equal to `derive()` (SAD 6.7, F-7).

`recompute` runs in the transaction of whatever changed a fact. `check_integrity` is the nightly net
for anything that slipped past: it reports drift, then repairs it through the same audited path.
"""

import logging
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from django.db import connection

from collectiq.audit import record
from collectiq.platform import outbox
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.platform.jobs import job_handler

from .domain.derive import DerivedState, Facts, derive
from .service_accounts import recompute_coverage

logger = logging.getLogger(__name__)
INVOICE_CHANGED = "InvoiceChanged"  # published by `invoices` when a figure that state follows changes
_STORED = "payment_status, paid_minor, outstanding_minor, overpayment_flag"


def _allocation_amounts(invoice_id: UUID | str) -> tuple[int, ...]:
    """Signed allocation amounts. The ledger table arrives with allocation (Task 19)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('payment_allocations') IS NOT NULL")
        if not cursor.fetchone()[0]:
            return ()
    rows = fetch_all("SELECT amount_minor FROM payment_allocations WHERE invoice_id = %s", [invoice_id])
    return tuple(int(r["amount_minor"]) for r in rows)


def load_facts(invoice_id: UUID | str) -> Facts:
    row = fetch_one(
        "SELECT i.gross_minor, s.open_task_count FROM invoices i"
        " JOIN invoice_state s ON s.invoice_id = i.id AND s.workspace_id = i.workspace_id WHERE i.id = %s",
        [invoice_id],
    )
    if row is None:
        raise LookupError(str(invoice_id))
    proposals = fetch_all(
        "SELECT count(*) FILTER (WHERE NOT ambiguous) AS single, count(*) FILTER (WHERE ambiguous) AS unclear"
        "  FROM reconciliation_matches WHERE invoice_id = %s AND status = 'PROPOSED' AND band <> 'LOW'",
        [invoice_id],
    )
    return Facts(
        gross_minor=row["gross_minor"],
        allocations=_allocation_amounts(invoice_id),
        open_verification_tasks=row["open_task_count"] + proposals[0]["single"],
        conflict=proposals[0]["unclear"] > 0,
    )


def _same(stored: dict[str, Any], derived: DerivedState) -> bool:
    return (
        stored["payment_status"] == derived.payment_status
        and stored["paid_minor"] == derived.paid_minor
        and stored["outstanding_minor"] == derived.outstanding_minor
        and stored["overpayment_flag"] == derived.overpayment_flag
    )


def recompute(ctx: RequestContext, invoice_id: UUID | str, facts: Facts | None = None) -> bool:
    """Re-derive one invoice in the caller's transaction. True when the stored row moved."""
    stored = fetch_one(f"SELECT {_STORED} FROM invoice_state WHERE invoice_id = %s FOR UPDATE", [invoice_id])  # noqa: S608
    if stored is None:
        raise LookupError(str(invoice_id))
    derived = derive(facts if facts is not None else load_facts(invoice_id))
    changed = not _same(stored, derived)
    if changed:
        execute(
            "UPDATE invoice_state SET payment_status = %s, paid_minor = %s, outstanding_minor = %s,"
            " overpayment_flag = %s, version = version + 1, updated_at = now() WHERE invoice_id = %s",
            [
                derived.payment_status,
                derived.paid_minor,
                derived.outstanding_minor,
                derived.overpayment_flag,
                invoice_id,
            ],
        )
    recompute_coverage(ctx, [UUID(str(invoice_id))])
    return changed


def check_integrity(ctx: RequestContext, repair: bool = True) -> list[str]:
    """Compare every open invoice's stored state with `derive()`. Returns the drifted invoice ids."""
    rows = fetch_all(
        f"SELECT s.invoice_id, s.{_STORED.replace(', ', ', s.')} FROM invoice_state s"  # noqa: S608
        " JOIN invoices i ON i.id = s.invoice_id AND i.workspace_id = s.workspace_id"
        " WHERE i.status IN ('ACTIVE', 'PENDING_REVIEW') ORDER BY s.invoice_id"
    )
    drifted = []
    for row in rows:
        if not _same(row, derive(load_facts(row["invoice_id"]))):
            drifted.append(str(row["invoice_id"]))
    for invoice_id in drifted:
        logger.error(
            "invoice state drift detected",
            extra={"workspace_id": str(ctx.workspace_id), "invoice_id": invoice_id},
        )
        if repair:
            before = fetch_one(f"SELECT {_STORED} FROM invoice_state WHERE invoice_id = %s", [invoice_id])  # noqa: S608
            recompute(ctx, invoice_id)
            after = fetch_one(f"SELECT {_STORED} FROM invoice_state WHERE invoice_id = %s", [invoice_id])  # noqa: S608
            record(
                ctx,
                "invoice_state.drift_repaired",
                "invoice",
                invoice_id,
                before=before,
                after=after,
                reason_codes=["INTEGRITY_CHECK"],
            )
    return drifted


@outbox.subscriber(INVOICE_CHANGED)
def _on_invoice_changed(ctx: RequestContext, payload: dict[str, Any]) -> None:
    if fetch_one("SELECT 1 FROM invoice_state WHERE invoice_id = %s", [payload["invoice_id"]]):
        recompute(ctx, payload["invoice_id"])


@job_handler("evidence.integrity_check")
def _integrity_job(ctx: RequestContext, payload: dict[str, Any]) -> None:
    check_integrity(ctx)


def recompute_many(ctx: RequestContext, invoice_ids: Sequence[UUID | str]) -> int:
    with tenant_tx(ctx):
        return sum(recompute(ctx, i) for i in invoice_ids)
