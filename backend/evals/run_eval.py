"""Runs the synthetic set and prints a report. The report is marked synthetic; see README.md."""

import json
from pathlib import Path

from collectiq.ai.eval_gate import auto_snooze_available


def build_report(rows: list[dict[str, str]], predictions: list[str]) -> dict[str, object]:
    correct = sum(1 for row, got in zip(rows, predictions, strict=True) if row["label"] == got)
    labels = {row["label"] for row in rows}
    return {
        "synthetic": True,
        "n": len(rows),
        "correct": correct,
        "passed": False,
        "labels_covered": len(labels),
        "labels_total": len(labels),
    }


if __name__ == "__main__":
    data = json.loads((Path(__file__).parent / "synthetic_set.json").read_text())
    report = build_report(data, [row["label"] for row in data])
    print(json.dumps({**report, "auto_snooze_available": auto_snooze_available(report)}, indent=2))
