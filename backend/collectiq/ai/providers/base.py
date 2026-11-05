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
