#!/usr/bin/env python3
"""Rejects compliance, certification, accuracy and uptime claims in UI strings and docs.

A line passes when it states a negative ("no SOC 2", "not tamper-proof", "never") or when it names the
policy-version snapshot rows, which are immutable as a data design and say nothing about the audit log.
Run from the repo root: `python3 scripts/check_claims.py [paths...]`.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

FORBIDDEN = re.compile(
    r"\bSOC[ -]?2\b|\bISO[ -]?27001\b|\bPCI([ -]DSS)?\b|\bDPDP\b|\bGDPR\b|\bHIPAA\b"
    r"|tamper[- ]?(proof|resistant|evident)|\bimmutable\b|bank[- ]grade|military[- ]grade"
    r"|\b\d{2,3}(\.\d+)?\s?%\s*(accura|uptime|available|confiden)|\b(accuracy|uptime) (of|guarantee|sla)\b"
    r"|\bguaranteed (accura|uptime|delivery)|\bfully compliant\b|\bcertified\b",
    re.IGNORECASE,
)
NEGATIVE = re.compile(
    r"\b(no|not|never|nor|without|isn't|aren't|doesn't|don't|cannot|can't|refus\w*|reject\w*|forbid\w*"
    r"|prohibit\w*)\b",
    re.IGNORECASE,
)
ALLOWED = re.compile(r"immutable (policy )?versions?|immutable snapshot|policy[_ ]versions?", re.IGNORECASE)
SKIP_PARTS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "stitch_collectiq_receivables_copilot",
    "var",
    "dist",
}
SKIP_NAMES = {
    "package-lock.json",
    "uv.lock",
    "check_claims.py",
    "test_check_claims.py",
    "openapi.generated.yaml",
}
SUFFIXES = {".ts", ".tsx", ".py", ".md", ".html", ".yaml", ".yml", ".json"}
ROOTS = ["frontend/src", "backend/collectiq", "docs", "README.md", "deploy"]
SKIP_FILES = {"CollectIQ_Post_Implementation_Audit.md"}


def violations_in(text: str) -> list[tuple[int, str]]:
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if FORBIDDEN.search(line) and not NEGATIVE.search(line) and not ALLOWED.search(line):
            found.append((number, line.strip()[:140]))
    return found


def files(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for item in paths:
        path = (REPO / item) if not Path(item).is_absolute() else Path(item)
        candidates = [path] if path.is_file() else sorted(path.rglob("*")) if path.is_dir() else []
        for candidate in candidates:
            if (
                candidate.is_file()
                and candidate.suffix in SUFFIXES
                and candidate.name not in SKIP_NAMES | SKIP_FILES
                and not SKIP_PARTS & set(candidate.parts)
            ):
                out.append(candidate)
    return out


def main(argv: list[str]) -> int:
    failures = 0
    for path in files(argv or ROOTS):
        for number, line in violations_in(path.read_text(encoding="utf-8", errors="ignore")):
            print(f"{path.relative_to(REPO)}:{number}: forbidden claim: {line}")
            failures += 1
    print(f"claims check: {failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
