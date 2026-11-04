"""What each row of a file means for the ledger. Facts go in, statuses come out, and nothing here writes.

Nothing merges by itself: anything that might be the same client or the same invoice becomes a question.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from .csv_parse import CsvRow
from .validate import RowError, RowMapping, normalize_name, normalize_number, similarity_key, validate_row

NEW = "NEW"
UPDATED = "UPDATED"
DUPLICATE = "DUPLICATE"
POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
INVALID = "INVALID"
CONFLICT = "CONFLICT"
AWAITING_CLIENT = "AWAITING_CLIENT"

UPDATE = "UPDATE"
IGNORE = "IGNORE"
KEEP_BOTH = "KEEP_BOTH"
MERGE = "MERGE"

ATTENTION = frozenset({UPDATED, POSSIBLE_DUPLICATE, INVALID, CONFLICT})

COMPARED = (
    "due_date",
    "issue_date",
    "currency",
    "gross_minor",
    "subtotal_minor",
    "tax_minor",
    "payment_terms",
    "po_number",
    "project_ref",
    "description",
)


@dataclass(frozen=True, slots=True)
class NewClient:
    """A client this import would create. `name` is the normalized name that asks for it."""

    name: str


ClientRef = UUID | NewClient


@dataclass(frozen=True, slots=True)
class KnownClient:
    id: UUID
    display_name: str
    names: frozenset[str]
    emails: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class Existing:
    id: UUID
    client_id: UUID
    invoice_number: str
    normalized_number: str
    external_id: str | None
    payment_references: list[str]
    provenance: dict[str, str]
    values: dict[str, Any]


@dataclass(slots=True)
class Row:
    number: int
    cells: list[str]
    values: dict[str, Any]
    errors: list[RowError]
    name: str = ""
    status: str = NEW
    client: ClientRef | None = None
    conflict: dict[str, int] | None = None
    diffs: list[dict[str, Any]] = field(default_factory=list)
    matches: list[dict[str, Any]] = field(default_factory=list)
    allowed: tuple[str, ...] = ()
    target: Existing | None = None
    action: str | None = None


@dataclass(slots=True)
class ClientPlan:
    resolved: dict[str, ClientRef] = field(default_factory=dict)
    questions: list[dict[str, Any]] = field(default_factory=list)
    aliases: list[tuple[ClientRef, str]] = field(default_factory=list)
    unresolved: set[str] = field(default_factory=set)
    errors: list[tuple[str, str]] = field(default_factory=list)


def read_rows(csv_rows: Iterable[CsvRow], mapping: RowMapping, date_format: str | None) -> list[Row]:
    rows = []
    for csv_row in csv_rows:
        result = validate_row(csv_row.values, mapping, date_format)
        row = Row(csv_row.number, csv_row.values, result.values, list(result.errors))
        if row.errors:
            row.status = INVALID
        else:
            row.name = normalize_name(row.values["client_name"])
            if result.conflict:
                row.conflict = {
                    "total_minor": row.values["gross_minor"],
                    "sum_minor": row.values["computed_minor"],
                }
        rows.append(row)
    return rows


@dataclass(slots=True)
class _Name:
    display_name: str
    rows: int = 0
    emails: set[str] = field(default_factory=set)


def _names_in_file(rows: Iterable[Row]) -> dict[str, _Name]:
    names: dict[str, _Name] = {}
    for row in rows:
        if row.errors:
            continue
        seen = names.setdefault(row.name, _Name(row.values["client_name"]))
        seen.rows += 1
        if row.values.get("client_email"):
            seen.emails.add(row.values["client_email"])
    return names


def _candidate(client: KnownClient, reason: str) -> dict[str, str]:
    return {"client_id": str(client.id), "display_name": client.display_name, "reason": reason}


def _question(
    name: str,
    seen: _Name,
    exact: Sequence[KnownClient],
    similar: Sequence[KnownClient],
    known: Sequence[KnownClient],
    in_file: list[str],
) -> dict[str, Any] | None:
    if exact:
        candidates = [_candidate(client, "SAME_NAME") for client in exact]
    else:
        candidates = [_candidate(client, "SIMILAR_NAME") for client in similar]
        already = {client.id for client in similar}
        candidates += [
            _candidate(client, "SAME_EMAIL")
            for client in known
            if client.id not in already and client.emails & seen.emails
        ]
    if not candidates and not in_file:
        return None
    return {
        "name": name,
        "display_name": seen.display_name,
        "rows": seen.rows,
        "candidates": candidates,
        "in_file": in_file,
        "decision_required": True,
    }


def _same_as_target(name: str, same_as: Mapping[str, str]) -> str | None:
    """Follows a chain of "same as" decisions. `None` when they go round in a circle."""
    visited = {name}
    current = same_as[name]
    while current in same_as:
        if current in visited:
            return None
        visited.add(current)
        current = same_as[current]
    return current


def match_clients(
    rows: Sequence[Row], known: Sequence[KnownClient], decisions: Mapping[str, Any]
) -> ClientPlan:
    """FR-009. A name that is exactly one client's is that client; a resemblance is only ever a question."""
    plan = ClientPlan()
    names = _names_in_file(rows)
    by_name: dict[str, list[KnownClient]] = defaultdict(list)
    by_key: dict[str, list[KnownClient]] = defaultdict(list)
    for client in known:
        for name in client.names:
            by_name[name].append(client)
        for key in {similarity_key(name) for name in client.names}:
            by_key[key].append(client)

    keys_seen: dict[str, list[str]] = defaultdict(list)
    asked: dict[str, dict[str, Any]] = {}
    for name, seen in names.items():
        exact = by_name.get(name, [])
        if len(exact) == 1:
            plan.resolved[name] = exact[0].id
            continue
        key = similarity_key(name)
        question = _question(name, seen, exact, by_key.get(key, []), known, list(keys_seen[key]))
        keys_seen[key].append(name)
        if question is None:
            plan.resolved[name] = NewClient(name)
        else:
            asked[name] = question
            plan.questions.append(question)
            plan.unresolved.add(name)

    _apply_client_decisions(plan, names, asked, {client.id: client for client in known}, decisions)
    for row in rows:
        row.client = plan.resolved.get(row.name) if not row.errors else None
    return plan


