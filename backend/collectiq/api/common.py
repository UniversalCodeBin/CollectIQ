"""Small request helpers shared by the views. Nothing here knows about a domain."""

from typing import Any
from uuid import UUID, uuid4

from rest_framework.serializers import Serializer

from collectiq.platform.errors import ProblemError
from collectiq.platform.logging import current_correlation_id

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


def correlation_id(request: Any) -> str:
    ctx = getattr(request, "ctx", None)
    return ctx.correlation_id if ctx else current_correlation_id() or str(uuid4())


def invalid(field: str, message: str) -> ProblemError:
    return ProblemError(
        "VALIDATION_FAILED",
        422,
        "Some fields are invalid.",
        {"errors": [{"field": field, "message": message}]},
    )


def validated(serializer_class: type[Serializer], request: Any) -> dict[str, Any]:
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def etag(version: int) -> str:
    return f'"{version}"'


def expected_version(request: Any) -> int:
    raw = request.headers.get("If-Match", "").strip().strip('"')
    if not raw.isascii() or not raw.isdigit():
        raise invalid("If-Match", "Send the version you last read, from its ETag.")
    return int(raw)


def page_params(request: Any) -> tuple[int, UUID | None]:
    raw_limit = request.query_params.get("limit", str(_DEFAULT_LIMIT))
    if not raw_limit.isascii() or not raw_limit.isdigit() or not 1 <= int(raw_limit) <= _MAX_LIMIT:
        raise invalid("limit", f"Use a number from 1 to {_MAX_LIMIT}.")
    raw_cursor = request.query_params.get("cursor")
    if raw_cursor is None:
        return int(raw_limit), None
    try:
        return int(raw_limit), UUID(raw_cursor)
    except ValueError:
        raise invalid("cursor", "This cursor is not valid. Start again from the first page.") from None
