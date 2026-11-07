"""Workspaces, members and invitations.

Row policies are OR'ed: inside a tenant transaction a user can still see their own memberships elsewhere.
So every query on workspaces and memberships names the workspace too.
"""

import hashlib
import json
import secrets
from typing import Any
from uuid import UUID, uuid5

from django.conf import settings

from collectiq.audit import record
from collectiq.identity.service import app_link
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx, user_tx
from collectiq.platform.email import send_email
from collectiq.platform.errors import ProblemError
from collectiq.platform.jobs import enqueue

_WORKSPACE_KEY_NAMESPACE = UUID("3f0b6f6e-6f0a-5c37-9b1a-1f6a2d6f4c11")
_EDITABLE = ("name", "legal_name", "sender_name", "timezone", "default_currency", "business_hours")
_WORKSPACE_COLUMNS = (
    "id, name, legal_name, sender_name, country, timezone, default_currency, business_hours, status, version"
)


def _not_found() -> ProblemError:
    return ProblemError("NOT_FOUND", 404, "We could not find that.")


def _workspace_dto(row: dict[str, Any]) -> dict[str, Any]:
    hours = row["business_hours"]
    return {
        **row,
        "id": str(row["id"]),
        "business_hours": json.loads(hours) if isinstance(hours, str) else hours,
    }


def workspaces_for(user_id: UUID) -> list[dict[str, Any]]:
    with user_tx(user_id):
        rows = fetch_all(
            """
            SELECT w.id, w.name, m.role
            FROM workspace_memberships m JOIN workspaces w ON w.id = m.workspace_id
            WHERE m.user_id = %s AND m.status = 'ACTIVE' AND w.status <> 'DELETED'
            ORDER BY w.name, w.id
            """,
            [user_id],
        )
    return [{**row, "id": str(row["id"])} for row in rows]


def role_in(user_id: UUID, workspace_id: UUID) -> str | None:
    with user_tx(user_id):
        row = fetch_one(
            """
            SELECT m.role
            FROM workspace_memberships m JOIN workspaces w ON w.id = m.workspace_id
            WHERE m.user_id = %s AND m.workspace_id = %s AND m.status = 'ACTIVE' AND w.status <> 'DELETED'
            """,
            [user_id, workspace_id],
        )
    return row["role"] if row else None


def new_workspace_id(user_id: UUID, key: UUID) -> UUID:
    """Derived from the key, so a retry lands in the same tenant and finds its stored response."""
    return uuid5(_WORKSPACE_KEY_NAMESPACE, f"{user_id}:{key}")


def create_workspace(ctx: RequestContext, fields: dict[str, Any]) -> dict[str, Any]:
    with tenant_tx(ctx):
        if fetch_one("SELECT 1 AS found FROM workspaces WHERE id = %s", [ctx.workspace_id]):
            # The key's stored response has expired, but its workspace exists. A new one would be a duplicate.
            raise ProblemError("DUPLICATE_RESOURCE", 409, "This request already created a workspace.")
        hours = fields.get("business_hours", {})
        execute(
            "INSERT INTO workspaces (id, name, country, timezone, default_currency, business_hours)"
            " VALUES (%s, %s, %s, %s, %s, %s::jsonb)",
            [
                ctx.workspace_id,
                fields["name"],
                fields["country"],
                fields["timezone"],
                fields["default_currency"],
                json.dumps(hours),
            ],
        )
        # INV: automation starts off. Turning it on is a separate, audited choice by a person.
        policy = {
            "mode": "MANUAL",
            "auto_snooze_enabled": False,
            "automation_paused": False,
            "cadence": {},
            "limits": {},
            "business_hours": hours,
            "sensitivity_defaults": {},
        }
        policy_id = fetch_all(
            "INSERT INTO workspace_policies (workspace_id, version, settings, changed_by)"
            " VALUES (%s, 1, %s::jsonb, %s) RETURNING id",
            [ctx.workspace_id, json.dumps(policy), ctx.user_id],
        )[0]["id"]
        execute("UPDATE workspaces SET active_policy_id = %s WHERE id = %s", [policy_id, ctx.workspace_id])
        execute(
            "INSERT INTO workspace_memberships (workspace_id, user_id, role) VALUES (%s, %s, 'OWNER')",
            [ctx.workspace_id, ctx.user_id],
        )
        record(ctx, "workspace.created", "workspace", str(ctx.workspace_id), after={"name": fields["name"]})
        return _read_workspace(ctx)


def _read_workspace(ctx: RequestContext) -> dict[str, Any]:
    return _workspace_dto(
        fetch_all(f"SELECT {_WORKSPACE_COLUMNS} FROM workspaces WHERE id = %s", [ctx.workspace_id])[0]  # noqa: S608
    )


def get_workspace(ctx: RequestContext) -> dict[str, Any]:
    with tenant_tx(ctx):
        return _read_workspace(ctx)


