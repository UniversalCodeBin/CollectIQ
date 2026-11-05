"""Payment state derivation (SAD 6.7): precedence table, TS-011/TS-012, F-7 and INV-01 properties."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from collectiq.evidence.domain.derive import Facts, derive


def facts(gross: int = 10_000, allocations: tuple[int, ...] = (), **kw: object) -> Facts:
    return Facts(gross_minor=gross, allocations=allocations, **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        (facts(), "OUTSTANDING"),
        (facts(allocations=(4_000,)), "PARTIALLY_PAID"),
        (facts(allocations=(10_000,)), "PAID_VERIFIED"),
        (facts(allocations=(6_000, 4_000)), "PAID_VERIFIED"),
        (facts(open_verification_tasks=1), "AWAITING_VERIFICATION"),
        (facts(allocations=(4_000,), open_verification_tasks=1), "AWAITING_VERIFICATION"),
        (facts(conflict=True), "UNCERTAIN"),
        (facts(ambiguous_candidates=2), "UNCERTAIN"),
        (facts(conflict=True, open_verification_tasks=1), "UNCERTAIN"),
        (facts(allocations=(10_000,), conflict=True), "PAID_VERIFIED"),
        (facts(allocations=(10_000,), open_verification_tasks=2), "PAID_VERIFIED"),
        (facts(allocations=(12_000,)), "UNCERTAIN"),
        (facts(allocations=(12_000,), overpayment_confirmed=True), "PAID_VERIFIED"),
        (facts(allocations=(10_000,), evidence_valid=False), "PARTIALLY_PAID"),
        (facts(allocations=(6_000, -6_000)), "OUTSTANDING"),
        (facts(allocations=(10_000, -2_000)), "PARTIALLY_PAID"),
    ],
)
def test_precedence(case: Facts, expected: str) -> None:
    assert derive(case).payment_status == expected


def test_ts012_sequence() -> None:
    steps = [(), (6_000,), (6_000, 4_000)]
    states = [derive(facts(allocations=a)) for a in steps]
    assert [s.payment_status for s in states] == ["OUTSTANDING", "PARTIALLY_PAID", "PAID_VERIFIED"]
    assert [s.outstanding_minor for s in states] == [10_000, 4_000, 0]
    over = derive(facts(allocations=(6_000, 4_000, 500)))
    assert over.overpayment_flag and over.payment_status == "UNCERTAIN"


def test_ts011_partial_reports_remaining() -> None:
    state = derive(facts(allocations=(4_000,)))
    assert (state.paid_minor, state.outstanding_minor) == (4_000, 6_000)


def test_missing_events_say_nothing() -> None:
    """INV-01: no allocation and no coverage input can produce anything but OUTSTANDING."""
    assert derive(facts()).payment_status == "OUTSTANDING"


amounts = st.lists(st.integers(-50_000, 50_000), max_size=8).map(tuple)


@given(
    gross=st.integers(0, 50_000),
    allocations=amounts,
    tasks=st.integers(0, 3),
    conflict=st.booleans(),
    ambiguous=st.integers(0, 3),
    confirmed=st.booleans(),
    valid=st.booleans(),
)
def test_properties(
    gross: int,
    allocations: tuple[int, ...],
    tasks: int,
    conflict: bool,
    ambiguous: int,
    confirmed: bool,
    valid: bool,
) -> None:
    state = derive(Facts(gross, allocations, tasks, conflict, ambiguous, confirmed, valid))
    paid = sum(allocations)
    assert state.paid_minor == paid
    assert state.outstanding_minor == max(0, gross - paid)
    assert state.outstanding_minor >= 0
    assert state.overpayment_flag == (paid > gross)
    if state.payment_status == "PAID_VERIFIED":
        assert paid >= gross and valid and (paid <= gross or confirmed)
    if paid < gross:
        assert state.payment_status != "PAID_VERIFIED"
    if paid <= 0 and not (tasks or conflict or ambiguous):
        assert state.payment_status == "OUTSTANDING"
    # deterministic
    assert state == derive(Facts(gross, allocations, tasks, conflict, ambiguous, confirmed, valid))
