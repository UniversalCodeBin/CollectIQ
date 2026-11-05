"""Generic bank-statement CSV. Credit versus debit comes from the sign or the column, never from guessing."""

import hashlib
import re
from collections.abc import Iterator
from datetime import date

from collectiq.evidence.parsers.base import Direction, MappingError, RawRow, StatementMapping
from collectiq.invoices.domain.csv_parse import CsvRejected, parse_amount, parse_csv, parse_date, sniff_upload
from collectiq.platform.money import currency_exponent

_REFERENCE = re.compile(r"\binv(?:oice)?[\s\-/_#:.]*0*([0-9]{1,12})\b", re.IGNORECASE)


def reference_candidates(text: str) -> list[str]:
    """Deterministic (FR-040): INV-2041, inv 2041 and INV/2041 all become INV-2041, in order, once each."""
    found: list[str] = []
    for match in _REFERENCE.finditer(text):
        candidate = f"INV-{match.group(1)}"
        if candidate not in found:
            found.append(candidate)
    return found


def fingerprint(
    account: str,
    value_date: date,
    amount_minor: int,
    currency: str,
    description: str,
    balance_minor: int | None,
) -> str:
    normalized = " ".join(description.casefold().split())
    parts = [
        account,
        value_date.isoformat(),
        str(amount_minor),
        currency,
        normalized,
        "" if balance_minor is None else str(balance_minor),
    ]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _signed(text: str, currency: str) -> tuple[Direction, int]:
    stripped = text.strip()
    negative = stripped.startswith("-") or (stripped.startswith("(") and stripped.endswith(")"))
    if stripped.startswith("(") and stripped.endswith(")"):
        stripped = stripped[1:-1]
    elif stripped.startswith("-"):
        stripped = stripped[1:]
    elif stripped.startswith("+"):
        stripped = stripped[1:]
    return ("DEBIT" if negative else "CREDIT"), parse_amount(stripped, currency)


class _Fail(Exception):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def _amount(cells: dict[str, str], mapping: StatementMapping, currency: str) -> tuple[Direction, int]:
    try:
        if mapping.amount:
            direction, amount = _signed(cells[mapping.amount], currency)
        else:
            credit = cells.get(mapping.credit or "", "").strip()
            debit = cells.get(mapping.debit or "", "").strip()
            if credit and debit:
                raise _Fail("amount", "Both the credit and the debit column have a value.")
            if credit:
                direction, amount = _signed(credit, currency)
                if direction == "DEBIT":
                    raise _Fail("credit", "A credit cannot be negative.")
            elif debit:
                _, amount = _signed(debit, currency)
                direction = "DEBIT"
            else:
                raise _Fail("amount", "The amount is blank.")
    except ValueError as error:
        raise _Fail("amount", str(error)) from None
    if amount == 0:
        raise _Fail("amount", "An amount of zero is not a transaction.")
    return direction, amount


def _balance(cells: dict[str, str], mapping: StatementMapping, currency: str) -> int | None:
    text = cells.get(mapping.balance or "", "").strip()
    if not text:
        return None
    try:
        direction, amount = _signed(text, currency)
    except ValueError as error:
        raise _Fail("balance", str(error)) from None
    return -amount if direction == "DEBIT" else amount


class GenericCsvParser:
    def sniff(self, data: bytes) -> bool:
        try:
            sniff_upload("statement.csv", data, max_bytes=len(data) + 1)
        except CsvRejected:
            return False
        return True

    def parse(
        self, data: bytes, mapping: StatementMapping, date_format: str | None, currency: str
    ) -> Iterator[RawRow]:
        parsed = parse_csv(data)
        missing = [c for c in mapping.columns() if c not in parsed.headers]
        if missing:
            raise MappingError(f"The file has no column named {', '.join(repr(c) for c in missing)}.")
        for row in parsed.rows:
            cells = dict(zip(parsed.headers, row.values, strict=False))
            yield self._row(row.number, cells, mapping, date_format, currency)

    def _row(
        self,
        number: int,
        cells: dict[str, str],
        mapping: StatementMapping,
        date_format: str | None,
        currency: str,
    ) -> RawRow:
        description = cells.get(mapping.description, "").strip()
        reference = cells.get(mapping.reference or "", "").strip() or None
        row_currency = cells.get(mapping.currency or "", "").strip().upper() or None
        try:
            used = row_currency or currency
            try:
                value_date = parse_date(cells[mapping.date], date_format)
            except ValueError as error:
                raise _Fail("date", str(error)) from None
            try:
                currency_exponent(used)
            except Exception:
                raise _Fail("currency", f"{used} is not a known currency code.") from None
            direction, amount = _amount(cells, mapping, used)
            balance = _balance(cells, mapping, used)
        except _Fail as fail:
            return RawRow(number, description, reference, error=fail.message, error_field=fail.field)
        return RawRow(number, description, reference, direction, amount, value_date, used, balance)
