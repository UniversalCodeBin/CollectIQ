"""One row at a time: what it says, what is wrong with it, and whether its figures disagree."""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from collectiq.platform.money import ISO_4217_CODES, currency_exponent

from .csv_parse import parse_amount, parse_date

REQUIRED_FIELDS = ("invoice_number", "client_name", "due_date", "currency", "total")
OPTIONAL_FIELDS = (
    "issue_date",
    "subtotal",
    "tax",
    "payment_terms",
    "payment_reference",
    "client_email",
    "po_number",
    "project_ref",
    "description",
    "external_id",
)
_LIMITS = {
    "invoice_number": 128,
    "client_name": 200,
    "payment_terms": 200,
    "payment_reference": 128,
    "po_number": 128,
    "project_ref": 128,
    "description": 2000,
    "external_id": 128,
}
_LABELS = {
    "invoice_number": "invoice number",
    "client_name": "client name",
    "due_date": "due date",
    "currency": "currency",
    "total": "total",
    "external_id": "source ID",
}
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_SUGGESTIONS = {
    "invoice_number": (
        "invoiceno",
        "invoicenumber",
        "invoice",
        "invno",
        "invoicenum",
        "billno",
        "billnumber",
    ),
    "client_name": ("client", "clientname", "customer", "customername", "company", "companyname", "billto"),
    "due_date": ("due", "duedate", "dueon", "paymentdue", "payby"),
    "currency": ("currency", "cur", "ccy", "currencycode"),
    "total": ("total", "grandtotal", "invoicetotal", "totalamount", "amount", "gross"),
    "issue_date": ("issued", "issuedate", "invoicedate", "billdate", "date"),
    "subtotal": ("subtotal", "net", "netamount", "taxableamount", "taxablevalue"),
    "tax": ("tax", "gst", "vat", "taxamount"),
    "payment_terms": ("terms", "paymentterms"),
    "payment_reference": ("paymentreference", "paymentref", "reference", "ref"),
    "client_email": ("email", "clientemail", "customeremail", "billingemail", "emailaddress"),
    "po_number": ("po", "pono", "ponumber", "purchaseorder"),
    "project_ref": ("project", "projectref", "projectreference", "projectcode"),
    "description": ("description", "notes", "memo", "details"),
    "external_id": ("externalid", "sourceid", "invoiceid"),
}
_LEGAL_SUFFIXES = frozenset(
    "pvt private ltd limited llp llc inc incorporated corp corporation co company plc gmbh".split()
)


@dataclass(frozen=True, slots=True)
class RowError:
    field: str
    message: str


@dataclass(slots=True)
class RowResult:
    values: dict[str, Any] = field(default_factory=dict)
    errors: list[RowError] = field(default_factory=list)
    conflict: bool = False


class RowMapping:
    """Which cell of a row holds which field. Built only from a mapping that passed `mapping_errors`."""

    def __init__(self, mapping: Mapping[str, str], headers: Sequence[str]) -> None:
        self.columns = len(headers)
        self._index = {target: headers.index(header) for target, header in mapping.items()}

    def cell(self, row: Sequence[str], target: str) -> str:
        index = self._index.get(target)
        return " ".join(row[index].split()) if index is not None else ""


def mapping_errors(mapping: Mapping[str, Any], headers: Sequence[str]) -> list[tuple[str, str]]:
    errors = [
        (f"mapping.{target}", "Choose the column that holds this field.")
        for target in REQUIRED_FIELDS
        if target not in mapping
    ]
    known = {*REQUIRED_FIELDS, *OPTIONAL_FIELDS}
    used: set[str] = set()
    for target, header in mapping.items():
        if target not in known:
            errors.append((f"mapping.{target}", "This is not a field that can be imported."))
        elif not isinstance(header, str) or header not in headers:
            errors.append((f"mapping.{target}", "This column is not in the file."))
        elif header in used:
            errors.append((f"mapping.{target}", "This column is already used for another field."))
        else:
            used.add(header)
    return errors


def _header_key(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.casefold())


