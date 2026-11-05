"""Keeps the redacted input exactly as it was sent to the provider, apart from the processing record.

Only the redacted form is stored: personal details were already replaced by tokens such as [EMAIL_1].
Retention clears it on a schedule (see `settings_privacy.service.apply_retention`).
"""

import json
from typing import Any
from uuid import UUID

from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute


def keep_redacted_input(ctx: RequestContext, processing_id: UUID, redacted: dict[str, Any] | None) -> None:
    """Inside a tenant transaction."""
    if redacted is None:
        return
    execute(
        "INSERT INTO ai_payloads (workspace_id, processing_id, redacted_input) VALUES (%s, %s, %s::jsonb)",
        [ctx.workspace_id, processing_id, json.dumps(redacted, default=str)],
    )
