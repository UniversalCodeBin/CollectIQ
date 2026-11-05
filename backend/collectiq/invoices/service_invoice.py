"""Changing one invoice: a correction, a cancellation, an archive. Each is audited with a reason."""

import json
from datetime import date
from typing import Any
from uuid import UUID

from collectiq.audit import record
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError

from .domain.validate import normalize_number
from .read_models import detail_in_tx
from .state import refresh_after_total_changed

CORRECTABLE_FIELDS = (
    "invoice_number",
    "due_date",
    "issue_date",
    "gross_minor",
    "po_number",
    "project_ref",
    "description",
    "payment_terms",
)
_OPEN_STATUSES = ("ACTIVE", "PENDING_REVIEW")
_LOCK = f"""
SELECT i.id, i.status, i.version, i.field_provenance, {", ".join("i." + f for f in CORRECTABLE_FIELDS)},
       s.paid_minor, s.payment_status
  FROM invoices i JOIN invoice_state s ON s.invoice_id = i.id AND s.workspace_id = i.workspace_id
 WHERE i.id = %s FOR UPDATE OF i
"""  # noqa: S608


def _not_found() -> ProblemError:
    return ProblemError("NOT_FOUND", 404, "We could not find that.")


def _refused(detail: str) -> ProblemError:
    return ProblemError("STATE_TRANSITION_INVALID", 409, detail)


def _locked(invoice_id: UUID) -> dict[str, Any]:
    row = fetch_one(_LOCK, [invoice_id])
    if row is None:
        raise _not_found()
    return row


def _plain(value: Any) -> Any:
    return value.isoformat() if isinstance(value, date) else value


def correct_invoice(
    ctx: RequestContext, invoice_id: UUID, version: int, changes: dict[str, Any], reason: str
) -> dict[str, Any]:
    """Fix a figure the source got wrong. The invoice then differs from its source, and says which fields."""
    with tenant_tx(ctx):
        row = _locked(invoice_id)
        if row["version"] != version:
            raise ProblemError(
                "CONFLICT_VERSION", 409, "This invoice changed since you opened it. Reload it."
            )
        if row["status"] not in _OPEN_STATUSES:
            raise _refused(f"A {row['status'].lower()} invoice cannot be corrected.")
        changed = {name: value for name, value in changes.items() if row[name] != value}
        if not changed:
            return detail_in_tx(ctx, invoice_id)
        values = dict(changed)
        if "invoice_number" in changed:
            values["normalized_number"] = normalize_number(changed["invoice_number"])
        sets = ", ".join(f"{name} = %({name})s" for name in values)
        marks = {name: "USER" for name in changed}
        execute(
            f"UPDATE invoices SET {sets}, field_provenance = field_provenance || %(marks)s::jsonb,"  # noqa: S608
            " diverges_from_source = true, version = version + 1, updated_at = now()"
            " WHERE id = %(invoice_id)s",
            {**values, "marks": _json(marks), "invoice_id": invoice_id},
        )
        if "gross_minor" in changed:
            refresh_after_total_changed(invoice_id)
        record(
            ctx,
            "invoice.corrected",
            "invoice",
            str(invoice_id),
            before={name: _plain(row[name]) for name in changed},
            after={**{name: _plain(value) for name, value in changed.items()}, "reason": reason},
            reason_codes=["USER_CORRECTION"],
        )
        return detail_in_tx(ctx, invoice_id)


def _json(value: dict[str, str]) -> str:
    return json.dumps(value)


def cancel_invoice(ctx: RequestContext, invoice_id: UUID, reason: str) -> dict[str, Any]:
    with tenant_tx(ctx):
        row = _locked(invoice_id)
        if row["status"] not in _OPEN_STATUSES:
            raise _refused(f"This invoice is already {row['status'].lower().replace('_', ' ')}.")
        if row["paid_minor"] > 0:
            raise _refused("Money has been received on this invoice, so it cannot be cancelled.")
        return _move(ctx, invoice_id, row["status"], "CANCELLED", "invoice.cancelled", reason)


def archive_invoice(ctx: RequestContext, invoice_id: UUID, reason: str) -> dict[str, Any]:
    with tenant_tx(ctx):
        row = _locked(invoice_id)
        finished = row["status"] in {"CANCELLED", "WRITTEN_OFF"} or (
            row["status"] == "ACTIVE" and row["payment_status"] == "PAID_VERIFIED"
        )
        if not finished:
            raise _refused("Only a cancelled, written-off or fully paid invoice can be archived.")
        return _move(ctx, invoice_id, row["status"], "ARCHIVED", "invoice.archived", reason)


def _move(
    ctx: RequestContext, invoice_id: UUID, before: str, after: str, action: str, reason: str
) -> dict[str, Any]:
    execute(
        "UPDATE invoices SET status = %s, version = version + 1, updated_at = now() WHERE id = %s",
        [after, invoice_id],
    )
    record(
        ctx,
        action,
        "invoice",
        str(invoice_id),
        before={"status": before},
        after={"status": after, "reason": reason},
        reason_codes=["USER_DECISION"],
    )
    return detail_in_tx(ctx, invoice_id)
