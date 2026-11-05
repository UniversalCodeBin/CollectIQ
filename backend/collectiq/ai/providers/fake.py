"""A scripted test adapter. It never leaves the process and is refused in production."""

from collections import deque

from .base import ProviderRequest


class FakeProvider:
    name = "fake"
    model_version = "fake-1"

    def __init__(self, script: list[str | Exception] | None = None) -> None:
        self._script: deque[str | Exception] = deque(script or [])
        self.requests: list[ProviderRequest] = []

    def complete(self, request: ProviderRequest) -> str:
        self.requests.append(request)
        if not self._script:
            raise TimeoutError("fake provider has no scripted response")
        item = self._script.popleft()
        if isinstance(item, Exception):
            raise item
        return item
