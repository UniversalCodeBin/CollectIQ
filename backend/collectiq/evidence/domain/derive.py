"""Payment status as a pure function of ledger facts (SAD 6.7, PRD BR-08).

No AI output, no clock and no coverage go in. A customer's claim reaches this only as an open
verification task, so it can hold a reminder back but can never make an invoice paid.
"""

from dataclasses import dataclass
from typing import Literal

PaymentStatus = Literal[
    "OUTSTANDING", "PARTIALLY_PAID", "PAID_VERIFIED", "AWAITING_VERIFICATION", "UNCERTAIN"
]


@dataclass(frozen=True, slots=True)
class Facts:
    gross_minor: int
    allocations: tuple[int, ...] = ()  # signed minor units; reversals are negative
    open_verification_tasks: int = 0
    conflict: bool = False
    ambiguous_candidates: int = 0  # unresolved match candidates (two or more)
    overpayment_confirmed: bool = False
    evidence_valid: bool = True  # every allocation rests on an accepted evidence type


@dataclass(frozen=True, slots=True)
class DerivedState:
    payment_status: PaymentStatus
    paid_minor: int
    outstanding_minor: int
    overpayment_flag: bool


def derive(facts: Facts) -> DerivedState:
    paid = sum(facts.allocations)
    gross = facts.gross_minor
    overpaid = paid > gross
    if paid >= gross and paid > 0 and (not overpaid or facts.overpayment_confirmed) and facts.evidence_valid:
        status: PaymentStatus = "PAID_VERIFIED"
    elif facts.conflict or facts.ambiguous_candidates >= 2 or overpaid:
        status = "UNCERTAIN"
    elif facts.open_verification_tasks > 0:
        status = "AWAITING_VERIFICATION"
    elif paid > 0:
        status = "PARTIALLY_PAID"
    else:
        status = "OUTSTANDING"
    return DerivedState(status, paid, max(0, gross - paid), overpaid)
