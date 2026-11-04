"""Every endpoint in one table, and the guard each view runs through.

The authorization matrix and the TS-023 harness are both generated from this table, so a route cannot
exist without a stated permission. The guard's order matters: a role check comes before body validation
and object lookup, so a refused caller learns nothing from the shape of the error.
"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import wraps
from typing import Any
from uuid import UUID

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response

from collectiq.identity import session, throttle
from collectiq.platform.context import RequestContext
from collectiq.platform.errors import ProblemError
from collectiq.tenancy.permissions import (
    AI_PAYLOADS,
    AI_SETTINGS_READ,
    AI_SETTINGS_WRITE,
    AUDIT_INSPECT,
    AUDIT_READ,
    AUTOMATION_PAUSE,
    CASE_NOTE,
    CASE_OPEN,
    CASE_RESOLVE,
    CASES_READ,
    CLIENTS_READ,
    CLIENTS_WRITE,
    DELETION,
    DRAFT_APPROVE,
    DRAFT_CREATE,
    DRAFT_READ,
    EXPORT,
    FINANCE_READ,
    INTEGRATIONS_MANAGE,
    INTEGRATIONS_READ,
    INVOICES_READ,
    LEDGER_WRITE,
    MEMBERS_MANAGE,
    MEMBERS_READ,
    MESSAGES_LIST,
    MESSAGES_READ,
    MESSAGES_WRITE,
    POLICY_READ,
    POLICY_WRITE,
    REVIEW_INBOX,
    SENSITIVE,
    WORKSPACE_READ,
    WORKSPACE_UPDATE,
    authorize,
)
from collectiq.tenancy.service import role_in

from .common import correlation_id

logger = logging.getLogger(__name__)

_NO_ROLE_MODES = ("self", "session")


@dataclass(frozen=True)
class EndpointSpec:
    id: str
    method: str
    path: str
    permission: str
    audited: bool
    mutates: bool
    priority: str
    idempotent: bool
    versioned: bool


def _spec(
    endpoint_id: str, method: str, path: str, permission: str, flags: str, priority: str
) -> EndpointSpec:
    """`flags` holds the TSD's letters: A audited, I idempotent, V versioned."""
    return EndpointSpec(
        id=endpoint_id,
        method=method,
        path=path,
        permission=permission,
        audited="A" in flags,
        mutates=method != "GET",
        priority=priority,
        idempotent="I" in flags,
        versioned="V" in flags,
    )


