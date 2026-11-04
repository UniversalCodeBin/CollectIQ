"""Shared by the identity, tenancy and authorization tests. Everything here is synthetic."""

import re
import uuid
from typing import Any

import psycopg
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from rest_framework.test import APIClient

from collectiq.platform import email as email_port

API = "/api/v1"
PASS = "correct-horse-battery-staple"
OTHER_PASS = "another-long-enough-phrase"
WORKSPACE_BODY = {
    "name": "Acme Studio",
    "country": "IN",
    "timezone": "Asia/Kolkata",
    "default_currency": "INR",
}


def idem() -> dict[str, str]:
    return {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}


def drain_jobs() -> None:
    call_command("run_worker", drain=True)


def mailbox(address: str) -> list[email_port.Email]:
    return [message for message in email_port.memory_outbox if message.to == address]


def token_from(message: email_port.Email) -> str:
    found = re.search(r"token=([^\s&]+)", message.body)
    assert found, "the email should carry a link with a token"
    return found.group(1)


def make_user(
    owner_db: psycopg.Connection, email: str, verified: bool = True, password: str = PASS
) -> uuid.UUID:
    row = owner_db.execute(
        "INSERT INTO users (email, password_hash, status, email_verified_at)"
        " VALUES (%s, %s, %s, CASE WHEN %s THEN now() END) RETURNING id",
        [email, make_password(password), "ACTIVE" if verified else "UNVERIFIED", verified],
    ).fetchone()
    assert row
    return row[0]


def login(client: APIClient, email: str, password: str = PASS) -> Any:
    return client.post(f"{API}/auth/login", {"email": email, "password": password}, format="json")


def logged_in(email: str, password: str = PASS) -> APIClient:
    client = APIClient()
    response = login(client, email, password)
    assert response.status_code == 200, response.content
    return client


def owner_workspace(owner_db: psycopg.Connection, email: str) -> tuple[APIClient, str]:
    make_user(owner_db, email)
    client = logged_in(email)
    response = client.post(f"{API}/workspaces", WORKSPACE_BODY, format="json", **idem())
    assert response.status_code == 201, response.content
    return client, response.json()["id"]


def add_member(
    owner_db: psycopg.Connection, workspace_id: str, email: str, role: str
) -> tuple[APIClient, str]:
    user_id = make_user(owner_db, email)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [workspace_id])
    row = owner_db.execute(
        "INSERT INTO workspace_memberships (workspace_id, user_id, role, status)"
        " VALUES (%s, %s, %s, 'ACTIVE') RETURNING id",
        [workspace_id, user_id, role],
    ).fetchone()
    assert row
    return logged_in(email), str(row[0])
