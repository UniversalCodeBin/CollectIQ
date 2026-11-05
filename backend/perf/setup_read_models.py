"""Creates a throwaway user and workspace holding 5,000 sample invoices, for the read-model benchmark.

Run: DJANGO_ENV=local uv run python manage.py shell < perf/setup_read_models.py
Prints WORKSPACE=<id>. Local databases only; the sample command refuses production.
"""

import os
import uuid

import psycopg
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from rest_framework.test import APIClient

EMAIL = f"perf-{uuid.uuid4().hex[:8]}@example.test"
PASSWORD = "perf-password-for-local-benchmark"  # pragma: allowlist secret

with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"], autocommit=True) as owner:
    owner.execute(
        "INSERT INTO users (email, password_hash, status, email_verified_at)"
        " VALUES (%s, %s, 'ACTIVE', now())",
        [EMAIL, make_password(PASSWORD)],
    )
client = APIClient(SERVER_NAME="127.0.0.1")
login = client.post("/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD}, format="json")
assert login.status_code == 200
made = client.post(
    "/api/v1/workspaces",
    {"name": "Perf Studio", "country": "IN", "timezone": "Asia/Kolkata", "default_currency": "INR"},
    format="json",
    HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
)
assert made.status_code == 201, made.content
workspace = made.json()["id"]
call_command("seed_sample", workspace=workspace, invoices=5000)
print(f"WORKSPACE={workspace}\nEMAIL={EMAIL}\nPASSWORD={PASSWORD}")
