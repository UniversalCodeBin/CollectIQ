"""Every API error as application/problem+json, with the SAD's codes and a correlation ID."""
import logging
from collections.abc import Iterator, Mapping
from typing import Any
from uuid import uuid4

from django.core.exceptions import PermissionDenied, RequestDataTooBig
from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response

from .errors import ProblemError
from .logging import current_correlation_id

logger = logging.getLogger(__name__)

CONTENT_TYPE = "application/problem+json"

# (exception, code, status). The status is fixed here because the catalogue, not DRF's default, is the
# contract.
_DRF_MAPPING: tuple[tuple[type[Exception], str, int], ...] = (
    (exceptions.NotAuthenticated, "AUTH_REQUIRED", 401),
    (exceptions.AuthenticationFailed, "AUTH_REQUIRED", 401),
    (exceptions.PermissionDenied, "FORBIDDEN", 403),
    (exceptions.NotFound, "NOT_FOUND", 404),
    (exceptions.ValidationError, "VALIDATION_FAILED", 422),
    (exceptions.ParseError, "VALIDATION_FAILED", 422),
    (exceptions.UnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE", 415),
    (exceptions.Throttled, "RATE_LIMITED", 429),
    (exceptions.MethodNotAllowed, "METHOD_NOT_ALLOWED", 405),
    (exceptions.NotAcceptable, "NOT_ACCEPTABLE", 406),
)


def _correlation_id(request: Any) -> str:
    ctx = getattr(request, "ctx", None)
    return ctx.correlation_id if ctx else current_correlation_id() or str(uuid4())


def _problem(
    request: Any,
    code: str,
    status: int,
    detail: str,
    extra: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> Response:
    body = {
        "type": f"/problems/{code.lower().replace('_', '-')}",
        "title": code.replace("_", " ").capitalize(),
        "status": status,
        "code": code,
        "detail": detail,
        "correlation_id": _correlation_id(request),
        **(extra or {}),
    }
    return Response(body, status=status, headers=headers, content_type=CONTENT_TYPE)


def _field_errors(detail: Any, field: str | None = None) -> Iterator[dict[str, str | None]]:
    if isinstance(detail, Mapping):
        for name, item in detail.items():
            yield from _field_errors(item, f"{field}.{name}" if field else str(name))
    elif isinstance(detail, list):
        for item in detail:
            yield from _field_errors(item, field)
    else:
        yield {"field": field, "message": str(detail)}


def _api_exception(exc: exceptions.APIException, request: Any) -> Response:
    headers = {}
    if getattr(exc, "auth_header", None):
        headers["WWW-Authenticate"] = exc.auth_header
    if getattr(exc, "wait", None):
        headers["Retry-After"] = str(int(exc.wait))
    code, status = next(
        ((code, status) for kind, code, status in _DRF_MAPPING if isinstance(exc, kind)),
        ("INTERNAL_ERROR", exc.status_code),
    )
    if isinstance(exc, exceptions.ValidationError):
        errors = list(_field_errors(exc.detail))
        return _problem(request, code, status, "Some fields are invalid.", {"errors": errors}, headers)
    return _problem(request, code, status, str(exc.detail), headers=headers)


def problem_exception_handler(exc: Exception, context: Mapping[str, Any]) -> Response:
    request = context.get("request")
    if isinstance(exc, ProblemError):
        return _problem(request, exc.code, exc.status, exc.detail, exc.extra)
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()
    if isinstance(exc, exceptions.APIException):
        return _api_exception(exc, request)
    if isinstance(exc, RequestDataTooBig):
        return _problem(request, "PAYLOAD_TOO_LARGE", 413, "The request is too large.")
    logger.error("unhandled exception", exc_info=exc)
    return _problem(request, "INTERNAL_ERROR", 500, "Something went wrong on our side.")
