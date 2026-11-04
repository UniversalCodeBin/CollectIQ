import os
from pathlib import Path

from dotenv import load_dotenv

# Read .env first so a developer's real database passwords win over the CI placeholders below.
load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-a-secret")  # pragma: allowlist secret
os.environ.setdefault(
    "COLLECTIQ_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="  # pragma: allowlist secret
)
os.environ.setdefault(
    "DATABASE_URL",
    "postgres://collectiq_app:unset@127.0.0.1:54329/collectiq_test",  # pragma: allowlist secret
)
os.environ.setdefault(
    "MIGRATION_DATABASE_URL",
    "postgres://collectiq_owner:unset@127.0.0.1:54329/collectiq_test",  # pragma: allowlist secret
)

from .base import *  # noqa: E402, F403
from .base import BASE_DIR, DATABASES  # noqa: E402

DJANGO_ENV = "test"
DATABASES["default"]["NAME"] = "collectiq_test"
DATABASES["default"]["CONN_MAX_AGE"] = 0
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only; never outside test
EMAIL_BACKEND_KIND = "memory"
COLLECTIQ_STORAGE_DIR = BASE_DIR / ".test-storage"
AI_PROVIDER = "none"
AUTH_IP_RATE_LIMIT = 10_000  # tests share one address; the limit has its own test
