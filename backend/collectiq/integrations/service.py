"""Connection lifecycle. CONNECTED_VERIFIED is only written after the verifier says yes (the DB agrees)."""

from collections.abc import Callable
from typing import Any

from django.conf import settings

from collectiq.audit import record
from collectiq.platform.context import RequestContext
from collectiq.platform.db import fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.tenancy.permissions import INTEGRATIONS_MANAGE, INTEGRATIONS_READ, authorize

from .registry import ENTRIES, PROVIDERS


def _stored(ctx: RequestContext) -> dict[str, dict[str, Any]]:
    rows = fetch_all(
        "SELECT provider, state, verified_at, last_error, external_account"
        " FROM integration_connections WHERE workspace_id = %s",
        [ctx.workspace_id],
    )
    return {r["provider"]: r for r in rows}


def _item(
    entry: Any, row: dict[str, Any] | None, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    if entry.kind != "PROVIDER":
        return {
            "key": entry.key,
            "label": entry.label,
            "kind": entry.kind,
            "state": entry.kind,
            "note": entry.note,
            "verified_at": None,
            "last_error": None,
        }
    item: dict[str, Any] = {
        "key": entry.key,
        "label": entry.label,
        "kind": entry.kind,
        "state": row["state"] if row else "NEEDS_CONFIGURATION",
        "note": entry.note,
        "verified_at": row["verified_at"].isoformat() if row and row["verified_at"] else None,
        "last_error": row["last_error"] if row else None,
    }
    if entry.key == "PAYPAL":
        item["environment"] = getattr(settings, "PAYPAL_ENVIRONMENT", "sandbox")
        item["external_account"] = row.get("external_account") if row else None
        item["webhook_status"] = "CONFIGURED" if getattr(settings, "PAYPAL_WEBHOOK_ID", "") else "MISSING"
        item["last_event_received_at"] = extra.get("last_event_received_at") if extra else None
        item["last_event_status"] = extra.get("last_event_status") if extra else None
    return item


def list_integrations(ctx: RequestContext) -> dict[str, Any]:
    authorize(ctx, INTEGRATIONS_READ)
    with tenant_tx(ctx):
        stored = _stored(ctx)
        last_pp_event = fetch_one(
            "SELECT received_at, status FROM webhook_events"
            " WHERE workspace_id = %s AND provider = 'PAYPAL' ORDER BY received_at DESC LIMIT 1",
            [ctx.workspace_id],
        )
        extra = {}
        if last_pp_event:
            extra["last_event_received_at"] = (
                last_pp_event["received_at"].isoformat() if last_pp_event["received_at"] else None
            )
            extra["last_event_status"] = last_pp_event["status"]
        return {"items": [_item(e, stored.get(e.key), extra if e.key == "PAYPAL" else None) for e in ENTRIES]}


def _provider(key: str) -> Any:
    if key not in PROVIDERS:
        raise ProblemError("VALIDATION_FAILED", 422, "That connection is not available.")
    return next(e for e in ENTRIES if e.key == key)


def _write(
    ctx: RequestContext,
    key: str,
    state: str,
    verified: bool,
    error: str | None,
    external_account: str | None = None,
) -> None:
    fetch_one(
        "INSERT INTO integration_connections"
        " (workspace_id, provider, state, verified_at, last_error, updated_by, external_account)"
        " VALUES (%s, %s, %s, CASE WHEN %s THEN now() END, %s, %s, %s)"
        " ON CONFLICT (workspace_id, provider) DO UPDATE SET state = EXCLUDED.state,"
        " verified_at = EXCLUDED.verified_at, last_error = EXCLUDED.last_error,"
        " updated_by = EXCLUDED.updated_by, updated_at = now(),"
        " external_account = CASE WHEN EXCLUDED.state = 'CONNECTED_VERIFIED' THEN EXCLUDED.external_account"
        " WHEN EXCLUDED.state = 'DISCONNECTED' THEN NULL ELSE integration_connections.external_account END"
        " RETURNING provider",
        [ctx.workspace_id, key, state, verified, error, ctx.user_id, external_account],
    )


def connect(
    ctx: RequestContext, key: str, verifier: Callable[[], bool], external_account: str | None = None
) -> dict[str, Any]:
    """Only a verifier that returns True produces CONNECTED_VERIFIED; an error or False never does."""
    authorize(ctx, INTEGRATIONS_MANAGE)
    entry = _provider(key)
    try:
        ok = bool(verifier())
        error = None if ok else "The provider did not confirm the connection."
    except Exception:  # noqa: BLE001 - any failure to verify means not verified
        ok, error = False, "The provider could not be reached."
    with tenant_tx(ctx):
        before = _item(entry, _stored(ctx).get(key))
        if ok:
            _write(ctx, key, "CONNECTED_VERIFIED", True, None, external_account)
            action = "integration.connected"
        else:
            state = "NEEDS_REAUTH" if before["state"] == "CONNECTED_VERIFIED" else "NEEDS_CONFIGURATION"
            _write(ctx, key, state, False, error)
            action = "integration.verification_failed"
        after = _item(entry, _stored(ctx).get(key))
        record(
            ctx,
            action,
            "integration",
            key,
            before={"state": before["state"]},
            after={"state": after["state"]},
        )
        return after


def is_connected(ctx: RequestContext, key: str) -> bool:
    """Inside a tenant transaction."""
    row = fetch_one(
        "SELECT state FROM integration_connections WHERE workspace_id = %s AND provider = %s",
        [ctx.workspace_id, key],
    )
    return bool(row and row["state"] == "CONNECTED_VERIFIED")


def disconnect(ctx: RequestContext, key: str, cleanup: Callable[[], None] | None = None) -> dict[str, Any]:
    authorize(ctx, INTEGRATIONS_MANAGE)
    entry = _provider(key)
    with tenant_tx(ctx):
        if cleanup:
            cleanup()
        before = _item(entry, _stored(ctx).get(key))
        _write(ctx, key, "DISCONNECTED", False, None)
        after = _item(entry, _stored(ctx).get(key))
        record(
            ctx,
            "integration.disconnected",
            "integration",
            key,
            before={"state": before["state"]},
            after={"state": after["state"]},
        )
        return after
