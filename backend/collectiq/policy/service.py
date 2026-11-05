"""Policy versions, the pause, persisted decisions, single use and approvals (E016-E020, E092, E101)."""

import json
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db import connection

from collectiq.audit import record
from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.tenancy.permissions import (
    AUDIT_INSPECT,
    AUTOMATION_PAUSE,
    DRAFT_APPROVE,
    POLICY_READ,
    POLICY_WRITE,
    authorize,
)

from . import authorized
from .authorized import AuthorizedAction
from .domain import (
    GATE_TEXT,
    ActionRequest,
    GateResult,
    Outcome,
    PolicyDecision,
    PolicyVersion,
    StateSnapshot,
    evaluate,
    explain,
)
from .domain.evaluate import fail_closed

DECISION_TTL = timedelta(hours=1)
DEFAULT_MAX_CONTACTS = 3
_MODES = ("MANUAL", "ASSISTED")


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value  # Django leaves jsonb as text


def _dto(row: dict[str, Any]) -> dict[str, Any]:
    settings = _json(row["settings"])
    return {
        "version": row["version"],
        "mode": settings.get("mode", "MANUAL"),
        "automation_paused": bool(settings.get("automation_paused", False)),
        "auto_snooze_enabled": bool(settings.get("auto_snooze_enabled", False)),
        # INV: not offered until the evaluation gate (PRD §5.3) has been passed.
        "auto_snooze_available": False,
        "cadence": settings.get("cadence", {}),
        "limits": settings.get("limits", {}),
        "business_hours": settings.get("business_hours", {}),
        "sensitivity_defaults": settings.get("sensitivity_defaults", {}),
        "changed_by": row["changed_by"],
        "effective_from": row["effective_from"],
    }


_COLUMNS = "p.id, p.version, p.settings, p.changed_by, p.effective_from"


def _active_row(ctx: RequestContext) -> dict[str, Any]:
    row = fetch_one(
        f"SELECT {_COLUMNS} FROM workspace_policies p"  # noqa: S608
        " JOIN workspaces w ON w.active_policy_id = p.id AND w.id = p.workspace_id WHERE w.id = %s",
        [ctx.workspace_id],
    )
    if row is None:
        raise ProblemError("NOT_FOUND", 404, "This workspace has no policy.")
    return row


def active_policy(ctx: RequestContext) -> PolicyVersion:
    row = _active_row(ctx)
    settings = _json(row["settings"])
    max_contacts = settings.get("limits", {}).get("max_contacts", DEFAULT_MAX_CONTACTS)
    return PolicyVersion(
        version=row["version"],
        mode=settings.get("mode", "MANUAL"),
        paused=bool(settings.get("automation_paused", False)),
        auto_snooze_enabled=bool(settings.get("auto_snooze_enabled", False)),
        auto_snooze_available=False,
        max_contacts=max_contacts if isinstance(max_contacts, int) else DEFAULT_MAX_CONTACTS,
    )


def active_settings(ctx: RequestContext) -> dict[str, Any]:
    """The stored settings of the active version, for callers that read cadence or business hours."""
    return dict(_json(_active_row(ctx)["settings"]))


def get_policy(ctx: RequestContext) -> dict[str, Any]:
    authorize(ctx, POLICY_READ)
    with tenant_tx(ctx):
        return _dto(_active_row(ctx))


def list_versions(ctx: RequestContext) -> dict[str, Any]:
    authorize(ctx, POLICY_READ)
    with tenant_tx(ctx):
        rows = fetch_all(
            f"SELECT {_COLUMNS} FROM workspace_policies p WHERE p.workspace_id = %s ORDER BY p.version DESC",  # noqa: S608
            [ctx.workspace_id],
        )
        return {"items": [_dto(r) for r in rows], "next_cursor": None}


def _write_version(
    ctx: RequestContext, settings: dict[str, Any], action: str, reason: str | None = None
) -> dict[str, Any]:
    execute(
        "SELECT 1 FROM workspaces WHERE id = %s FOR UPDATE", [ctx.workspace_id]
    )  # serialises version numbers
    before = _active_row(ctx)
    created = fetch_one(
        "INSERT INTO workspace_policies (workspace_id, version, settings, changed_by)"
        " SELECT %s, coalesce(max(version), 0) + 1, %s::jsonb, %s FROM workspace_policies"
        " WHERE workspace_id = %s"
        " RETURNING id, version",
        [ctx.workspace_id, json.dumps(settings), ctx.user_id, ctx.workspace_id],
    )
    assert created
    execute("UPDATE workspaces SET active_policy_id = %s WHERE id = %s", [created["id"], ctx.workspace_id])
    record(
        ctx,
        action,
        "workspace_policy",
        str(created["id"]),
        before={"version": before["version"], **_json(before["settings"])},
        after={"version": created["version"], **settings},
        reason_codes=[reason] if reason else (),
    )
    return _dto(_active_row(ctx))


