"""Invoice CSV import (TSD M05): upload, map, review, then one all-or-nothing commit.

Nothing reaches the ledger before the commit. The upload is kept encrypted and read again for every
preview, so what is committed is what the file says now against what the ledger holds now.
"""

import csv
import hashlib
import io
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from django.conf import settings
from django.db import DatabaseError

from collectiq.audit import record
from collectiq.platform.context import RequestContext
from collectiq.platform.crypto import get_cipher
from collectiq.platform.db import execute, execute_many, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.platform.outbox import publish
from collectiq.platform.scan import get_scanner
from collectiq.platform.storage import get_storage, storage_key

from . import clients
from .domain.csv_parse import DATE_FORMATS, CsvRejected, ParsedCsv, parse_csv, sniff_upload
from .domain.reconcile import (
    ATTENTION,
    COMPARED,
    CONFLICT,
    DUPLICATE,
    IGNORE,
    INVALID,
    KEEP_BOTH,
    MERGE,
    NEW,
    POSSIBLE_DUPLICATE,
    UPDATE,
    UPDATED,
    ClientPlan,
    ClientRef,
    Existing,
    KnownClient,
    NewClient,
    Row,
    blockers,
    classify,
    match_clients,
    preview_counts,
    read_rows,
)
from .domain.validate import RowMapping, mapping_errors, normalize_number, suggest_mapping
from .state import create_states, refresh_after_total_changed

KIND = "INVOICE_CSV"
SOURCE_SYSTEM = "CSV"
FAILED_REASON = "Nothing was added. Something went wrong while saving this import. You can try again."
DEFAULT_ROW_LIMIT = 200

_BATCH = (
    "SELECT b.id, b.status, b.mapping, b.date_format, b.counts, b.failure_reason,"
    " f.id AS file_id, f.storage_key, f.file_name, f.scan_status"
    " FROM import_batches b JOIN stored_files f ON f.id = b.file_id AND f.workspace_id = b.workspace_id"
    " WHERE b.id = %s"
)
_OPEN = ("PREVIEW", "IMPORT_FAILED")
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


class ImportCommitFailed(Exception):
    """The database refused the commit and it rolled back. Its message may hold row values: do not log it."""


@dataclass(slots=True)
class _Evaluation:
    parsed: ParsedCsv
    rows: list[Row]
    plan: ClientPlan
    errors: list[tuple[str, str]]


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str | bytes) else value


def _not_found() -> ProblemError:
    return ProblemError("NOT_FOUND", 404, "We could not find that.")


def _rejected(rejection: CsvRejected) -> ProblemError:
    code, status = {
        "type": ("UNSUPPORTED_MEDIA_TYPE", 415),
        "size": ("PAYLOAD_TOO_LARGE", 413),
        "content": ("IMPORT_VALIDATION_FAILED", 422),
    }[rejection.kind]
    return ProblemError(code, status, rejection.reason)


def _field_errors(errors: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"field": name, "message": message} for name, message in errors]


def _safe_file_name(name: str) -> str:
    base = re.split(r"[/\\]", name)[-1]
    cleaned = "".join(character for character in base if character.isprintable()).strip()
    return cleaned[:255] or "upload.csv"


def _saved_mapping() -> dict[str, str] | None:
    row = fetch_one("SELECT mapping FROM import_mappings WHERE kind = %s", [KIND])
    return _json(row["mapping"]) if row else None


def _suggested(headers: Sequence[str]) -> dict[str, str]:
    saved = _saved_mapping()
    if saved and all(header in headers for header in saved.values()):
        return saved
    return suggest_mapping(headers)