def update_workspace(ctx: RequestContext, expected_version: int, changes: dict[str, Any]) -> dict[str, Any]:
    with tenant_tx(ctx):
        row = fetch_all(
            f"SELECT {_WORKSPACE_COLUMNS} FROM workspaces WHERE id = %s FOR UPDATE",  # noqa: S608
            [ctx.workspace_id],
        )[0]
        current = _workspace_dto(row)
        if current["version"] != expected_version:
            raise ProblemError("CONFLICT_VERSION", 409, "This workspace changed. Reload and try again.")
        changed = {name: value for name, value in changes.items() if current[name] != value}
        if not changed:
            return current
        merged = {name: changed.get(name, current[name]) for name in _EDITABLE}
        execute(
            "UPDATE workspaces SET name = %s, legal_name = %s, sender_name = %s, timezone = %s,"
            " default_currency = %s, business_hours = %s::jsonb, version = version + 1, updated_at = now()"
            " WHERE id = %s",
            [
                merged["name"],
                merged["legal_name"],
                merged["sender_name"],
                merged["timezone"],
                merged["default_currency"],
                json.dumps(merged["business_hours"]),
                ctx.workspace_id,
            ],
        )
        record(
            ctx,
            "workspace.updated",
            "workspace",
            str(ctx.workspace_id),
            before={name: current[name] for name in changed},
            after=changed,
        )
        return _read_workspace(ctx)


def list_members(ctx: RequestContext, limit: int, cursor: UUID | None) -> dict[str, Any]:
    with tenant_tx(ctx):
        rows = fetch_all(
            """
            SELECT id, user_id, email, role, status FROM (
                SELECT m.id, m.user_id, u.email::text AS email, m.role, m.status
                FROM workspace_memberships m JOIN users u ON u.id = m.user_id
                WHERE m.workspace_id = %(ws)s AND m.status = 'ACTIVE'
                UNION ALL
                SELECT i.id, NULL::uuid, i.email::text, i.role, 'INVITED'
                FROM workspace_invitations i
                WHERE i.workspace_id = %(ws)s AND i.accepted_at IS NULL AND i.revoked_at IS NULL
                    AND i.expires_at > now()
            ) people
            WHERE %(cursor)s::uuid IS NULL OR id > %(cursor)s::uuid
            ORDER BY id LIMIT %(limit)s
            """,
            {"ws": ctx.workspace_id, "cursor": cursor, "limit": limit + 1},
        )
    page = rows[:limit]
    return {
        "items": [
            {**row, "id": str(row["id"]), "user_id": str(row["user_id"]) if row["user_id"] else None}
            for row in page
        ],
        "next_cursor": str(page[-1]["id"]) if len(rows) > limit else None,
    }


def invite(ctx: RequestContext, email: str, role: str) -> dict[str, Any]:
    email = email.strip()
    with tenant_tx(ctx):
        # Two racing invitations for one address would otherwise trip the unique index as a 500.
        execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            [f"invite:{ctx.workspace_id}:{email.lower()}"],
        )
        if fetch_one(
            """
            SELECT 1 AS found FROM workspace_memberships m JOIN users u ON u.id = m.user_id
            WHERE m.workspace_id = %s AND m.status = 'ACTIVE' AND u.email = %s::citext
            """,
            [ctx.workspace_id, email],
        ):
            raise ProblemError("DUPLICATE_RESOURCE", 409, "This person is already a member.")
        execute(
            "UPDATE workspace_invitations SET revoked_at = now()"
            " WHERE workspace_id = %s AND email = %s::citext AND accepted_at IS NULL AND revoked_at IS NULL",
            [ctx.workspace_id, email],
        )
        row = fetch_all(
            "INSERT INTO workspace_invitations (workspace_id, email, role, expires_at, invited_by)"
            " VALUES (%s, %s, %s, now() + %s, %s) RETURNING id, expires_at",
            [ctx.workspace_id, email, role, settings.INVITATION_TTL, ctx.user_id],
        )[0]
        enqueue(ctx, "tenancy.invitation_email", {"invitation_id": str(row["id"])})
        record(ctx, "member.invited", "invitation", str(row["id"]), after={"role": role})
    return {
        "id": str(row["id"]),
        "email": email,
        "role": role,
        "status": "INVITED",
        "expires_at": row["expires_at"],
    }


def _token_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def send_invitation(ctx: RequestContext, invitation_id: str) -> None:
    """Runs as a job. The token is created here, so it never rests in a job's payload."""
    row = fetch_one(
        """
        SELECT i.email::text AS email, w.name AS workspace_name
        FROM workspace_invitations i JOIN workspaces w ON w.id = i.workspace_id
        WHERE i.workspace_id = %s AND i.id = %s AND i.accepted_at IS NULL AND i.revoked_at IS NULL
            AND i.expires_at > now()
        """,
        [ctx.workspace_id, invitation_id],
    )
    if row is None:
        return
    # The workspace is in the token because it picks the tenant the lookup runs under.
    token = f"{ctx.workspace_id}.{secrets.token_urlsafe(32)}"
    execute(
        "UPDATE workspace_invitations SET token_hash = %s WHERE workspace_id = %s AND id = %s",
        [_token_digest(token), ctx.workspace_id, invitation_id],
    )
    send_email(
        row["email"],
        f"You have been invited to {row['workspace_name']} on CollectIQ",
        f"Accept your invitation:\n\n{app_link('/invitations/accept', token)}\n\n"
        "If you were not expecting this, you can ignore this message.",
    )


