"""Checks a reminder body before a person may approve it. Pure: no database, no clock.

The fact block is the part of a reminder that must stay true: invoice number, amount, due date. A person
may soften or reword the text around it, but not lose or change those facts, and may not add threats,
legal claims or statements that the customer has paid.
"""

import re
from dataclasses import dataclass
from typing import Any

MAX_BODY = 5000

_FORBIDDEN = (
    (re.compile(r"\b(legal action|lawyer|solicitor|sue you|court|lawsuit)\b", re.I), "NO_LEGAL_THREATS"),
    (re.compile(r"\b(blacklist|police|arrest|jail|report you|credit bureau)\b", re.I), "NO_THREATS"),
    (
        re.compile(r"\b(we have received your payment|you have paid|payment received)\b", re.I),
        "NO_PAID_CLAIM",
    ),
    (re.compile(r"\b(final notice|last warning|last chance)\b", re.I), "NO_ESCALATION_WORDING"),
)


@dataclass(frozen=True)
class LintFinding:
    code: str
    message: str


def _amount_forms(facts: dict[str, Any]) -> list[str]:
    return [str(facts["amount_text"]), str(facts["amount_plain"])]


def lint_reminder(body: str, fact_block: dict[str, Any]) -> list[LintFinding]:
    findings: list[LintFinding] = []
    text = body.strip()
    if not text:
        return [LintFinding("EMPTY", "The reminder needs some text.")]
    if len(text) > MAX_BODY:
        findings.append(LintFinding("TOO_LONG", f"Keep the reminder under {MAX_BODY} characters."))
    if str(fact_block["invoice_number"]) not in text:
        findings.append(LintFinding("MISSING_INVOICE_NUMBER", "Keep the invoice number in the reminder."))
    if not any(form in text for form in _amount_forms(fact_block)):
        findings.append(LintFinding("MISSING_AMOUNT", "Keep the amount outstanding in the reminder."))
    if str(fact_block["due_date"]) not in text:
        findings.append(LintFinding("MISSING_DUE_DATE", "Keep the due date in the reminder."))
    for pattern, code in _FORBIDDEN:
        if pattern.search(text):
            findings.append(LintFinding(code, "This wording is not allowed in a reminder."))
    return findings