def _batch(batch_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    row = fetch_one(_BATCH + (" FOR UPDATE OF b" if lock else ""), [batch_id])
    if row is None:
        raise _not_found()
    row["mapping"] = _json(row["mapping"])
    row["counts"] = _json(row["counts"])
    return row


def _require_open(batch: Mapping[str, Any]) -> None:
    if batch["status"] not in _OPEN:
        raise ProblemError(
            "STATE_TRANSITION_INVALID", 409, f"This import is already {batch['status'].lower()}."
        )


def _read_file(ctx: RequestContext, batch: Mapping[str, Any]) -> ParsedCsv:
    sealed = get_storage().get(ctx, batch["storage_key"])
    data = get_cipher().decrypt(ctx, sealed, str(batch["file_id"]).encode())
    return parse_csv(data, settings.MAX_IMPORT_ROWS)


def _known_clients() -> list[KnownClient]:
    names: dict[UUID, set[str]] = {}
    display: dict[UUID, str] = {}
    for row in fetch_all("SELECT id, display_name, normalized_name FROM clients"):
        names[row["id"]] = {row["normalized_name"]}
        display[row["id"]] = row["display_name"]
    for row in fetch_all("SELECT client_id, normalized_text FROM client_aliases WHERE kind = 'NAME'"):
        names[row["client_id"]].add(row["normalized_text"])
    emails: dict[UUID, set[str]] = {}
    for row in fetch_all("SELECT client_id, email FROM client_contacts"):
        emails.setdefault(row["client_id"], set()).add(str(row["email"]).casefold())
    return [
        KnownClient(client_id, display[client_id], frozenset(known), frozenset(emails.get(client_id, ())))
        for client_id, known in names.items()
    ]


def _existing(rows: Sequence[Row]) -> list[Existing]:
    client_ids = list({row.client for row in rows if isinstance(row.client, UUID)})
    external_ids = list({row.values["external_id"] for row in rows if row.values.get("external_id")})
    if not client_ids and not external_ids:
        return []
    found = fetch_all(
        "SELECT id, client_id, invoice_number, normalized_number, external_id, payment_references,"  # noqa: S608
        f" field_provenance, {', '.join(COMPARED)} FROM invoices"
        " WHERE source_system = %s AND (client_id = ANY(%s::uuid[]) OR external_id = ANY(%s::text[]))",
        [SOURCE_SYSTEM, client_ids, external_ids],
    )
    return [
        Existing(
            id=row["id"],
            client_id=row["client_id"],
            invoice_number=row["invoice_number"],
            normalized_number=row["normalized_number"],
            external_id=row["external_id"],
            payment_references=list(row["payment_references"]),
            provenance=_json(row["field_provenance"]),
            values={name: row[name] for name in COMPARED},
        )
        for row in found
    ]


def _evaluate(ctx: RequestContext, batch: Mapping[str, Any], decisions: Mapping[str, Any]) -> _Evaluation:
    parsed = _read_file(ctx, batch)
    mapping = RowMapping(batch["mapping"], parsed.headers)
    rows = read_rows(parsed.rows, mapping, batch["date_format"])
    plan = match_clients(rows, _known_clients(), decisions.get("clients", {}))
    errors = classify(rows, _existing(rows), decisions.get("rows", {}))
    return _Evaluation(parsed, rows, plan, [*plan.errors, *errors])


def _row_out(row: Row) -> dict[str, Any]:
    return {
        "row": row.number,
        "status": row.status,
        "invoice_number": row.values.get("invoice_number"),
        "client_name": row.values.get("client_name"),
        "currency": row.values.get("currency"),
        "errors": [{"field": error.field, "message": error.message} for error in row.errors],
        "diffs": row.diffs,
        "matches": row.matches,
        "allowed_decisions": list(row.allowed),
        "conflict": row.conflict if row.status == CONFLICT else None,
    }


def _page(rows: Sequence[Row], limit: int, after_row: int) -> tuple[list[dict[str, Any]], int | None]:
    waiting = [row for row in rows if row.status in ATTENTION and row.number > after_row]
    page = waiting[:limit]
    more = len(waiting) > limit
    return [_row_out(row) for row in page], page[-1].number if more else None


def _action(action: str, reason: str | None) -> dict[str, Any]:
    return {"action": action, "allowed": reason is None, "reason": reason}


def _allowed_actions(status: str, commit_reason: str | None) -> list[dict[str, Any]]:
    if status not in _OPEN:
        closed = f"This import is already {status.lower()}."
        return [_action("COMMIT", closed), _action("DISCARD", closed)]
    return [_action("COMMIT", commit_reason), _action("DISCARD", None)]


def _view(
    ctx: RequestContext,
    batch: Mapping[str, Any],
    limit: int = DEFAULT_ROW_LIMIT,
    after_row: int = 0,
) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": str(batch["id"]),
        "kind": KIND,
        "status": batch["status"],
        "file_name": batch["file_name"],
        "scan_status": batch["scan_status"],
        "headers": [],
        "suggested_mapping": {},
        "date_format_options": list(DATE_FORMATS),
        "mapping": batch["mapping"],
        "date_format": batch["date_format"],
        "counts": batch["counts"],
        "rows": [],
        "next_row": None,
        "client_matches": [],
        "failure_reason": batch["failure_reason"],
    }
    if batch["status"] not in _OPEN:
        return {**view, "allowed_actions": _allowed_actions(batch["status"], None)}
    if batch["mapping"] is None:
        parsed = _read_file(ctx, batch)
        return {
            **view,
            "headers": parsed.headers,
            "suggested_mapping": _suggested(parsed.headers),
            "counts": {"total_rows": len(parsed.rows)},
            "allowed_actions": _allowed_actions(
                batch["status"], "Choose which column holds each field first."
            ),
        }
    evaluation = _evaluate(ctx, batch, {})
    rows, next_row = _page(evaluation.rows, limit, after_row)
    reasons = blockers(evaluation.rows, skip_invalid=False)
    return {
        **view,
        "headers": evaluation.parsed.headers,
        "suggested_mapping": _suggested(evaluation.parsed.headers),
        "counts": preview_counts(evaluation.rows, evaluation.plan),
        "rows": rows,
        "next_row": next_row,
        "client_matches": evaluation.plan.questions,
        "allowed_actions": _allowed_actions(batch["status"], reasons[0] if reasons else None),
    }


