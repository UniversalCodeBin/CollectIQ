"""Audit history: scoped search, CSV/JSON export and the hash-chain check (E099, E100).

Callers check permissions, because tenancy sits above audit.

The notice is the only claim made about the trail: append-only by database permissions, with a hash chain
that detects casual edits, and not tamper-resistant against a database superuser.
"""

import csv
import io
import json
from typing import Any

from collectiq.audit.service import record
from collectiq.platform.context import RequestContext
from collectiq.platform.db import fetch_all, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.platform.jobs import job_handler

NOTICE = (
    "Audit records are append-only by database permissions, with a hash chain that detects casual edits; "
    "not tamper-resistant against a database superuser."
)
FILTERS = ("action", "object_type", "object_id", "actor_id", "from", "to")
EXPORT_CAP = 10000
COLUMNS = (
    "id", "occurred_at", "actor_type", "actor_id", "action", "object_type", "object_id",
    "before", "after", "reason_codes", "policy_decision_id", "correlation_id",
)  # fmt: skip
_SELECT = (
    "SELECT id, occurred_at, actor_type, actor_id, action, object_type, object_id, before_masked,"
    " after_masked, reason_codes, policy_decision_id, correlation_id FROM audit_events"
)


def _where(filters: dict[str, str], cursor: int | None) -> tuple[str, list[Any]]:
    clauses: list[str] = ["TRUE"]
    args: list[Any] = []
    for name in ("action", "object_type", "object_id"):
        if name in filters:
            clauses.append(f"{name} = %s")
            args.append(filters[name])
    if "actor_id" in filters:
        clauses.append("actor_id::text = %s")
        args.append(filters["actor_id"])
    if "from" in filters:
        clauses.append("occurred_at >= %s::timestamptz")
        args.append(filters["from"])
    if "to" in filters:
        clauses.append("occurred_at <= %s::timestamptz")
        args.append(filters["to"])
    if cursor is not None:
        clauses.append("id < %s")
        args.append(cursor)
    return " AND ".join(clauses), args


def _dto(row: dict[str, Any]) -> dict[str, Any]:
    def js(value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value

    return {
        "id": row["id"],
        "occurred_at": row["occurred_at"].isoformat(),
        "actor_type": row["actor_type"],
        "actor_id": str(row["actor_id"]) if row["actor_id"] else None,
        "action": row["action"],
        "object_type": row["object_type"],
        "object_id": row["object_id"],
        "before": js(row["before_masked"]),
        "after": js(row["after_masked"]),
        "reason_codes": row["reason_codes"] or [],
        "policy_decision_id": str(row["policy_decision_id"]) if row["policy_decision_id"] else None,
        "correlation_id": row["correlation_id"],
    }


def search(ctx: RequestContext, filters: dict[str, str], cursor: int | None, limit: int) -> dict[str, Any]:
    with tenant_tx(ctx):
        where, args = _where(filters, cursor)
        rows = fetch_all(f"{_SELECT} WHERE {where} ORDER BY id DESC LIMIT %s", [*args, limit + 1])  # noqa: S608
    page = rows[:limit]
    return {
        "items": [_dto(r) for r in page],
        "next_cursor": str(page[-1]["id"]) if len(rows) > limit else None,
        "notice": NOTICE,
    }


def neutralise(value: Any) -> str:
    """A spreadsheet runs a cell that starts with = + - @ tab or CR, so those get a leading quote."""
    text = "" if value is None else value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def export(ctx: RequestContext, filters: dict[str, str], fmt: str) -> dict[str, Any]:
    if fmt not in ("CSV", "JSON"):
        raise ProblemError("VALIDATION_FAILED", 422, "Choose CSV or JSON.")
    with tenant_tx(ctx):
        where, args = _where(filters, None)
        rows = fetch_all(f"{_SELECT} WHERE {where} ORDER BY id LIMIT %s", [*args, EXPORT_CAP + 1])  # noqa: S608
        truncated = len(rows) > EXPORT_CAP
        items = [_dto(r) for r in rows[:EXPORT_CAP]]
        if fmt == "CSV":
            out = io.StringIO()
            writer = csv.writer(out, lineterminator="\r\n")
            writer.writerow(COLUMNS)
            for item in items:
                writer.writerow([neutralise(item[c]) for c in COLUMNS])
            content = out.getvalue()
        else:
            content = json.dumps(items, sort_keys=True)
        record(
            ctx,
            "audit.exported",
            "audit_export",
            ctx.correlation_id,
            after={"format": fmt, "rows": len(items), "filters": sorted(filters)},
            reason_codes=["SENSITIVE_EXPORT"],
        )
    return {
        "format": fmt,
        "filename": f"audit-events.{fmt.lower()}",
        "rows": len(items),
        "truncated": truncated,
        "content": content,
        "notice": NOTICE,
    }


def verify_chain(ctx: RequestContext) -> dict[str, Any]:
    """Recomputes every link. A stored hash that differs from the recomputed one, or a prev_hash that is not
    the previous row's hash, is a break. A break is itself recorded."""
    with tenant_tx(ctx):
        rows = fetch_all(
            "SELECT id, prev_hash, hash, audit_event_hash(e) AS expected FROM audit_events e ORDER BY id"
        )
        bad: int | None = None
        previous: bytes | None = None
        for row in rows:
            prev = bytes(row["prev_hash"]) if row["prev_hash"] is not None else None
            if prev != previous or bytes(row["hash"]) != bytes(row["expected"]):
                bad = row["id"]
                break
            previous = bytes(row["hash"])
        if bad is not None:
            record(
                ctx,
                "audit.chain_break_detected",
                "audit_chain",
                str(bad),
                after={"first_bad_id": bad, "checked": len(rows)},
                reason_codes=["CHAIN_BREAK"],
            )
    return {"intact": bad is None, "first_bad_id": bad, "checked": len(rows)}


@job_handler("audit.verify_chain")
def _verify_job(ctx: RequestContext, payload: dict[str, Any]) -> None:
    verify_chain(ctx)
