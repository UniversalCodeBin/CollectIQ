"""What the gateway hands a provider. There is deliberately no field for tools or functions."""

from dataclasses import dataclass
from typing import Any, Protocol


class AIConfigurationError(RuntimeError):
    """The AI provider setting is unusable, or names a test adapter where it is not allowed."""


@dataclass(frozen=True)
class ProviderRequest:
    task_id: str
    instructions: str
    input: dict[str, Any]
    output_keys: tuple[str, ...]
    repair: bool = False
    previous_output: str | None = None


class Provider(Protocol):
    name: str
    model_version: str

    def complete(self, request: ProviderRequest) -> str:
        """Returns the model's raw text. Raises on timeout or transport failure."""
        ...


class FailoverProvider:
    """Tries each provider in order and returns the first answer. Reports which one answered."""

    def __init__(self, providers: list[Provider]) -> None:
        if not providers:
            raise AIConfigurationError("FailoverProvider needs at least one provider.")
        self._providers = providers
        self.name = "+".join(p.name for p in providers)
        self.model_version = providers[0].model_version

    def complete(self, request: ProviderRequest) -> str:
        last: Exception | None = None
        for provider in self._providers:
            try:
                reply = provider.complete(request)
            except Exception as exc:  # noqa: BLE001 - the next provider gets a turn
                last = exc
                continue
            self.model_version = provider.model_version
            return reply
        assert last is not None
        raise last