def upload_invoices(ctx: RequestContext, file_name: str, data: bytes) -> dict[str, Any]:
    """Refused before anything is stored. The malware scanner is a no-op port until OD-14 is decided."""
    name = _safe_file_name(file_name)
    try:
        sniff_upload(name, data, settings.MAX_UPLOAD_BYTES)
        parsed = parse_csv(data, settings.MAX_IMPORT_ROWS)
    except CsvRejected as rejection:
        raise _rejected(rejection) from None
    file_id = uuid4()
    key = storage_key(ctx, "imports", str(file_id))
    scan_status = get_scanner().scan(data)
    with tenant_tx(ctx):
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
                scan_status,
                ctx.user_id,
            ],
        )
        batch_id = fetch_all(
            "INSERT INTO import_batches (workspace_id, kind, file_id, source_system, counts, created_by)"
            " VALUES (%s, %s, %s, %s, %s::jsonb, %s) RETURNING id",
            [
                ctx.workspace_id,
                KIND,
                file_id,
                SOURCE_SYSTEM,
                json.dumps({"total_rows": len(parsed.rows)}),
                ctx.user_id,
            ],
        )[0]["id"]
        record(ctx, "import.uploaded", "import_batch", str(batch_id), after={"rows": len(parsed.rows)})
        get_storage().put(ctx, key, get_cipher().encrypt(ctx, data, str(file_id).encode()))
        return _view(ctx, _batch(batch_id))


def get_import(
    ctx: RequestContext, batch_id: UUID, limit: int = DEFAULT_ROW_LIMIT, after_row: int = 0
) -> dict[str, Any]:
    with tenant_tx(ctx):
        return _view(ctx, _batch(batch_id), limit, after_row)


