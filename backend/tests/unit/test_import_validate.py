"""Per-row validation for invoice imports."""

from datetime import date

import pytest

from collectiq.invoices.domain.validate import (
    RowMapping,
    mapping_errors,
    normalize_number,
    similarity_key,
    suggest_mapping,
    validate_row,
)

HEADERS = ["No", "Client", "Due", "Cur", "Total", "Sub", "Tax", "Issued", "Email"]
MAPPING = RowMapping(
    {
        "invoice_number": "No",
        "client_name": "Client",
        "due_date": "Due",
        "currency": "Cur",
        "total": "Total",
        "subtotal": "Sub",
        "tax": "Tax",
        "issue_date": "Issued",
        "client_email": "Email",
    },
    HEADERS,
)
GOOD = ["INV-1", "Acme", "2026-05-01", "inr", "118.00", "100.00", "18.00", "2026-04-01", "A@Example.Test"]


def _validate(row: list[str] = GOOD, date_format: str | None = "YYYY-MM-DD"):
    return validate_row(row, MAPPING, date_format)


def _fields(result) -> set[str]:
    return {error.field for error in result.errors}


def test_good_row_yields_normalised_values() -> None:
    result = _validate()
    assert result.errors == []
    assert result.conflict is False
    assert result.values["invoice_number"] == "INV-1"
    assert result.values["currency"] == "INR"
    assert result.values["gross_minor"] == 11800
    assert result.values["subtotal_minor"] == 10000
    assert result.values["tax_minor"] == 1800
    assert result.values["due_date"] == date(2026, 5, 1)
    assert result.values["client_email"] == "a@example.test"


@pytest.mark.parametrize(
    ("index", "value", "field"),
    [
        (0, " ", "invoice_number"),
        (1, "", "client_name"),
        (2, "", "due_date"),
        (3, "XXQ", "currency"),
        (4, "-1.00", "total"),
        (4, "", "total"),
        (5, "abc", "subtotal"),
        (6, "-1", "tax"),
        (7, "2026-05-02", "issue_date"),
        (8, "not-an-email", "client_email"),
        (0, "x" * 129, "invoice_number"),
        (1, "x" * 201, "client_name"),
    ],
)
def test_bad_values_are_reported_per_field(index: int, value: str, field: str) -> None:
    row = list(GOOD)
    row[index] = value
    assert field in _fields(_validate(row))


def test_due_date_on_issue_date_is_allowed() -> None:
    row = list(GOOD)
    row[7] = row[2]
    assert _validate(row).errors == []


def test_row_with_the_wrong_number_of_cells_is_invalid() -> None:
    assert "row" in _fields(_validate(GOOD[:3]))
    assert "row" in _fields(_validate([*GOOD, "extra"]))


def test_without_a_date_format_every_row_is_blocked_even_iso_dates() -> None:
    result = _validate(date_format=None)
    assert "date_format" in _fields(result)


def test_total_within_the_tolerance_is_not_a_conflict() -> None:
    row = list(GOOD)
    row[4] = "118.01"
    assert _validate(row).conflict is False
    row[4] = "117.99"
    assert _validate(row).conflict is False


def test_total_beyond_the_tolerance_is_a_conflict() -> None:
    row = list(GOOD)
    row[4] = "118.02"
    assert _validate(row).conflict is True


def test_zero_decimal_currency_has_no_tolerance() -> None:
    row = list(GOOD)
    row[3] = "JPY"
    row[4], row[5], row[6] = "119", "100", "18"
    assert _validate(row).conflict is True


def test_conflict_needs_both_subtotal_and_tax() -> None:
    row = list(GOOD)
    row[4] = "500.00"
    row[6] = ""
    assert _validate(row).conflict is False


def test_mapping_requires_the_five_required_fields() -> None:
    errors = mapping_errors({"invoice_number": "No", "client_name": "Client"}, HEADERS)
    assert {error[0] for error in errors} == {"mapping.due_date", "mapping.currency", "mapping.total"}


def test_mapping_refuses_unknown_targets_headers_and_reuse() -> None:
    base = {
        "invoice_number": "No",
        "client_name": "Client",
        "due_date": "Due",
        "currency": "Cur",
        "total": "Total",
    }
    assert mapping_errors(base, HEADERS) == []
    assert mapping_errors({**base, "colour": "Sub"}, HEADERS)[0][0] == "mapping.colour"
    assert mapping_errors({**base, "tax": "Nope"}, HEADERS)[0][0] == "mapping.tax"
    assert mapping_errors({**base, "tax": "Total"}, HEADERS)[0][0] == "mapping.tax"


def test_suggestion_recognises_common_headers() -> None:
    suggested = suggest_mapping(["Invoice No", "Client Name", "Due Date", "Currency", "Grand Total", "GST"])
    assert suggested == {
        "invoice_number": "Invoice No",
        "client_name": "Client Name",
        "due_date": "Due Date",
        "currency": "Currency",
        "total": "Grand Total",
        "tax": "GST",
    }


def test_invoice_number_normalisation_ignores_case_and_punctuation() -> None:
    assert normalize_number(" inv-00 1/A ") == normalize_number("INV001A")
    assert normalize_number("---") == "---"


def test_legal_suffixes_share_a_similarity_key() -> None:
    assert similarity_key("Acme Pvt Ltd") == similarity_key("ACME Private Limited")
    assert similarity_key("Acme Pvt. Ltd.") == similarity_key("acme")
    assert similarity_key("Acme") != similarity_key("Acme Tools")