_SPECS = (
    _spec("E001", "POST", "/auth/register", "public", "IA", "P0"),
    _spec("E002", "POST", "/auth/verify-email", "public", "A", "P0"),
    _spec("E003", "POST", "/auth/login", "public", "A", "P0"),
    _spec("E004", "POST", "/auth/logout", "session", "A", "P0"),
    _spec("E005", "POST", "/auth/password-reset/request", "public", "A", "P0"),
    _spec("E006", "POST", "/auth/password-reset/confirm", "public", "A", "P0"),
    _spec("E007", "POST", "/auth/mfa/enroll", "session", "A", "P1"),
    _spec("E008", "POST", "/auth/mfa/verify", "session", "A", "P1"),
    _spec("E009", "GET", "/auth/session", "session", "", "P0"),
    _spec("E010", "POST", "/workspaces", "session", "IA", "P0"),
    _spec("E011", "GET", "/workspaces/{ws}", WORKSPACE_READ, "", "P0"),
    _spec("E012", "PATCH", "/workspaces/{ws}", WORKSPACE_UPDATE, "AV", "P0"),
    _spec("E013", "GET", "/workspaces/{ws}/members", MEMBERS_READ, "", "P0"),
    _spec("E014", "POST", "/workspaces/{ws}/invitations", MEMBERS_MANAGE, "IA", "P0"),
    _spec("E015", "DELETE", "/workspaces/{ws}/members/{member_id}", MEMBERS_MANAGE, "IA", "P0"),
    _spec("E016", "GET", "/workspaces/{ws}/policy", POLICY_READ, "", "P0"),
    _spec("E017", "PUT", "/workspaces/{ws}/policy", POLICY_WRITE, "IA", "P0"),
    _spec("E018", "GET", "/workspaces/{ws}/policy/versions", POLICY_READ, "", "P0"),
    _spec("E019", "POST", "/workspaces/{ws}/automation/pause", AUTOMATION_PAUSE, "A", "P0"),
    _spec("E020", "POST", "/workspaces/{ws}/automation/resume", AUTOMATION_PAUSE, "A", "P0"),
    _spec("E021", "GET", "/workspaces/{ws}/clients", CLIENTS_READ, "", "P0"),
    _spec("E022", "POST", "/workspaces/{ws}/clients", CLIENTS_WRITE, "IA", "P0"),
    _spec("E023", "GET", "/workspaces/{ws}/clients/{client_id}", CLIENTS_READ, "", "P0"),
    _spec("E024", "PATCH", "/workspaces/{ws}/clients/{client_id}", CLIENTS_WRITE, "AV", "P0"),
    _spec("E025", "POST", "/workspaces/{ws}/clients/{client_id}/contacts", CLIENTS_WRITE, "IA", "P0"),
    _spec(
        "E026",
        "PATCH",
        "/workspaces/{ws}/clients/{client_id}/contacts/{contact_id}",
        CLIENTS_WRITE,
        "A",
        "P0",
    ),
    _spec("E027", "POST", "/workspaces/{ws}/contacts/{contact_id}/suppression", CLIENTS_WRITE, "IA", "P0"),
    _spec("E028", "DELETE", "/workspaces/{ws}/contacts/{contact_id}/suppression", CLIENTS_WRITE, "IA", "P0"),
    _spec("E029", "GET", "/workspaces/{ws}/payment-accounts", FINANCE_READ, "", "P0"),
    _spec("E030", "POST", "/workspaces/{ws}/payment-accounts", LEDGER_WRITE, "IA", "P0"),
    _spec("E031", "PATCH", "/workspaces/{ws}/payment-accounts/{account_id}", LEDGER_WRITE, "AV", "P0"),
    _spec("E032", "GET", "/workspaces/{ws}/payment-accounts/{account_id}/coverage", FINANCE_READ, "", "P0"),
    _spec("E033", "POST", "/workspaces/{ws}/imports/invoices", LEDGER_WRITE, "IA", "P0"),
    _spec("E034", "PUT", "/workspaces/{ws}/imports/{import_id}/mapping", LEDGER_WRITE, "A", "P0"),
    _spec("E035", "POST", "/workspaces/{ws}/imports/{import_id}/commit", LEDGER_WRITE, "IA", "P0"),
    _spec("E036", "DELETE", "/workspaces/{ws}/imports/{import_id}", LEDGER_WRITE, "A", "P0"),
    _spec("E037", "GET", "/workspaces/{ws}/imports/{import_id}", FINANCE_READ, "", "P0"),
    _spec("E038", "POST", "/workspaces/{ws}/invoices/pdf", LEDGER_WRITE, "IA", "P0"),
    _spec("E039", "GET", "/workspaces/{ws}/extractions/{extraction_id}", FINANCE_READ, "", "P0"),
    _spec("E040", "PATCH", "/workspaces/{ws}/extractions/{extraction_id}", LEDGER_WRITE, "AV", "P0"),
    _spec("E041", "POST", "/workspaces/{ws}/extractions/{extraction_id}/confirm", LEDGER_WRITE, "IA", "P0"),
    _spec("E042", "GET", "/workspaces/{ws}/invoices", INVOICES_READ, "", "P0"),
    _spec("E043", "GET", "/workspaces/{ws}/invoices/{invoice_id}", INVOICES_READ, "", "P0"),
    _spec("E044", "PATCH", "/workspaces/{ws}/invoices/{invoice_id}", LEDGER_WRITE, "AV", "P0"),
    _spec("E045", "POST", "/workspaces/{ws}/invoices/{invoice_id}/cancel", LEDGER_WRITE, "IA", "P0"),
    _spec("E046", "POST", "/workspaces/{ws}/invoices/{invoice_id}/archive", LEDGER_WRITE, "IA", "P0"),
    _spec("E047", "GET", "/workspaces/{ws}/queue", INVOICES_READ, "", "P0"),
    _spec("E048", "GET", "/workspaces/{ws}/dashboard", FINANCE_READ, "", "P0"),
    _spec("E049", "POST", "/workspaces/{ws}/payments", LEDGER_WRITE, "IA", "P0"),
    _spec("E050", "GET", "/workspaces/{ws}/payments", FINANCE_READ, "", "P0"),
    _spec("E051", "GET", "/workspaces/{ws}/payments/{payment_id}", FINANCE_READ, "", "P0"),
    _spec("E052", "POST", "/workspaces/{ws}/payments/{payment_id}/void", LEDGER_WRITE, "IA", "P0"),
    _spec("E053", "POST", "/workspaces/{ws}/imports/transactions", LEDGER_WRITE, "IA", "P0"),
    _spec("E054", "POST", "/workspaces/{ws}/attestations", LEDGER_WRITE, "IA", "P0"),
    _spec("E055", "GET", "/workspaces/{ws}/transactions/unmatched", FINANCE_READ, "", "P0"),
    _spec("E056", "GET", "/workspaces/{ws}/reconciliation/proposals", FINANCE_READ, "", "P0"),
    _spec(
        "E057",
        "POST",
        "/workspaces/{ws}/reconciliation/proposals/{proposal_id}/confirm",
        LEDGER_WRITE,
        "IA",
        "P0",
    ),
    _spec(
        "E058",
        "POST",
        "/workspaces/{ws}/reconciliation/proposals/{proposal_id}/reject",
        LEDGER_WRITE,
        "IA",
        "P0",
    ),
    _spec("E059", "POST", "/workspaces/{ws}/allocations", LEDGER_WRITE, "IA", "P0"),
    _spec("E060", "POST", "/workspaces/{ws}/allocations/{allocation_id}/reverse", LEDGER_WRITE, "IA", "P0"),
    _spec(
        "E061",
        "POST",
        "/workspaces/{ws}/transactions/{transaction_id}/mark-duplicate",
        LEDGER_WRITE,
        "IA",
        "P0",
    ),
    _spec("E062", "POST", "/workspaces/{ws}/messages", MESSAGES_WRITE, "IA", "P0"),
    _spec("E063", "GET", "/workspaces/{ws}/messages", MESSAGES_LIST, "", "P0"),
    _spec("E064", "GET", "/workspaces/{ws}/messages/{message_id}", MESSAGES_READ, "", "P0"),
    _spec("E065", "GET", "/workspaces/{ws}/invoices/{invoice_id}/messages", MESSAGES_READ, "", "P0"),
    _spec("E066", "POST", "/workspaces/{ws}/messages/{message_id}/associations", MESSAGES_WRITE, "IA", "P0"),
    _spec("E067", "GET", "/workspaces/{ws}/messages/{message_id}/interpretation", MESSAGES_READ, "", "P0"),
    _spec(
        "E068",
        "POST",
        "/workspaces/{ws}/interpretations/{interpretation_id}/accept",
        MESSAGES_WRITE,
        "IA",
        "P0",
    ),
    _spec(
        "E069",
        "POST",
        "/workspaces/{ws}/interpretations/{interpretation_id}/dismiss",
        MESSAGES_WRITE,
        "IA",
        "P0",
    ),
    _spec(
        "E070",
        "POST",
        "/workspaces/{ws}/interpretations/{interpretation_id}/correct",
        MESSAGES_WRITE,
        "IA",
        "P0",
    ),
    _spec("E071", "GET", "/workspaces/{ws}/invoices/{invoice_id}/commitments", MESSAGES_READ, "", "P0"),
    _spec("E072", "POST", "/workspaces/{ws}/commitments", MESSAGES_WRITE, "IA", "P0"),
    _spec("E073", "PATCH", "/workspaces/{ws}/commitments/{commitment_id}", MESSAGES_WRITE, "AV", "P0"),
    _spec(
        "E074",
        "POST",
        "/workspaces/{ws}/invoices/{invoice_id}/snooze/approve",
        MESSAGES_WRITE,
        "IA",
        "P0",
    ),
    _spec("E075", "POST", "/workspaces/{ws}/invoices/{invoice_id}/snooze/undo", MESSAGES_WRITE, "IA", "P0"),
    _spec("E076", "GET", "/workspaces/{ws}/cases", CASES_READ, "", "P0"),
    _spec("E077", "GET", "/workspaces/{ws}/cases/{case_id}", CASES_READ, "", "P0"),
    _spec("E078", "POST", "/workspaces/{ws}/cases", CASE_OPEN, "IA", "P0"),
    _spec("E079", "PATCH", "/workspaces/{ws}/cases/{case_id}", CASE_NOTE, "AV", "P0"),
    _spec("E080", "POST", "/workspaces/{ws}/cases/{case_id}/resolve", CASE_RESOLVE, "IA", "P0"),
    _spec("E081", "POST", "/workspaces/{ws}/cases/{case_id}/reopen", CASE_RESOLVE, "IA", "P0"),
    _spec(
        "E082",
        "POST",
        "/workspaces/{ws}/invoices/{invoice_id}/followups/resume",
        CASE_RESOLVE,
        "IA",
        "P0",
    ),
    _spec("E083", "GET", "/workspaces/{ws}/reminders", DRAFT_READ, "", "P0"),
    _spec("E084", "GET", "/workspaces/{ws}/reminders/{reminder_id}", DRAFT_READ, "", "P0"),
    _spec(
        "E085",
        "POST",
        "/workspaces/{ws}/invoices/{invoice_id}/reminders/evaluate",
        DRAFT_CREATE,
        "IA",
        "P0",
    ),
    _spec("E086", "PATCH", "/workspaces/{ws}/reminders/{reminder_id}", DRAFT_APPROVE, "AV", "P0"),
    _spec("E087", "POST", "/workspaces/{ws}/reminders/{reminder_id}/approve", DRAFT_APPROVE, "IA", "P0"),
    _spec("E088", "POST", "/workspaces/{ws}/reminders/{reminder_id}/reject", DRAFT_APPROVE, "IA", "P0"),
    _spec("E089", "POST", "/workspaces/{ws}/reminders/{reminder_id}/mark-sent", DRAFT_APPROVE, "IA", "P0"),
    _spec("E090", "POST", "/workspaces/{ws}/reminders/{reminder_id}/send", DRAFT_APPROVE, "IA", "P1"),
    _spec(
        "E091",
        "POST",
        "/workspaces/{ws}/reminders/{reminder_id}/confirm-unknown",
        DRAFT_APPROVE,
        "IA",
        "P1",
    ),
    _spec("E092", "POST", "/workspaces/{ws}/approvals/{approval_id}/decide", DRAFT_APPROVE, "IA", "P0"),
    _spec("E093", "GET", "/workspaces/{ws}/integrations", INTEGRATIONS_READ, "", "P0"),
    _spec("E094", "POST", "/workspaces/{ws}/integrations/gmail/connect", INTEGRATIONS_MANAGE, "A", "P1"),
    _spec("E095", "GET", "/integrations/gmail/callback", "session", "A", "P1"),
    _spec("E096", "POST", "/workspaces/{ws}/integrations/gmail/monitoring", INTEGRATIONS_MANAGE, "A", "P1"),
    _spec(
        "E097",
        "DELETE",
        "/workspaces/{ws}/integrations/{integration_id}",
        INTEGRATIONS_MANAGE,
        "IA",
        "P1",
    ),
    _spec("E098", "POST", "/webhooks/paypal", "webhook", "A", "P1"),
    _spec("E099", "GET", "/workspaces/{ws}/audit-events", AUDIT_READ, "", "P0"),
    _spec("E100", "POST", "/workspaces/{ws}/audit-events/exports", EXPORT, "IA", "P0"),
    _spec("E101", "GET", "/workspaces/{ws}/policy-decisions/{decision_id}", AUDIT_INSPECT, "", "P0"),
    _spec("E102", "POST", "/workspaces/{ws}/exports", EXPORT, "IA", "P0"),
    _spec("E103", "GET", "/workspaces/{ws}/exports/{export_id}", EXPORT, "", "P0"),
    _spec("E104", "POST", "/workspaces/{ws}/deletion", DELETION, "IA", "P0"),
    _spec("E105", "GET", "/workspaces/{ws}/ai/payloads", AI_PAYLOADS, "A", "P0"),
    _spec("E106", "GET", "/workspaces/{ws}/notifications", "self", "", "P0"),
    _spec("E107", "POST", "/workspaces/{ws}/notifications/{notification_id}/read", "self", "", "P0"),
    _spec("E108", "GET", "/workspaces/{ws}/review-inbox", REVIEW_INBOX, "", "P0"),
    _spec("E109", "GET", "/workspaces/{ws}/ai/settings", AI_SETTINGS_READ, "", "P0"),
    _spec("E110", "PUT", "/workspaces/{ws}/ai/settings", AI_SETTINGS_WRITE, "IA", "P0"),
    _spec("E111", "GET", "/health/live", "infra", "", "P0"),
    _spec("E112", "GET", "/health/ready", "infra", "", "P0"),
    # Proposed additions, not yet in the TSD table. See docs/api/endpoint-status.yaml.
    _spec("E113", "POST", "/auth/verify-email/resend", "public", "A", "P0"),
    _spec("E114", "POST", "/invitations/accept", "session", "A", "P0"),
    _spec("E115", "PATCH", "/workspaces/{ws}/members/{member_id}", MEMBERS_MANAGE, "A", "P0"),
)