def set_mapping(
    ctx: RequestContext, batch_id: UUID, mapping: Mapping[str, str], date_format: str | None
) -> dict[str, Any]:
    with tenant_tx(ctx):
        batch = _batch(batch_id, lock=True)
        _require_open(batch)
        headers = _read_file(ctx, batch).headers
        errors = mapping_errors(mapping, headers)
        if date_format is not None and date_format not in DATE_FORMATS:
            errors.append(("date_format", "This date format is not supported."))
        if errors:
            raise ProblemError(
                "VALIDATION_FAILED", 422, "Some fields are invalid.", {"errors": _field_errors(errors)}
            )
        batch.update(mapping=dict(mapping), date_format=date_format, status="PREVIEW", failure_reason=None)
        evaluation = _evaluate(ctx, batch, {})
        counts = preview_counts(evaluation.rows, evaluation.plan)
        execute(
            "UPDATE import_batches SET mapping = %s::jsonb, date_format = %s, counts = %s::jsonb,"
            " status = 'PREVIEW', failure_reason = NULL, updated_at = now() WHERE id = %s",
            [json.dumps(batch["mapping"]), date_format, json.dumps(counts), batch_id],
        )
        record(ctx, "import.previewed", "import_batch", str(batch_id), after={"counts": counts})
        batch["counts"] = counts
        return _view(ctx, batch)


def _invoice_values(batch_id: UUID, row: Row, invoice_id: UUID, client_id: UUID) -> dict[str, Any]:
    values = row.values
    reference = values.get("payment_reference")
    provenance = {name: "IMPORT" for name in ("invoice_number", *COMPARED) if values.get(name) is not None}
    return {
        "id": invoice_id,
        "client_id": client_id,
        "external_id": values.get("external_id"),
        "invoice_number": values["invoice_number"],
        "normalized_number": normalize_number(values["invoice_number"]),
        "payment_references": [reference] if reference else [],
        "import_batch_id": batch_id,
        "source_row": row.number,
        "field_provenance": json.dumps(provenance),
        **{name: values.get(name) for name in COMPARED},
    }


def _raw_row(headers: Sequence[str], row: Row) -> bytes:
    return json.dumps(dict(zip(headers, row.cells, strict=False)), ensure_ascii=False).encode()


def _will_write(row: Row) -> bool:
    if row.action == IGNORE:
        return False
    return row.status == NEW or row.status in (UPDATED, POSSIBLE_DUPLICATE)


def _create_clients(ctx: RequestContext, rows: Sequence[Row]) -> dict[str, UUID]:
    """Only clients a written row needs, under the name the file gave them first."""
    display: dict[str, str] = {}
    for row in rows:
        if not row.errors:
            display.setdefault(row.name, row.values["client_name"])
    created: dict[str, UUID] = {}
    for row in rows:
        if _will_write(row) and isinstance(row.client, NewClient) and row.client.name not in created:
            name = row.client.name
            created[name] = UUID(clients.create_client(ctx, {"display_name": display[name]})["id"])
    return created


def _client_id(ref: ClientRef | None, created: Mapping[str, UUID]) -> UUID | None:
    if isinstance(ref, NewClient):
        return created.get(ref.name)
    return ref


def _link_contacts_and_aliases(
    ctx: RequestContext, evaluation: _Evaluation, created: Mapping[str, UUID]
) -> None:
    for ref, text in evaluation.plan.aliases:
        client_id = _client_id(ref, created)
        if client_id is not None:
            clients.add_alias(ctx, client_id, text)
    done: set[tuple[UUID, str]] = set()
    for row in evaluation.rows:
        email = row.values.get("client_email")
        client_id = _client_id(row.client, created)
        if not email or client_id is None or row.action == IGNORE or row.status == INVALID:
            continue
        if (client_id, email) not in done:
            done.add((client_id, email))
            clients.ensure_contact(ctx, client_id, email)


