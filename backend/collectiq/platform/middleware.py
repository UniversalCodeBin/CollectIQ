"""One correlation ID per request, in the logs and on the response."""

import re
from collections.abc import Callable
from uuid import uuid4

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from .logging import bind_correlation_id, current_correlation_id

_HEADER = "X-Correlation-ID"
_ACCEPTABLE = re.compile(r"[A-Za-z0-9._-]{1,128}")


class CorrelationIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        offered = request.headers.get(_HEADER, "")
        correlation_id = offered if _ACCEPTABLE.fullmatch(offered) else str(uuid4())
        with bind_correlation_id(correlation_id):
            response = self.get_response(request)
        response[_HEADER] = correlation_id
        return response


class UploadLimitMiddleware:
    """Refuses an oversized body from its declared length, before anything reads it (SEC-11)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            declared = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            declared = 0
        if declared > settings.COLLECTIQ_MAX_REQUEST_BYTES:
            return JsonResponse(
                {
                    "type": "/problems/payload-too-large",
                    "title": "Payload too large",
                    "status": 413,
                    "code": "PAYLOAD_TOO_LARGE",
                    "detail": "This upload is too large. Split the file and upload the parts.",
                    "correlation_id": current_correlation_id(),
                },
                status=413,
                content_type="application/problem+json",
            )
        return self.get_response(request)
