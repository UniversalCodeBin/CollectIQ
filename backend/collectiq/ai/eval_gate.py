"""Whether anything may act on an AI reading without a person (AIR-12).

Nothing may, until a real evaluation report on real workspace data passes. The synthetic set run here
reports results but is marked as unable to satisfy the gate.
"""

from typing import Any


def auto_snooze_available(report: dict[str, Any] | None, *, test_only_override: bool = False) -> bool:
    if test_only_override:
        return True
    if not report or report.get("synthetic", True):
        return False
    return bool(report.get("passed")) and report.get("labels_covered") == report.get("labels_total")
