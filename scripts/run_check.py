#!/usr/bin/env python3
"""`make check`: the local quality gate.

Every step runs even after one fails, so a single run reports everything that is wrong. A tool
that is not installed counts as a failure; a gate that cannot run has not passed.

Suites that need PostgreSQL (`tests/rls`, `tests/integration`, ...) run under `make test`.
"""
import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"


@dataclass(frozen=True)
class Step:
    name: str
    argv: list[str]
    cwd: Path


def _tracked_files() -> list[str]:
    """Everything git would commit, which is what a secret scan has to cover."""
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    skip_names = {"package-lock.json", "uv.lock"}
    return [
        name
        for name in result.stdout.splitlines()
        if Path(name).name not in skip_names
        and not name.startswith("stitch_collectiq_receivables_copilot/")
        and (REPO / name).is_file()
    ]


def all_steps() -> list[Step]:
    uv_run = ["uv", "run", "--quiet"]
    return [
        Step("ruff", [*uv_run, "ruff", "check", "."], BACKEND),
        Step("mypy", [*uv_run, "mypy", "collectiq"], BACKEND),
        Step("import-linter", [*uv_run, "lint-imports"], BACKEND),
        Step("no-db-imports", [*uv_run, "python", "../scripts/check_no_db_imports.py"], BACKEND),
        Step("float money check", [*uv_run, "python", "../scripts/check_no_float_money.py"], BACKEND),
        Step(
            "detect-secrets",
            [*uv_run, "--project", "backend", "detect-secrets-hook", "--baseline", ".secrets.baseline",
             *_tracked_files()],
            REPO,
        ),
        Step("openapi diff", [*uv_run, "python", "../scripts/check_openapi.py"], BACKEND),
        Step("traceability", [*uv_run, "python", "../scripts/check_traceability.py"], BACKEND),
        Step("eslint", ["npm", "run", "--silent", "lint"], FRONTEND),
        Step("tsc", ["npm", "run", "--silent", "typecheck"], FRONTEND),
        Step("pytest (no database)", [*uv_run, "pytest", "tests/unit", "tests/meta", "-q"], BACKEND),
        Step("vitest", ["npm", "run", "--silent", "test"], FRONTEND),
    ]


def _run(step: Step, quiet: bool) -> int:
    try:
        result = subprocess.run(step.argv, cwd=step.cwd, capture_output=True, text=True)
    except OSError as error:
        if not quiet:
            print(f"    could not start {step.argv[0]}: {error}")
        return 127
    if result.returncode != 0 and not quiet:
        print(result.stdout + result.stderr)
    return result.returncode


def run_steps(steps: list[Step], quiet: bool = False) -> tuple[list[Step], int]:
    failed = []
    for step in steps:
        code = _run(step, quiet)
        if not quiet:
            print(f"{'ok  ' if code == 0 else 'FAIL'} {step.name}", flush=True)
        if code != 0:
            failed.append(step)
    return failed, len(steps)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="run only steps whose name contains this text")
    args = parser.parse_args()
    steps = [s for s in all_steps() if not args.only or args.only in s.name]
    failed, ran = run_steps(steps)
    print(f"\n{ran - len(failed)} of {ran} checks passed")
    if failed:
        print("failed: " + ", ".join(step.name for step in failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
