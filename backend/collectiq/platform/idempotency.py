"""`@idempotent`: one user intent, one effect. A retry replays the stored response (TSD 666, 799, 1050)."""
import hashlib
import json
from collections.abc import Callable
from functools import wraps
from typing import Any
from uuid import UUID

from django.db import connection, transaction
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from .context import RequestContext
from .db import tenant_tx
from .errors import ProblemError

_HEADER = "Idempotency-Key"
_REPLAYED_HEADERS = ("ETag", "Location")


def _key(request: Any) -> UUID:
    try:
        return UUID(request.headers.get(_HEADER, ""))
    except ValueError:
        raise ProblemError(
            "VALIDATION_FAILED",
            422,
            "This request needs a valid idempotency key.",
            {"errors": [{"field": _HEADER, "message": "Send a UUID, reused when the request is retried."}]},
        ) from None


def _request_hash(request: Any, ctx: RequestContext) -> bytes:
    digest = hashlib.sha256()
    for part in (request.method, request.get_full_path(), str(ctx.user_id)):
        digest.update(part.encode())
        digest.update(b"\x00")
    digest.update(request.body)
    return digest.digest()


def _claim(
    ctx: RequestContext, key: UUID, request_hash: bytes
) -> tuple[bytes, int | None, str | None, str | None]:
    """A concurrent duplicate waits on the INSERT until the first request commits or rolls back."""
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM idempotency_keys WHERE workspace_id = %s AND key = %s"
            " AND created_at < now() - interval '24 hours'",
            [ctx.workspace_id, key],
        )
        cursor.execute(
            "INSERT INTO idempotency_keys (workspace_id, key, request_hash) VALUES (%s, %s, %s)"
            " ON CONFLICT (workspace_id, key) DO NOTHING",
            [ctx.workspace_id, key, request_hash],
        )
        cursor.execute(
            "SELECT request_hash, response_status, response_body, response_headers FROM idempotency_keys"
            " WHERE workspace_id = %s AND key = %s",
            [ctx.workspace_id, key],
        )
        stored_hash, status, body, headers = cursor.fetchone()
    return bytes(stored_hash), status, body, headers


def _store(ctx: RequestContext, key: UUID, response: Response) -> None:
    # Kept as rendered text: jsonb would reorder the keys, and the replay must match byte for byte.
    body = None if response.data is None else JSONRenderer().render(response.data).decode()
    headers = {name: response[name] for name in _REPLAYED_HEADERS if name in response}
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE idempotency_keys SET response_status = %s, response_body = %s,"
            " response_headers = %s::jsonb"
            " WHERE workspace_id = %s AND key = %s",
            [response.status_code, body, json.dumps(headers), ctx.workspace_id, key],
        )


def idempotent(view_method: Callable[..., Response]) -> Callable[..., Response]:
    """The view's work commits with the stored response. A failure undoes both and frees the key to retry."""

    @wraps(view_method)
    def wrapper(view: Any, request: Any, *args: Any, **kwargs: Any) -> Response:
        ctx = getattr(request, "ctx", None)
        if ctx is None:
            raise RuntimeError("@idempotent needs request.ctx, set before the view method runs")
        key = _key(request)
        request_hash = _request_hash(request, ctx)
        with tenant_tx(ctx):
            stored_hash, status, body, headers = _claim(ctx, key, request_hash)
            if stored_hash != request_hash:
                raise ProblemError(
                    "IDEMPOTENCY_MISMATCH",
                    422,
                    "This idempotency key was already used for a different request.",
                )
            if status is not None:
                data = None if body is None else json.loads(body)
                return Response(data, status=status, headers=json.loads(headers or "{}"))
            response = view_method(view, request, *args, **kwargs)
            if response.status_code >= 400:
                transaction.set_rollback(True)
            else:
                _store(ctx, key, response)
            return response

    return wrapper
