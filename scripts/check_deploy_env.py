"""Checks an env file before a staging or production deploy. Usage: check_deploy_env.py FILE [--production].

FILE GUIDE: reads KEY=VALUE lines (no shell evaluation), prints one line per problem, exits 1 if any.
It checks shape and safety, not that a service is reachable: placeholders left in, a weak or short key,
the app role pointing at the owner role, AI fake/none rules, flags that need credentials, hosts and origins.
"""

import sys
from pathlib import Path
from urllib.parse import urlparse

REQUIRED = (
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "CSRF_TRUSTED_ORIGINS",
    "DATABASE_URL",
    "MIGRATION_DATABASE_URL",
    "COLLECTIQ_MASTER_KEY",
    "APP_BASE_URL",
)
SECRETS = ("DJANGO_SECRET_KEY", "COLLECTIQ_MASTER_KEY", "POSTGRES_PASSWORD", "COLLECTIQ_OWNER_PASSWORD", "COLLECTIQ_APP_PASSWORD")
PLACEHOLDER_WORDS = ("change-me", "changeme", "placeholder", "example", "your-", "xxxx")


def load(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
    return values


def problems(env: dict[str, str], production: bool) -> list[str]:
    out = [f"{key} is missing" for key in REQUIRED if not env.get(key)]
    for key in SECRETS:
        value = env.get(key, "")
        if value and any(word in value.lower() for word in PLACEHOLDER_WORDS):
            out.append(f"{key} still looks like a placeholder")
    for key in ("DJANGO_SECRET_KEY", "COLLECTIQ_MASTER_KEY"):
        if env.get(key) and len(env[key]) < 32:
            out.append(f"{key} is shorter than 32 characters")
    app, owner = urlparse(env.get("DATABASE_URL", "")), urlparse(env.get("MIGRATION_DATABASE_URL", ""))
    if app.username and app.username == owner.username:
        out.append("DATABASE_URL uses the owner role; the app must run as the restricted app role")
    if env.get("DJANGO_ENV", "production") != "production":
        out.append("DJANGO_ENV is not production")
    if env.get("AI_PROVIDER", "none") == "fake":
        out.append("AI_PROVIDER=fake is refused in production")
    if env.get("EMAIL_BACKEND_KIND") == "smtp" and not (env.get("SMTP_HOST") and env.get("SMTP_FROM")):
        out.append("EMAIL_BACKEND_KIND=smtp needs SMTP_HOST and SMTP_FROM")
    if env.get("FEATURE_GMAIL_SEND") in ("1", "true", "True"):
        out.append("FEATURE_GMAIL_SEND is on: confirm Google client credentials and OD-11 are settled first")
    if env.get("FEATURE_PAYPAL_WEBHOOK") in ("1", "true", "True"):
        out.append("FEATURE_PAYPAL_WEBHOOK is on: confirm a real merchant check exists; none ships in this build")
    if production:
        if env.get("SCANNER_KIND", "none") == "none":
            out.append("SCANNER_KIND=none: uploads are recorded as not scanned")
        if "localhost" in env.get("DJANGO_ALLOWED_HOSTS", "") or "127.0.0.1" in env.get("DJANGO_ALLOWED_HOSTS", ""):
            out.append("DJANGO_ALLOWED_HOSTS lists a local host")
        if not env.get("APP_BASE_URL", "").startswith("https://"):
            out.append("APP_BASE_URL is not https")
        if any(not origin.startswith("https://") for origin in filter(None, env.get("CSRF_TRUSTED_ORIGINS", "").split(","))):
            out.append("CSRF_TRUSTED_ORIGINS has a non-https origin")
    return out


def main(argv: list[str]) -> int:
    files = [a for a in argv if not a.startswith("--")]
    if len(files) != 1:
        print(__doc__)
        return 2
    found = problems(load(Path(files[0])), production="--production" in argv)
    for line in found:
        print(f"PROBLEM: {line}")
    print("no problems found" if not found else f"{len(found)} problem(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
