"""The capability that proves a policy decision allowed an action (SAD §8).

Only `collectiq.policy.service.authorize_execution` mints one, inside the executor's transaction, after it has
consumed the decision. An executor takes an `AuthorizedAction` as a parameter, so it cannot run without one.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

_MINT = object()


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizedAction:
    decision_id: UUID
    action: str
    subject: str
    approved_by: UUID | None
    _token: Any

    def __post_init__(self) -> None:
        if self._token is not _MINT:
            raise TypeError("An AuthorizedAction is issued by the policy service only.")


def _mint(decision_id: UUID, action: str, subject: str, approved_by: UUID | None) -> AuthorizedAction:
    return AuthorizedAction(
        decision_id=decision_id, action=action, subject=subject, approved_by=approved_by, _token=_MINT
    )
