"""The pre-deploy env check refuses placeholders and unsafe settings and accepts a sound production file."""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).parents[3] / "scripts" / "check_deploy_env.py"
_SPEC = importlib.util.spec_from_file_location("check_deploy_env", _PATH)
check = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check)

GOOD = {
    "DJANGO_ENV": "production",
    "DJANGO_SECRET_KEY": "k" * 50,
    "COLLECTIQ_MASTER_KEY": "m" * 50,
    "DJANGO_ALLOWED_HOSTS": "app.corp.test",
    "CSRF_TRUSTED_ORIGINS": "https://app.corp.test",
    "DATABASE_URL": "postgres://collectiq_app:pw@db:5432/collectiq",  # pragma: allowlist secret
    "MIGRATION_DATABASE_URL": "postgres://collectiq_owner:pw2@db:5432/collectiq",  # pragma: allowlist secret
    "APP_BASE_URL": "https://app.corp.test",
    "SCANNER_KIND": "clamav",
    "AI_PROVIDER": "none",
}


def test_a_sound_production_file_passes() -> None:
    assert check.problems(GOOD, production=True) == []


def test_unsafe_values_are_each_reported() -> None:
    bad = {
        **GOOD,
        "DJANGO_SECRET_KEY": "change-me-" + "x" * 40,  # pragma: allowlist secret
        "DATABASE_URL": GOOD["MIGRATION_DATABASE_URL"],
        "AI_PROVIDER": "fake",
        "FEATURE_PAYPAL_WEBHOOK": "true",
        "APP_BASE_URL": "http://app.corp.test",
    }
    text = " | ".join(check.problems(bad, production=True))
    for part in ("placeholder", "owner role", "AI_PROVIDER=fake", "FEATURE_PAYPAL_WEBHOOK", "not https"):
        assert part in text
