#!/usr/bin/env python3
"""Fail if the traceability matrix hides what has not been decided yet.

Checks that the matrix keeps one row per requirement, that a stray comma has not shifted a row
(a shifted row shows up as an invalid Priority), that every P0 row has a requirement-level mapping
and an owning task, and that every PRD scenario TS-001...TS-035 is owned by a task or deferred with
a stated reason.
"""
import csv
import io
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MATRIX = REPO / "CollectIQ_Requirements_Traceability.csv"
EXPECTED_ROWS = 221
LAST_TASK = 40

VALID_PRIORITIES = {
    "P0",
    "P0 (pre-pilot)",
    "P0 (conditional)",
    "P0 (shell) / P1 (Gmail, PayPal)",
    "P0 / P1",
    "P0 gate",
    "P1",
    "P1 (gated)",
    "P1 (when integrations land; vault design P0)",
    "P2",
}

# Who proves each PRD scenario. Where two tasks share one, the first owns the scenario and the note
# names the other path.
SCENARIOS: dict[str, dict[str, str]] = {
    "TS-001": {"owner": "T24"},
    "TS-002": {"owner": "T11"},
    "TS-003": {"owner": "T31"},
    "TS-004": {"owner": "T18"},
    "TS-005": {"owner": "T23", "note": "AI path in T30"},
    "TS-006": {"owner": "T22"},
    "TS-007": {"owner": "T30"},
    "TS-008": {"owner": "T30"},
    "TS-009": {"owner": "T23"},
    "TS-010": {"owner": "T23"},
    "TS-011": {"owner": "T19", "note": "draft amount in T24"},
    "TS-012": {"owner": "T19", "note": "state sequence in T17"},
    "TS-013": {"owner": "T19"},
    "TS-014": {"owner": "T24", "note": "webhook dedupe in T34"},
    "TS-015": {"owner": "T30"},
    "TS-016": {"owner": "T34"},
    "TS-017": {"owner": "T30"},
    "TS-018": {"owner": "T34"},
    "TS-019": {
        "owner": "Deferred",
        "reason": "Needs Gmail mailbox monitoring (E096), deferred under plan A4 and OD-11.",
    },
    "TS-020": {"owner": "T30"},
    "TS-021": {"owner": "T21"},
    "TS-022": {"owner": "T36"},
    "TS-023": {"owner": "T37"},
    "TS-024": {"owner": "T7"},
    "TS-025": {"owner": "T34"},
    "TS-026": {
        "owner": "Deferred",
        "reason": "Needs Gmail mailbox monitoring (E096), deferred under plan A4 and OD-11.",
    },
    "TS-027": {"owner": "T24"},
    "TS-028": {"owner": "T29", "note": "UI path in T36"},
    "TS-029": {"owner": "T30"},
    "TS-030": {"owner": "T30"},
    "TS-031": {"owner": "T16"},
    "TS-032": {"owner": "T15"},
    "TS-033": {"owner": "T23"},
    "TS-034": {"owner": "T22"},
    "TS-035": {"owner": "T23"},
}


def read_rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text, newline="")))


def _is_task(owner: str) -> bool:
    match = re.fullmatch(r"T([1-9]\d*)", owner)
    return match is not None and int(match.group(1)) <= LAST_TASK


def _row_problems(row: dict) -> list[str]:
    requirement = row.get("Requirement ID", "?")
    priority = (row.get("Priority") or "").strip()
    if priority not in VALID_PRIORITIES:
        return [f"{requirement}: Priority {priority[:40]!r} is not valid; a comma may have shifted this row"]
    if not priority.startswith("P0"):
        return []
    problems = []
    if "RANGE-LEVEL" in (row.get("Mapping granularity") or ""):
        problems.append(f"{requirement}: P0 row is still RANGE-LEVEL")
    owner = (row.get("Owner task") or "").strip()
    owners = [part.strip() for part in owner.split(",") if part.strip()]
    if not owners or not all(_is_task(part) for part in owners):
        problems.append(f"{requirement}: Owner task {owner!r} does not name a real task")
    return problems


def _scenario_problems(scenarios: dict) -> list[str]:
    problems = []
    for number in range(1, 36):
        scenario_id = f"TS-{number:03d}"
        scenario = scenarios.get(scenario_id)
        if scenario is None:
            problems.append(f"{scenario_id}: no owner recorded")
        elif scenario.get("owner") == "Deferred":
            if not (scenario.get("reason") or "").strip():
                problems.append(f"{scenario_id}: deferred without a reason")
        elif not _is_task(scenario.get("owner", "")):
            problems.append(f"{scenario_id}: owner {scenario.get('owner')!r} is not a real task")
    return problems


def find_problems(rows: list[dict], scenarios: dict, expected_rows: int) -> list[str]:
    problems = []
    if len(rows) != expected_rows:
        problems.append(f"matrix has {len(rows)} rows, expected {expected_rows}")
    for row in rows:
        problems.extend(_row_problems(row))
    problems.extend(_scenario_problems(scenarios))
    return problems


def main() -> int:
    text = MATRIX.read_text(encoding="utf-8-sig")
    problems = find_problems(read_rows(text), SCENARIOS, EXPECTED_ROWS)
    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} traceability problems")
        return 1
    print(f"traceability ok: {EXPECTED_ROWS} rows, TS-001...TS-035 accounted for")
    return 0


if __name__ == "__main__":
    sys.exit(main())
