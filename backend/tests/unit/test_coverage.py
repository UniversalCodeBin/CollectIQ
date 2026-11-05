"""Evidence coverage (SAD 6.8, AC-1): what the workspace has actually looked at, and how recently."""

from datetime import date

import pytest

from collectiq.evidence.domain.coverage import (
    Attestation,
    CoverageRange,
    coverage_as_of,
    coverage_status,
    merge_ranges,
)

ISSUE = date(2026, 10, 1)


def d(day: int, month: int = 10) -> date:
    return date(2026, month, day)


def rng(account: str, start: date, end: date) -> CoverageRange:
    return CoverageRange(account, start, end)


def inv_att(day: date, invoice: str = "inv-1") -> Attestation:
    return Attestation("INVOICE", None, invoice, day)


def acct_att(account: str, day: date) -> Attestation:
    return Attestation("ACCOUNT", account, None, day)


def test_no_accounts_and_no_attestation_is_not_covered() -> None:
    assert coverage_as_of(ISSUE, "inv-1", [], [], []) is None


def test_no_accounts_only_invoice_attestation_counts() -> None:
    ranges = [rng("a1", d(1), d(30))]  # ranges of an account that is not declared are ignored
    attestations = [acct_att("a1", d(29)), inv_att(d(20)), inv_att(d(25), invoice="inv-2")]
    assert coverage_as_of(ISSUE, "inv-1", [], ranges, attestations) == d(20)


def test_coverage_runs_to_the_end_of_a_range_that_starts_by_the_issue_date() -> None:
    assert coverage_as_of(ISSUE, "inv-1", ["a1"], [rng("a1", d(1), d(28))], []) == d(28)


def test_statement_starting_after_the_issue_date_proves_nothing() -> None:
    assert coverage_as_of(ISSUE, "inv-1", ["a1"], [rng("a1", d(5), d(28))], []) is None


def test_gap_in_ranges_stops_contiguous_coverage() -> None:
    ranges = [rng("a1", d(1), d(10)), rng("a1", d(15), d(28))]
    assert coverage_as_of(ISSUE, "inv-1", ["a1"], ranges, []) == d(10)


def test_adjacent_ranges_join_without_a_gap() -> None:
    ranges = [rng("a1", d(1), d(10)), rng("a1", d(11), d(28))]
    assert coverage_as_of(ISSUE, "inv-1", ["a1"], ranges, []) == d(28)


def test_overlapping_ranges_join() -> None:
    ranges = [rng("a1", d(1), d(20)), rng("a1", d(10), d(28))]
    assert coverage_as_of(ISSUE, "inv-1", ["a1"], ranges, []) == d(28)


def test_a_range_that_began_before_the_issue_date_chains_forward() -> None:
    ranges = [rng("a1", date(2026, 9, 1), date(2026, 9, 30)), rng("a1", d(1), d(20))]
    assert coverage_as_of(ISSUE, "inv-1", ["a1"], ranges, []) == d(20)


def test_the_least_covered_account_limits_coverage() -> None:
    ranges = [rng("a1", d(1), d(28)), rng("a2", d(1), d(14))]
    assert coverage_as_of(ISSUE, "inv-1", ["a1", "a2"], ranges, []) == d(14)


def test_an_account_with_no_statement_means_no_account_coverage() -> None:
    assert coverage_as_of(ISSUE, "inv-1", ["a1", "a2"], [rng("a1", d(1), d(28))], []) is None


def test_account_attestation_extends_that_accounts_coverage() -> None:
    ranges = [rng("a1", d(1), d(14)), rng("a2", d(1), d(14))]
    attestations = [acct_att("a1", d(28)), acct_att("a2", d(21))]
    assert coverage_as_of(ISSUE, "inv-1", ["a1", "a2"], ranges, attestations) == d(21)


def test_account_attestation_alone_covers_an_account() -> None:
    assert coverage_as_of(ISSUE, "inv-1", ["a1"], [], [acct_att("a1", d(20))]) == d(20)


def test_attestation_older_than_the_invoice_proves_nothing() -> None:
    assert coverage_as_of(ISSUE, "inv-1", ["a1"], [], [acct_att("a1", date(2026, 9, 20))]) is None


def test_invoice_attestation_wins_when_it_is_later() -> None:
    ranges = [rng("a1", d(1), d(10))]
    assert coverage_as_of(ISSUE, "inv-1", ["a1"], ranges, [inv_att(d(25))]) == d(25)


def test_an_attestation_never_shortens_coverage() -> None:
    ranges = [rng("a1", d(1), d(28))]
    assert coverage_as_of(ISSUE, "inv-1", ["a1"], ranges, [inv_att(d(5))]) == d(28)


def test_an_invoice_without_an_issue_date_is_covered_only_by_attestation() -> None:
    assert coverage_as_of(None, "inv-1", ["a1"], [rng("a1", d(1), d(28))], []) is None
    assert coverage_as_of(None, "inv-1", ["a1"], [rng("a1", d(1), d(28))], [inv_att(d(20))]) == d(20)


def test_merge_ranges_is_sorted_and_joined() -> None:
    merged = merge_ranges([rng("a", d(15), d(20)), rng("a", d(1), d(10)), rng("a", d(11), d(12))])
    assert merged == [(d(1), d(12)), (d(15), d(20))]


@pytest.mark.parametrize(
    ("as_of", "expected"),
    [
        (None, "MISSING"),
        (d(28), "SUPPORTED"),  # today is 30 Oct: 2 days
        (d(23), "SUPPORTED"),  # exactly 7 days
        (d(22), "STALE"),  # 8 days
    ],
)
def test_status_against_the_freshness_window(as_of: date | None, expected: str) -> None:
    assert coverage_status(as_of, d(30)) == expected


def test_ts_032_sequence_missing_then_supported_then_stale() -> None:
    today = d(10)
    assert coverage_status(coverage_as_of(ISSUE, "inv-1", ["a1"], [], []), today) == "MISSING"
    as_of = coverage_as_of(ISSUE, "inv-1", ["a1"], [rng("a1", d(1), d(9))], [])
    assert coverage_status(as_of, today) == "SUPPORTED"
    assert coverage_status(as_of, d(30)) == "STALE"
    assert coverage_status(as_of, d(30), window_days=30) == "SUPPORTED"


def test_missing_event_does_not_change_status() -> None:
    # Coverage is a function of what was looked at, never of what was received: the same ranges and
    # attestations give the same answer however many transactions exist or are absent.
    as_of = coverage_as_of(ISSUE, "inv-1", ["a1"], [rng("a1", d(1), d(20))], [])
    assert as_of == d(20)
    assert coverage_as_of(ISSUE, "inv-1", ["a1"], [rng("a1", d(1), d(20))], []) == as_of


def test_a_coverage_date_in_the_future_is_still_current() -> None:
    assert coverage_status(d(30, 11), d(30)) == "SUPPORTED"


def test_account_summary_lists_gaps_and_counts_only_contiguous_statements() -> None:
    from collectiq.evidence.domain.coverage import account_coverage

    summary = account_coverage([rng("a", d(1), d(10)), rng("a", d(15), d(28))], [])
    assert summary.statements_through == d(10)
    assert summary.gaps == [(d(11), d(14))]
    assert summary.covered_through == d(10)


def test_account_summary_with_an_attestation_and_nothing_else() -> None:
    from collectiq.evidence.domain.coverage import account_coverage

    summary = account_coverage([], [acct_att("a", d(20))])
    assert (summary.statements_through, summary.attested_through, summary.covered_through) == (
        None,
        d(20),
        d(20),
    )
    assert summary.gaps == []
