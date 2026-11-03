#!/usr/bin/env python3
"""Create .env from .env.example with random local secrets. Never overwrites an existing .env."""
import base64
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    target = ROOT / ".env"
    if target.exists():
        print(".env already exists; leaving it alone")
        return 0
    owner_pw = secrets.token_urlsafe(24)
    app_pw = secrets.token_urlsafe(24)
    values = {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
        "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
        "COLLECTIQ_OWNER_PASSWORD": owner_pw,
        "COLLECTIQ_APP_PASSWORD": app_pw,
        "DATABASE_URL": f"postgres://collectiq_app:{app_pw}@127.0.0.1:54329/collectiq",
        "MIGRATION_DATABASE_URL": f"postgres://collectiq_owner:{owner_pw}@127.0.0.1:54329/collectiq",
        "COLLECTIQ_MASTER_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
    }
    lines = []
    for line in (ROOT / ".env.example").read_text().splitlines():
        key = line.split("=", 1)[0]
        lines.append(f"{key}={values[key]}" if key in values and not line.startswith("#") else line)
    target.write_text("\n".join(lines) + "\n")
    target.chmod(0o600)
    print("wrote .env with random local secrets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
