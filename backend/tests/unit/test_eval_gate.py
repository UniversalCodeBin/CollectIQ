"""Nothing acts on an AI reading without a person until a real evaluation passes (AIR-12)."""

import pytest

from collectiq.ai.eval_gate import auto_snooze_available

PASSING = {"synthetic": False, "passed": True, "labels_covered": 10, "labels_total": 10}


def test_auto_snooze_unavailable_without_eval_report() -> None:
    assert auto_snooze_available(None) is False
    assert auto_snooze_available({}) is False


@pytest.mark.parametrize(
    "report",
    [
        {**PASSING, "synthetic": True},
        {**PASSING, "passed": False},
        {**PASSING, "labels_covered": 9},
    ],
)
def test_synthetic_failing_or_partial_reports_do_not_open_the_gate(report: dict[str, object]) -> None:
    assert auto_snooze_available(report) is False


def test_a_real_passing_report_opens_it_and_the_override_is_explicit() -> None:
    assert auto_snooze_available(PASSING) is True
    assert auto_snooze_available(None, test_only_override=True) is True
