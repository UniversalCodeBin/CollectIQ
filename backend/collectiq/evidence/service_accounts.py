"""Declared receiving accounts, the ranges looked at, and attestations (E029-E032, E054).

Coverage is recomputed in the transaction of whatever changed it (SAD 6.7). It only ever moves the
`evidence_coverage` and `coverage_as_of` columns of `invoice_state`; payment status is not touched here.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from django.conf import settings

from collectiq.audit import record
from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError

from .domain.coverage import (
    Attestation,
    CoverageRange,
    account_coverage,
    coverage_as_of,
    coverage_status,
)

_ACCOUNT = "id, kind, label, currency, status, version"
_INSERT_ACCOUNT = (
    "INSERT INTO payment_accounts (workspace_id, kind, label, currency) VALUES (%s, %s, %s, %s)"
    " ON CONFLICT DO NOTHING RETURNING id, kind, label, currency, status, version"
)
_UPDATE_ACCOUNT = (
    "UPDATE payment_accounts SET label = %s, status = %s, version = version + 1, updated_at = now()"
    " WHERE id = %s RETURNING id, kind, label, currency, status, version"
)
MAX_INVOICES_PER_ATTESTATION = 500


def freshness_days() -> int:
    return int(getattr(settings, "EVIDENCE_FRESHNESS_DAYS", 7))


def _not_found() -> ProblemError:
    return ProblemError("NOT_FOUND", 404, "We could not find that.")


def _invalid(field: str, message: str) -> ProblemError:
    return ProblemError(
        "VALIDATION_FAILED",
        422,
        "Some fields are invalid.",
        {"errors": [{"field": field, "message": message}]},
    )


def _account_dto(row: Mapping[str, Any]) -> dict[str, Any]:
    return {**row, "id": str(row["id"])}


def _require_account(account_id: UUID, lock: bool = False) -> dict[str, Any]:
    row = fetch_one(
        f"SELECT {_ACCOUNT} FROM payment_accounts WHERE id = %s{' FOR UPDATE' if lock else ''}",  # noqa: S608
        [account_id],
    )
    if row is None:
        raise _not_found()
    return row


def _day(moment: datetime) -> date:
    return moment.astimezone(UTC).date()


def _midnight(day: date | None) -> datetime | None:
    return datetime.combine(day, time.min, tzinfo=UTC) if day else None


# ---- recompute -----------------------------------------------------------------------------------


def recompute_coverage(ctx: RequestContext, invoice_ids: Sequence[UUID] | None = None) -> int:
    """Re-derive coverage for open invoices. Runs in the caller's transaction. Returns the rows changed."""
    today = clock.today()
    window = freshness_days()
    accounts = [str(r["id"]) for r in fetch_all("SELECT id FROM payment_accounts WHERE status = 'ACTIVE'")]
    ranges = [
        CoverageRange(str(r["payment_account_id"]), r["covers_from"], r["covers_to"])
        for r in fetch_all("SELECT payment_account_id, covers_from, covers_to FROM account_coverages")
    ]
    attestations = [
        Attestation(
            r["scope"],
            str(r["payment_account_id"]) if r["payment_account_id"] else None,
            str(r["invoice_id"]) if r["invoice_id"] else None,
            _day(r["as_of"]),
        )
        for r in fetch_all("SELECT scope, payment_account_id, invoice_id, as_of FROM evidence_attestations")
    ]
    wanted = list(invoice_ids) if invoice_ids is not None else None
    rows = fetch_all(
        "SELECT i.id, i.issue_date, s.evidence_coverage, s.coverage_as_of"
        "  FROM invoices i JOIN invoice_state s ON s.invoice_id = i.id AND s.workspace_id = i.workspace_id"
        " WHERE i.status IN ('ACTIVE', 'PENDING_REVIEW')"
        "   AND (%(ids)s::uuid[] IS NULL OR i.id = ANY(%(ids)s::uuid[]))",
        {"ids": wanted},
    )
    changed = 0
    for row in rows:
        reached = coverage_as_of(row["issue_date"], str(row["id"]), accounts, ranges, attestations)
        state = coverage_status(reached, today, window)
        before = _day(row["coverage_as_of"]) if row["coverage_as_of"] else None
        if state == row["evidence_coverage"] and reached == before:
            continue
        execute(
            "UPDATE invoice_state SET evidence_coverage = %s, coverage_as_of = %s,"
            " version = version + 1, updated_at = now() WHERE invoice_id = %s",
            [state, _midnight(reached), row["id"]],
        )
        changed += 1
    return changed


# ---- accounts (E029-E031) ---------------------------------------------------------------------


