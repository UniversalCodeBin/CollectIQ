"""Statement row parsing: signed amounts, locales, fingerprints and reference candidates (FR-037..FR-041)."""

from datetime import date

import pytest

from collectiq.evidence.parsers.base import RawRow, StatementMapping
from collectiq.evidence.parsers.generic_csv import GenericCsvParser, fingerprint, reference_candidates

MAPPING = StatementMapping(date="Date", description="Narration", amount="Amount")


def _parse(
    text: str, mapping: StatementMapping = MAPPING, fmt: str | None = "YYYY-MM-DD", currency: str = "INR"
):
    return list(GenericCsvParser().parse(text.encode(), mapping, fmt, currency))


def test_sniff_accepts_csv_and_refuses_binary() -> None:
    parser = GenericCsvParser()
    assert parser.sniff(b"Date,Amount\n2026-01-01,1\n")
    assert not parser.sniff(b"PK\x03\x04zip")
    assert not parser.sniff(b"\xff\xfeU\x00")


def test_credit_and_debit_by_sign() -> None:
    rows = _parse('Date,Narration,Amount\n2026-01-01,Acme INV-1,"1,500.50"\n2026-01-02,Rent,-200.00\n')
    assert [(r.direction, r.amount_minor) for r in rows] == [("CREDIT", 150050), ("DEBIT", 20000)]


def test_negative_in_debit_column_is_still_a_debit() -> None:
    mapping = StatementMapping(date="Date", description="Narration", credit="Credit", debit="Debit")
    rows = _parse("Date,Narration,Credit,Debit\n2026-01-01,A,,-50.00\n2026-01-01,B,75.00,\n", mapping)
    assert [(r.direction, r.amount_minor) for r in rows] == [("DEBIT", 5000), ("CREDIT", 7500)]


def test_parentheses_mean_debit() -> None:
    rows = _parse("Date,Narration,Amount\n2026-01-01,A,(40.00)\n")
    assert rows[0].direction == "DEBIT" and rows[0].amount_minor == 4000


def test_bom_semicolon_indian_grouping_and_dd_mm() -> None:
    text = '﻿Date;Narration;Amount\n03/04/2026;Acme;"2,50,000.00"\n'
    rows = _parse(text, fmt="DD/MM/YYYY")
    assert rows[0].value_date == date(2026, 4, 3) and rows[0].amount_minor == 25000000


def test_ambiguous_date_without_format_is_a_row_error_not_a_guess() -> None:
    rows = _parse("Date,Narration,Amount\n03/04/2026,Acme,10.00\n", fmt=None)
    assert isinstance(rows[0], RawRow) and rows[0].error and "date format" in rows[0].error.lower()


def test_three_decimals_on_two_exponent_currency_is_an_error() -> None:
    rows = _parse("Date,Narration,Amount\n2026-01-01,Acme,10.005\n")
    assert rows[0].error


def test_blank_and_zero_amounts_are_errors() -> None:
    rows = _parse("Date,Narration,Amount\n2026-01-01,A,\n2026-01-01,B,0.00\n")
    assert all(r.error for r in rows)


def test_row_numbers_follow_the_spreadsheet() -> None:
    rows = _parse("Date,Narration,Amount\n\n2026-01-01,A,1.00\n")
    assert rows[0].number == 3


def test_row_currency_column_overrides_and_mismatch_is_reported_by_service() -> None:
    mapping = StatementMapping(date="Date", description="Narration", amount="Amount", currency="Cur")
    rows = _parse("Date,Narration,Amount,Cur\n2026-01-01,A,1.00,USD\n", mapping)
    assert rows[0].currency == "USD"


def test_fingerprint_ignores_case_and_spacing_but_not_amount_or_date() -> None:
    base = fingerprint("acct", date(2026, 1, 1), 100, "INR", "Acme  INV-1", None)
    assert base == fingerprint("acct", date(2026, 1, 1), 100, "INR", "acme inv-1", None)
    assert base != fingerprint("acct", date(2026, 1, 2), 100, "INR", "Acme INV-1", None)
    assert base != fingerprint("acct", date(2026, 1, 1), 101, "INR", "Acme INV-1", None)
    assert base != fingerprint("acct", date(2026, 1, 1), 100, "INR", "Acme INV-1", 5)
    assert base != fingerprint("other", date(2026, 1, 1), 100, "INR", "Acme INV-1", None)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("INV-2041 Acme", ["INV-2041"]),
        ("NEFT/ACME/inv 2041/ref", ["INV-2041"]),
        ("Payment for INV/2041 and INV-2042", ["INV-2041", "INV-2042"]),
        ("Salary March", []),
    ],
)
def test_reference_candidates(text: str, expected: list[str]) -> None:
    assert reference_candidates(text) == expected
