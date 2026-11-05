"""How far the workspace has actually looked for payments (SAD 6.8, AC-1). Pure: no database, no clock.

Coverage answers "up to when do we know what arrived?". It is built only from statement ranges and
attestations that a person made. A payment that did not show up changes nothing here (INV-01).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

FRESHNESS_DAYS = 7  # [PROP] A7; the service reads the configured value
CoverageState = Literal["SUPPORTED", "STALE", "MISSING"]


@dataclass(frozen=True)
class CoverageRange:
    account_id: str
    covers_from: date
    covers_to: date


@dataclass(frozen=True)
class Attestation:
    scope: Literal["ACCOUNT", "INVOICE"]
    account_id: str | None
    invoice_id: str | None
    as_of: date


def merge_ranges(ranges: Iterable[CoverageRange]) -> list[tuple[date, date]]:
    """Overlapping and back-to-back ranges become one; a missing day keeps two apart."""
    merged: list[tuple[date, date]] = []
    for item in sorted(ranges, key=lambda r: (r.covers_from, r.covers_to)):
        if merged and item.covers_from <= merged[-1][1] + timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], item.covers_to))
        else:
            merged.append((item.covers_from, item.covers_to))
    return merged


def _account_coverage_to(
    since: date | None, ranges: Sequence[CoverageRange], attestations: Sequence[Attestation]
) -> date | None:
    reached: date | None = None
    if since is not None:
        for start, end in merge_ranges(ranges):
            if start <= since <= end:
                reached = end
    for attestation in attestations:
        if since is not None and attestation.as_of < since:
            continue
        if reached is None or attestation.as_of > reached:
            reached = attestation.as_of
    return reached


def coverage_as_of(
    issue_date: date | None,
    invoice_id: str,
    accounts: Sequence[str],
    ranges: Sequence[CoverageRange],
    attestations: Sequence[Attestation],
) -> date | None:
    """The date up to which nothing could have arrived unseen, or None when that is not known.

    With declared accounts, the least covered one limits the answer: a statement for one account says
    nothing about another. A statement only counts when it runs unbroken from the invoice's issue
    date. An invoice with no issue date cannot be placed against a statement, so only an attestation
    covers it. With no declared accounts, only an attestation about this invoice counts.
    """
    from_invoice = [
        a.as_of
        for a in attestations
        if a.scope == "INVOICE"
        and a.invoice_id == invoice_id
        and (issue_date is None or a.as_of >= issue_date)
    ]
    per_account: list[date | None] = [
        _account_coverage_to(
            issue_date,
            [r for r in ranges if r.account_id == account],
            [a for a in attestations if a.scope == "ACCOUNT" and a.account_id == account],
        )
        for account in accounts
    ]
    from_accounts = None if (not per_account or None in per_account) else min(d for d in per_account if d)
    known = [d for d in (*from_invoice, from_accounts) if d is not None]
    return max(known) if known else None


def coverage_status(as_of: date | None, today: date, window_days: int = FRESHNESS_DAYS) -> CoverageState:
    """MISSING if never looked, SUPPORTED while the look is recent, STALE once it has aged out."""
    if as_of is None:
        return "MISSING"
    return "SUPPORTED" if (today - as_of).days <= window_days else "STALE"


@dataclass(frozen=True)
class AccountCoverage:
    """What one account's statements and attestations add up to, for the accounts screen."""

    statements_through: date | None
    attested_through: date | None
    covered_through: date | None
    gaps: list[tuple[date, date]]


def account_coverage(ranges: Sequence[CoverageRange], attestations: Sequence[Attestation]) -> AccountCoverage:
    """Contiguous from the earliest statement; later pieces past a gap are listed as gaps, not counted."""
    merged = merge_ranges(ranges)
    statements_through = merged[0][1] if merged else None
    attested = [a.as_of for a in attestations]
    attested_through = max(attested) if attested else None
    known = [d for d in (statements_through, attested_through) if d is not None]
    gaps = [
        (merged[i][1] + timedelta(days=1), merged[i + 1][0] - timedelta(days=1))
        for i in range(len(merged) - 1)
    ]
    return AccountCoverage(statements_through, attested_through, max(known) if known else None, gaps)
