"""TS-023 probe. Watches every API call made by any test and every audit insert, then checks the pairing.

A successful, non-replayed call to an audited mutating endpoint must write at least one audit event under
that request's correlation ID, with an actor type, a workspace (when the path has one), an object type, an
object ID and the correlation ID itself. Nothing here changes behaviour; it only observes.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from django.db.backends.utils import CursorWrapper
from django.http import HttpRequest, HttpResponse

from collectiq.platform.logging import current_correlation_id

# Column order of the INSERT in collectiq.audit.service.record.
_COLUMNS = (
    "workspace_id", "actor_type", "actor_id", "action", "object_type", "object_id",
    "before_masked", "after_masked", "reason_codes", "evidence_refs", "policy_decision_id", "correlation_id",
)  # fmt: skip


@dataclass
class Probe:
    audits: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    seen_ok: set[str] = field(default_factory=set)
    violations: list[str] = field(default_factory=list)
    keys: set[str] = field(default_factory=set)
    installed: bool = False

    def reset(self) -> None:
        self.audits.clear()
        self.seen_ok.clear()
        self.violations.clear()
        self.keys.clear()


PROBE = Probe()
_original: Callable[..., Any] | None = None


def install() -> None:
    global _original
    if PROBE.installed:
        return
    _original = CursorWrapper.execute

    def execute(self: CursorWrapper, sql: Any, params: Any = None) -> Any:
        text = str(sql)
        if "INSERT INTO audit_events" in text and params is not None and len(params) == len(_COLUMNS):
            row = dict(zip(_COLUMNS, params, strict=True))
            PROBE.audits[str(row["correlation_id"])].append(row)
        return _original(self, sql, params)  # type: ignore[misc]

    CursorWrapper.execute = execute  # type: ignore[method-assign]
    PROBE.installed = True


def _endpoint_id(request: HttpRequest) -> str | None:
    match = getattr(request, "resolver_match", None)
    view_class = getattr(getattr(match, "func", None), "view_class", None)
    handler = getattr(view_class, request.method.lower(), None) if view_class and request.method else None
    return getattr(handler, "endpoint_id", None)


def _problems(row: dict[str, Any], has_workspace: bool) -> list[str]:
    missing = [
        name
        for name in ("actor_type", "action", "object_type", "object_id", "correlation_id")
        if not row[name]
    ]
    if has_workspace and not row["workspace_id"]:
        missing.append("workspace_id")
    return missing


class ProbeMiddleware:
    """Innermost middleware, so the correlation ID bound by the outer one is still current."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        try:
            self._check(request, response)
        except Exception as error:  # noqa: BLE001 - the probe must never break a request
            PROBE.violations.append(f"probe failure: {error!r}")
        return response

    def _check(self, request: HttpRequest, response: HttpResponse) -> None:
        from collectiq.api.registry import ENDPOINTS  # noqa: PLC0415

        endpoint_id = _endpoint_id(request)
        if endpoint_id is None or not (200 <= response.status_code < 300):
            return
        spec = ENDPOINTS[endpoint_id]
        if not spec.mutates:
            return
        if getattr(response, "_no_mutation", False):
            return
        key = request.headers.get("Idempotency-Key")
        if key and f"{endpoint_id}:{key}" in PROBE.keys:
            return  # a replay returns the stored response and writes nothing
        if key:
            PROBE.keys.add(f"{endpoint_id}:{key}")
        PROBE.seen_ok.add(endpoint_id)
        if not spec.audited:
            return
        rows = PROBE.audits.get(current_correlation_id() or "", [])
        if not rows:
            PROBE.violations.append(f"{endpoint_id} {request.method} {request.path} wrote no audit event")
            return
        for row in rows:
            gaps = _problems(row, "{ws}" in spec.path)
            if gaps:
                PROBE.violations.append(f"{endpoint_id} audit event {row['action']!r} lacks {gaps}")
