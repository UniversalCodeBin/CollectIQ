"""Pure parsing rules for invoice CSV files. Money is never rounded and dates are never guessed."""

from datetime import date
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from collectiq.invoices.domain.csv_parse import (
    CsvRejected,
    parse_amount,
    parse_csv,
    parse_date,
    sniff_upload,
)
from collectiq.platform.money import currency_exponent

FIXTURES = Path(__file__).parents[1] / "fixtures" / "invoices"


def _grouped(minor: int, currency: str, indian: bool) -> str:
    exponent = currency_exponent(currency)
    whole, fraction = divmod(minor, 10**exponent)
    digits = str(whole)
    if indian and len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        pairs = [head[max(i - 2, 0) : i] for i in range(len(head), 0, -2)][::-1]
        grouped = ",".join([*pairs, tail])
    else:
        grouped = f"{whole:,}"
    return f"{grouped}.{fraction:0{exponent}d}" if exponent else grouped


def test_indian_grouping_parses_to_minor_units() -> None:
    assert parse_amount("2,50,000.00", "INR") == 25000000


def test_currency_symbol_is_accepted_when_it_matches() -> None:
    assert parse_amount("₹1,000.50", "INR") == 100050
    assert parse_amount("$1,000.50", "USD") == 100050
    assert parse_amount("INR 1,000.50", "INR") == 100050
    assert parse_amount("1,000.50 USD", "USD") == 100050


def test_currency_symbol_that_contradicts_the_currency_is_rejected() -> None:
    with pytest.raises(ValueError, match="currency"):
        parse_amount("$1,000.50", "INR")
    with pytest.raises(ValueError, match="currency"):
        parse_amount("EUR 10.00", "USD")


def test_excess_precision_is_rejected_never_rounded() -> None:
    with pytest.raises(ValueError):
        parse_amount("10.555", "USD")


def test_zero_decimal_currency_rejects_a_fraction() -> None:
    with pytest.raises(ValueError):
        parse_amount("1000.5", "JPY")
    assert parse_amount("1000", "JPY") == 1000


def test_three_decimal_currency_keeps_three_digits() -> None:
    assert parse_amount("1.234", "KWD") == 1234


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "-5.00",
        "(5.00)",
        "+5.00",
        "1e5",
        ".50",
        "5.",
        "1,00",
        "10,5",
        "1,000,00",
        "1,0000",
        ",100",
        "100,",
        "1,000.5,0",
        "١٢٣",
        "12 34",
        "NaN",
        "Infinity",
    ],
)
def test_malformed_amounts_are_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        parse_amount(text, "INR")


def test_comma_decimal_amount_is_rejected_clearly() -> None:
    with pytest.raises(ValueError, match="comma"):
        parse_amount("1000,50", "INR")


def test_thin_spaces_and_no_break_spaces_are_ignored_around_the_value() -> None:
    assert parse_amount(" 100.00 ", "INR") == 10000


def test_amount_above_the_storable_range_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_amount("9" * 30, "INR")


def test_unknown_currency_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_amount("10.00", "XXQ")


@given(
    st.integers(min_value=0, max_value=10**15), st.sampled_from(["INR", "USD", "JPY", "KWD"]), st.booleans()
)
def test_grouped_amounts_round_trip_exactly(minor: int, currency: str, indian: bool) -> None:
    assert parse_amount(_grouped(minor, currency, indian), currency) == minor


def test_date_requires_an_explicit_format() -> None:
    with pytest.raises(ValueError, match="format"):
        parse_date("03/04/2026", None)


def test_date_uses_the_chosen_format_and_never_guesses() -> None:
    assert parse_date("03/04/2026", "DD/MM/YYYY") == date(2026, 4, 3)
    assert parse_date("03/04/2026", "MM/DD/YYYY") == date(2026, 3, 4)
    assert parse_date("2026-04-03", "YYYY-MM-DD") == date(2026, 4, 3)
    assert parse_date("03.04.2026", "DD.MM.YYYY") == date(2026, 4, 3)


@pytest.mark.parametrize(
    ("text", "fmt"),
    [
        ("31/02/2026", "DD/MM/YYYY"),
        ("13/13/2026", "MM/DD/YYYY"),
        ("2026-04-03", "DD/MM/YYYY"),
        ("3/4/26", "DD/MM/YYYY"),
        ("", "DD/MM/YYYY"),
        ("03/04/2026", "not-a-format"),
        ("٠٣/٠٤/٢٠٢٦", "DD/MM/YYYY"),
    ],
)
def test_bad_dates_are_rejected(text: str, fmt: str) -> None:
    with pytest.raises(ValueError):
        parse_date(text, fmt)


def test_bom_stripped() -> None:
    parsed = parse_csv((FIXTURES / "bom.csv").read_bytes())
    assert parsed.headers[0] == "Invoice No"


def test_semicolon_delimiter_handled_or_rejected_clearly() -> None:
    parsed = parse_csv((FIXTURES / "semicolon.csv").read_bytes())
    assert parsed.headers == ["Invoice No", "Client", "Due", "Currency", "Total"]
    assert parsed.rows[0].values[4] == "1,000.00"


def test_row_numbers_match_the_spreadsheet_and_skip_blank_lines() -> None:
    parsed = parse_csv(b"A,B\n1,2\n\n , \n3,4\n")
    assert [(row.number, row.values) for row in parsed.rows] == [(2, ["1", "2"]), (5, ["3", "4"])]


def test_quoted_newline_is_one_spreadsheet_row() -> None:
    parsed = parse_csv(b'A,B\n"line\nbreak",2\n3,4\n')
    assert [row.number for row in parsed.rows] == [2, 3]
    assert parsed.rows[0].values[0] == "line\nbreak"


def test_header_only_file_is_rejected() -> None:
    with pytest.raises(CsvRejected, match="no invoice rows"):
        parse_csv(b"A,B\n")


def test_empty_or_duplicate_headers_are_rejected() -> None:
    with pytest.raises(CsvRejected, match="column"):
        parse_csv(b"A,,C\n1,2,3\n")
    with pytest.raises(CsvRejected, match="column"):
        parse_csv(b"A,a\n1,2\n")


def test_unterminated_quote_is_rejected() -> None:
    with pytest.raises(CsvRejected):
        parse_csv(b'A,B\n"oops,2\n')


@pytest.mark.parametrize(
    "payload",
    [
        b"PK\x03\x04rest-of-a-zip",
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1old-office",
        b"%PDF-1.7 not a csv",
        b"A,B\n1,\x002\n",
        b"\xff\xfeA\x00,\x00B\x00",
        b"\xfe\xff\x00A\x00,\x00B",
        b"A,B\n\xe9,2\n",
    ],
)
def test_content_that_is_not_utf8_text_is_refused(payload: bytes) -> None:
    with pytest.raises(CsvRejected) as raised:
        sniff_upload("invoices.csv", payload)
    assert raised.value.kind == "type"


def test_wrong_extension_is_refused() -> None:
    with pytest.raises(CsvRejected) as raised:
        sniff_upload("invoices.xlsx", b"A,B\n1,2\n")
    assert raised.value.kind == "type"


def test_plain_csv_passes_the_sniff() -> None:
    sniff_upload("Invoices.CSV", b"A,B\n1,2\n")
