"""Money, problem errors and the RLS migration helper. No database."""
import uuid

import pytest

from collectiq.platform.context import RequestContext
from collectiq.platform.errors import ProblemError
from collectiq.platform.money import Money
from collectiq.platform.rls import enable_rls


@pytest.mark.parametrize(
    ("text", "currency", "minor"),
    [
        ("1234.50", "INR", 123450),
        ("100", "JPY", 100),
        ("1.234", "KWD", 1234),
        ("-1.50", "USD", -150),
        ("0", "INR", 0),
    ],
)
def test_decimal_text_converts_to_minor_units(text, currency, minor):
    assert Money.from_decimal_text(text, currency) == Money(minor, currency)


@pytest.mark.parametrize(
    ("text", "currency"),
    [("1.234", "INR"), ("12.340", "INR"), ("100.5", "JPY"), ("1.2345", "KWD")],
)
def test_digits_beyond_the_currency_exponent_are_rejected_not_rounded(text, currency):
    with pytest.raises(ValueError, match="fractional digits"):
        Money.from_decimal_text(text, currency)


@pytest.mark.parametrize("text", ["", "abc", "NaN", "Infinity", "1e3", "1,000.00", " 1.00", ".5", "1."])
def test_malformed_amount_text_is_rejected(text):
    with pytest.raises(ValueError, match="amount"):
        Money.from_decimal_text(text, "INR")


@pytest.mark.parametrize("amount", [1.5, True, "100", None])
def test_amount_must_be_an_integer(amount):
    with pytest.raises(TypeError):
        Money(amount, "INR")


@pytest.mark.parametrize("currency", ["inr", "IN", "INRS", "", "1NR"])
def test_currency_must_be_three_capital_letters(currency):
    with pytest.raises(ValueError, match="currency"):
        Money(1, currency)


@pytest.mark.parametrize("amount", [2**63, -(2**63) - 1])
def test_amount_outside_bigint_is_rejected(amount):
    with pytest.raises(ValueError, match="BIGINT"):
        Money(amount, "INR")


def test_same_currency_adds_and_subtracts():
    assert Money(150, "INR") + Money(50, "INR") == Money(200, "INR")
    assert Money(150, "INR") - Money(50, "INR") == Money(100, "INR")


@pytest.mark.parametrize("operation", [Money.__add__, Money.__sub__])
def test_cross_currency_arithmetic_is_refused(operation):
    with pytest.raises(ValueError, match="currency"):
        operation(Money(1, "INR"), Money(1, "USD"))


def test_problem_error_carries_its_fields():
    error = ProblemError("CONFLICT_VERSION", 409, "This changed.", extra={"current": 3})
    assert (error.code, error.status, error.detail) == ("CONFLICT_VERSION", 409, "This changed.")
    assert error.extra == {"current": 3}
    assert str(error) == "CONFLICT_VERSION: This changed."


def test_problem_error_extra_defaults_empty():
    assert ProblemError("X", 400, "d").extra == {}


def test_request_context_is_immutable():
    ctx = RequestContext(uuid.uuid4(), uuid.uuid4(), "OWNER", "c", "USER")
    with pytest.raises(AttributeError):
        ctx.workspace_id = uuid.uuid4()  # type: ignore[misc]


def test_enable_rls_forces_rls_with_the_nullif_predicate_and_reverses():
    operation = enable_rls("client_contacts")
    assert "ENABLE ROW LEVEL SECURITY" in operation.sql
    assert "FORCE ROW LEVEL SECURITY" in operation.sql
    assert "NULLIF(current_setting('app.workspace_id', true), '')::uuid" in operation.sql
    assert "WITH CHECK" in operation.sql
    assert "DROP POLICY" in operation.reverse_sql
    assert "DISABLE ROW LEVEL SECURITY" in operation.reverse_sql


@pytest.mark.parametrize("table", ["a; DROP TABLE b", "Clients", "1abc", '"x"', ""])
def test_enable_rls_refuses_unsafe_table_names(table):
    with pytest.raises(ValueError, match="table"):
        enable_rls(table)
