#!/usr/bin/env python3
"""F-9: no floating point in money paths.

Flags `float(...)`, float literals, `float` annotations and `FloatField` in Python, and
`parseFloat(` in the frontend. A line that genuinely has nothing to do with money (a timeout,
for instance) can carry `# float-ok: <reason>`.
"""
import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COLLECTIQ = REPO / "backend" / "collectiq"
DEFAULT_PATHS = [
    COLLECTIQ / "evidence",
    COLLECTIQ / "invoices",
    COLLECTIQ / "comms",
    COLLECTIQ / "cases",
    COLLECTIQ / "policy",
    COLLECTIQ / "api",
    COLLECTIQ / "platform" / "money.py",
    REPO / "frontend" / "src",
]
SUPPRESSION = re.compile(r"#\s*float-ok:\s*\S")
FRONTEND_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}
PARSE_FLOAT = re.compile(r"\bparseFloat\s*\(|\bNumber\.parseFloat\s*\(")


def _annotation_is_float(node: ast.expr | None) -> bool:
    return node is not None and any(
        isinstance(part, ast.Name) and part.id == "float" for part in ast.walk(node)
    )


def python_float_lines(source: str, filename: str) -> list[int]:
    lines: set[int] = set()
    for node in ast.walk(ast.parse(source, filename=filename)):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in {"float", "FloatField"}:
                lines.add(node.lineno)
            elif isinstance(func, ast.Attribute) and func.attr == "FloatField":
                lines.add(node.lineno)
        elif isinstance(node, ast.Constant) and isinstance(node.value, float):
            lines.add(node.lineno)
        elif isinstance(node, ast.AnnAssign) and _annotation_is_float(node.annotation):
            lines.add(node.lineno)
        elif isinstance(node, ast.arg) and _annotation_is_float(node.annotation):
            lines.add(node.lineno)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _annotation_is_float(node.returns):
            lines.add(node.lineno)
    source_lines = source.splitlines()
    return sorted(line for line in lines if not SUPPRESSION.search(source_lines[line - 1]))


def frontend_float_lines(source: str) -> list[int]:
    return [
        number
        for number, line in enumerate(source.splitlines(), start=1)
        if PARSE_FLOAT.search(line) and "float-ok:" not in line
    ]


def _files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(path for path in root.rglob("*") if path.is_file())


def scan(root: Path) -> list[str]:
    problems = []
    for path in _files(root):
        if path.suffix == ".py":
            found = python_float_lines(path.read_text(encoding="utf-8"), str(path))
        elif path.suffix in FRONTEND_SUFFIXES:
            found = frontend_float_lines(path.read_text(encoding="utf-8"))
        else:
            continue
        problems.extend(f"{path}:{line}: floating point in a money path" for line in found)
    return problems


def main(argv: list[str]) -> int:
    roots = [Path(arg) for arg in argv] or DEFAULT_PATHS
    problems = [problem for root in roots if root.exists() for problem in scan(root)]
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
