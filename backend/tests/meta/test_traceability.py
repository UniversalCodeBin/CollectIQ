"""The traceability gate rejects a matrix that hides what is not decided yet."""
import csv
import importlib.util
import io
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "check_traceability.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_traceability", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COLUMNS = [
    "Requirement ID", "Source", "Requirement (PRD v0.1, abbreviated)", "Priority",
    "Acceptance criteria (PRD)", "Module(s)", "Screen(s)", "API endpoint IDs", "Data entities",
    "Policy gates", "Test IDs", "Mapping granularity", "Implementation status", "Notes",
    "Owner task",
]


def _row(**overrides) -> dict:
    row = dict.fromkeys(COLUMNS, "x")
    row.update({
        "Requirement ID": "FR-001",
        "Priority": "P0",
        "Mapping granularity": "REQUIREMENT-LEVEL",
        "Owner task": "T11",
        "Test IDs": "TS-002",
    })
    row.update(overrides)
    return row


def _scenarios(owner: str = "T1") -> dict:
    return {f"TS-{n:03d}": {"owner": owner} for n in range(1, 36)}


def _problems(rows, scenarios=None, expected=1):
    return _load().find_problems(rows, scenarios or _scenarios(), expected_rows=expected)


def test_row_count_is_enforced():
    assert any("rows" in p for p in _problems([_row()], expected=221))


def test_unknown_priority_rejected():
    assert any("Priority" in p for p in _problems([_row(Priority="sometime")]))


def test_shifted_row_is_rejected_as_a_bad_priority():
    """A comma in an unquoted field pushes text into the Priority column."""
    shifted = _row(Priority="the rest of the requirement text")
    assert any("FR-001" in p and "Priority" in p for p in _problems([shifted]))


@pytest.mark.parametrize("priority", ["P0", "P0 (pre-pilot)", "P0 (conditional)", "P0 gate", "P0 / P1"])
def test_range_level_on_p0_rejected(priority):
    row = _row(Priority=priority, **{"Mapping granularity": "RANGE-LEVEL (refine in M0)"})
    assert any("RANGE-LEVEL" in p for p in _problems([row]))


def test_range_level_on_p1_allowed():
    row = _row(Priority="P1", **{"Mapping granularity": "RANGE-LEVEL (refine in M0)"})
    assert _problems([row]) == []


def test_p0_without_owner_rejected():
    assert any("Owner" in p for p in _problems([_row(**{"Owner task": ""})]))


def test_scenario_missing_rejected():
    scenarios = _scenarios()
    del scenarios["TS-007"]
    assert any("TS-007" in p for p in _problems([_row()], scenarios))


def test_deferred_scenario_needs_reason():
    scenarios = _scenarios()
    scenarios["TS-019"] = {"owner": "Deferred"}
    assert any("TS-019" in p for p in _problems([_row()], scenarios))


def test_deferred_scenario_with_reason_passes():
    scenarios = _scenarios()
    scenarios["TS-019"] = {"owner": "Deferred", "reason": "needs a real mailbox"}
    assert _problems([_row()], scenarios) == []


def test_scenario_owner_must_be_a_real_task():
    scenarios = _scenarios()
    scenarios["TS-001"] = {"owner": "T99"}
    assert any("TS-001" in p for p in _problems([_row()], scenarios))


def test_csv_reader_keeps_a_row_per_requirement():
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(_row())
    assert len(_load().read_rows(text.getvalue())) == 1
