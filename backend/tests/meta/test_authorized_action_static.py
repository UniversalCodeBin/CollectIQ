"""TS-021: nothing outside the policy package can mint an AuthorizedAction or switch a decision on."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "collectiq"
POLICY = ROOT / "policy"


def _sources() -> list[tuple[Path, ast.AST]]:
    return [(p, ast.parse(p.read_text())) for p in ROOT.rglob("*.py") if "migrations" not in p.parts]


def _outside_policy() -> list[tuple[Path, ast.AST]]:
    return [(p, t) for p, t in _sources() if POLICY not in p.parents]


def test_only_the_policy_package_builds_an_authorized_action() -> None:
    for path, tree in _outside_policy():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                assert name not in {"AuthorizedAction", "_mint"}, f"{path} builds an AuthorizedAction"


def test_only_the_policy_service_mints() -> None:
    minting = [
        p
        for p, t in _sources()
        if any(isinstance(n, ast.Attribute) and n.attr == "_mint" for n in ast.walk(t))
    ]
    assert minting == [POLICY / "service.py"]


def test_nothing_outside_policy_writes_decision_state() -> None:
    for path, _ in _outside_policy():
        text = path.read_text().lower()
        assert "update policy_decisions" not in text and "insert into policy_decisions" not in text, path
        assert "update approval_requests" not in text and "insert into approval_requests" not in text, path
