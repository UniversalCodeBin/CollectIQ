"""What the screens read: the invoice list, the queue, one invoice, and the dashboard (FR-019, FR-022).

Every figure comes from stored state; nothing here is scored or estimated. Filtering that SQL can do
exactly is done in SQL. The tile, aging and exception rules live once, in `domain.queue`, so the rows a
tile counts are the rows its filter lists; those are applied here, in Python, over the filtered rows.
"""

import base64
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from collectiq.platform.context import RequestContext
from collectiq.platform.db import fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.platform.money import ISO_4217_CODES, currency_exponent
from collectiq.tenancy.permissions import LEDGER_WRITE, allowed_roles

from .domain.queue import (
    ACTION_LABELS,
    AGING_BUCKETS,
    ENDED_STATUSES,
    TILES,
    QueueEntry,
    QueueFacts,
    exception_order,
    is_open,
    queue_entry,
    tile_matches,
)

SORTS = (
    "default",
    "due_date",
    "amount",
    "-amount",
    "invoice_number",
    "-invoice_number",
    "-evidence_as_of",
    "exception",
)
_DESCENDING = frozenset({"-amount", "-invoice_number", "-evidence_as_of"})
_ROLE_LABELS = {"OWNER": "Owner", "FINANCE_ADMIN": "Finance admin"}
_EXPONENTS = {
    digits: sorted(code for code in ISO_4217_CODES if currency_exponent(code) == digits)
    for digits in (0, 3, 4)
}
_CORRECTABLE = ("ACTIVE", "PENDING_REVIEW")

_SELECT = """
SELECT i.id, i.invoice_number, i.currency, i.due_date, i.issue_date, i.gross_minor, i.status, i.client_id,
       c.display_name AS client_name, i.assignee_id, i.import_batch_id, i.source_system, i.version,
       s.payment_status, s.coverage_as_of, s.paid_minor, s.outstanding_minor, s.overpayment_flag,
       s.dispute_status, s.reminder_status, s.snooze_until
  FROM invoices i
  JOIN invoice_state s ON s.invoice_id = i.id AND s.workspace_id = i.workspace_id
  JOIN clients c ON c.id = i.client_id AND c.workspace_id = i.workspace_id
"""


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ListQuery:
    payment_status: str | None = None
    reminder_status: str | None = None
    dispute_status: str | None = None
    currency: str | None = None
    due_from: date | None = None
    due_to: date | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    client_id: UUID | None = None
    assignee: UUID | None = None
    import_batch: UUID | None = None
    tile: str | None = None
    aging: str | None = None
    q: str | None = None
    sort: str = "default"
    limit: int = 50
    cursor: str | None = None


def _bad(field: str, message: str) -> ProblemError:
    return ProblemError(
        "VALIDATION_FAILED",
        422,
        "Some fields are invalid.",
        {"errors": [{"field": field, "message": message}]},
    )


def _not_found() -> ProblemError:
    return ProblemError("NOT_FOUND", 404, "We could not find that.")


def _today(now: datetime) -> date:
    row = fetch_one("SELECT timezone FROM workspaces LIMIT 1")
    zone = ZoneInfo(row["timezone"]) if row else UTC
    return now.astimezone(zone).date()


def _major(column: str) -> str:
    return (
        f"({column}::numeric / CASE WHEN i.currency = ANY(%(exp0)s) THEN 1"
        " WHEN i.currency = ANY(%(exp3)s) THEN 1000"
        " WHEN i.currency = ANY(%(exp4)s) THEN 10000 ELSE 100 END)"
    )


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _where(ctx: RequestContext, query: ListQuery) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {f"exp{digits}": codes for digits, codes in _EXPONENTS.items()}
    clauses: list[str] = []
    equal = {
        "payment_status": "s.payment_status",
        "reminder_status": "s.reminder_status",
        "dispute_status": "s.dispute_status",
        "currency": "i.currency",
        "client_id": "i.client_id",
        "assignee": "i.assignee_id",
        "import_batch": "i.import_batch_id",
    }
    for name, column in equal.items():
        value = getattr(query, name)
        if value is not None:
            clauses.append(f"{column} = %({name})s")
            params[name] = value
    if query.due_from is not None:
        clauses.append("i.due_date >= %(due_from)s")
        params["due_from"] = query.due_from
    if query.due_to is not None:
        clauses.append("i.due_date <= %(due_to)s")
        params["due_to"] = query.due_to
    if query.amount_min is not None:
        clauses.append(f"{_major('s.outstanding_minor')} >= %(amount_min)s")
        params["amount_min"] = query.amount_min
    if query.amount_max is not None:
        clauses.append(f"{_major('s.outstanding_minor')} <= %(amount_max)s")
        params["amount_max"] = query.amount_max
    if query.q:
        parts = [
            "i.invoice_number ILIKE %(q_like)s ESCAPE '\\'",
            "c.display_name ILIKE %(q_like)s ESCAPE '\\'",
        ]
        params["q_like"] = _like(query.q)
        try:
            amount = Decimal(query.q)
        except ArithmeticError:
            amount = None
        if amount is not None and amount.is_finite() and amount >= 0:
            parts.append(f"{_major('s.outstanding_minor')} = %(q_amount)s")
            parts.append(f"{_major('i.gross_minor')} = %(q_amount)s")
            params["q_amount"] = amount
        clauses.append("(" + " OR ".join(parts) + ")")
    if ctx.role == "PROJECT_LEAD":
        clauses.append("i.assignee_id = %(scope_user)s")
        params["scope_user"] = ctx.user_id
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _allowed_roles() -> list[str]:
    return [label for role, label in _ROLE_LABELS.items() if role in allowed_roles(LEDGER_WRITE)]