def _apply_client_decisions(
    plan: ClientPlan,
    names: Mapping[str, _Name],
    asked: Mapping[str, dict[str, Any]],
    known: Mapping[UUID, KnownClient],
    decisions: Mapping[str, Any],
) -> None:
    same_as: dict[str, str] = {}
    for raw_key, decision in decisions.items():
        name = normalize_name(raw_key)
        field_name = f"clients.{raw_key}"
        if name not in asked:
            plan.errors.append((field_name, "This name is not waiting for a decision."))
        elif decision["action"] == "NEW":
            plan.resolved[name] = NewClient(name)
            plan.unresolved.discard(name)
        elif decision["action"] == "LINK":
            if decision["client_id"] not in known:
                plan.errors.append((field_name, "This client does not exist."))
                continue
            plan.resolved[name] = decision["client_id"]
            plan.unresolved.discard(name)
            plan.aliases.append((decision["client_id"], names[name].display_name))
        else:
            target = normalize_name(decision["name"])
            if target == name or target not in names:
                plan.errors.append((field_name, "Choose another name from this file."))
                continue
            same_as[name] = target
    for name in same_as:
        settled = _same_as_target(name, same_as)
        if settled is None:
            plan.errors.append((f"clients.{name}", "These names point at each other. Choose one to keep."))
        elif settled in plan.resolved:
            plan.resolved[name] = plan.resolved[settled]
            plan.unresolved.discard(name)
            plan.aliases.append((plan.resolved[target], names[name].display_name))


def _json_safe(value: Any) -> Any:
    return value.isoformat() if isinstance(value, date) else value


def _diff(existing: Existing, name: str, current: Any, incoming: Any) -> dict[str, Any]:
    return {
        "field": name,
        "current": _json_safe(current),
        "incoming": _json_safe(incoming),
        "kept": existing.provenance.get(name) == "USER",
    }


