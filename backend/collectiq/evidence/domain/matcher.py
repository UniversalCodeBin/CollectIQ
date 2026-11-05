"""Explainable match suggestions (SAD 6.3-6.5). Pure, no I/O.

Scores are an internal ordering aid and are never shown. Nothing here applies a match: a result is only
ever a proposal for a person to confirm (BR-12). Weights are provisional until calibrated on pilot data.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

MATCHER_VERSION = "m1-2026-11"
MAX_CANDIDATES = 10
NO_CANDIDATE_BELOW = 20
LOW_BELOW = 50
HIGH_AT = 80
MARGIN = 20

W_REFERENCE_EXACT = 50
W_REFERENCE_NORMALIZED = 40
W_AMOUNT_OUTSTANDING = 30
W_AMOUNT_GROSS = 25
W_PARTIAL = 15
W_DATE = 10
W_ALIAS_EXACT = 15
W_ALIAS_FUZZY = 8
W_ALIAS_CONFIRMED = 10
W_HISTORY = 5
DATE_BEFORE_ISSUE = timedelta(days=7)
DATE_AFTER_DUE = timedelta(days=90)

Band = Literal["HIGH", "MEDIUM", "LOW"]
_LABELS = {"HIGH": "Strong", "MEDIUM": "Possible", "LOW": "Weak"}
_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


@dataclass(frozen=True, slots=True)
class Txn:
    id: str
    amount_minor: int
    currency: str
    value_date: date
    reference_candidates: tuple[str, ...]
    descriptor: str | None


@dataclass(frozen=True, slots=True)
class Candidate:
    id: str
    normalized_number: str
    currency: str
    gross_minor: int
    outstanding_minor: int
    issue_date: date | None
    due_date: date
    aliases: tuple[str, ...] = ()
    alias_confirmed: bool = False
    account_history: bool = False


@dataclass(frozen=True, slots=True)
class Factor:
    code: str
    points: int
    text: str


@dataclass(frozen=True, slots=True)
class MatchResult:
    invoice_id: str
    score: int
    band: Band
    label: str
    factors: tuple[Factor, ...]
    ambiguous: bool


def _fold(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _digits(text: str) -> str | None:
    runs = re.findall(r"\d+", text)
    return str(int(runs[-1])) if runs else None


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.casefold()) if len(t) > 1}


def _alias_factor(descriptor: str | None, aliases: Sequence[str]) -> Factor | None:
    if not descriptor or not aliases:
        return None
    folded = _fold(descriptor)
    if any(_fold(a) == folded for a in aliases):
        return Factor("ALIAS_EXACT", W_ALIAS_EXACT, "The payer name matches a name saved for this client.")
    seen = _tokens(descriptor)
    for alias in aliases:
        wanted = _tokens(alias)
        if wanted and 2 * len(wanted & seen) >= len(wanted):
            return Factor(
                "ALIAS_PARTIAL", W_ALIAS_FUZZY, "The payer name overlaps a name saved for this client."
            )
    return None


def _reference(txn: Txn, number: str) -> Factor | None:
    folded = [_fold(c) for c in txn.reference_candidates]
    if number in folded:
        return Factor("REFERENCE_EXACT", W_REFERENCE_EXACT, "The payment mentions this invoice number.")
    wanted = _digits(number)
    if wanted and any(_digits(c) == wanted for c in folded):
        return Factor(
            "REFERENCE_NORMALIZED",
            W_REFERENCE_NORMALIZED,
            "The payment mentions a number close to this invoice's.",
        )
    return None


def _score(txn: Txn, c: Candidate) -> tuple[int, list[Factor], bool, bool]:
    factors: list[Factor] = []
    ref = _reference(txn, c.normalized_number)
    if ref:
        factors.append(ref)
    amount_ok = False
    if abs(txn.amount_minor - c.outstanding_minor) <= 1:
        factors.append(
            Factor("AMOUNT_OUTSTANDING", W_AMOUNT_OUTSTANDING, "The amount equals what is still owed.")
        )
        amount_ok = True
    elif abs(txn.amount_minor - c.gross_minor) <= 1:
        factors.append(Factor("AMOUNT_GROSS", W_AMOUNT_GROSS, "The amount equals the invoice total."))
        amount_ok = True
    elif ref and 0 < txn.amount_minor < c.outstanding_minor:
        factors.append(
            Factor(
                "PARTIAL_WITH_REFERENCE",
                W_PARTIAL,
                "Less than is owed, with this invoice number: a part payment.",
            )
        )
    low = c.issue_date - DATE_BEFORE_ISSUE if c.issue_date else date.min
    if low <= txn.value_date <= c.due_date + DATE_AFTER_DUE:
        factors.append(Factor("DATE_IN_WINDOW", W_DATE, "The payment date is in the expected period."))
    alias = _alias_factor(txn.descriptor, c.aliases)
    if alias:
        factors.append(alias)
    if c.alias_confirmed:
        factors.append(
            Factor("ALIAS_CONFIRMED", W_ALIAS_CONFIRMED, "This payer was confirmed for this client before.")
        )
    if c.account_history:
        factors.append(Factor("ACCOUNT_HISTORY", W_HISTORY, "This account has paid this client before."))
    return sum(f.points for f in factors), factors, ref is not None, amount_ok


def match(
    txn: Txn, candidates: Sequence[Candidate], matcher_version: str = MATCHER_VERSION
) -> list[MatchResult]:
    scored = []
    for c in candidates:
        if c.currency != txn.currency or c.outstanding_minor <= 0:
            continue
        score, factors, has_ref, amount_ok = _score(txn, c)
        if score >= NO_CANDIDATE_BELOW:
            scored.append((score, c.id, factors, has_ref, amount_ok))
    scored.sort(key=lambda s: (-s[0], s[1]))
    scored = scored[:MAX_CANDIDATES]
    results: list[MatchResult] = []
    for index, (score, invoice_id, factors, has_ref, _amount_ok) in enumerate(scored):
        rival = max((s[0] for i, s in enumerate(scored) if i != index), default=None)
        margin_ok = rival is None or rival <= score - MARGIN
        full_amount = any(f.code in ("AMOUNT_OUTSTANDING", "AMOUNT_GROSS") for f in factors)
        band: Band
        if score >= HIGH_AT and has_ref and full_amount and margin_ok:
            band = "HIGH"
        elif score >= LOW_BELOW or (score >= HIGH_AT and has_ref and full_amount):
            band = "MEDIUM"
        else:
            band = "LOW"
        results.append(MatchResult(invoice_id, score, band, _LABELS[band], tuple(factors), False))
    return [
        MatchResult(
            r.invoice_id,
            r.score,
            r.band,
            r.label,
            r.factors,
            _ORDER[r.band] >= 2
            and any(o is not r and _ORDER[o.band] >= 2 and abs(o.score - r.score) < MARGIN for o in results),
        )
        for r in results
    ]
