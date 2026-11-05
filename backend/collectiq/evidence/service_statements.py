"""Statement import (E053, TSD M09): credits become evidence rows; nothing here allocates or marks paid.

The same file imported twice adds nothing (INV-11). Identical same-day rows are told apart by their
position in the file; when an earlier import already holds some of them, the extra ones wait for a person.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

from django.conf import settings

from collectiq.audit import record
from collectiq.evidence import service_accounts
from collectiq.evidence.parsers.base import MappingError, RawRow, StatementMapping
from collectiq.evidence.parsers.generic_csv import GenericCsvParser, fingerprint, reference_candidates
from collectiq.invoices.domain.csv_parse import DATE_FORMATS, CsvRejected, sniff_upload
from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, execute_many, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.platform.scan import get_scanner
from collectiq.platform.storage import storage_key

KIND = "STATEMENT_CSV"
SOURCE_TYPES = ("BANK_CSV", "UPI_CSV", "CASH_LOG")
MAPPING_FIELDS = ("date", "description", "amount", "credit", "debit", "currency", "balance", "reference")
REPEATED = "REPEATED_SAME_DAY"


@dataclass(frozen=True, slots=True)
class StatementOptions:
    source_type: str
    mapping: Mapping[str, Any]
    date_format: str | None = None
    include_debits: bool = False
    coverage_from: date | None = None
    coverage_to: date | None = None
    skip_invalid: bool = False
    confirm_repeated: bool = False
    dry_run: bool = False


@dataclass(slots=True)
class _Planned:
    row: RawRow
    fingerprint: str
    index: int


def _invalid(field: str, message: str) -> ProblemError:
    return ProblemError(
        "VALIDATION_FAILED",
        422,
        "Some fields are invalid.",
        {"errors": [{"field": field, "message": message}]},
    )


def _statement_mapping(raw: Mapping[str, Any]) -> StatementMapping:
    unknown = sorted(set(raw) - set(MAPPING_FIELDS))
    if unknown:
        raise _invalid("mapping", f"Unknown mapping field: {unknown[0]}.")
    values = {k: str(v).strip() or None for k, v in raw.items() if v is not None}
    for required in ("date", "description"):
        if not values.get(required):
            raise _invalid("mapping", f"Choose the column for {required}.")
    mapping = StatementMapping(**values)  # type: ignore[arg-type]
    if not mapping.is_usable():
        raise _invalid(
            "mapping", "Choose either one amount column, or a credit and/or a debit column, not both."
        )
    return mapping


def _check_options(options: StatementOptions) -> None:
    if options.source_type not in SOURCE_TYPES:
        raise _invalid("source_type", "This source type is not supported.")
    if options.date_format is not None and options.date_format not in DATE_FORMATS:
        raise _invalid("date_format", "This date format is not supported.")
    start, end = options.coverage_from, options.coverage_to
    if (start is None) != (end is None):
        raise _invalid("coverage_to", "Give both ends of the range you looked at, or neither.")
    if start is not None and end is not None:
        if end < start:
            raise _invalid("coverage_to", "The end of the range comes before its start.")
        if end > clock.today():
            raise _invalid("coverage_to", "A statement cannot cover days that have not happened yet.")


def _account(account_id: UUID) -> dict[str, Any]:
    row = fetch_one("SELECT id, currency, status FROM payment_accounts WHERE id = %s", [account_id])
    if row is None:
        raise ProblemError("NOT_FOUND", 404, "We could not find that.")
    if row["status"] != "ACTIVE":
        raise ProblemError(
            "STATE_TRANSITION_INVALID", 409, "This account is inactive. Activate it before importing."
        )
    return row


def _read(data: bytes, mapping: StatementMapping, options: StatementOptions, currency: str) -> list[RawRow]:
    try:
        return list(GenericCsvParser().parse(data, mapping, options.date_format, currency))
    except MappingError as error:
        raise _invalid("mapping", str(error)) from None
    except CsvRejected as rejection:
        raise ProblemError("IMPORT_VALIDATION_FAILED", 422, rejection.reason) from None


def _existing_counts(account_id: UUID, fingerprints: list[str]) -> Counter[str]:
    if not fingerprints:
        return Counter()
    found = fetch_all(
        "SELECT fingerprint, count(*) AS n FROM payment_transactions"
        " WHERE payment_account_id = %s AND fingerprint = ANY(%s::text[]) GROUP BY fingerprint",
        [account_id, fingerprints],
    )
    return Counter({row["fingerprint"]: row["n"] for row in found})


def _plan(rows: list[RawRow], account: Mapping[str, Any], options: StatementOptions) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    kept: list[tuple[RawRow, str]] = []
    discarded = 0
    for row in rows:
        problem = (row.error_field, row.error) if row.error else None
        if problem is None and row.currency != account["currency"]:
            problem = ("currency", f"This row is in {row.currency}; the account holds {account['currency']}.")
        if problem is not None:
            errors.append({"row": row.number, "field": problem[0], "message": problem[1]})
        elif row.direction == "DEBIT" and not options.include_debits:
            discarded += 1
        else:
            scope = str(account["id"]) + ("/DEBIT" if row.direction == "DEBIT" else "")
            assert row.value_date and row.amount_minor and row.currency
            kept.append(
                (
                    row,
                    fingerprint(
                        scope,
                        row.value_date,
                        row.amount_minor,
                        row.currency,
                        row.description,
                        row.balance_minor,
                    ),
                )
            )
    seen: Counter[str] = Counter()
    planned = []
    for row, print_ in kept:
        planned.append(_Planned(row, print_, seen[print_]))
        seen[print_] += 1
    held_before = _existing_counts(account["id"], list(seen))
    to_add: list[_Planned] = []
    held: list[dict[str, Any]] = []
    skipped = 0
    for item in planned:
        have = held_before[item.fingerprint]
        if item.index < have:
            skipped += 1
        elif have > 0 and not options.confirm_repeated:
            held.append({"row": item.row.number, "reason": REPEATED})
        else:
            to_add.append(item)
    counts = {
        "total_rows": len(rows),
        "added": len(to_add),
        "skipped_duplicate": skipped,
        "held_for_confirmation": len(held),
        "discarded_debits": discarded,
        "invalid": len(errors),
    }
    return {"counts": counts, "errors": errors, "held_rows": held, "to_add": to_add}


def _report(batch_id: UUID | None, plan: Mapping[str, Any], options: StatementOptions) -> dict[str, Any]:
    coverage = None
    if options.coverage_from and options.coverage_to:
        coverage = {
            "covers_from": options.coverage_from.isoformat(),
            "covers_to": options.coverage_to.isoformat(),
        }
    return {
        "id": None if batch_id is None else str(batch_id),
        "status": "PREVIEW" if options.dry_run else "COMMITTED",
        "dry_run": options.dry_run,
        "counts": plan["counts"],
        "errors": plan["errors"],
        "held_rows": plan["held_rows"],
        "coverage": coverage if not options.dry_run else None,
    }


def import_statement(
    ctx: RequestContext, account_id: UUID, file_name: str, data: bytes, options: StatementOptions
) -> dict[str, Any]:
    from collectiq.invoices.service_import import _rejected, _safe_file_name

    name = _safe_file_name(file_name)
    try:
        sniff_upload(name, data, settings.MAX_UPLOAD_BYTES)
    except CsvRejected as rejection:
        raise _rejected(rejection) from None
    _check_options(options)
    mapping = _statement_mapping(options.mapping)
    with tenant_tx(ctx):
        account = _account(account_id)
        plan = _plan(_read(data, mapping, options, account["currency"]), account, options)
        if options.dry_run:
            return _report(None, plan, options)
        if plan["errors"] and not options.skip_invalid:
            raise ProblemError(
                "IMPORT_VALIDATION_FAILED",
                422,
                "Some rows could not be read. Nothing was imported.",
                {"errors": plan["errors"], "counts": plan["counts"]},
            )
        batch_id = _store(ctx, account, name, data, mapping, options, plan)
        return _report(batch_id, plan, options)


def _store(
    ctx: RequestContext,
    account: Mapping[str, Any],
    name: str,
    data: bytes,
    mapping: StatementMapping,
    options: StatementOptions,
    plan: Mapping[str, Any],
) -> UUID:
    file_id = uuid4()
    key = storage_key(ctx, "imports", str(file_id))
    execute(
        "INSERT INTO stored_files (id, workspace_id, kind, storage_key, file_name, content_sha256,"
        " size_bytes, scan_status, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [
            file_id,
            ctx.workspace_id,
            KIND,
            key,
            name,
            hashlib.sha256(data).digest(),
            len(data),
            get_scanner().scan(data),
            ctx.user_id,
        ],
    )
    mapping_json = json.dumps({f: getattr(mapping, f) for f in MAPPING_FIELDS if getattr(mapping, f)})
    batch_id = fetch_all(
        "INSERT INTO import_batches (workspace_id, kind, file_id, source_system, mapping, date_format,"
        " status,"
        " counts, payment_account_id, created_by)"
        " VALUES (%s, %s, %s, %s, %s::jsonb, %s, 'COMMITTED', %s::jsonb, %s, %s)"
        " RETURNING id",
        [
            ctx.workspace_id,
            KIND,
            file_id,
            options.source_type,
            mapping_json,
            options.date_format,
            json.dumps(plan["counts"]),
            account["id"],
            ctx.user_id,
        ],
    )[0]["id"]
    execute_many(
        "INSERT INTO payment_transactions (workspace_id, payment_account_id, source_type, direction,"
        " amount_minor,"
        " currency, value_date, reference, reference_candidates, payer_descriptor, balance_minor,"
        " fingerprint, occurrence_index, import_batch_id, entered_by)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT (workspace_id, payment_account_id, fingerprint, occurrence_index) DO NOTHING",
        [
            [
                ctx.workspace_id,
                account["id"],
                options.source_type,
                i.row.direction,
                i.row.amount_minor,
                i.row.currency,
                i.row.value_date,
                i.row.reference,
                reference_candidates(f"{i.row.reference or ''} {i.row.description}"),
                i.row.description or None,
                i.row.balance_minor,
                i.fingerprint,
                i.index,
                batch_id,
                ctx.user_id,
            ]
            for i in plan["to_add"]
        ],
    )
    if options.date_format is not None:
        execute(
            "INSERT INTO import_mappings (workspace_id, kind, mapping, date_format)"
            " VALUES (%s, %s, %s::jsonb, %s)"
            " ON CONFLICT (workspace_id, kind) DO UPDATE SET mapping = EXCLUDED.mapping,"
            " date_format = EXCLUDED.date_format, updated_at = now()",
            [ctx.workspace_id, f"STATEMENT_{options.source_type}", mapping_json, options.date_format],
        )
    record(
        ctx,
        "transactions.imported",
        "import_batch",
        str(batch_id),
        after={
            **plan["counts"],
            "payment_account_id": str(account["id"]),
            "source_type": options.source_type,
        },
    )
    if options.coverage_from and options.coverage_to:
        service_accounts.record_coverage(
            ctx, account["id"], options.coverage_from, options.coverage_to, batch_id
        )
    return batch_id
