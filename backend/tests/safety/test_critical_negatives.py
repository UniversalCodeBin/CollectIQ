"""The 12 critical negatives, each tied to the test that proves it, checkable in one run.

Each entry names the file and test function. The test below fails if a named test is renamed or removed, so
a critical negative cannot lose its proof without this file saying so. Run the named tests with
`pytest tests/safety/test_critical_negatives.py -k proof_runs` (see `test_the_named_proofs_exist`).
"""

import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parents[1]

# number -> (statement, file under tests/, test function)
CRITICAL_NEGATIVES: dict[int, tuple[str, str, str]] = {
    1: (
        "A customer's claim never changes a balance or marks an invoice paid",
        "integration/test_conversations.py",
        "test_claim_never_changes_balance_or_marks_paid",
    ),
    2: (
        "Missing statement evidence never changes an invoice status",
        "integration/test_accounts.py",
        "test_missing_event_does_not_change_status",
    ),
    3: (
        "A suggested match does not change the balance",
        "integration/test_matching.py",
        "test_ts004_unique_strong_match_waits_for_a_person",
    ),
    4: (
        "A duplicate transaction cannot be allocated twice",
        "integration/test_allocation_db.py",
        "test_duplicate_transaction_cannot_allocate_twice",
    ),
    5: (
        "A role without the permission cannot allocate",
        "integration/test_allocation_db.py",
        "test_finance_role_without_permission_denied",
    ),
    6: (
        "There is no scheduled or automatic send path",
        "integration/test_reminders.py",
        "test_there_is_no_scheduled_or_automatic_send_path",
    ),
    7: (
        "An open dispute blocks approval of a reminder",
        "integration/test_cases.py",
        "test_open_dispute_blocks_approval",
    ),
    8: (
        "A coverage gap blocks a reminder with the expected outcome",
        "integration/test_reminders.py",
        "test_coverage_gap_blocks_with_expected_outcome",
    ),
    9: (
        "A failed import commit leaves no records",
        "integration/test_import.py",
        "test_failed_commit_leaves_no_records",
    ),
    10: (
        "A failed AI call does not bypass safety",
        "integration/test_interpretation.py",
        "test_failed_ai_does_not_bypass_safety",
    ),
    11: (
        "An approved and copied reminder is not reported as sent",
        "integration/test_reminders.py",
        "test_approved_and_copied_is_not_reported_sent",
    ),
    12: (
        "Every audited write leaves an audit event with its required fields",
        "safety/test_audit_completeness.py",
        "test_no_audited_write_so_far_lacked_its_event",
    ),
}


def _functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def test_there_are_exactly_twelve_critical_negatives() -> None:
    assert sorted(CRITICAL_NEGATIVES) == list(range(1, 13))


@pytest.mark.parametrize("number", sorted(CRITICAL_NEGATIVES))
def test_the_named_proofs_exist(number: int) -> None:
    statement, filename, function = CRITICAL_NEGATIVES[number]
    path = TESTS / filename
    assert path.exists(), f"critical negative {number} ({statement}): {filename} is missing"
    assert function in _functions(path), f"critical negative {number} ({statement}): {function} is gone"