def update_policy(ctx: RequestContext, changes: dict[str, Any]) -> dict[str, Any]:
    authorize(ctx, POLICY_WRITE)
    with tenant_tx(ctx):
        settings = dict(_json(_active_row(ctx)["settings"]))
        settings.update({k: v for k, v in changes.items() if v is not None})
        return _write_version(ctx, settings, "policy.changed")


def _set_paused(ctx: RequestContext, paused: bool, reason: str | None) -> dict[str, Any]:
    authorize(ctx, AUTOMATION_PAUSE)
    with tenant_tx(ctx):
        current = _active_row(ctx)
        current_settings = _json(current["settings"])
        if bool(current_settings.get("automation_paused", False)) == paused:
            return _dto(current)
        settings = {**current_settings, "automation_paused": paused}
        return _write_version(ctx, settings, "automation.paused" if paused else "automation.resumed", reason)


def pause(ctx: RequestContext, reason: str | None = None) -> dict[str, Any]:
    return _set_paused(ctx, True, reason)


def resume(ctx: RequestContext) -> dict[str, Any]:
    return _set_paused(ctx, False, None)


# --- decisions ---


def _uuid_or_none(value: object) -> str | None:
    try:
        return str(UUID(str(value)))
    except ValueError:
        return None


def decide(ctx: RequestContext, req: ActionRequest, snap: StateSnapshot) -> dict[str, Any]:
    """Evaluates, stores the decision and, when a person must approve, the pending approval."""
    with tenant_tx(ctx):
        try:
            policy = active_policy(ctx)
            decision = evaluate(req, snap, policy)
        except Exception:  # noqa: BLE001  # INV: when the check cannot finish, the answer is no.
            policy = PolicyVersion(version=0)
            decision = fail_closed(req, snap, policy)
        expires_at = clock.now() + DECISION_TTL
        row = fetch_one(
            "INSERT INTO policy_decisions (workspace_id, action_type, subject, actor_kind, actor_user_id,"
            " outcome,"
            " gate_results, reasons, rules_version, policy_version, state_version, inputs_hash, expires_at)"
            " VALUES (%s, %s, %s, %s, %s::uuid, %s, %s::jsonb, %s::text[], %s, %s, %s, %s, %s) RETURNING id",
            [
                ctx.workspace_id,
                str(req.action),
                str(req.subject),
                str(req.actor.kind),
                _uuid_or_none(req.actor.user_id),
                str(decision.outcome),
                json.dumps(
                    [{"gate": g.gate, "passed": g.passed, "reason": g.reason} for g in decision.gate_results]
                ),
                list(decision.reasons),
                decision.rules_version,
                decision.policy_version,
                decision.state_version,
                decision.inputs_hash,
                expires_at,
            ],
        )
        assert row
        approval_id = None
        if decision.outcome == Outcome.REQUIRE_APPROVAL:
            approval = fetch_one(
                "INSERT INTO approval_requests (workspace_id, decision_id) VALUES (%s, %s) RETURNING id",
                [ctx.workspace_id, row["id"]],
            )
            assert approval
            approval_id = approval["id"]
        return {
            "id": row["id"],
            "outcome": decision.outcome,
            "reasons": list(decision.reasons),
            "gate_results": [
                {"gate": g.gate, "passed": g.passed, "reason": g.reason} for g in decision.gate_results
            ],
            "policy_version": decision.policy_version,
            "state_version": decision.state_version,
            "expires_at": expires_at,
            "approval_id": approval_id,
        }


def _blocked(detail: str) -> ProblemError:
    return ProblemError("POLICY_BLOCKED", 409, detail)