def suggest_mapping(headers: Sequence[str]) -> dict[str, str]:
    by_key = {_header_key(header): header for header in headers}
    suggested: dict[str, str] = {}
    used: set[str] = set()
    for target, synonyms in _SUGGESTIONS.items():
        for synonym in synonyms:
            header = by_key.get(synonym)
            if header is not None and header not in used:
                suggested[target] = header
                used.add(header)
                break
    return suggested


def collapse(text: str) -> str:
    return " ".join(text.split())


def normalize_name(name: str) -> str:
    """The form client names are compared in (FR-009)."""
    return collapse(name).casefold()


def normalize_number(number: str) -> str:
    """So that `INV-001` and `inv 001` are recognised as one invoice number."""
    folded = unicodedata.normalize("NFKC", number).casefold().strip()
    return "".join(character for character in folded if character.isalnum()) or folded


def similarity_key(name: str) -> str:
    """Names that may be one business. Only ever a question for a person, never a merge."""
    words = re.sub(r"[^\w\s]", "", unicodedata.normalize("NFKC", name).casefold()).split()
    while len(words) > 1 and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


def _amount(result: RowResult, text: str, currency: str, target: str, name: str) -> int | None:
    try:
        return parse_amount(text, currency)
    except ValueError as exc:
        result.errors.append(RowError(target, str(exc)))
        result.values[name] = None
        return None


def _date(result: RowResult, text: str, date_format: str, target: str) -> None:
    try:
        result.values[target] = parse_date(text, date_format)
    except ValueError as exc:
        result.errors.append(RowError(target, str(exc)))


def _dates(result: RowResult, row: Sequence[str], mapping: RowMapping, date_format: str | None) -> None:
    due, issue = mapping.cell(row, "due_date"), mapping.cell(row, "issue_date")
    if date_format is None:
        result.errors.append(RowError("date_format", "Choose a date format to read the dates in this file."))
        return
    if due:
        _date(result, due, date_format, "due_date")
    if issue:
        _date(result, issue, date_format, "issue_date")
    due_date, issue_date = result.values.get("due_date"), result.values.get("issue_date")
    if due_date and issue_date and due_date < issue_date:
        result.errors.append(RowError("issue_date", "The due date is before the issue date."))


def _amounts(result: RowResult, row: Sequence[str], mapping: RowMapping) -> None:
    currency = mapping.cell(row, "currency").upper()
    if currency not in ISO_4217_CODES:
        if currency:
            result.errors.append(RowError("currency", "This is not a known currency code."))
        return
    result.values["currency"] = currency
    gross = None
    if mapping.cell(row, "total"):
        gross = _amount(result, mapping.cell(row, "total"), currency, "total", "gross_minor")
    subtotal = tax = None
    if mapping.cell(row, "subtotal"):
        subtotal = _amount(result, mapping.cell(row, "subtotal"), currency, "subtotal", "subtotal_minor")
    if mapping.cell(row, "tax"):
        tax = _amount(result, mapping.cell(row, "tax"), currency, "tax", "tax_minor")
    result.values.update(gross_minor=gross, subtotal_minor=subtotal, tax_minor=tax)
    if gross is not None and subtotal is not None and tax is not None:
        result.values["computed_minor"] = subtotal + tax
        result.conflict = abs(gross - (subtotal + tax)) > 10 ** currency_exponent(currency) // 100


def validate_row(row: Sequence[str], mapping: RowMapping, date_format: str | None) -> RowResult:
    result = RowResult()
    if len(row) != mapping.columns:
        result.errors.append(
            RowError("row", f"This row has {len(row)} cells; the file has {mapping.columns} columns.")
        )
        return result
    for target in REQUIRED_FIELDS:
        if not mapping.cell(row, target):
            result.errors.append(RowError(target, f"The {_LABELS[target]} is blank."))
    for target, limit in _LIMITS.items():
        text = mapping.cell(row, target)
        if len(text) > limit:
            result.errors.append(RowError(target, f"This is longer than {limit} characters."))
        result.values[target] = text or None
    _dates(result, row, mapping, date_format)
    _amounts(result, row, mapping)
    email = mapping.cell(row, "client_email").casefold()
    if email and (len(email) > 254 or _EMAIL.fullmatch(email) is None):
        result.errors.append(RowError("client_email", "This is not a valid email address."))
    result.values["client_email"] = email or None
    return result
