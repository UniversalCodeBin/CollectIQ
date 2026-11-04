"""Clients, their contacts and suppression (TSD M07, FR-149). Every value here is user-entered."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from django.db import IntegrityError

from collectiq.audit import record
from collectiq.platform.context import RequestContext
from collectiq.platform.db import fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError

from .domain.validate import collapse, normalize_name

_CLIENT = "id, display_name, normalized_name, sensitivity, tone, version"
_CONTACT = "id, client_id, email, name, status, suppression_reason"


def _not_found() -> ProblemError:
    return ProblemError("NOT_FOUND", 404, "We could not find that.")


def _duplicate_contact() -> ProblemError:
    return ProblemError("DUPLICATE_RESOURCE", 409, "This client already has a contact with that email.")


def _client_dto(row: Mapping[str, Any]) -> dict[str, Any]:
    return {**row, "id": str(row["id"])}


def _contact_dto(row: Mapping[str, Any]) -> dict[str, Any]:
    return {**row, "id": str(row["id"]), "client_id": str(row["client_id"]), "email": str(row["email"])}


def _require_client(client_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    suffix = " FOR UPDATE" if lock else ""
    row = fetch_one(f"SELECT {_CLIENT} FROM clients WHERE id = %s{suffix}", [client_id])  # noqa: S608
    if row is None:
        raise _not_found()
    return row


def list_clients(ctx: RequestContext, limit: int, cursor: UUID | None) -> dict[str, Any]:
    with tenant_tx(ctx):
        rows = fetch_all(
            f"SELECT {_CLIENT} FROM clients"  # noqa: S608
            " WHERE %(cursor)s::uuid IS NULL OR id > %(cursor)s::uuid"
            " ORDER BY id LIMIT %(limit)s",
            {"cursor": cursor, "limit": limit + 1},
        )
    page = rows[:limit]
    return {
        "items": [_client_dto(row) for row in page],
        "next_cursor": str(page[-1]["id"]) if len(rows) > limit else None,
    }


def create_client(ctx: RequestContext, fields: Mapping[str, Any]) -> dict[str, Any]:
    display_name = collapse(fields["display_name"])
    with tenant_tx(ctx):
        row = fetch_all(
            "INSERT INTO clients (workspace_id, display_name, normalized_name, sensitivity, tone)"  # noqa: S608
            " VALUES (%s, %s, %s, %s, %s)"
            f" RETURNING {_CLIENT}",
            [
                ctx.workspace_id,
                display_name,
                normalize_name(display_name),
                fields.get("sensitivity", "STANDARD"),
                fields.get("tone", "NEUTRAL"),
            ],
        )[0]
        record(
            ctx,
            "client.created",
            "client",
            str(row["id"]),
            after={"display_name": display_name, "sensitivity": row["sensitivity"], "tone": row["tone"]},
        )
    return _client_dto(row)


def client_profile(ctx: RequestContext, client_id: UUID) -> dict[str, Any]:
    """The client with what is known about it. Invoice figures join `summary` once invoices exist."""
    with tenant_tx(ctx):
        client = _require_client(client_id)
        contacts = fetch_all(
            f"SELECT {_CONTACT} FROM client_contacts WHERE client_id = %s ORDER BY created_at, id",  # noqa: S608
            [client_id],
        )
        aliases = fetch_all(
            "SELECT id, text, kind FROM client_aliases WHERE client_id = %s ORDER BY created_at, id",
            [client_id],
        )
    suppressed = sum(1 for contact in contacts if contact["status"] == "SUPPRESSED")
    return {
        **_client_dto(client),
        "contacts": [_contact_dto(contact) for contact in contacts],
        "aliases": [{**alias, "id": str(alias["id"])} for alias in aliases],
        "summary": {
            "contacts_total": len(contacts),
            "contacts_active": len(contacts) - suppressed,
            "contacts_suppressed": suppressed,
        },
    }


def update_client(
    ctx: RequestContext, client_id: UUID, expected_version: int, changes: Mapping[str, Any]
) -> dict[str, Any]:
    wanted = dict(changes)
    if "display_name" in wanted:
        wanted["display_name"] = collapse(wanted["display_name"])
    with tenant_tx(ctx):
        current = _require_client(client_id, lock=True)
        if current["version"] != expected_version:
            raise ProblemError("CONFLICT_VERSION", 409, "This client changed. Reload and try again.")
        changed = {name: value for name, value in wanted.items() if current[name] != value}
        if not changed:
            return _client_dto(current)
        row = fetch_all(
            "UPDATE clients SET display_name = %(display_name)s, normalized_name = %(normalized_name)s,"  # noqa: S608
            " sensitivity = %(sensitivity)s, tone = %(tone)s, version = version + 1, updated_at = now()"
            f" WHERE id = %(id)s RETURNING {_CLIENT}",  # noqa: S608
            {
                "id": client_id,
                "display_name": changed.get("display_name", current["display_name"]),
                "normalized_name": normalize_name(changed.get("display_name", current["display_name"])),
                "sensitivity": changed.get("sensitivity", current["sensitivity"]),
                "tone": changed.get("tone", current["tone"]),
            },
        )[0]
        record(
            ctx,
            "client.updated",
            "client",
            str(client_id),
            before={name: current[name] for name in changed},
            after=changed,
        )
    return _client_dto(row)


def add_contact(ctx: RequestContext, client_id: UUID, email: str, name: str | None = None) -> dict[str, Any]:
    with tenant_tx(ctx):
        _require_client(client_id)
        row = fetch_one(
            "INSERT INTO client_contacts (workspace_id, client_id, email, name) VALUES (%s, %s, %s, %s)"  # noqa: S608
            " ON CONFLICT (workspace_id, client_id, email) DO NOTHING"
            f" RETURNING {_CONTACT}",
            [ctx.workspace_id, client_id, email, name],
        )
        if row is None:
            raise _duplicate_contact()
        record(ctx, "contact.added", "contact", str(row["id"]), after={"client_id": str(client_id)})
    return _contact_dto(row)


def ensure_contact(ctx: RequestContext, client_id: UUID, email: str) -> None:
    """For an import, where an address already known is not a mistake. A suppressed one stays suppressed."""
    row = fetch_one(
        "INSERT INTO client_contacts (workspace_id, client_id, email) VALUES (%s, %s, %s)"
        " ON CONFLICT (workspace_id, client_id, email) DO NOTHING RETURNING id",
        [ctx.workspace_id, client_id, email],
    )
    if row is not None:
        record(ctx, "contact.added", "contact", str(row["id"]), after={"client_id": str(client_id)})


def add_alias(ctx: RequestContext, client_id: UUID, text: str, kind: str = "NAME") -> None:
    """Remembers another name for a client, so the same question is not asked twice (FR-009)."""
    row = fetch_one(
        "INSERT INTO client_aliases (workspace_id, client_id, text, normalized_text, kind)"
        " VALUES (%s, %s, %s, %s, %s)"
        " ON CONFLICT (workspace_id, client_id, kind, normalized_text) DO NOTHING RETURNING id",
        [ctx.workspace_id, client_id, collapse(text), normalize_name(text), kind],
    )
    if row is not None:
        record(ctx, "client.alias_added", "client", str(client_id), after={"alias_id": str(row["id"])})


def update_contact(
    ctx: RequestContext, client_id: UUID, contact_id: UUID, changes: Mapping[str, Any]
) -> dict[str, Any]:
    with tenant_tx(ctx):
        current = fetch_one(
            f"SELECT {_CONTACT} FROM client_contacts WHERE id = %s AND client_id = %s FOR UPDATE",  # noqa: S608
            [contact_id, client_id],
        )
        if current is None:
            raise _not_found()
        changed = {name: value for name, value in changes.items() if current[name] != value}
        if not changed:
            return _contact_dto(current)
        if "email" in changed and current["status"] == "SUPPRESSED":
            raise ProblemError(
                "STATE_TRANSITION_INVALID",
                409,
                "This contact is suppressed. Clear the suppression before changing the address.",
            )
        try:
            row = fetch_all(
                "UPDATE client_contacts SET email = %s, name = %s, updated_at = now()"  # noqa: S608
                f" WHERE id = %s RETURNING {_CONTACT}",  # noqa: S608
                [changed.get("email", current["email"]), changed.get("name", current["name"]), contact_id],
            )[0]
        except IntegrityError as error:
            raise _duplicate_contact() from error
        # Names of the fields only: the audit trail is append-only, a person's address must not stay in it.
        record(ctx, "contact.updated", "contact", str(contact_id), after={"fields": sorted(changed)})
    return _contact_dto(row)


def _locked_contact(contact_id: UUID) -> dict[str, Any]:
    row = fetch_one(f"SELECT {_CONTACT} FROM client_contacts WHERE id = %s FOR UPDATE", [contact_id])  # noqa: S608
    if row is None:
        raise _not_found()
    return row


def suppress_contact(ctx: RequestContext, contact_id: UUID, reason: str) -> dict[str, Any]:
    with tenant_tx(ctx):
        if _locked_contact(contact_id)["status"] == "SUPPRESSED":
            raise ProblemError("STATE_TRANSITION_INVALID", 409, "This contact is already suppressed.")
        row = fetch_all(
            "UPDATE client_contacts SET status = 'SUPPRESSED', suppression_reason = %s, updated_at = now()"  # noqa: S608
            f" WHERE id = %s RETURNING {_CONTACT}",  # noqa: S608
            [reason, contact_id],
        )[0]
        record(
            ctx,
            "contact.suppressed",
            "contact",
            str(contact_id),
            before={"status": "ACTIVE"},
            after={"status": "SUPPRESSED", "reason": reason},
        )
    return _contact_dto(row)


def clear_suppression(ctx: RequestContext, contact_id: UUID, reason: str | None = None) -> None:
    with tenant_tx(ctx):
        if _locked_contact(contact_id)["status"] != "SUPPRESSED":
            raise ProblemError("STATE_TRANSITION_INVALID", 409, "This contact is not suppressed.")
        fetch_all(
            "UPDATE client_contacts SET status = 'ACTIVE', suppression_reason = NULL, updated_at = now()"
            " WHERE id = %s RETURNING id",
            [contact_id],
        )
        record(
            ctx,
            "contact.suppression_cleared",
            "contact",
            str(contact_id),
            before={"status": "SUPPRESSED"},
            after={"status": "ACTIVE", "reason": reason},
        )


def approved_recipient(ctx: RequestContext, contact_id: UUID) -> dict[str, Any]:
    """The check behind G9 (FR-097): an address suppressed anywhere in the workspace is not sendable."""
    with tenant_tx(ctx):
        row = fetch_one(f"SELECT {_CONTACT} FROM client_contacts WHERE id = %s", [contact_id])  # noqa: S608
        if row is None:
            raise _not_found()
        blocked = fetch_one(
            "SELECT 1 AS blocked FROM client_contacts WHERE email = %s AND status = 'SUPPRESSED' LIMIT 1",
            [row["email"]],
        )
    if blocked is not None:
        raise ProblemError("POLICY_BLOCKED", 409, "This contact is suppressed and cannot receive messages.")
    return _contact_dto(row)
