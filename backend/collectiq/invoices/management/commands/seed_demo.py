"""Creates one verified demo login per role in a demo workspace, with sample invoices. Never in production.

Safe to run again: existing users, the workspace and its memberships are left as they are.
"""

import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from collectiq.platform.context import RequestContext, global_context
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.tenancy.service import create_workspace

DEMO_WORKSPACE_ID = uuid.uuid5(uuid.NAMESPACE_URL, "collectiq-demo-workspace")
# Local testing only. The example.test domain never receives mail, and the password is public on purpose.
DEMO_PASSWORD = "DemoPassword-2026"  # noqa: S105  # pragma: allowlist secret (public demo value)
DEMO_USERS = (
    ("owner@example.test", "OWNER"),
    ("finance@example.test", "FINANCE_ADMIN"),
    ("lead@example.test", "PROJECT_LEAD"),
)


class Command(BaseCommand):
    help = "Create one demo login per role and sample invoices. Refused in production."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--invoices", type=int, default=30)

    def handle(self, *args: Any, **options: Any) -> None:
        if settings.DJANGO_ENV == "production":
            raise CommandError("Demo logins are never created in production.")
        user_ids = self._users()
        owner_id = user_ids["OWNER"]
        ctx = RequestContext(DEMO_WORKSPACE_ID, owner_id, "OWNER", str(uuid.uuid4()), "USER")
        created = self._workspace(ctx)
        with tenant_tx(ctx):
            for _email, role in DEMO_USERS:
                execute(
                    "INSERT INTO workspace_memberships (workspace_id, user_id, role) VALUES (%s, %s, %s)"
                    " ON CONFLICT (workspace_id, user_id) DO NOTHING",
                    [DEMO_WORKSPACE_ID, user_ids[role], role],
                )
            has_invoices = fetch_one("SELECT 1 AS found FROM invoices LIMIT 1") is not None
        if not has_invoices:
            call_command("seed_sample", workspace=str(DEMO_WORKSPACE_ID), invoices=int(options["invoices"]),
                         stdout=self.stdout)  # fmt: skip
        state = "created" if created else "already existed"
        self.stdout.write(f"Demo workspace {state}: {DEMO_WORKSPACE_ID}")
        self.stdout.write(f"Sign in with password {DEMO_PASSWORD}")
        for email, role in DEMO_USERS:
            self.stdout.write(f"  {role:<14} {email}")

    def _users(self) -> dict[str, uuid.UUID]:
        password_hash = make_password(DEMO_PASSWORD)  # slow, so outside the transaction
        ids: dict[str, uuid.UUID] = {}
        with tenant_tx(global_context(str(uuid.uuid4()))):
            for email, role in DEMO_USERS:
                execute(
                    "INSERT INTO users (email, password_hash, status, email_verified_at)"
                    " VALUES (%s, %s, 'ACTIVE', now()) ON CONFLICT (email) DO NOTHING",
                    [email, password_hash],
                )
                ids[role] = fetch_all("SELECT id FROM users WHERE email = %s::citext", [email])[0]["id"]
        return ids

    def _workspace(self, ctx: RequestContext) -> bool:
        with tenant_tx(ctx):
            exists = fetch_one("SELECT 1 AS found FROM workspaces WHERE id = %s", [DEMO_WORKSPACE_ID])
        if exists:
            return False
        create_workspace(
            ctx,
            {
                "name": "Demo Workspace",
                "country": "IN",
                "timezone": "Asia/Kolkata",
                "default_currency": "INR",
            },
        )
        return True
