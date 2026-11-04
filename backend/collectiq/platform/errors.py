"""The one error type services raise for a problem+json response."""
from collections.abc import Mapping
from typing import Any


class ProblemError(Exception):
    def __init__(self, code: str, status: int, detail: str, extra: Mapping[str, Any] | None = None) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.status = status
        self.detail = detail
        self.extra = dict(extra or {})
