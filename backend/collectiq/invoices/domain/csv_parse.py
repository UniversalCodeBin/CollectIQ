"""Turning an uploaded file into rows. Money is never rounded and a date format is never guessed."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from collectiq.platform.money import ISO_4217_CODES, Money

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10_000

_REJECTED_MAGIC = (
    (b"PK\x03\x04", "This looks like an Excel or zip file, not a CSV. Save it as CSV and upload it again."),
    (
        b"\xd0\xcf\x11\xe0",
        "This looks like an old Excel file, not a CSV. Save it as CSV and upload it again.",
    ),
    (b"%PDF", "This looks like a PDF, not a CSV."),
    (b"\xff\xfe", "This file is UTF-16. Save it as UTF-8 CSV and upload it again."),
    (b"\xfe\xff", "This file is UTF-16. Save it as UTF-8 CSV and upload it again."),
)
_NOT_UTF8 = "This file is not UTF-8 text. Save it as UTF-8 CSV and upload it again."
_DELIMITERS = (",", ";", "\t")

_SYMBOLS: dict[str, frozenset[str]] = {
    "₹": frozenset({"INR"}),
    "€": frozenset({"EUR"}),
    "£": frozenset({"GBP"}),
    "¥": frozenset({"JPY", "CNY"}),
    "$": frozenset({"USD", "AUD", "CAD", "NZD", "SGD", "HKD", "MXN"}),
}
_MARK = r"[A-Za-z]{3}|[Rr][Ss]\.?|[₹€£¥$]"
_AMOUNT_SHAPE = re.compile(rf"(?P<prefix>{_MARK})?\s*(?P<number>[^\sA-Za-z₹€£¥$]*)\s*(?P<suffix>{_MARK})?")
_PLAIN = re.compile(r"[0-9]+(\.[0-9]+)?")
_WESTERN = re.compile(r"[0-9]{1,3}(,[0-9]{3})+(\.[0-9]+)?")
_INDIAN = re.compile(r"[0-9]{1,2}(,[0-9]{2})*,[0-9]{3}(\.[0-9]+)?")

_DAY = r"(?P<d>[0-9]{1,2})"
_MONTH = r"(?P<m>[0-9]{1,2})"
_YEAR = r"(?P<y>[0-9]{4})"
DATE_FORMATS: dict[str, re.Pattern[str]] = {
    "DD/MM/YYYY": re.compile(rf"{_DAY}/{_MONTH}/{_YEAR}"),
    "MM/DD/YYYY": re.compile(rf"{_MONTH}/{_DAY}/{_YEAR}"),
    "YYYY-MM-DD": re.compile(rf"{_YEAR}-{_MONTH}-{_DAY}"),
    "DD-MM-YYYY": re.compile(rf"{_DAY}-{_MONTH}-{_YEAR}"),
    "MM-DD-YYYY": re.compile(rf"{_MONTH}-{_DAY}-{_YEAR}"),
    "DD.MM.YYYY": re.compile(rf"{_DAY}\.{_MONTH}\.{_YEAR}"),
    "YYYY/MM/DD": re.compile(rf"{_YEAR}/{_MONTH}/{_DAY}"),
}


class CsvRejected(Exception):
    """The file itself cannot be used. `kind` picks the response: type 415, size 413, content 422."""

    def __init__(self, kind: Literal["type", "size", "content"], reason: str) -> None:
        super().__init__(reason)
        self.kind = kind
        self.reason = reason


@dataclass(frozen=True, slots=True)
class CsvRow:
    number: int
    values: list[str]


@dataclass(frozen=True, slots=True)
class ParsedCsv:
    headers: list[str]
    rows: list[CsvRow]


def _check_mark(mark: str | None, currency: str) -> None:
    if mark is None:
        return
    if mark[0] in _SYMBOLS:
        matches = currency in _SYMBOLS[mark[0]]
    elif mark.casefold().startswith("rs"):
        matches = currency == "INR"
    else:
        matches = mark.upper() == currency
    if not matches:
        raise ValueError(f"This amount is marked {mark}, but the currency of the row is {currency}.")


def parse_amount(text: str, currency: str) -> int:
    """Minor units of a non-negative amount. Indian and Western digit grouping are both understood."""
    if currency not in ISO_4217_CODES:
        raise ValueError("This is not a known currency code.")
    stripped = text.strip()
    if not stripped:
        raise ValueError("The amount is blank.")
    shape = _AMOUNT_SHAPE.fullmatch(stripped)
    if shape is None:
        raise ValueError("This is not a plain amount.")
    _check_mark(shape["prefix"], currency)
    _check_mark(shape["suffix"], currency)
    number = shape["number"]
    if _PLAIN.fullmatch(number) is None and not _WESTERN.fullmatch(number) and not _INDIAN.fullmatch(number):
        if number.startswith("-") or number.startswith("("):
            raise ValueError("Amounts cannot be negative.")
        if "," in number:
            raise ValueError("A comma may only separate thousands. Use a point for decimals.")
        raise ValueError("This is not a plain amount.")
    return Money.from_decimal_text(number.replace(",", ""), currency).amount_minor


def parse_date(text: str, fmt: str | None) -> date:
    if fmt is None:
        raise ValueError("Choose a date format first; dates are never guessed.")
    pattern = DATE_FORMATS.get(fmt)
    if pattern is None:
        raise ValueError("This date format is not supported.")
    found = pattern.fullmatch(text.strip())
    if found is None:
        raise ValueError(f"This date does not match {fmt}.")
    try:
        return date(int(found["y"]), int(found["m"]), int(found["d"]))
    except ValueError:
        raise ValueError("This date does not exist.") from None


def _megabytes(size: int) -> str:
    return f"{size / (1024 * 1024):g} MB"


def sniff_upload(filename: str, data: bytes, max_bytes: int = MAX_UPLOAD_BYTES) -> None:
    """Judge by content as well as name: a renamed spreadsheet must not get as far as parsing."""
    if not filename.casefold().endswith(".csv"):
        raise CsvRejected("type", "Only .csv files can be imported.")
    if len(data) > max_bytes:
        raise CsvRejected(
            "size", f"This file is larger than {_megabytes(max_bytes)}. Split it and upload the parts."
        )
    for magic, reason in _REJECTED_MAGIC:
        if data.startswith(magic):
            raise CsvRejected("type", reason)
    if b"\x00" in data:
        raise CsvRejected("type", _NOT_UTF8)
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise CsvRejected("type", _NOT_UTF8) from None


def _delimiter(text: str) -> str:
    first = next((line for line in text.splitlines() if line.strip()), "")
    return max(_DELIMITERS, key=first.count)


def _header_row(cells: list[str]) -> list[str]:
    headers = [cell.strip() for cell in cells]
    if any(not header for header in headers):
        raise CsvRejected("content", "Every column needs a heading. One of the headings is empty.")
    if len({header.casefold() for header in headers}) != len(headers):
        raise CsvRejected("content", "Two columns have the same heading. Rename one and upload it again.")
    return headers


def parse_csv(data: bytes, max_rows: int = MAX_ROWS) -> ParsedCsv:
    """`number` is the row a spreadsheet shows: blank rows count, a quoted line break does not."""
    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(text), strict=True)
    headers: list[str] | None = None
    rows: list[CsvRow] = []
    try:
        for number, cells in enumerate(reader, start=1):
            if not any(cell.strip() for cell in cells):
                continue
            if headers is None:
                headers = _header_row(cells)
                continue
            rows.append(CsvRow(number, cells))
            if len(rows) > max_rows:
                raise CsvRejected(
                    "size", f"This file has more than {max_rows:,} rows. Split it and upload the parts."
                )
    except csv.Error:
        raise CsvRejected("content", "This file could not be read as CSV. Check for a stray quote.") from None
    if headers is None or not rows:
        raise CsvRejected("content", "This file has no invoice rows.")
    return ParsedCsv(headers, rows)
