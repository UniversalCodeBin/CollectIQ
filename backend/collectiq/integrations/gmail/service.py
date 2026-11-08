"""Gmail send-only connection and submission. Off unless FEATURE_GMAIL_SEND; not verified against Google."""

import hashlib
import secrets
from base64 import urlsafe_b64encode
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings

from collectiq.comms import service_send
from collectiq.integrations import service as connections
from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from collectiq.platform.crypto import get_cipher
from collectiq.platform.db import execute, fetch_one, tenant_tx, user_tx
from collectiq.platform.errors import ProblemError
from collectiq.tenancy.permissions import INTEGRATIONS_MANAGE, authorize
from collectiq.tenancy.service import role_in

from .transport import SEND_SCOPE, NotConfigured, ProviderRejected, ProviderUnknown, get_transport

_STATE_AAD = b"oauth-state"
_CRED_AAD = b"gmail-credential"
_STATE_TTL = timedelta(minutes=10)


def _enabled() -> None:
    if not settings.FEATURE_GMAIL_SEND:
        raise ProblemError("FEATURE_DISABLED", 409, "Sending through Gmail is not turned on.")


def _digest(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def start(ctx: RequestContext) -> dict[str, str]:
    authorize(ctx, INTEGRATIONS_MANAGE)
    _enabled()
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    challenge = urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    try:
        url = get_transport().authorization_url(state, challenge)
    except NotConfigured as exc:
        raise ProblemError("NOT_CONFIGURED", 409, "Gmail is not set up in this deployment.") from exc
    with tenant_tx(ctx):
        sealed = get_cipher().encrypt(ctx, verifier.encode(), _STATE_AAD)
        execute(
            "INSERT INTO oauth_states"
            " (state_hash, workspace_id, user_id, provider, verifier_sealed, expires_at)"
            " VALUES (%s, %s, %s, 'GMAIL', %s, %s)",
            [_digest(state), ctx.workspace_id, ctx.user_id, sealed, clock.now() + _STATE_TTL],
        )
    return {"authorization_url": url}


def complete(user_id: UUID, correlation_id: str, state: str, code: str) -> UUID:
    """Returns the workspace to send the person back to."""
    _enabled()
    with user_tx(user_id):
        row = fetch_one("SELECT * FROM consume_oauth_state(%s, %s)", [_digest(state), user_id])
    if not row:
        raise ProblemError("VALIDATION_FAILED", 400, "This connection link is not valid or has expired.")
    workspace_id = row["workspace_id"]
    role = role_in(user_id, workspace_id)
    if role is None:
        raise ProblemError("NOT_FOUND", 404, "We could not find that.")
    ctx = RequestContext(workspace_id, user_id, role, correlation_id, "USER")
    authorize(ctx, INTEGRATIONS_MANAGE)
    with tenant_tx(ctx):
        verifier = get_cipher().decrypt(ctx, bytes(row["verifier_sealed"]), _STATE_AAD).decode()
    try:
        granted = get_transport().exchange(code, verifier)
    except NotConfigured as exc:
        raise ProblemError("NOT_CONFIGURED", 409, "Gmail is not set up in this deployment.") from exc
    scopes = sorted(set(granted.get("scopes", [])))
    only_send = scopes == [SEND_SCOPE]
    if only_send:
        with tenant_tx(ctx):
            sealed = get_cipher().encrypt(ctx, str(granted["refresh_token"]).encode(), _CRED_AAD)
            execute(
                "INSERT INTO oauth_credential_refs (workspace_id, provider, sealed, scopes)"
                " VALUES (%s, 'GMAIL', %s, %s)"
                " ON CONFLICT (workspace_id, provider) DO UPDATE SET sealed = EXCLUDED.sealed,"
                " scopes = EXCLUDED.scopes, updated_at = now()",
                [ctx.workspace_id, sealed, scopes],
            )
    connections.connect(ctx, "GMAIL", lambda: only_send)
    if not only_send:
        raise ProblemError("CONFLICT", 409, "Only permission to send was expected, so nothing was connected.")
    return workspace_id


def disconnect(ctx: RequestContext) -> dict[str, Any]:
    authorize(ctx, INTEGRATIONS_MANAGE)
    credential = _credential(ctx)

    def cleanup() -> None:
        execute(
            "DELETE FROM oauth_credential_refs WHERE workspace_id = %s AND provider = 'GMAIL'",
            [ctx.workspace_id],
        )

    result = connections.disconnect(ctx, "GMAIL", cleanup)
    if credential:
        try:
            get_transport().revoke(credential)
        except (NotConfigured, ProviderUnknown, ProviderRejected):
            pass  # the local credential is already gone; revocation at the provider is best effort
    return result


def _credential(ctx: RequestContext) -> str | None:
    with tenant_tx(ctx):
        row = fetch_one(
            "SELECT sealed FROM oauth_credential_refs WHERE workspace_id = %s AND provider = 'GMAIL'",
            [ctx.workspace_id],
        )
        if not row:
            return None
        return get_cipher().decrypt(ctx, bytes(row["sealed"]), _CRED_AAD).decode()


def send_reminder(ctx: RequestContext, reminder_id: UUID) -> dict[str, Any]:
    _enabled()
    credential = None
    with tenant_tx(ctx):
        if connections.is_connected(ctx, "GMAIL"):
            row = fetch_one(
                "SELECT sealed FROM oauth_credential_refs WHERE workspace_id = %s AND provider = 'GMAIL'",
                [ctx.workspace_id],
            )
            if row:
                credential = get_cipher().decrypt(ctx, bytes(row["sealed"]), _CRED_AAD).decode()
    if credential is None:
        raise ProblemError("NOT_CONNECTED", 409, "Connect Gmail before sending.")
    message = service_send.begin(ctx, reminder_id)
    try:
        message_id = get_transport().send(credential, message["to"], message["subject"], message["body"])
    except ProviderRejected:
        service_send.finish(ctx, reminder_id, "REJECTED", error="The provider refused the message.")
        raise ProblemError("PROVIDER_REJECTED", 502, "Gmail refused the message. It was not sent.") from None
    except (ProviderUnknown, NotConfigured):
        return service_send.finish(
            ctx, reminder_id, "UNKNOWN", error="The result of the submission is not known."
        )
    return service_send.finish(ctx, reminder_id, "SUBMITTED", message_id=message_id)


def start_monitoring(ctx: RequestContext) -> dict[str, Any]:
    """Reading replies needs a read permission this build never requests (send only). Refused, not faked."""
    authorize(ctx, INTEGRATIONS_MANAGE)
    raise ProblemError(
        "NOT_AVAILABLE",
        409,
        "Watching Gmail for replies is not available. It needs read permission, which is not requested.",
    )