_INSERT_INVOICE = (
    "INSERT INTO invoices (workspace_id, id, client_id, source_system, external_id, invoice_number,"
    " normalized_number, issue_date, due_date, currency, gross_minor, subtotal_minor, tax_minor,"
    " payment_terms, payment_references, po_number, project_ref, description, import_batch_id, source_row,"
    " raw_row_ciphertext, field_provenance, possible_duplicate_of)"
    " VALUES (%(workspace_id)s, %(id)s, %(client_id)s, %(source_system)s, %(external_id)s,"
    " %(invoice_number)s,"
    " %(normalized_number)s, %(issue_date)s, %(due_date)s, %(currency)s, %(gross_minor)s, %(subtotal_minor)s,"
    " %(tax_minor)s, %(payment_terms)s, %(payment_references)s::text[], %(po_number)s, %(project_ref)s,"
    " %(description)s, %(import_batch_id)s, %(source_row)s, %(raw_row_ciphertext)s,"
    " %(field_provenance)s::jsonb, %(possible_duplicate_of)s)"
)


def _duplicate_of(row: Row, created_rows: Mapping[int, UUID]) -> UUID | None:
    """The invoice this one was kept alongside: the ledger's, or a row written earlier from this file."""
    if row.status != POSSIBLE_DUPLICATE:
        return None
    if row.target is not None:
        return row.target.id
    return next((created_rows[m["row"]] for m in row.matches if m["row"] in created_rows), None)


def _insert_invoices(
    ctx: RequestContext,
    batch_id: UUID,
    evaluation: _Evaluation,
    created: Mapping[str, UUID],
) -> int:
    to_create = [
        row
        for row in evaluation.rows
        if row.action != IGNORE
        and (row.status == NEW or (row.status == POSSIBLE_DUPLICATE and row.action == KEEP_BOTH))
    ]
    if not to_create:
        return 0
    headers = evaluation.parsed.headers
    ids = [uuid4() for _ in to_create]
    sealed = get_cipher().encrypt_many(
        ctx,
        [_raw_row(headers, row) for row in to_create],
        [str(invoice_id).encode() for invoice_id in ids],
    )
    created_rows: dict[int, UUID] = {}
    parameters = []
    for row, invoice_id, ciphertext in zip(to_create, ids, sealed, strict=True):
        client_id = _client_id(row.client, created)
        if client_id is None:
            raise ProblemError("INTERNAL_ERROR", 500, FAILED_REASON)
        parameters.append(
            {
                **_invoice_values(batch_id, row, invoice_id, client_id),
                "workspace_id": ctx.workspace_id,
                "source_system": SOURCE_SYSTEM,
                "raw_row_ciphertext": ciphertext,
                "possible_duplicate_of": _duplicate_of(row, created_rows),
            }
        )
        created_rows[row.number] = invoice_id
    execute_many(_INSERT_INVOICE, parameters)
    create_states(parameters)
    for row, invoice_id in zip(to_create, ids, strict=True):
        record(
            ctx,
            "invoice.created",
            "invoice",
            str(invoice_id),
            after={
                "invoice_number": row.values["invoice_number"],
                "batch_id": str(batch_id),
                "source_row": row.number,
                "currency": row.values["currency"],
                "gross_minor": row.values["gross_minor"],
            },
        )
    return len(to_create)