def _summaries(account_ids: Sequence[UUID]) -> dict[str, dict[str, Any]]:
    ranges = fetch_all(
        "SELECT payment_account_id, covers_from, covers_to FROM account_coverages"
        " WHERE payment_account_id = ANY(%s::uuid[])",
        [list(account_ids)],
    )
    atts = fetch_all(
        "SELECT payment_account_id, as_of FROM evidence_attestations"
        " WHERE scope = 'ACCOUNT' AND payment_account_id = ANY(%s::uuid[])",
        [list(account_ids)],
    )
    today, window = clock.today(), freshness_days()
    out: dict[str, dict[str, Any]] = {}
    for account_id in account_ids:
        key = str(account_id)
        summary = account_coverage(
            [
                CoverageRange(key, r["covers_from"], r["covers_to"])
                for r in ranges
                if r["payment_account_id"] == account_id
            ],
            [
                Attestation("ACCOUNT", key, None, _day(a["as_of"]))
                for a in atts
                if a["payment_account_id"] == account_id
            ],
        )
        out[key] = {
            "covered_through": summary.covered_through,
            "statements_through": summary.statements_through,
            "attested_through": summary.attested_through,
            "gaps": [{"from": a, "to": b} for a, b in summary.gaps],
            "coverage_status": coverage_status(summary.covered_through, today, window),
        }
    return out


def list_accounts(ctx: RequestContext, limit: int, cursor: UUID | None) -> dict[str, Any]:
    with tenant_tx(ctx):
        rows = fetch_all(
            f"SELECT {_ACCOUNT} FROM payment_accounts"  # noqa: S608
            " WHERE %(cursor)s::uuid IS NULL OR id > %(cursor)s::uuid ORDER BY id LIMIT %(limit)s",
            {"cursor": cursor, "limit": limit + 1},
        )
        page = rows[:limit]
        summaries = _summaries([r["id"] for r in page]) if page else {}
    items = [{**_account_dto(r), **summaries[str(r["id"])]} for r in page]
    return {"items": items, "next_cursor": str(page[-1]["id"]) if len(rows) > limit else None}


def create_account(ctx: RequestContext, kind: str, label: str, currency: str) -> dict[str, Any]:
    label = " ".join(label.split())
    if not label:
        raise _invalid("label", "Give the account a name.")
    with tenant_tx(ctx):
        row = fetch_one(
            _INSERT_ACCOUNT,
            [ctx.workspace_id, kind, label, currency],
        )
        if row is None:
            raise ProblemError("DUPLICATE_RESOURCE", 409, "An account with that name already exists.")
        record(
            ctx,
            "account.declared",
            "payment_account",
            str(row["id"]),
            after={"kind": kind, "label": label, "currency": currency},
        )
        recompute_coverage(ctx)  # a new account has no statement yet, so coverage can only narrow
    return _account_dto(row)


def update_account(
    ctx: RequestContext, account_id: UUID, expected_version: int, changes: Mapping[str, Any]
) -> dict[str, Any]:
    with tenant_tx(ctx):
        current = _require_account(account_id, lock=True)
        if current["version"] != expected_version:
            raise ProblemError("CONFLICT_VERSION", 409, "This account changed. Reload and try again.")
        wanted = dict(changes)
        if "label" in wanted:
            wanted["label"] = " ".join(wanted["label"].split())
            if not wanted["label"]:
                raise _invalid("label", "Give the account a name.")
        changed = {k: v for k, v in wanted.items() if current[k] != v}
        if not changed:
            return _account_dto(current)
        try:
            row = fetch_all(
                _UPDATE_ACCOUNT,
                [
                    changed.get("label", current["label"]),
                    changed.get("status", current["status"]),
                    account_id,
                ],
            )[0]
        except Exception as exc:  # unique label index
            if "payment_accounts_label" in str(exc):
                raise ProblemError(
                    "DUPLICATE_RESOURCE", 409, "An account with that name already exists."
                ) from exc
            raise
        record(
            ctx,
            "account.updated",
            "payment_account",
            str(account_id),
            before={k: current[k] for k in changed},
            after=changed,
        )
        if "status" in changed:
            recompute_coverage(ctx)
    return _account_dto(row)


# ---- coverage and attestations (E032, E054) ---------------------------------------------------


