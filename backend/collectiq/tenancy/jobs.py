from typing import Any

from collectiq.platform.context import RequestContext
from collectiq.platform.jobs import job_handler

from .service import send_invitation


@job_handler("tenancy.invitation_email")
def invitation_email(ctx: RequestContext, payload: dict[str, Any]) -> None:
    send_invitation(ctx, payload["invitation_id"])