def _apply_update(ctx: RequestContext, batch_id: UUID, headers: Sequence[str], row: Row) -> None:
    target = row.target
    if target is None:
        raise ProblemError("INTERNAL_ERROR", 500, FAILED_REASON)
    applied = [diff for diff in row.diffs if not diff["kept"]]
    any_kept = any(diff["kept"] for diff in row.diffs)
    sets = []
    parameters: list[Any] = []
    for diff in applied:
        name = diff["field"]
        if name == "payment_references":
            sets.append("payment_references = %s::text[]")
            parameters.append(diff["incoming"])
        elif name == "invoice_number":
            sets.append("invoice_number = %s, normalized_number = %s")
            parameters += [row.values["invoice_number"], normalize_number(row.values["invoice_number"])]
        else:
            sets.append(f"{name} = %s")
            parameters.append(row.values[name])
    provenance = {diff["field"]: "IMPORT" for diff in applied}
    sealed = get_cipher().encrypt(ctx, _raw_row(headers, row), str(target.id).encode())
    execute(
        f"UPDATE invoices SET {', '.join(sets)},"  # noqa: S608
        " field_provenance = field_provenance || %s::jsonb,"
        " diverges_from_source = diverges_from_source OR %s,"
        " import_batch_id = %s, source_row = %s, raw_row_ciphertext = %s, version = version + 1,"
        " updated_at = now() WHERE id = %s",
        [*parameters, json.dumps(provenance), any_kept, batch_id, row.number, sealed, target.id],
    )
    if any(diff["field"] == "gross_minor" for diff in applied):
        refresh_after_total_changed(target.id)
        publish(ctx, "InvoiceChanged", {"invoice_id": str(target.id)})
    record(
        ctx,
        "invoice.updated",
        "invoice",
        str(target.id),
        before={diff["field"]: diff["current"] for diff in applied},
        after={diff["field"]: diff["incoming"] for diff in applied},
    )


def _apply_merge(ctx: RequestContext, batch_id: UUID, row: Row) -> None:
    """Keeps the invoice and remembers the other number, so a payment quoting it can still be matched."""
    target = row.target
    if target is None:
        raise ProblemError("INTERNAL_ERROR", 500, FAILED_REASON)
    number = row.values["invoice_number"]
    execute(
        "UPDATE invoices SET payment_references = array_append(payment_references, %s),"
        " version = version + 1, updated_at = now()"
        " WHERE id = %s AND NOT (%s = ANY(payment_references))",
        [number, target.id, number],
    )
    record(
        ctx,
        "invoice.merged",
        "invoice",
        str(target.id),
        after={"merged_number": number, "batch_id": str(batch_id), "source_row": row.number},
    )


def _save_mapping(ctx: RequestContext, batch: Mapping[str, Any]) -> None:
    execute(
        "INSERT INTO import_mappings (workspace_id, kind, mapping, date_format)"
        " VALUES (%s, %s, %s::jsonb, %s)"
        " ON CONFLICT (workspace_id, kind)"
        " DO UPDATE SET mapping = EXCLUDED.mapping, date_format = EXCLUDED.date_format, updated_at = now()",
        [ctx.workspace_id, KIND, json.dumps(batch["mapping"]), batch["date_format"]],
    )


def _refuse_if_undecided(evaluation: _Evaluation, skip_invalid: bool) -> None:
    errors = list(evaluation.errors)
    reasons = blockers(evaluation.rows, skip_invalid)
    if errors or reasons:
        detail = reasons[0] if reasons and not errors else "Some of these choices cannot be applied."
        raise ProblemError(
            "IMPORT_VALIDATION_FAILED",
            422,
            detail,
            {"errors": [*_field_errors(errors), *_field_errors([("import", reason) for reason in reasons])]},
        )


