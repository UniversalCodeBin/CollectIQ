"""AI opt-ins and the workspace kill switch (E109, E110).

Every opt-in starts off. The kill switch stops every AI call for the workspace and wins over the opt-ins.
`provider_configured` says whether a provider exists at all, so a screen can say "AI is not configured"
instead of offering a switch that does nothing.
"""

from typing import Any

from collectiq.ai.runtime import get_gateway
from collectiq.audit import record
from collectiq.platform.context import RequestContext
from collectiq.platform.db import fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError

from .permissions import AI_SETTINGS_READ, AI_SETTINGS_WRITE, authorize

PDF = "pdf_extraction_enabled"
REPLIES = "reply_interpretation_enabled"
BRIEF = "invoice_brief_enabled"
FLAGS = (PDF, REPLIES, BRIEF, "kill_switch")


def _row(ctx: RequestContext) -> dict[str, bool]:
    row = fetch_one(
        "SELECT pdf_extraction_enabled, reply_interpretation_enabled, invoice_brief_enabled, kill_switch"
        " FROM workspace_ai_settings WHERE workspace_id = %s",
        [ctx.workspace_id],
    )
    return {name: bool(row[name]) if row else False for name in FLAGS}


def _view(ctx: RequestContext) -> dict[str, Any]:
    return {**_row(ctx), "provider_configured": get_gateway().configured}


def enabled(ctx: RequestContext, feature: str) -> bool:
    """For callers already inside a tenant transaction. Off unless opted in and not switched off."""
    if feature not in (PDF, REPLIES, BRIEF):
        raise ValueError(feature)
    row = _row(ctx)
    return row[feature] and not row["kill_switch"]


def get_settings(ctx: RequestContext) -> dict[str, Any]:
    authorize(ctx, AI_SETTINGS_READ)
    with tenant_tx(ctx):
        return _view(ctx)


def put_settings(ctx: RequestContext, changes: dict[str, bool]) -> dict[str, Any]:
    authorize(ctx, AI_SETTINGS_WRITE)
    unknown = set(changes) - set(FLAGS)
    if unknown or not changes:
        raise ProblemError("VALIDATION_FAILED", 422, "Send at least one of the AI switches.")
    with tenant_tx(ctx):
        before = _row(ctx)
        after = {**before, **changes}
        fetch_one(
            "INSERT INTO workspace_ai_settings (workspace_id, pdf_extraction_enabled,"
            " reply_interpretation_enabled, invoice_brief_enabled, kill_switch, updated_by)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (workspace_id) DO UPDATE SET"
            " pdf_extraction_enabled = EXCLUDED.pdf_extraction_enabled,"
            " reply_interpretation_enabled = EXCLUDED.reply_interpretation_enabled,"
            " invoice_brief_enabled = EXCLUDED.invoice_brief_enabled,"
            " kill_switch = EXCLUDED.kill_switch, updated_by = EXCLUDED.updated_by, updated_at = now()"
            " RETURNING workspace_id",
            [ctx.workspace_id, after[PDF], after[REPLIES], after[BRIEF], after["kill_switch"], ctx.user_id],
        )
        record(ctx, "ai_settings.updated", "workspace", str(ctx.workspace_id), before=before, after=after)
        return _view(ctx)