def _diffs(row: Row, existing: Existing, *, by_source_id: bool = False) -> list[dict[str, Any]]:
    """A blank cell says nothing about a field, so it never erases one."""
    diffs = []
    for name in COMPARED:
        incoming = row.values.get(name)
        if incoming is not None and incoming != existing.values.get(name):
            diffs.append(_diff(existing, name, existing.values.get(name), incoming))
    reference = row.values.get("payment_reference")
    if reference and normalize_number(reference) not in {
        normalize_number(known) for known in existing.payment_references
    }:
        references = existing.payment_references
        diffs.append(_diff(existing, "payment_references", references, [*references, reference]))
    if by_source_id and normalize_number(row.values["invoice_number"]) != existing.normalized_number:
        diffs.append(_diff(existing, "invoice_number", existing.invoice_number, row.values["invoice_number"]))
    return diffs


def _unchanged(row: Row, existing: Existing) -> bool:
    return all(diff["kept"] for diff in _diffs(row, existing))


def _same_invoice(row: Row, existing: Existing, *, by_source_id: bool = False) -> None:
    diffs = _diffs(row, existing, by_source_id=by_source_id)
    if all(diff["kept"] for diff in diffs):
        row.status = DUPLICATE
        return
    row.status = UPDATED
    row.diffs = diffs
    row.target = existing
    row.allowed = (UPDATE, IGNORE)


def _ledger_match(existing: Existing) -> dict[str, Any]:
    return {
        "invoice_id": str(existing.id),
        "invoice_number": existing.invoice_number,
        "issue_date": _json_safe(existing.values.get("issue_date")),
        "gross_minor": existing.values.get("gross_minor"),
        "currency": existing.values.get("currency"),
    }


def _possible_duplicate_of_ledger(row: Row, hits: Sequence[Existing]) -> None:
    row.status = POSSIBLE_DUPLICATE
    row.matches = [_ledger_match(existing) for existing in hits]
    row.target = hits[0]
    row.allowed = (KEEP_BOTH, MERGE, IGNORE)


class _Ledger:
    def __init__(self, existing: Iterable[Existing]) -> None:
        self.by_external: dict[str, Existing] = {}
        self.by_number: dict[tuple[UUID, str], list[Existing]] = defaultdict(list)
        self.by_reference: dict[tuple[UUID, str], list[Existing]] = defaultdict(list)
        self.by_amount: dict[tuple[Any, ...], list[Existing]] = defaultdict(list)
        for invoice in existing:
            if invoice.external_id:
                self.by_external[invoice.external_id] = invoice
            self.by_number[(invoice.client_id, invoice.normalized_number)].append(invoice)
            for reference in invoice.payment_references:
                self.by_reference[(invoice.client_id, normalize_number(reference))].append(invoice)
            values = invoice.values
            if values.get("issue_date"):
                key = (invoice.client_id, values["gross_minor"], values["currency"], values["issue_date"])
                self.by_amount[key].append(invoice)

    def place(self, row: Row) -> None:
        number = normalize_number(row.values["invoice_number"])
        external_id = row.values.get("external_id")
        hit = self.by_external.get(external_id) if external_id else None
        if hit is not None:
            if hit.client_id != row.client:
                row.status = INVALID
                row.errors.append(
                    RowError(
                        "external_id", "This source ID already belongs to an invoice for another client."
                    )
                )
            else:
                _same_invoice(row, hit, by_source_id=True)
            return
        client = row.client
        if not isinstance(client, UUID):
            return
        self._place_for_client(row, client, number, has_external_id=bool(external_id))

    def _place_for_client(self, row: Row, client: UUID, number: str, *, has_external_id: bool) -> None:
        hits = self.by_number.get((client, number), [])
        if hits:
            if has_external_id:
                _possible_duplicate_of_ledger(row, hits)
            elif any(_unchanged(row, existing) for existing in hits):
                row.status = DUPLICATE
            elif len(hits) == 1:
                _same_invoice(row, hits[0])
            else:
                _possible_duplicate_of_ledger(row, hits)
            return
        amount = (row.values["gross_minor"], row.values["currency"], row.values.get("issue_date"))
        referenced = self.by_reference.get((client, number), [])
        if referenced:
            # A number an earlier merge folded into that invoice: the same file again adds nothing.
            same = any(
                (ref.values.get("gross_minor"), ref.values.get("currency"), ref.values.get("issue_date"))
                == amount
                for ref in referenced
            )
            if same:
                row.status = DUPLICATE
            else:
                _possible_duplicate_of_ledger(row, referenced)
            return
        if amount[2] is not None:
            twins = self.by_amount.get((client, *amount), [])
            if twins:
                _possible_duplicate_of_ledger(row, twins)