def _invalid_invitation() -> ProblemError:
    return ProblemError(
        "VALIDATION_FAILED",
        422,
        "Some fields are invalid.",
        {"errors": [{"field": "token", "message": "This invitation is invalid or has expired."}]},
    )


def accept_invitation(token: str, user_id: UUID, email: str, correlation_id: str) -> dict[str, Any]:
    try:
        workspace_id = UUID(token.split(".", 1)[0])
    except ValueError:
        raise _invalid_invitation() from None
    ctx = RequestContext(workspace_id, user_id, None, correlation_id, "USER")
    with tenant_tx(ctx):
        invitation = fetch_one(
            """
            SELECT i.id, i.email::text AS email, i.role
            FROM workspace_invitations i JOIN workspaces w ON w.id = i.workspace_id
            WHERE i.workspace_id = %s AND i.token_hash = %s AND i.accepted_at IS NULL AND i.revoked_at IS NULL
                AND i.expires_at > now() AND w.status <> 'DELETED'
            FOR UPDATE OF i
            """,
            [workspace_id, _token_digest(token)],
        )
        if invitation is None:
            raise _invalid_invitation()
        if invitation["email"].lower() != email.strip().lower():
            raise _not_found()
        member = fetch_all(
            """
            INSERT INTO workspace_memberships AS m (workspace_id, user_id, role) VALUES (%s, %s, %s)
            ON CONFLICT (workspace_id, user_id) DO UPDATE SET
                role = CASE WHEN m.status = 'ACTIVE' THEN m.role ELSE EXCLUDED.role END,
                status = 'ACTIVE',
                updated_at = now()
            RETURNING id, role
            """,
            [workspace_id, user_id, invitation["role"]],
        )[0]
        execute("UPDATE workspace_invitations SET accepted_at = now() WHERE id = %s", [invitation["id"]])
        record(ctx, "member.accepted", "membership", str(member["id"]), after={"role": member["role"]})
    return {"workspace_id": str(workspace_id), "role": member["role"]}


def _lock_owners(ctx: RequestContext) -> list[UUID]:
    """Taken before counting. A second removal waits here, then sees the first one's result (FR-144)."""
    rows = fetch_all(
        "SELECT id FROM workspace_memberships"
        " WHERE workspace_id = %s AND role = 'OWNER' AND status = 'ACTIVE'"
        " ORDER BY id FOR UPDATE",
        [ctx.workspace_id],
    )
    return [row["id"] for row in rows]


def _last_owner() -> ProblemError:
    return ProblemError("STATE_TRANSITION_INVALID", 409, "A workspace must keep at least one owner.")


def _active_member(ctx: RequestContext, member_id: UUID) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT m.id, m.user_id, u.email::text AS email, m.role, m.status
        FROM workspace_memberships m JOIN users u ON u.id = m.user_id
        WHERE m.workspace_id = %s AND m.id = %s AND m.status = 'ACTIVE'
        FOR UPDATE OF m
        """,
        [ctx.workspace_id, member_id],
    )


def remove_member(ctx: RequestContext, member_id: UUID) -> None:
    with tenant_tx(ctx):
        owners = _lock_owners(ctx)
        member = _active_member(ctx, member_id)
        if member is None:
            revoked = execute(
                "UPDATE workspace_invitations SET revoked_at = now()"
                " WHERE workspace_id = %s AND id = %s AND accepted_at IS NULL AND revoked_at IS NULL",
                [ctx.workspace_id, member_id],
            )
            if not revoked:
                raise _not_found()
            record(ctx, "member.invitation_revoked", "invitation", str(member_id))
            return
        if member["role"] == "OWNER" and len(owners) <= 1:
            raise _last_owner()
        execute(
            "UPDATE workspace_memberships SET status = 'REMOVED', updated_at = now()"
            " WHERE workspace_id = %s AND id = %s",
            [ctx.workspace_id, member_id],
        )
        record(ctx, "member.removed", "membership", str(member_id), before={"role": member["role"]})


def change_role(ctx: RequestContext, member_id: UUID, role: str) -> dict[str, Any]:
    with tenant_tx(ctx):
        owners = _lock_owners(ctx)
        member = _active_member(ctx, member_id)
        if member is None:
            raise _not_found()
        if member["role"] != role:
            if member["role"] == "OWNER" and len(owners) <= 1:
                raise _last_owner()
            execute(
                "UPDATE workspace_memberships SET role = %s, updated_at = now()"
                " WHERE workspace_id = %s AND id = %s",
                [role, ctx.workspace_id, member_id],
            )
            record(
                ctx,
                "member.role_changed",
                "membership",
                str(member_id),
                before={"role": member["role"]},
                after={"role": role},
            )
    return {**member, "id": str(member["id"]), "user_id": str(member["user_id"]), "role": role}
