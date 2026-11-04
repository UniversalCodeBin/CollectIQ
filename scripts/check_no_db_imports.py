#!/usr/bin/env python3
"""Flag any import of django.db from the API layer or the AI package.

import-linter cannot forbid a subpackage of an external package (it squashes
`django.db` to `django`), so this boundary is checked from the syntax tree.
"""
import argparse
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_API = REPO / "backend" / "collectiq" / "api"
DEFAULT_AI = REPO / "backend" / "collectiq" / "ai"

API_MESSAGE = "The API layer calls services and never touches the ORM"
AI_MESSAGE = "The AI package has no database handle"


def _is_db_module(name: str | None) -> bool:
    return name is not None and (name == "django.db" or name.startswith("django.db."))


def db_import_lines(source: str, filename: str) -> list[int]:
    lines = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        if isinstance(node, ast.Import) and any(_is_db_module(alias.name) for alias in node.names):
            lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            if _is_db_module(node.module):
                lines.append(node.lineno)
            elif node.module == "django" and any(alias.name == "db" for alias in node.names):
                lines.append(node.lineno)
    return sorted(lines)


def scan(root: Path, message: str) -> list[str]:
    problems = []
    for path in sorted(root.rglob("*.py")):
        for line in db_import_lines(path.read_text(encoding="utf-8"), str(path)):
            problems.append(f"{path}:{line}: {message}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", type=Path, default=DEFAULT_API)
    parser.add_argument("--ai", type=Path, default=DEFAULT_AI)
    args = parser.parse_args()
    problems = scan(args.api, API_MESSAGE) + scan(args.ai, AI_MESSAGE)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
