"""Who is acting, on which workspace, for one unit of work."""
from dataclasses import dataclass
from uuid import UUID

# Auth events and auth email happen before any workspace exists. They use this reserved scope, which no real
# workspace can have, so jobs and the audit chain keep their one shape.
GLOBAL_WORKSPACE_ID = UUID(int=0)


@dataclass(frozen=True, slots=True)
class RequestContext:
    workspace_id: UUID
    user_id: UUID | None
    role: str | None
    correlation_id: str
    actor_type: str


def global_context(correlation_id: str, user_id: UUID | None = None) -> RequestContext:
    return RequestContext(GLOBAL_WORKSPACE_ID, user_id, None, correlation_id, "USER" if user_id else "SYSTEM")
