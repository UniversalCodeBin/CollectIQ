"""The quality gate itself is under test: each check must reject a seeded violation."""
import importlib.util
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
SCRIPTS = REPO / "scripts"


def _lint_imports() -> subprocess.CompletedProcess:
    # The console script, not `-m importlinter.cli`: that module has no __main__ guard,
    # so it exits 0 without checking anything and every boundary test would pass falsely.
    return subprocess.run(
        [str(Path(sys.executable).parent / "lint-imports"), "--no-cache"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(BACKEND), "PATH": "/usr/bin:/bin"},
    )


def _seed(relative: str, source: str) -> Path:
    path = BACKEND / "collectiq" / relative
    path.write_text(source)
    return path


def test_clean_tree_keeps_every_boundary():
    result = _lint_imports()
    assert result.returncode == 0, result.stdout + result.stderr


def test_seeded_boundary_violation_fails():
    seeded = _seed("ai/_seeded_violation.py", "import collectiq.evidence.models  # noqa\n")
    try:
        result = _lint_imports()
    finally:
        seeded.unlink()
    assert result.returncode != 0
    assert "AI imports no domain module" in result.stdout


def test_seeded_api_model_import_fails():
    seeded = _seed("api/_seeded_violation.py", "import collectiq.invoices.models  # noqa\n")
    try:
        result = _lint_imports()
    finally:
        seeded.unlink()
    assert result.returncode != 0
    assert "never touches the ORM" in result.stdout


def _db_import_check(api: Path, ai: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "check_no_db_imports.py"), "--api", str(api), "--ai", str(ai)],
        capture_output=True,
        text=True,
    )


def test_api_importing_django_db_is_flagged(tmp_path):
    api, ai = tmp_path / "api", tmp_path / "ai"
    api.mkdir()
    ai.mkdir()
    (api / "views.py").write_text("x = 1\nfrom django.db import connection\n")
    result = _db_import_check(api, ai)
    assert result.returncode != 0
    assert "views.py:2" in result.stdout and "never touches the ORM" in result.stdout


def test_ai_importing_django_db_submodule_is_flagged(tmp_path):
    api, ai = tmp_path / "api", tmp_path / "ai"
    api.mkdir()
    ai.mkdir()
    (ai / "gateway.py").write_text("import django.db.models as m\n")
    result = _db_import_check(api, ai)
    assert result.returncode != 0
    assert "gateway.py:1" in result.stdout and "no database handle" in result.stdout


def test_real_tree_has_no_db_import_in_api_or_ai():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "check_no_db_imports.py")], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout


def test_seeded_foreign_write_to_ledger_models_fails():
    seeded = _seed("comms/_seeded_violation.py", "import collectiq.evidence.models  # noqa\n")
    try:
        result = _lint_imports()
    finally:
        seeded.unlink()
    assert result.returncode != 0
    assert "Only evidence may write" in result.stdout


def _float_check(target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "check_no_float_money.py"), str(target)],
        capture_output=True,
        text=True,
    )


def test_float_in_money_path_is_flagged(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("def total(amount):\n    return float(amount) * 1.5\n")
    result = _float_check(tmp_path)
    assert result.returncode != 0
    assert "bad.py:2" in result.stdout


def test_float_annotation_and_field_are_flagged(tmp_path):
    (tmp_path / "a.py").write_text("amount: float = 0\n")
    (tmp_path / "b.py").write_text("from django.db import models\nx = models.FloatField()\n")
    result = _float_check(tmp_path)
    assert result.returncode != 0
    assert "a.py:1" in result.stdout and "b.py:2" in result.stdout


def test_integer_money_passes(tmp_path):
    (tmp_path / "ok.py").write_text("def total(amount_minor: int) -> int:\n    return amount_minor * 2\n")
    assert _float_check(tmp_path).returncode == 0


def _load_check_openapi():
    spec = importlib.util.spec_from_file_location("check_openapi", SCRIPTS / "check_openapi.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_endpoint_with_no_owner_is_flagged():
    check = _load_check_openapi()
    problems = check.unaccounted(
        contract={"E001", "E002", "E003", "E004"},
        implemented={"E001"},
        status={"planned": {"E002": 7}, "deferred": {"E003": "needs Gmail access"}},
        final=False,
    )
    assert problems == ["E004: not implemented, planned or deferred"]


def test_planned_endpoint_fails_the_final_gate_but_deferred_with_reason_passes():
    check = _load_check_openapi()
    problems = check.unaccounted(
        contract={"E002", "E003"},
        implemented=set(),
        status={"planned": {"E002": 7}, "deferred": {"E003": "needs Gmail access"}},
        final=True,
    )
    assert problems == ["E002: still planned at the final gate"]


def test_deferred_without_a_reason_is_flagged():
    check = _load_check_openapi()
    problems = check.unaccounted(
        contract={"E003"}, implemented=set(), status={"planned": {}, "deferred": {"E003": ""}}, final=False
    )
    assert problems == ["E003: deferred without a reason"]


def _load_run_check():
    spec = importlib.util.spec_from_file_location("run_check", SCRIPTS / "run_check.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_check"] = module
    spec.loader.exec_module(module)
    return module


def test_gate_runner_fails_when_any_step_fails(tmp_path):
    run_check = _load_run_check()
    steps = [
        run_check.Step("passes", [sys.executable, "-c", "pass"], tmp_path),
        run_check.Step("fails", [sys.executable, "-c", "raise SystemExit(3)"], tmp_path),
        run_check.Step("still runs", [sys.executable, "-c", "pass"], tmp_path),
    ]
    failed, ran = run_check.run_steps(steps, quiet=True)
    assert [step.name for step in failed] == ["fails"]
    assert ran == 3  # one failure must not hide the others


def test_gate_runner_treats_a_missing_tool_as_failure(tmp_path):
    run_check = _load_run_check()
    failed, _ = run_check.run_steps(
        [run_check.Step("missing", ["definitely-not-a-real-binary"], tmp_path)], quiet=True
    )
    assert [step.name for step in failed] == ["missing"]


def test_gate_lists_every_required_check():
    names = " ".join(step.name for step in _load_run_check().all_steps())
    for required in (
        "ruff", "mypy", "import-linter", "no-db-imports", "float", "detect-secrets",
        "openapi", "traceability", "eslint", "tsc", "pytest", "vitest",
    ):
        assert required in names, required
