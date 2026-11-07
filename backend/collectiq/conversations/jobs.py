"""Background jobs owned by the conversations module (queued nightly by `schedule_nightly`)."""

from typing import Any

from collectiq.platform.context import RequestContext
from collectiq.platform.jobs import job_handler

from .service_commitments import end_expired_snoozes


@job_handler("conversations.snooze_expiry")
def snooze_expiry(ctx: RequestContext, payload: dict[str, Any]) -> None:
    end_expired_snoozes(ctx)