ENDPOINTS: dict[str, EndpointSpec] = {spec.id: spec for spec in _SPECS}
BOUND: set[str] = set()


class _CsrfCheck(CsrfViewMiddleware):
    def _reject(self, request: Any, reason: str) -> str:
        return reason


def _noop_response(request: Any) -> Any:
    raise RuntimeError("The CSRF check never calls through")


def _enforce_csrf(request: Any) -> None:
    check = _CsrfCheck(_noop_response)
    check.process_request(request._request)
    reason = check.process_view(request._request, _noop_response, (), {})
    if reason:
        raise ProblemError("FORBIDDEN", 403, "This request could not be verified. Reload and try again.")


def _check_origin(request: Any) -> None:
    """A public POST has no CSRF token yet. A foreign Origin still has no business sending one."""
    origin = request.headers.get("Origin")
    if (
        origin
        and origin != f"{request.scheme}://{request.get_host()}"
        and origin not in settings.CSRF_TRUSTED_ORIGINS
    ):
        raise ProblemError("FORBIDDEN", 403, "This request could not be verified.")


def _auth_required() -> ProblemError:
    return ProblemError("AUTH_REQUIRED", 401, "Please sign in to continue.")


def _workspace_context(request: Any, spec: EndpointSpec, principal: session.Principal, ws: UUID) -> None:
    if not principal.verified:
        raise ProblemError("FORBIDDEN", 403, "Verify your email address to continue.")
    role = role_in(principal.user_id, ws)
    if role is None:
        # The same answer as a workspace that does not exist. Only the log says otherwise (SEC-07).
        logger.warning(
            "workspace_access_refused",
            extra={"workspace_id": str(ws), "user_id": str(principal.user_id), "endpoint_id": spec.id},
        )
        raise ProblemError("NOT_FOUND", 404, "We could not find that.")
    request.ctx = RequestContext(ws, principal.user_id, role, correlation_id(request), "USER")
    if spec.permission not in _NO_ROLE_MODES:
        authorize(request.ctx, spec.permission)


