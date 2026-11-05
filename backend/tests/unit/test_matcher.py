"""Matcher bands and factors (SAD 6.3-6.5, TS-004, BR-11, BR-12)."""

from datetime import date

from collectiq.evidence.domain.matcher import MATCHER_VERSION, Candidate, Txn, match

TXN = Txn(
    id="t1",
    amount_minor=10_000,
    currency="INR",
    value_date=date(2026, 10, 20),
    reference_candidates=("INV-42",),
    descriptor="NEFT NORTHWIND TRADERS",
)


def cand(id: str = "i1", **kw: object) -> Candidate:
    base: dict[str, object] = {
        "id": id,
        "normalized_number": "inv42",
        "currency": "INR",
        "gross_minor": 10_000,
        "outstanding_minor": 10_000,
        "issue_date": date(2026, 10, 1),
        "due_date": date(2026, 10, 31),
        "aliases": (),
    }
    base.update(kw)
    return Candidate(**base)  # type: ignore[arg-type]


def test_reference_amount_date_is_high() -> None:
    [r] = match(TXN, [cand()])
    assert r.band == "HIGH" and r.label == "Strong" and not r.ambiguous
    assert {f.code for f in r.factors} >= {"REFERENCE_EXACT", "AMOUNT_OUTSTANDING", "DATE_IN_WINDOW"}


def test_high_band_requires_reference_amount_and_margin() -> None:
    no_ref = Txn("t", 10_000, "INR", date(2026, 10, 20), (), "NORTHWIND")
    [r] = match(no_ref, [cand(aliases=("northwind",))])
    assert r.band == "MEDIUM"  # alias 15 + amount 30 + date 10, never HIGH
    wrong_amount = Txn("t", 7_000, "INR", date(2026, 10, 20), ("INV-42",), None)
    [r] = match(wrong_amount, [cand()])
    assert r.band != "HIGH"
    [a, b] = match(TXN, [cand("i1"), cand("i2")])
    assert a.ambiguous and b.ambiguous and a.band == b.band == "MEDIUM"  # margin rule fails


def test_partial_with_reference_is_plausible() -> None:
    part = Txn("t", 4_000, "INR", date(2026, 10, 20), ("INV-42",), None)
    [r] = match(part, [cand()])
    assert "PARTIAL_WITH_REFERENCE" in {f.code for f in r.factors}
    assert r.band == "MEDIUM"  # 50 + 15 + 10, and a partial is never Strong


def test_partial_payment_uses_remaining_balance() -> None:
    txn = Txn("t", 6_000, "INR", date(2026, 10, 25), ("INV-42",), None)
    [r] = match(txn, [cand(outstanding_minor=6_000)])
    assert r.band == "HIGH"


def test_normalized_reference_scores_below_exact() -> None:
    [exact] = match(TXN, [cand()])
    [loose] = match(TXN, [cand(normalized_number="inv0042")])
    assert "REFERENCE_NORMALIZED" in {f.code for f in loose.factors}
    assert loose.score < exact.score


def test_currency_and_settled_invoices_are_excluded() -> None:
    assert match(TXN, [cand(currency="USD")]) == []
    assert match(TXN, [cand(outstanding_minor=0)]) == []


def test_below_twenty_is_no_candidate_and_low_is_weak() -> None:
    far = Txn("t", 123, "INR", date(2027, 5, 1), (), None)
    assert match(far, [cand()]) == []
    low = Txn("t", 10_000, "INR", date(2027, 5, 1), (), None)
    [r] = match(low, [cand()])
    assert (r.band, r.label) == ("LOW", "Weak")


def test_candidates_capped_at_10() -> None:
    results = match(TXN, [cand(f"i{n}") for n in range(25)])
    assert len(results) == 10


def test_payer_overlapping_a_saved_name_is_a_partial_alias() -> None:
    no_ref = Txn("t", 10_000, "INR", date(2026, 10, 20), (), "NEFT NORTHWIND TRADERS")
    [overlap] = match(no_ref, [cand(aliases=("Northwind Traders Ltd",))])
    assert "ALIAS_PARTIAL" in {f.code for f in overlap.factors}
    [elsewhere] = match(no_ref, [cand(aliases=("Contoso Holdings Ltd",))])
    assert not {f.code for f in elsewhere.factors} & {"ALIAS_PARTIAL", "ALIAS_EXACT"}


def test_version_is_stamped() -> None:
    assert MATCHER_VERSION