def _write(ctx: RequestContext, batch_id: UUID, decisions: Mapping[str, Any]) -> dict[str, Any]:
    batch = _batch(batch_id, lock=True)
    _require_open(batch)
    if batch["mapping"] is None:
        raise ProblemError("IMPORT_VALIDATION_FAILED", 422, "Choose which column holds each field first.")
    # Two imports running together must each see what the other wrote.
    fetch_one(
        "SELECT pg_advisory_xact_lock(hashtextextended('import:' || %s, 0)) IS NULL", [str(ctx.workspace_id)]
    )
    evaluation = _evaluate(ctx, batch, decisions)
    _refuse_if_undecided(evaluation, bool(decisions.get("skip_invalid")))

    rows = evaluation.rows
    created = _create_clients(ctx, rows)
    _link_contacts_and_aliases(ctx, evaluation, created)
    created_count = _insert_invoices(ctx, batch_id, evaluation, created)
    updated = merged = 0
    for row in rows:
        if row.status == UPDATED and row.action == UPDATE:
            _apply_update(ctx, batch_id, evaluation.parsed.headers, row)
            updated += 1
        elif row.status == POSSIBLE_DUPLICATE and row.action == MERGE:
            _apply_merge(ctx, batch_id, row)
            merged += 1
    _save_mapping(ctx, batch)
    counts = {
        "total_rows": len(rows),
        "created": created_count,
        "updated": updated,
        "merged": merged,
        "unchanged": sum(1 for row in rows if row.status == DUPLICATE),
        "ignored": sum(1 for row in rows if row.action == IGNORE),
        "skipped_invalid": sum(1 for row in rows if row.status == INVALID),
    }
    execute(
        "UPDATE import_batches SET status = 'COMMITTED', counts = %s::jsonb, failure_reason = NULL,"
        " updated_at = now() WHERE id = %s",
        [json.dumps(counts), batch_id],
    )
    record(ctx, "import.committed", "import_batch", str(batch_id), after={"counts": counts})
    return _view(ctx, {**batch, "status": "COMMITTED", "counts": counts, "failure_reason": None})


def commit_import(ctx: RequestContext, batch_id: UUID, decisions: Mapping[str, Any]) -> dict[str, Any]:
    """One transaction (FR-008). Refused or failed, the ledger is exactly as it was."""
    try:
        with tenant_tx(ctx):
            return _write(ctx, batch_id, decisions)
    except DatabaseError as error:
        raise ImportCommitFailed from error


def record_failure(ctx: RequestContext, batch_id: UUID) -> None:
    with tenant_tx(ctx):
        execute(
            "UPDATE import_batches SET status = 'IMPORT_FAILED', failure_reason = %s, updated_at = now()"
            " WHERE id = %s",
            [FAILED_REASON, batch_id],
        )
        record(ctx, "import.failed", "import_batch", str(batch_id))


def discard_import(ctx: RequestContext, batch_id: UUID) -> None:
    with tenant_tx(ctx):
        batch = _batch(batch_id, lock=True)
        _require_open(batch)
        execute(
            "UPDATE import_batches SET status = 'DISCARDED', updated_at = now() WHERE id = %s", [batch_id]
        )
        execute("UPDATE stored_files SET deleted_at = now() WHERE id = %s", [batch["file_id"]])
        record(ctx, "import.discarded", "import_batch", str(batch_id))
    get_storage().delete(ctx, batch["storage_key"])


def _spreadsheet_safe(text: Any) -> str:
    """A cell that a spreadsheet would run as a formula is written as text."""
    cell = "" if text is None else str(text)
    return f"'{cell}" if cell.startswith(_FORMULA_START) else cell


def error_report(ctx: RequestContext, batch_id: UUID) -> str:
    with tenant_tx(ctx):
        batch = _batch(batch_id)
        if batch["status"] == "DISCARDED":
            raise ProblemError("STATE_TRANSITION_INVALID", 409, "This import was discarded.")
        rows = _evaluate(ctx, batch, {}).rows if batch["mapping"] is not None else []
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["row", "invoice_number", "field", "problem"])
    for row in rows:
        number = row.values.get("invoice_number")
        for error in row.errors:
            writer.writerow([row.number, *map(_spreadsheet_safe, (number, error.field, error.message))])
        if row.status == CONFLICT:
            writer.writerow(
                [row.number, _spreadsheet_safe(number), "total", "The total is not the subtotal plus tax."]
            )
    return out.getvalue()