def _guard(request: Any, spec: EndpointSpec, kwargs: dict[str, Any]) -> None:
    if spec.permission in ("infra", "webhook"):
        return
    if spec.permission == "public":
        if spec.mutates:
            _check_origin(request)
        throttle.check_ip(request.META.get("REMOTE_ADDR", ""))
        return
    raw = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
    principal = session.authenticate(raw) if raw else None
    if principal is None:
        raise _auth_required()
    if principal.idle and spec.permission in SENSITIVE:
        raise _auth_required()
    session.touch(principal.session_id)
    if spec.mutates:
        _enforce_csrf(request)
    request.principal = principal
    if "ws" in kwargs:
        _workspace_context(request, spec, principal, kwargs["ws"])


def _headers(spec: EndpointSpec) -> Iterable[OpenApiParameter]:
    if spec.idempotent:
        yield OpenApiParameter("Idempotency-Key", OpenApiTypes.UUID, OpenApiParameter.HEADER, required=True)
    if spec.versioned:
        yield OpenApiParameter("If-Match", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True)


def endpoint(
    endpoint_id: str,
    *,
    request: Any = None,
    responses: Any = None,
    parameters: Iterable[Any] = (),
) -> Callable[[Callable[..., Response]], Callable[..., Response]]:
    """Bind a view method to its row in the table. Goes outside `@idempotent`, so a refusal claims no key."""
    spec = ENDPOINTS[endpoint_id]

    def decorate(method: Callable[..., Response]) -> Callable[..., Response]:
        @wraps(method)
        def wrapper(view: Any, req: Any, *args: Any, **kwargs: Any) -> Response:
            _guard(req, spec, kwargs)
            return method(view, req, *args, **kwargs)

        wrapper.endpoint_id = endpoint_id  # type: ignore[attr-defined]
        BOUND.add(endpoint_id)
        documented: Callable[..., Response] = extend_schema(
            operation_id=endpoint_id,
            request=request,
            responses=responses,
            parameters=[*_headers(spec), *parameters],
            extensions={"x-endpoint-id": endpoint_id},
        )(wrapper)
        return documented

    return decorate
