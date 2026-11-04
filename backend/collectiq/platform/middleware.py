"""One correlation ID per request, in the logs and on the response."""
import re
from collections.abc import Callable
from uuid import uuid4

from django.http import HttpRequest, HttpResponse

from .logging import bind_correlation_id

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
