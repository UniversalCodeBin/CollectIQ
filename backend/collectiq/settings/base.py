"""Shared settings. Values come from the environment; nothing secret lives here."""
import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BASE_DIR.parent
load_dotenv(REPO_ROOT / ".env", override=False)


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"{name} is not set. Run `make env`, or see .env.example.")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


DJANGO_ENV = env("DJANGO_ENV", "local")
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
_HOSTS = env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
ALLOWED_HOSTS = [h.strip() for h in _HOSTS.split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "collectiq.platform",
    "collectiq.audit",
    "collectiq.identity",
    "collectiq.tenancy",
    "collectiq.policy",
    "collectiq.invoices",
    "collectiq.evidence",
    "collectiq.cases",
    "collectiq.conversations",
    "collectiq.comms",
    "collectiq.integrations",
    "collectiq.notifications",
    "collectiq.settings_privacy",
]

MIDDLEWARE = [
    "collectiq.platform.middleware.CorrelationIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "collectiq.platform.middleware.UploadLimitMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "collectiq.api.urls"
WSGI_APPLICATION = None
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"

_db_role = os.environ.get("DJANGO_DB_ROLE", "app")
_db_url = env("MIGRATION_DATABASE_URL") if _db_role == "owner" else env("DATABASE_URL")
DATABASES = {"default": dj_database_url.parse(_db_url, conn_max_age=60)}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]

# Sessions: an opaque server-side token in an HttpOnly cookie. See collectiq.identity.session.
SESSION_COOKIE_NAME = "collectiq_session"
SESSION_ABSOLUTE_TTL = timedelta(hours=12)  # FR-155
SESSION_IDLE_SENSITIVE = timedelta(minutes=30)  # FR-155
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_NAME = "collectiq_csrf"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads it and echoes it in X-CSRFToken

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "collectiq.platform.problem.problem_exception_handler",
}

# One handler, one formatter: every route ends in the scrubber (INV-12, SEC-12).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"scrubbed": {"()": "collectiq.platform.logging.ScrubbingJsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "scrubbed"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "CollectIQ API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

COLLECTIQ_MASTER_KEY = env("COLLECTIQ_MASTER_KEY")
COLLECTIQ_STORAGE_DIR = Path(env("COLLECTIQ_STORAGE_DIR", "var/storage"))
if not COLLECTIQ_STORAGE_DIR.is_absolute():
    COLLECTIQ_STORAGE_DIR = REPO_ROOT / COLLECTIQ_STORAGE_DIR
EMAIL_BACKEND_KIND = env("EMAIL_BACKEND_KIND", "file")
EMAIL_FILE_PATH = Path(env("EMAIL_FILE_PATH", "var/mail"))
if not EMAIL_FILE_PATH.is_absolute():
    EMAIL_FILE_PATH = REPO_ROOT / EMAIL_FILE_PATH

AI_PROVIDER = env("AI_PROVIDER", "none")
AI_KILL_SWITCH = env_bool("AI_KILL_SWITCH")
FEATURE_PDF_EXTRACTION = env_bool("FEATURE_PDF_EXTRACTION")
FEATURE_GMAIL_SEND = env_bool("FEATURE_GMAIL_SEND")
FEATURE_PAYPAL_WEBHOOK = env_bool("FEATURE_PAYPAL_WEBHOOK")

# Provisional defaults (OD-16, OD-17). Workspace policy overrides these where the spec allows it.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 10_000
# The upload plus room for the multipart envelope; a larger declared body is refused unread.
COLLECTIQ_MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024
IDEMPOTENCY_TTL = timedelta(hours=24)

# [PROP] Configurable defaults for the auth limits. The specs fix the behavior, not these values.
AUTH_LOCKOUT_THRESHOLD = 5
AUTH_LOCKOUT_SECONDS = 900
AUTH_IP_RATE_LIMIT = 60  # per minute, per address
AUTH_EMAIL_HOURLY_LIMIT = 5  # per address; over it the request still succeeds and sends nothing
EMAIL_VERIFY_TTL = timedelta(hours=24)
PASSWORD_RESET_TTL = timedelta(hours=1)
INVITATION_TTL = timedelta(days=7)
APP_BASE_URL = env("APP_BASE_URL", "http://localhost:5173")