def _loaded(value: Any) -> Any:
    """The driver hands jsonb back as text."""
    return json.loads(value) if isinstance(value, str) else value


def allowed_actions(role: str, status: str, payment_status: str, paid_minor: int) -> list[dict[str, Any]]:
    """What this person may do to this invoice now, each with the reason when it may not be done."""

    def item(action: str, reason: str | None) -> dict[str, Any]:
        return {"action": action, "allowed": reason is None, "reason": reason}

    if role not in allowed_roles(LEDGER_WRITE):
        why = "Only an owner or finance admin can change an invoice."
        return [item("CORRECT", why), item("CANCEL", why), item("ARCHIVE", why)]
    ended = "This invoice is already " + status.lower().replace("_", " ") + "."
    correct = None if status in _CORRECTABLE else ended
    if status not in _CORRECTABLE:
        cancel: str | None = ended
    elif paid_minor > 0:
        cancel = "Money has been received on this invoice, so it cannot be cancelled."
    else:
        cancel = None
    can_archive = status in {"CANCELLED", "WRITTEN_OFF"} or (
        status == "ACTIVE" and payment_status == "PAID_VERIFIED"
    )
    if can_archive:
        archive: str | None = None
    elif status == "ARCHIVED":
        archive = ended
    else:
        archive = "Only a cancelled, written-off or fully paid invoice can be archived."
    return [item("CORRECT", correct), item("CANCEL", cancel), item("ARCHIVE", archive)]


def _facts(row: dict[str, Any]) -> QueueFacts:
    return QueueFacts(
        invoice_id=str(row["id"]),
        status=row["status"],
        payment_status=row["payment_status"],
        coverage_as_of=row["coverage_as_of"],
        dispute_status=row["dispute_status"],
        reminder_status=row["reminder_status"],
        snooze_until=row["snooze_until"],
        due_date=row["due_date"],
        outstanding_minor=row["outstanding_minor"],
        overpayment=row["overpayment_flag"],
    )


def _recommended(ctx: RequestContext, entry: QueueEntry) -> dict[str, Any] | None:
    if entry.action is None:
        return None
    can_act = ctx.role in allowed_roles(LEDGER_WRITE)
    return {
        "code": entry.action,
        "label": ACTION_LABELS[entry.action],
        "can_act": can_act,
        "performed_by": _allowed_roles(),
        "reason": None if can_act else "Only an owner or finance admin can do this.",
    }


def _enrich(rows: list[dict[str, Any]], now: datetime, today: date) -> list[dict[str, Any]]:
    for row in rows:
        row["entry"] = queue_entry(_facts(row), today, now)
    return rows


def _apply_filters(rows: list[dict[str, Any]], query: ListQuery, today: date) -> list[dict[str, Any]]:
    kept = rows
    if query.tile is not None:
        kept = [
            r
            for r in kept
            if tile_matches(
                query.tile,
                r["status"],
                r["payment_status"],
                r["dispute_status"],
                r["reminder_status"],
                r["due_date"],
                today,
            )
        ]
    if query.aging is not None:
        kept = [
            r for r in kept if is_open(r["status"], r["payment_status"]) and r["entry"].aging == query.aging
        ]
    return kept


def _key(sort: str, row: dict[str, Any]) -> list[Any]:
    ident = str(row["id"])
    if sort in {"default", "due_date"}:
        return [row["due_date"].isoformat(), ident]
    if sort in {"amount", "-amount"}:
        return [row["outstanding_minor"], ident]
    if sort in {"invoice_number", "-invoice_number"}:
        return [row["invoice_number"].lower(), ident]
    if sort == "-evidence_as_of":
        as_of = row["coverage_as_of"]
        return [as_of.isoformat() if as_of else "", ident]
    entry: QueueEntry = row["entry"]
    return [*exception_order(entry.tier, entry.days_overdue, row["outstanding_minor"]), ident]


