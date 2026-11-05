"""The claims gate rejects seeded compliance, certification, accuracy and uptime claims."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "check_claims", Path(__file__).resolve().parents[3] / "scripts" / "check_claims.py"
)
assert SPEC and SPEC.loader
claims = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(claims)


def test_rejects_seeded_claims() -> None:
    for line in (
        "We are SOC 2 compliant",
        "Your data is protected to PCI DSS standards",
        "An immutable audit log",
        "Tamper-proof history",
        "99.9% uptime",
        "97% accuracy on invoices",
        "Fully compliant with GDPR",
        "ISO 27001 certified",
        "Bank-grade security",
    ):
        assert claims.violations_in(line), line


def test_accepts_negative_statements_and_plain_text() -> None:
    for line in (
        "Make no SOC 2, ISO, PCI, DPDP or GDPR claim.",
        "Append-only by database permissions; not tamper-resistant against a database superuser.",
        "Each save writes a new immutable policy version.",
        "Nothing is sent without a person approving it.",
    ):
        assert not claims.violations_in(line), line


def test_the_repository_is_clean() -> None:
    assert claims.main([]) == 0
