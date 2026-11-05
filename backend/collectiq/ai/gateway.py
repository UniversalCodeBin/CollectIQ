"""The only door to a model. allowlist → minimise → redact → pseudonymise → cap → call → parse → validate.

The caller persists the processing record from the result.
Nothing here reads a database or imports a domain module.
"""

import hashlib
import json
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .providers.base import AIConfigurationError, Provider, ProviderRequest
from .providers.fake import FakeProvider
from .redaction import Redactor
from .registry import TASKS
from .schemas import validate


@dataclass(frozen=True)
class AIConfig:
    kill_switch: bool = False
    max_retries: int = 1
    timeout_seconds: float = 20.0
    rate_limit: int = 60
    rate_window_seconds: int = 60


@dataclass(frozen=True)
class AIResult:
    task_id: str
    # OK, AI_NOT_CONFIGURED, DISABLED, RATE_LIMITED, PROVIDER_ERROR, INVALID_OUTPUT or UNKNOWN_TASK
    status: str
    data: dict[str, Any] | None = None
    provider: str | None = None
    model_version: str | None = None
    input_sha256: str = ""
    redacted_input: dict[str, Any] | None = None
    dropped_fields: tuple[str, ...] = ()
    repaired: bool = False
    attempts: int = 0
    error: str | None = None


def build_provider(name: str, *, production: bool) -> Provider | None:
    name = (name or "none").strip().lower()
    if name == "none":
        return None
    if name == "fake":
        if production:
            raise AIConfigurationError("AI_PROVIDER=fake is a test adapter and is refused in production.")
        return FakeProvider()
    raise AIConfigurationError(f"No AI provider adapter named {name!r} is installed.")


class Gateway:
    def __init__(
        self,
        provider: Provider | None,
        config: AIConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._provider = provider
        self._config = config or AIConfig()
        self._clock = clock
        self._calls: dict[str, deque[float]] = defaultdict(deque)

    def _limited(self, scope: str) -> bool:
        now = self._clock()
        window = self._calls[scope]
        while window and now - window[0] >= self._config.rate_window_seconds:
            window.popleft()
        if len(window) >= self._config.rate_limit:
            return True
        window.append(now)
        return False

    def run(self, task_id: str, payload: dict[str, Any], scope: str = "global") -> AIResult:
        spec = TASKS.get(task_id)
        if spec is None:
            return AIResult(task_id, "UNKNOWN_TASK")
        if self._config.kill_switch:
            return AIResult(task_id, "DISABLED")
        if self._provider is None:
            return AIResult(task_id, "AI_NOT_CONFIGURED")
        if self._limited(scope):
            return AIResult(task_id, "RATE_LIMITED", provider=self._provider.name)

        dropped = tuple(sorted(set(payload) - set(spec.allowed_fields)))
        redactor = Redactor()
        minimised: dict[str, Any] = {}
        for key in spec.allowed_fields:
            if key not in payload or payload[key] is None:
                continue
            value = payload[key]
            if isinstance(value, str):
                value = (
                    redactor.name(value)
                    if key in spec.pseudonymise
                    else redactor.text(value)[: spec.max_chars]
                )
            minimised[key] = value
        digest = hashlib.sha256(json.dumps(minimised, sort_keys=True, default=str).encode()).hexdigest()
        base: dict[str, Any] = {
            "task_id": task_id,
            "provider": self._provider.name,
            "model_version": self._provider.model_version,
            "input_sha256": digest,
            "redacted_input": minimised,
            "dropped_fields": dropped,
        }
        request = ProviderRequest(task_id, spec.instructions, minimised, tuple(spec.output))
        attempts = 0
        raw: str | None = None
        for _ in range(self._config.max_retries + 1):
            attempts += 1
            try:
                raw = self._provider.complete(request)
                break
            except Exception as exc:  # noqa: BLE001 - any provider failure degrades to the same safe state
                error = type(exc).__name__
        if raw is None:
            return AIResult(status="PROVIDER_ERROR", attempts=attempts, error=error, **base)

        data = _parse(raw, spec.output)
        repaired = False
        if data is None:
            repaired = True
            attempts += 1
            repair = ProviderRequest(
                task_id,
                spec.instructions,
                minimised,
                tuple(spec.output),
                repair=True,
                previous_output=raw[:2000],
            )
            try:
                data = _parse(self._provider.complete(repair), spec.output)
            except Exception as exc:  # noqa: BLE001
                return AIResult(
                    status="PROVIDER_ERROR",
                    repaired=True,
                    attempts=attempts,
                    error=type(exc).__name__,
                    **base,
                )
        if data is None:
            return AIResult(status="INVALID_OUTPUT", repaired=repaired, attempts=attempts, **base)
        return AIResult(status="OK", data=data, repaired=repaired, attempts=attempts, **base)


def _parse(raw: str, shape: dict[str, Any]) -> dict[str, Any] | None:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if validate(data, shape) else None