def _fingerprint(row: Row) -> tuple[Any, ...]:
    return (
        row.client,
        normalize_number(row.values["invoice_number"]),
        row.values.get("external_id"),
        row.values.get("payment_reference"),
        *(row.values.get(name) for name in COMPARED),
    )


def _file_match(row: Row) -> dict[str, Any]:
    return {
        "row": row.number,
        "invoice_number": row.values["invoice_number"],
        "issue_date": _json_safe(row.values.get("issue_date")),
        "gross_minor": row.values["gross_minor"],
        "currency": row.values["currency"],
    }


def _flag_twins(group: Sequence[Row]) -> None:
    for row in group:
        row.status = POSSIBLE_DUPLICATE
        row.allowed = (KEEP_BOTH, IGNORE)
        row.matches = [_file_match(other) for other in group if other is not row]


def _drop_repeats(group: Sequence[Row]) -> list[Row]:
    """An exact repeat of a row earlier in the file is the same invoice said twice."""
    kept: list[Row] = []
    seen: set[tuple[Any, ...]] = set()
    for row in group:
        fingerprint = _fingerprint(row)
        if fingerprint in seen:
            row.status = DUPLICATE
        else:
            seen.add(fingerprint)
            kept.append(row)
    return kept


def _drop_repeats_of_one_question(rows: Sequence[Row]) -> None:
    """The same row twice, resembling an invoice already held, is one decision for a person, not two."""
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        if row.status != POSSIBLE_DUPLICATE or row.errors:
            continue
        fingerprint = _fingerprint(row)
        if fingerprint in seen:
            row.status, row.matches, row.allowed, row.target = DUPLICATE, [], (), None
        else:
            seen.add(fingerprint)


def _within_file(rows: Sequence[Row]) -> None:
    _settle_updates(rows)
    _settle_source_ids(rows)
    _drop_repeats_of_one_question(rows)
    by_number: dict[tuple[Any, str], list[Row]] = defaultdict(list)
    for row in rows:
        if row.status == NEW and not row.errors:
            by_number[(row.client, normalize_number(row.values["invoice_number"]))].append(row)
    for group in by_number.values():
        kept = _drop_repeats(group)
        if len(kept) > 1:
            _flag_twins(kept)
    by_amount: dict[tuple[Any, ...], list[Row]] = defaultdict(list)
    for row in rows:
        if row.status == NEW and not row.errors and row.values.get("issue_date"):
            values = row.values
            by_amount[(row.client, values["gross_minor"], values["currency"], values["issue_date"])].append(
                row
            )
    for group in by_amount.values():
        if len(group) > 1:
            _flag_twins(group)


def _settle_updates(rows: Sequence[Row]) -> None:
    first: dict[UUID, Row] = {}
    for row in rows:
        if row.status != UPDATED or row.target is None:
            continue
        earlier = first.setdefault(row.target.id, row)
        if earlier is row:
            continue
        row.diffs, row.allowed, row.target = [], (), None
        if _fingerprint(row)[2:] == _fingerprint(earlier)[2:]:
            row.status = DUPLICATE
        else:
            row.status = INVALID
            row.errors.append(
                RowError(
                    "invoice_number", f"Row {earlier.number} changes this invoice differently. Keep one row."
                )
            )


