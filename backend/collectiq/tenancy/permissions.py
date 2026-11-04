"""Who may do what. Deny by default: a permission or role not named here is refused (TSD M03, L685-696)."""
from collectiq.audit import record
from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx
from collectiq.platform.errors import ProblemError

_O = frozenset({"OWNER"})
_OF = frozenset({"OWNER", "FINANCE_ADMIN"})
_OFL = frozenset({"OWNER", "FINANCE_ADMIN", "PROJECT_LEAD"})

WORKSPACE_READ = "workspace.read"
WORKSPACE_UPDATE = "workspace.update"
MEMBERS_READ = "members.read"
MEMBERS_MANAGE = "members.manage"
POLICY_READ = "policy.read"
POLICY_WRITE = "policy.write"
AUTOMATION_PAUSE = "automation.pause"
CLIENTS_READ = "clients.read"
CLIENTS_WRITE = "clients.write"
FINANCE_READ = "finance.read"
INVOICES_READ = "invoices.read"
LEDGER_WRITE = "ledger.write"
CASES_READ = "cases.read"
CASE_OPEN = "case.open"
CASE_NOTE = "case.note"
CASE_RESOLVE = "case.resolve"
MESSAGES_LIST = "messages.list"
MESSAGES_READ = "messages.read"
MESSAGES_WRITE = "messages.write"
DRAFT_READ = "draft.read"
DRAFT_CREATE = "draft.create"
DRAFT_APPROVE = "draft.approve"
INTEGRATIONS_READ = "integrations.read"
INTEGRATIONS_MANAGE = "integrations.manage"
AUDIT_READ = "audit.read"
AUDIT_INSPECT = "audit.inspect"
EXPORT = "export"
DELETION = "deletion"
AI_PAYLOADS = "ai.payloads"
AI_SETTINGS_READ = "ai.settings.read"
AI_SETTINGS_WRITE = "ai.settings.write"
REVIEW_INBOX = "review.inbox"

_MATRIX: dict[str, frozenset[str]] = {
    WORKSPACE_READ: _OF,
    WORKSPACE_UPDATE: _O,
    MEMBERS_READ: _OF,
    MEMBERS_MANAGE: _O,
    POLICY_READ: _OF,
    POLICY_WRITE: _OF,
    AUTOMATION_PAUSE: _OF,
    CLIENTS_READ: _OFL,
    CLIENTS_WRITE: _OF,
    FINANCE_READ: _OF,
    INVOICES_READ: _OFL,
    LEDGER_WRITE: _OF,
    CASES_READ: _OFL,
    CASE_OPEN: _OF,
    CASE_NOTE: _OFL,
    CASE_RESOLVE: _OF,
    MESSAGES_LIST: _OF,
    MESSAGES_READ: _OFL,
    MESSAGES_WRITE: _OF,
    DRAFT_READ: _OFL,
    DRAFT_CREATE: _OF,
    DRAFT_APPROVE: _OF,
    INTEGRATIONS_READ: _OF,
    INTEGRATIONS_MANAGE: _O,
    AUDIT_READ: _OFL,
    AUDIT_INSPECT: _OF,
    EXPORT: _OF,
    DELETION: _O,
    AI_PAYLOADS: _OF,
    AI_SETTINGS_READ: _OF,
    AI_SETTINGS_WRITE: _O,
    REVIEW_INBOX: _OFL,
}

# INV-03, INV-06: anything that is not a person may open a case or draft a reminder, and nothing more.
_NON_HUMAN = frozenset({CASE_OPEN, DRAFT_CREATE})

# FR-155 asks for the idle limit on these, and TSD M03 audits a refusal of them.
SENSITIVE = frozenset(
    {MEMBERS_MANAGE, POLICY_WRITE, AUTOMATION_PAUSE, INTEGRATIONS_MANAGE, DELETION, AI_SETTINGS_WRITE}
)


def allowed_roles(permission: str) -> set[str]:
    return set(_MATRIX.get(permission, ()))


def is_allowed(role: str | None, actor_type: str, permission: str) -> bool:
    if actor_type != "USER":
        return permission in _NON_HUMAN
    return role in _MATRIX.get(permission, ())


def authorize(ctx: RequestContext, permission: str) -> None:
    if is_allowed(ctx.role, ctx.actor_type, permission):
        return
    if permission in SENSITIVE:
        with tenant_tx(ctx):
            record(ctx, "authz.denied", "permission", permission)
    raise ProblemError("FORBIDDEN", 403, "You do not have permission to do this.")
