"""Workspace export, deletion, the AI payload inspector and retention (E102-E105).

The export reads an allowlist of this workspace's tables and drops every secret or sealed column. Deletion
runs the privileged procedure `privacy_delete_workspace`, which scans for leftovers and rolls back unless
none remain. The audit history is kept: it is append-only by database permissions.
"""

import json
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings

from collectiq.audit import record
from collectiq.notifications import service as notifications
from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.platform.jobs import enqueue, job_handler
from collectiq.platform.storage import get_storage, storage_key
from collectiq.tenancy.permissions import AI_PAYLOADS, DELETION, EXPORT, authorize

CONFIRMATION = "DELETE MY WORKSPACE"
EXPORT_TABLES = (
    "workspace_memberships", "workspace_policies", "clients", "client_contacts", "client_aliases",
    "invoices", "invoice_state", "payment_transactions", "payment_allocations", "cases", "case_notes",
    "reminders", "commitments", "audit_events",
)  # fmt: skip
SECRET_KEYS = (
    "wrapped_key", "sealed", "verifier_sealed", "body_enc", "raw_row_ciphertext", "token_hash",
    "password_hash", "hash", "prev_hash", "content_sha256",
)  # fmt: skip
EXPORT_DAYS = 7
DEFAULT_PAYLOAD_RETENTION_DAYS = 30


def _not_found() -> ProblemError:
    return ProblemError("NOT_FOUND", 404, "We could not find that.")


def _retention_days() -> int:
    return int(getattr(settings, "COLLECTIQ_PAYLOAD_RETENTION_DAYS", DEFAULT_PAYLOAD_RETENTION_DAYS))


def _dto(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "expires_at": row["expires_at"].isoformat(),
        "size_bytes": row["size_bytes"],
    }


def request_export(ctx: RequestContext) -> dict[str, Any]:
    authorize(ctx, EXPORT)
    with tenant_tx(ctx):
        row = fetch_one(
            "INSERT INTO export_requests (workspace_id, requested_by, expires_at) VALUES (%s, %s, %s)"
            " RETURNING id, status, created_at, completed_at, expires_at, size_bytes",
            [ctx.workspace_id, ctx.user_id, clock.now() + timedelta(days=EXPORT_DAYS)],
        )
        assert row
        enqueue(ctx, "privacy.build_export", {"export_id": str(row["id"])}, f"export:{row['id']}")
        record(ctx, "workspace.export_requested", "export", str(row["id"]), reason_codes=["SENSITIVE_EXPORT"])
        return _dto(row)


def _rows(table: str, ctx: RequestContext) -> list[Any]:
    # table names come from the constant allowlist above, never from input
    sql = f"SELECT to_jsonb(t) - %s::text[] AS doc FROM {table} t WHERE t.workspace_id = %s ORDER BY 1"  # noqa: S608
    docs = [r["doc"] for r in fetch_all(sql, [list(SECRET_KEYS), ctx.workspace_id])]
    return [json.loads(d) if isinstance(d, str) else d for d in docs]


def build_export(ctx: RequestContext, export_id: UUID) -> None:
    with tenant_tx(ctx):
        row = fetch_one("SELECT id, status FROM export_requests WHERE id = %s FOR UPDATE", [export_id])
        if row is None or row["status"] != "PENDING":
            return
        workspace = fetch_one(
            "SELECT id, name, country, timezone, default_currency FROM workspaces WHERE id = %s",
            [ctx.workspace_id],
        )
        content: dict[str, Any] = {"workspace": json.loads(json.dumps(workspace, default=str))}
        for table in EXPORT_TABLES:
            content[table] = _rows(table, ctx)
        data = json.dumps(content, default=str, sort_keys=True).encode()
        key = storage_key(ctx, "exports", f"{export_id}.json")
        get_storage().put(ctx, key, data)
        execute(
            "UPDATE export_requests SET status = 'READY', storage_key = %s, size_bytes = %s,"
            " completed_at = now() WHERE id = %s",
            [key, len(data), export_id],
        )
        record(ctx, "workspace.export_ready", "export", str(export_id), reason_codes=["SENSITIVE_EXPORT"])


@job_handler("privacy.build_export")
def _export_job(ctx: RequestContext, payload: dict[str, Any]) -> None:
    build_export(ctx, UUID(payload["export_id"]))


def get_export(ctx: RequestContext, export_id: UUID) -> dict[str, Any]:
    authorize(ctx, EXPORT)
    with tenant_tx(ctx):
        row = fetch_one(
            "SELECT id, status, storage_key, size_bytes, created_at, completed_at, expires_at"
            " FROM export_requests WHERE workspace_id = %s AND id = %s",
            [ctx.workspace_id, export_id],
        )
        if row is None:
            raise _not_found()
        out = _dto(row)
        out["content"] = None
        if row["status"] == "READY" and row["expires_at"] > clock.now() and row["storage_key"]:
            out["content"] = json.loads(get_storage().get(ctx, row["storage_key"]))
            record(
                ctx,
                "workspace.export_downloaded",
                "export",
                str(export_id),
                reason_codes=["SENSITIVE_EXPORT"],
            )
        return out