def authorize_execution(
    ctx: RequestContext, decision_id: UUID, req: ActionRequest, snap: StateSnapshot
) -> AuthorizedAction:
    """Re-checks a stored decision against the state now and consumes it, in the executor's transaction."""
    if not connection.in_atomic_block:
        raise RuntimeError("authorize_execution must run inside the transaction of the action it authorizes")
    row = fetch_one(
        "SELECT * FROM policy_decisions WHERE id = %s AND workspace_id = %s FOR UPDATE",
        [decision_id, ctx.workspace_id],
    )
    if row is None:
        raise ProblemError("NOT_FOUND", 404, "This decision does not exist.")
    if row["consumed_at"] is not None:
        raise _blocked("This decision was already used.")
    if row["expires_at"] <= clock.now():
        raise _blocked("This decision has expired. Check again.")
    policy = active_policy(ctx)
    if policy.version != row["policy_version"]:
        raise _blocked("The automation policy changed after this was decided. Check again.")
    if snap.state_version != row["state_version"]:
        raise _blocked("The invoice changed after this was decided. Check again.")
    now = evaluate(req, snap, policy)
    if now.inputs_hash != row["inputs_hash"] or str(now.outcome) != row["outcome"]:
        raise _blocked("The situation changed after this was decided. Check again.")
    approved_by = None
    if now.outcome == Outcome.REQUIRE_APPROVAL:
        approval = fetch_one(
            "SELECT status, decided_by FROM approval_requests WHERE decision_id = %s", [decision_id]
        )
        if approval is None or approval["status"] != "APPROVED":
            raise _blocked("A person needs to approve this first.")
        approved_by = approval["decided_by"]
    elif now.outcome != Outcome.ALLOW_AUTOMATIC:
        raise _blocked("This action is not permitted right now.")
    if not execute(
        "UPDATE policy_decisions SET consumed_at = now() WHERE id = %s AND consumed_at IS NULL", [decision_id]
    ):
        raise _blocked("This decision was already used.")
    return authorized._mint(decision_id, str(req.action), str(req.subject), approved_by)  # noqa: SLF001


# --- approvals (E092) ---


def _approval_dto(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "decision_id": row["decision_id"],
        "status": row["status"],
        "decided_by": row["decided_by"],
        "decided_at": row["decided_at"],
        "note": row["note"],
    }


def decide_approval(
    ctx: RequestContext, approval_id: UUID, decision: str, note: str | None
) -> dict[str, Any]:
    authorize(ctx, DRAFT_APPROVE)
    with tenant_tx(ctx):
        row = fetch_one(
            "SELECT a.*, d.expires_at, d.action_type FROM approval_requests a"
            " JOIN policy_decisions d ON d.id = a.decision_id AND d.workspace_id = a.workspace_id"
            " WHERE a.id = %s AND a.workspace_id = %s FOR UPDATE OF a",
            [approval_id, ctx.workspace_id],
        )
        if row is None:
            raise ProblemError("NOT_FOUND", 404, "This approval does not exist.")
        if row["status"] != "PENDING":
            raise ProblemError("CONFLICT", 409, "This approval was already decided.")
        if row["expires_at"] <= clock.now():
            raise ProblemError("CONFLICT", 409, "This approval expired. Ask for a new check.")
        updated = fetch_one(
            "UPDATE approval_requests SET status = %s, decided_by = %s, decided_at = now(), note = %s"
            " WHERE id = %s RETURNING *",
            [decision, ctx.user_id, note, approval_id],
        )
        assert updated
        record(
            ctx,
            f"approval.{decision.lower()}",
            "approval_request",
            str(approval_id),
            before={"status": "PENDING"},
            after={"status": decision},
            policy_decision_id=row["decision_id"],
        )
        return _approval_dto(updated)


# --- why-view (E101) ---


def get_decision(ctx: RequestContext, decision_id: UUID) -> dict[str, Any]:
    authorize(ctx, AUDIT_INSPECT)
    with tenant_tx(ctx):
        row = fetch_one(
            "SELECT * FROM policy_decisions WHERE id = %s AND workspace_id = %s",
            [decision_id, ctx.workspace_id],
        )
        if row is None:
            raise ProblemError("NOT_FOUND", 404, "This decision does not exist.")
        approval = fetch_one("SELECT * FROM approval_requests WHERE decision_id = %s", [decision_id])
    results = tuple(GateResult(g["gate"], g["passed"], g["reason"]) for g in _json(row["gate_results"]))
    stored = PolicyDecision(
        Outcome(row["outcome"]),
        results,
        tuple(row["reasons"]),
        row["rules_version"],
        row["policy_version"],
        row["state_version"],
        row["inputs_hash"],
    )
    return {
        "id": row["id"],
        "action_type": row["action_type"],
        "outcome": row["outcome"],
        "explanation": explain(stored),
        "gates": [{"gate": g.gate, "passed": g.passed, "text": GATE_TEXT[g.gate]} for g in results],
        "policy_version": row["policy_version"],
        "rules_version": row["rules_version"],
        "state_version": row["state_version"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "consumed_at": row["consumed_at"],
        "approval": _approval_dto(approval) if approval else None,
    }
