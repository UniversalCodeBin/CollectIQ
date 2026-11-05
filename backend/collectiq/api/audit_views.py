"""Audit history: search and export (E099, E100)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.audit import history
from collectiq.platform.idempotency import idempotent
from collectiq.tenancy.permissions import AUDIT_READ, EXPORT, authorize

from .common import invalid, query_values, validated
from .registry import endpoint
from .serializers import AuditExportIn, AuditExportOut, AuditPageOut

_QUERY = [OpenApiParameter(n, str, required=False) for n in (*history.FILTERS, "limit", "cursor")]


def _cursor_and_limit(values: dict[str, str]) -> tuple[int | None, int]:
    raw_limit = values.pop("limit", "50")
    if not raw_limit.isascii() or not raw_limit.isdigit() or not 1 <= int(raw_limit) <= 200:
        raise invalid("limit", "Use a number from 1 to 200.")
    raw = values.pop("cursor", None)
    if raw is None:
        return None, int(raw_limit)
    if not raw.isascii() or not raw.isdigit():
        raise invalid("cursor", "This cursor is not valid. Start again from the first page.")
    return int(raw), int(raw_limit)


def _filters(values: dict[str, str]) -> dict[str, str]:
    for name in ("from", "to"):
        if name in values:
            try:
                datetime.fromisoformat(values[name])
            except ValueError:
                raise invalid(name, "Use an ISO 8601 date or time.") from None
    return values


class AuditEventsView(APIView):
    @endpoint("E099", responses={200: AuditPageOut}, parameters=_QUERY)
    def get(self, request: Any, ws: UUID) -> Response:
        authorize(request.ctx, AUDIT_READ)
        values = query_values(request, [*history.FILTERS, "limit", "cursor"])
        cursor, limit = _cursor_and_limit(values)
        return Response(history.search(request.ctx, _filters(values), cursor, limit))


class AuditExportView(APIView):
    @endpoint("E100", request=AuditExportIn, responses={200: AuditExportOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        authorize(request.ctx, EXPORT)
        data = validated(AuditExportIn, request)
        filters = _filters({k: str(v) for k, v in (data.get("filters") or {}).items()})
        unknown = set(filters) - set(history.FILTERS)
        if unknown:
            raise invalid("filters", "This filter is not recognised.")
        return Response(history.export(request.ctx, filters, data.get("format", "CSV")))