def _encode(sort: str, key: list[Any]) -> str:
    raw = json.dumps({"s": sort, "k": key}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(cursor: str, sort: str) -> list[Any]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        body = json.loads(base64.urlsafe_b64decode(padded.encode()))
        if not isinstance(body, dict) or not isinstance(body.get("k"), list):
            raise ValueError
    except ValueError:
        raise _bad("cursor", "This cursor is not valid. Start again from the first page.") from None
    if body.get("s") != sort:
        raise _bad("cursor", "This cursor belongs to a different sort. Start again from the first page.")
    return list(body["k"])


def _page(rows: list[dict[str, Any]], sort: str, query: ListQuery) -> tuple[list[dict[str, Any]], str | None]:
    descending = sort in _DESCENDING
    ordered = sorted(rows, key=lambda r: _key(sort, r), reverse=descending)
    if query.cursor is not None:
        after = _decode(query.cursor, sort)
        try:
            ordered = [r for r in ordered if (_key(sort, r) < after if descending else _key(sort, r) > after)]
        except TypeError:
            raise _bad("cursor", "This cursor is not valid. Start again from the first page.") from None
    page = ordered[: query.limit]
    more = len(ordered) > query.limit
    return page, (_encode(sort, _key(sort, page[-1])) if more and page else None)


def _load(ctx: RequestContext, query: ListQuery) -> tuple[list[dict[str, Any]], date, datetime]:
    now = _now()
    today = _today(now)
    where, params = _where(ctx, query)
    rows = _enrich(fetch_all(_SELECT + where, params), now, today)  # noqa: S608
    return _apply_filters(rows, query, today), today, now


def _item(ctx: RequestContext, row: dict[str, Any]) -> dict[str, Any]:
    entry: QueueEntry = row["entry"]
    as_of = row["coverage_as_of"]
    return {
        "id": str(row["id"]),
        "invoice_number": row["invoice_number"],
        "client_id": str(row["client_id"]),
        "client_name": row["client_name"],
        "currency": row["currency"],
        "status": row["status"],
        "due_date": row["due_date"].isoformat(),
        "outstanding_minor": row["outstanding_minor"],
        "paid_minor": row["paid_minor"],
        "payment_status": row["payment_status"],
        "dispute_status": row["dispute_status"],
        "reminder_status": row["reminder_status"],
        "evidence_coverage": entry.coverage,
        "evidence_as_of": as_of.isoformat() if as_of else None,
        "days_overdue": entry.days_overdue,
        "due_bucket": entry.due_bucket,
        "allowed_actions": allowed_actions(
            ctx.role or "", row["status"], row["payment_status"], row["paid_minor"]
        ),
    }


def list_invoices(ctx: RequestContext, query: ListQuery) -> dict[str, Any]:
    with tenant_tx(ctx):
        rows, _today_, _now_ = _load(ctx, query)
        page, next_cursor = _page(rows, query.sort, query)
        return {"items": [_item(ctx, row) for row in page], "next_cursor": next_cursor}


def queue(ctx: RequestContext, query: ListQuery) -> dict[str, Any]:
    """Invoices that have something to decide or do, in exception order unless another sort is asked for."""
    sort = "exception" if query.sort == "default" else query.sort
    with tenant_tx(ctx):
        rows, _today_, _now_ = _load(ctx, query)
        rows = [row for row in rows if row["entry"].tier is not None]
        page, next_cursor = _page(rows, sort, query)
        items = []
        for row in page:
            entry: QueueEntry = row["entry"]
            items.append(
                {
                    **_item(ctx, row),
                    "tier": entry.tier,
                    "reasons": [{"code": r.code, "label": r.label, "link": r.link} for r in entry.reasons],
                    "why_not": [{"code": w.code, "label": w.label} for w in entry.why_not],
                    "recommended_action": _recommended(ctx, entry),
                    "sample": row["source_system"] == "SAMPLE",
                }
            )
        return {"items": items, "next_cursor": next_cursor}


_DETAIL = """
SELECT i.subtotal_minor, i.tax_minor, i.payment_terms, i.po_number, i.project_ref, i.description,
       i.line_items, i.diverges_from_source, i.field_provenance, i.source_row, f.file_name
  FROM invoices i
  LEFT JOIN import_batches b ON b.id = i.import_batch_id AND b.workspace_id = i.workspace_id
  LEFT JOIN stored_files f ON f.id = b.file_id AND f.workspace_id = b.workspace_id
 WHERE i.id = %s
"""


def invoice_detail(ctx: RequestContext, invoice_id: UUID) -> dict[str, Any]:
    with tenant_tx(ctx):
        return detail_in_tx(ctx, invoice_id)


def detail_in_tx(ctx: RequestContext, invoice_id: UUID) -> dict[str, Any]:
    """Runs inside the caller's transaction, so a write can answer with the state it just made."""
    now = _now()
    today = _today(now)
    where, params = _where(ctx, ListQuery())
    scope = (where + " AND " if where else " WHERE ") + "i.id = %(invoice_id)s"
    rows = _enrich(fetch_all(_SELECT + scope, {**params, "invoice_id": invoice_id}), now, today)  # noqa: S608
    extra = fetch_one(_DETAIL, [invoice_id])
    if not rows or extra is None:
        raise _not_found()
    row = rows[0]
    entry: QueueEntry = row["entry"]
    as_of = row["coverage_as_of"]
    provenance = _loaded(extra["field_provenance"]) or {}
    return {
        "version": row["version"],
        "facts": {
            "id": str(row["id"]),
            "invoice_number": row["invoice_number"],
            "client_id": str(row["client_id"]),
            "client_name": row["client_name"],
            "status": row["status"],
            "currency": row["currency"],
            "issue_date": row["issue_date"].isoformat() if row["issue_date"] else None,
            "due_date": row["due_date"].isoformat(),
            "gross_minor": row["gross_minor"],
            "subtotal_minor": extra["subtotal_minor"],
            "tax_minor": extra["tax_minor"],
            "payment_terms": extra["payment_terms"],
            "po_number": extra["po_number"],
            "project_ref": extra["project_ref"],
            "description": extra["description"],
            "line_items": _loaded(extra["line_items"]) or [],
            "diverges_from_source": extra["diverges_from_source"],
            "corrected_fields": sorted(name for name, source in provenance.items() if source == "USER"),
            "assignee_id": str(row["assignee_id"]) if row["assignee_id"] else None,
        },
        "derived": {
            "payment_status": row["payment_status"],
            "evidence_coverage": entry.coverage,
            "evidence_as_of": as_of.isoformat() if as_of else None,
            "outstanding_minor": row["outstanding_minor"],
            "paid_minor": row["paid_minor"],
            "overpayment_flag": row["overpayment_flag"],
            "dispute_status": row["dispute_status"],
            "reminder_status": row["reminder_status"],
            "days_overdue": entry.days_overdue,
            "due_bucket": entry.due_bucket,
        },
        "ai_claims": [],
        "provenance": {
            "source_system": row["source_system"],
            "file_name": extra["file_name"],
            "source_row": _loaded(extra["source_row"]),
            "import_id": str(row["import_batch_id"]) if row["import_batch_id"] else None,
        },
        "recommended_action": _recommended(ctx, entry),
        "reasons": [{"code": r.code, "label": r.label, "link": r.link} for r in entry.reasons],
        "why_not": [{"code": w.code, "label": w.label} for w in entry.why_not],
        "allowed_actions": allowed_actions(
            ctx.role or "", row["status"], row["payment_status"], row["paid_minor"]
        ),
    }


def dashboard(ctx: RequestContext) -> dict[str, Any]:
    """Totals per currency, since an amount in one currency never adds to another's."""
    with tenant_tx(ctx):
        now = _now()
        today = _today(now)
        rows = _enrich(fetch_all(_SELECT), now, today)
        sample = fetch_one("SELECT EXISTS (SELECT 1 FROM invoices WHERE source_system = 'SAMPLE') AS found")
    blocks = []
    for currency in sorted({row["currency"] for row in rows}):
        mine = [row for row in rows if row["currency"] == currency]
        tiles = []
        for key in TILES:
            hits = [
                r
                for r in mine
                if tile_matches(
                    key,
                    r["status"],
                    r["payment_status"],
                    r["dispute_status"],
                    r["reminder_status"],
                    r["due_date"],
                    today,
                )
            ]
            tiles.append(
                {
                    "key": key,
                    "count": len(hits),
                    "amount_minor": sum(r["outstanding_minor"] for r in hits),
                    "filter": {"tile": key, "currency": currency},
                }
            )
        open_rows = [r for r in mine if is_open(r["status"], r["payment_status"])]
        aging = []
        for bucket in AGING_BUCKETS:
            hits = [r for r in open_rows if r["entry"].aging == bucket]
            aging.append(
                {
                    "bucket": bucket,
                    "count": len(hits),
                    "amount_minor": sum(r["outstanding_minor"] for r in hits),
                    "filter": {"aging": bucket, "currency": currency},
                }
            )
        blocks.append({"currency": currency, "tiles": tiles, "aging": aging})
    return {
        "currencies": blocks,
        "has_sample_data": bool(sample and sample["found"]),
        "as_of_date": today.isoformat(),
    }


__all__ = [
    "ENDED_STATUSES",
    "SORTS",
    "ListQuery",
    "allowed_actions",
    "detail_in_tx",
    "dashboard",
    "invoice_detail",
    "list_invoices",
    "queue",
]