def _settle_source_ids(rows: Sequence[Row]) -> None:
    first: dict[str, Row] = {}
    for row in rows:
        external_id = row.values.get("external_id")
        if row.status != NEW or row.errors or not external_id:
            continue
        earlier = first.setdefault(external_id, row)
        if earlier is row:
            continue
        if _fingerprint(row) == _fingerprint(earlier):
            row.status = DUPLICATE
        else:
            row.status = INVALID
            row.errors.append(
                RowError("external_id", f"Row {earlier.number} has this source ID with different details.")
            )


def _row_decisions(
    rows: Sequence[Row], decisions: Mapping[str, Any]
) -> tuple[dict[int, Any], list[tuple[str, str]]]:
    numbers = {row.number for row in rows}
    wanted: dict[int, Any] = {}
    errors = []
    for key, decision in decisions.items():
        number = int(key) if key.isdigit() else None
        if number is None or number not in numbers:
            errors.append((f"rows.{key}", "This row is not in the file."))
        else:
            wanted[number] = decision
    return wanted, errors


def classify(
    rows: Sequence[Row], existing: Iterable[Existing], decisions: Mapping[str, Any]
) -> list[tuple[str, str]]:
    """Gives every row its status, then applies what a person decided. Returns decisions that are wrong."""
    wanted, errors = _row_decisions(rows, decisions)
    ledger = _Ledger(existing)
    for row in rows:
        decision = wanted.get(row.number, {})
        source = decision.get("total_source")
        if source is not None and row.conflict is None:
            errors.append((f"rows.{row.number}", "This row has no disagreement about its total."))
        if row.errors:
            row.status = INVALID
            continue
        if row.conflict is not None and source is None:
            row.status = CONFLICT
            row.allowed = (IGNORE,)
            continue
        if source == "SUM":
            row.values["gross_minor"] = row.values["computed_minor"]
        if row.client is None:
            row.status = AWAITING_CLIENT
            row.allowed = (IGNORE,)
            continue
        ledger.place(row)
    _within_file(rows)
    for row in rows:
        action = wanted.get(row.number, {}).get("action")
        if action is None:
            continue
        if action not in row.allowed:
            errors.append((f"rows.{row.number}", "This choice is not available for this row."))
        else:
            row.action = action
    return errors


def preview_counts(rows: Sequence[Row], plan: ClientPlan) -> dict[str, int]:
    tally = {
        status: 0
        for status in (NEW, UPDATED, DUPLICATE, POSSIBLE_DUPLICATE, INVALID, CONFLICT, AWAITING_CLIENT)
    }
    for row in rows:
        tally[row.status] += 1
    return {
        "total_rows": len(rows),
        "new": tally[NEW],
        "updated": tally[UPDATED],
        "duplicate": tally[DUPLICATE],
        "possible_duplicate": tally[POSSIBLE_DUPLICATE],
        "invalid": tally[INVALID],
        "conflict": tally[CONFLICT],
        "awaiting_client": tally[AWAITING_CLIENT],
        "client_decisions": len(plan.unresolved),
    }


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def blockers(rows: Sequence[Row], skip_invalid: bool) -> list[str]:
    """Why this file cannot be committed yet, in the order a person would deal with it."""
    undecided = [row for row in rows if row.action is None]
    waiting = sum(1 for row in undecided if row.status == AWAITING_CLIENT)
    conflicts = sum(1 for row in undecided if row.status == CONFLICT)
    matches = sum(1 for row in undecided if row.status in (UPDATED, POSSIBLE_DUPLICATE))
    invalid = sum(1 for row in rows if row.status == INVALID)
    reasons = []
    if invalid == len(rows):
        reasons.append("No row in this file can be imported yet. Check the problems listed for each row.")
    if waiting:
        reasons.append(f"Choose which client {_plural(waiting, 'row belongs', 'rows belong')} to.")
    if conflicts:
        reasons.append(f"Choose the total to keep for {_plural(conflicts, 'row', 'rows')}.")
    if matches:
        reasons.append(
            f"Decide what to do with {_plural(matches, 'row that matches', 'rows that match')} an invoice."
        )
    if invalid and not skip_invalid and invalid != len(rows):
        reasons.append(f"Fix {_plural(invalid, 'invalid row', 'invalid rows')} or choose to skip them.")
    return reasons
