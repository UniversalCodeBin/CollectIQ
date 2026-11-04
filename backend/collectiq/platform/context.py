"""Who is acting, on which workspace, for one unit of work."""
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RequestContext:
    workspace_id: UUID
    user_id: UUID | None
    role: str | None
    correlation_id: str
    actor_type: str