def delete_workspace(ctx: RequestContext, confirmation: str) -> dict[str, Any]:
    authorize(ctx, DELETION)
    if confirmation != CONFIRMATION:
        raise ProblemError(
            "VALIDATION_FAILED",
            422,
            "The confirmation text does not match.",
            extra={"field": "confirmation_text"},
        )
    with tenant_tx(ctx):
        keys = [r["storage_key"] for r in fetch_all("SELECT storage_key FROM stored_files", [])]
        keys += [
            r["storage_key"]
            for r in fetch_all("SELECT storage_key FROM export_requests", [])
            if r["storage_key"]
        ]
        record(
            ctx,
            "workspace.deletion_requested",
            "workspace",
            str(ctx.workspace_id),
            reason_codes=["HUMAN_REQUESTED"],
        )
        removed = fetch_one(
            "SELECT privacy_delete_workspace(%s, %s) AS removed", [ctx.workspace_id, ctx.user_id]
        )
        assert removed
        scan = fetch_one(
            "SELECT rows_remaining, tables_cleared, completed_at FROM deletion_records"
            " WHERE workspace_id = %s",
            [ctx.workspace_id],
        )
        assert scan
    storage = get_storage()  # after the commit: a rolled-back deletion must not lose files
    for key in keys:
        storage.delete(ctx, key)
    return {
        "status": "DELETED",
        "rows_deleted": int(removed["removed"]),
        "rows_remaining": int(scan["rows_remaining"]),
        "tables_cleared": int(scan["tables_cleared"]),
        "completed_at": scan["completed_at"].isoformat(),
        "note": "The audit history is retained: append-only by database permissions.",
    }


def list_payloads(ctx: RequestContext, limit: int = 50) -> dict[str, Any]:
    authorize(ctx, AI_PAYLOADS)
    with tenant_tx(ctx):
        rows = fetch_all(
            "SELECT r.id, r.task_id, r.subject_type, r.provider, r.model_version, r.input_sha256, r.status,"
            " r.dropped_fields, p.redacted_input, r.created_at FROM ai_processing_records r"
            " LEFT JOIN ai_payloads p ON p.workspace_id = r.workspace_id AND p.processing_id = r.id"
            " WHERE r.workspace_id = %s ORDER BY r.created_at DESC, r.id LIMIT %s",
            [ctx.workspace_id, limit],
        )
        record(
            ctx, "ai_payloads.viewed", "ai_payloads", str(ctx.workspace_id), reason_codes=["SENSITIVE_VIEW"]
        )
    items = []
    for r in rows:
        payload = r["redacted_input"]
        items.append(
            {
                "id": str(r["id"]),
                "task_id": r["task_id"],
                "subject_type": r["subject_type"],
                "provider": r["provider"],
                "model_version": r["model_version"],
                "input_sha256": r["input_sha256"],
                "status": r["status"],
                "dropped_fields": list(r["dropped_fields"] or []),
                "payload": json.loads(payload) if isinstance(payload, str) else payload,
                "created_at": r["created_at"].isoformat(),
            }
        )
    return {
        "items": items,
        "note": "Shown as sent to the provider, with personal details replaced by tokens."
        " Raw values are not kept here.",
    }


def apply_retention(ctx: RequestContext) -> dict[str, int]:
    """Inside a tenant transaction. Clears old payload text and removes expired exports."""
    cutoff = clock.now() - timedelta(days=_retention_days())
    cleared = execute(
        "DELETE FROM ai_payloads WHERE workspace_id = %s AND created_at < %s",
        [ctx.workspace_id, cutoff],
    )
    expired = fetch_all(
        "SELECT id, storage_key FROM export_requests WHERE workspace_id = %s AND expires_at < %s",
        [ctx.workspace_id, clock.now()],
    )
    storage = get_storage()
    for row in expired:
        if row["storage_key"]:
            storage.delete(ctx, row["storage_key"])
        execute("DELETE FROM export_requests WHERE id = %s", [row["id"]])
    stale_notifications = notifications.delete_expired(ctx)
    if cleared or expired or stale_notifications:
        record(
            ctx,
            "privacy.retention_applied",
            "workspace",
            str(ctx.workspace_id),
            after={
                "payloads_cleared": cleared,
                "exports_removed": len(expired),
                "notifications_removed": stale_notifications,
            },
        )
    return {
        "payloads_cleared": cleared,
        "exports_removed": len(expired),
        "notifications_removed": stale_notifications,
    }


@job_handler("privacy.retention")
def _retention_job(ctx: RequestContext, payload: dict[str, Any]) -> None:
    with tenant_tx(ctx):
        apply_retention(ctx)
