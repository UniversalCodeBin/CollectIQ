#!/usr/bin/env python3
"""The committed schema matches the code, and every contract endpoint has an owner.

An endpoint in `CollectIQ_API_Contracts.yaml` must be implemented (its view carries
`x-endpoint-id`), planned for a task, or deferred with a reason. `--final` removes "planned"
as an answer, so the last milestone cannot end with an endpoint nobody decided on.
"""
import argparse
import difflib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
CONTRACT = REPO / "CollectIQ_API_Contracts.yaml"
GENERATED = REPO / "docs" / "api" / "openapi.generated.yaml"
STATUS = REPO / "docs" / "api" / "endpoint-status.yaml"
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}


def unaccounted(contract: set[str], implemented: set[str], status: dict, final: bool) -> list[str]:
    planned = status.get("planned") or {}
    deferred = status.get("deferred") or {}
    problems = []
    for endpoint in sorted(contract - implemented):
        if endpoint in deferred:
            if not str(deferred[endpoint] or "").strip():
                problems.append(f"{endpoint}: deferred without a reason")
        elif endpoint in planned:
            if final:
                problems.append(f"{endpoint}: still planned at the final gate")
        else:
            problems.append(f"{endpoint}: not implemented, planned or deferred")
    return problems


def endpoint_ids(schema: dict) -> set[str]:
    found = set()
    for operations in (schema.get("paths") or {}).values():
        for method, operation in operations.items():
            if method in HTTP_METHODS and "x-endpoint-id" in operation:
                found.add(operation["x-endpoint-id"])
    return found


def regenerate() -> str:
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "openapi.yaml"
        result = subprocess.run(
            [sys.executable, "manage.py", "spectacular", "--file", str(target), "--validate"],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "collectiq.settings.test"},
        )
        if result.returncode != 0:
            raise SystemExit(f"schema generation failed:\n{result.stdout}{result.stderr}")
        return target.read_text(encoding="utf-8")


def main() -> int:
    import yaml

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", action="store_true", help="planned endpoints fail the check")
    args = parser.parse_args()

    problems = []
    fresh = regenerate()
    committed = GENERATED.read_text(encoding="utf-8") if GENERATED.exists() else ""
    if fresh != committed:
        diff = difflib.unified_diff(
            committed.splitlines(), fresh.splitlines(), "committed", "regenerated", lineterm="", n=1
        )
        print("\n".join(list(diff)[:40]))
        problems.append(f"{GENERATED.relative_to(REPO)} is out of date: run `make openapi`")

    contract = endpoint_ids(yaml.safe_load(CONTRACT.read_text(encoding="utf-8")))
    implemented = endpoint_ids(yaml.safe_load(fresh))
    status = yaml.safe_load(STATUS.read_text(encoding="utf-8"))
    problems += unaccounted(contract, implemented, status, final=args.final)
    problems += [f"{endpoint}: implemented but not in the contract" for endpoint in sorted(implemented - contract)]

    for problem in problems:
        print(problem)
    if not problems:
        print(f"{len(implemented)} of {len(contract)} contract endpoints implemented; the rest have an owner")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