def account_coverage_detail(ctx: RequestContext, account_id: UUID) -> dict[str, Any]:
    with tenant_tx(ctx):
        account = _require_account(account_id)
        summary = _summaries([account_id])[str(account_id)]
        ranges = fetch_all(
            "SELECT id, covers_from, covers_to, import_batch_id, created_at FROM account_coverages"
            " WHERE payment_account_id = %s ORDER BY covers_from, covers_to",
            [account_id],
        )
        attestations = fetch_all(
            "SELECT id, as_of, note, attested_by, created_at FROM evidence_attestations"
            " WHERE scope = 'ACCOUNT' AND payment_account_id = %s ORDER BY as_of DESC",
            [account_id],
        )
    days = freshness_days()
    through = summary["covered_through"]
    return {
        "account": _account_dto(account),
        **summary,
        "freshness_window_days": days,
        "ranges": [
            {
                "id": str(r["id"]),
                "covers_from": r["covers_from"],
                "covers_to": r["covers_to"],
                "import_batch_id": str(r["import_batch_id"]) if r["import_batch_id"] else None,
                "recorded_at": r["created_at"],
            }
            for r in ranges
        ],
        "attestations": [
            {
                "id": str(a["id"]),
                "as_of": a["as_of"],
                "note": a["note"],
                "attested_by": str(a["attested_by"]),
                "recorded_at": a["created_at"],
            }
            for a in attestations
        ],
        "fresh_until": through + timedelta(days=days) if through else None,
    }


def record_coverage(
    ctx: RequestContext,
    account_id: UUID,
    covers_from: date,
    covers_to: date,
    import_batch_id: UUID | None = None,
) -> None:
    """A confirmed statement range. Used by the statement import (T16) and by tests."""
    if covers_to < covers_from:
        raise _invalid("covers_to", "The end of the range comes before its start.")
    if covers_to > clock.today():
        raise _invalid("covers_to", "A statement cannot cover days that have not happened yet.")
    with tenant_tx(ctx):
        _require_account(account_id)
        execute(
            "INSERT INTO account_coverages (workspace_id, payment_account_id, covers_from, covers_to,"
            " import_batch_id, confirmed_by) VALUES (%s, %s, %s, %s, %s, %s)",
            [ctx.workspace_id, account_id, covers_from, covers_to, import_batch_id, ctx.user_id],
        )
        record(
            ctx,
            "coverage.recorded",
            "payment_account",
            str(account_id),
            after={"covers_from": covers_from.isoformat(), "covers_to": covers_to.isoformat()},
        )
        recompute_coverage(ctx)


def attest(
    ctx: RequestContext,
    scope: str,
    as_of: datetime,
    note: str | None,
    account_id: UUID | None = None,
    invoice_ids: Sequence[UUID] = (),
) -> dict[str, Any]:
    """'I checked; nothing is missing as of this time.' It widens what we have looked at, nothing more."""
    if as_of > clock.now():
        raise _invalid("as_of", "An attestation cannot be dated in the future.")
    if scope == "ACCOUNT":
        if account_id is None or invoice_ids:
            raise _invalid("account_id", "An account attestation names one account and no invoices.")
    elif scope == "INVOICE":
        if account_id is not None or not invoice_ids:
            raise _invalid("invoice_ids", "An invoice attestation names invoices and no account.")
        if len(set(invoice_ids)) != len(invoice_ids) or len(invoice_ids) > MAX_INVOICES_PER_ATTESTATION:
            raise _invalid("invoice_ids", f"Name each invoice once, at most {MAX_INVOICES_PER_ATTESTATION}.")
    else:
        raise _invalid("scope", "Use ACCOUNT or INVOICE.")
    with tenant_tx(ctx):
        if account_id is not None:
            _require_account(account_id)
        if invoice_ids:
            found = fetch_all("SELECT id FROM invoices WHERE id = ANY(%s::uuid[])", [list(invoice_ids)])
            if len(found) != len(invoice_ids):
                raise _not_found()
        targets: list[tuple[UUID | None, UUID | None]] = (
            [(account_id, None)] if scope == "ACCOUNT" else [(None, i) for i in invoice_ids]
        )
        ids: list[str] = []
        for acct, inv in targets:
            row = fetch_one(
                "INSERT INTO evidence_attestations"
                " (workspace_id, scope, payment_account_id, invoice_id, as_of, note, attested_by)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                [ctx.workspace_id, scope, acct, inv, as_of, note, ctx.user_id],
            )
            assert row
            ids.append(str(row["id"]))
            record(
                ctx,
                "attestation.recorded",
                "payment_account" if acct else "invoice",
                str(acct or inv),
                after={
                    "scope": scope,
                    "as_of": as_of.isoformat(),
                    "coverage_date": _day(as_of).isoformat(),
                    "attested_by": str(ctx.user_id),
                    "note": note,
                },
            )
        recompute_coverage(ctx, list(invoice_ids) if scope == "INVOICE" else None)
    return {"scope": scope, "as_of": as_of, "attestation_ids": ids, "coverage_date": _day(as_of)}
