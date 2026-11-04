"""Invoice import (E033-E037, E116). The rules are in `invoices.service_import`."""

import logging
from typing import Any
from uuid import UUID

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.invoices import service_import as service
from collectiq.platform.errors import ProblemError
from collectiq.platform.idempotency import idempotent

from .common import invalid, validated
from .registry import endpoint
from .serializers import ImportBatchOut, ImportCommitIn, ImportMappingIn

logger = logging.getLogger(__name__)

_MAX_ROW_LIMIT = 500
_UPLOAD_BODY = {
    "multipart/form-data": {
        "type": "object",
        "properties": {"file": {"type": "string", "format": "binary"}},
        "required": ["file"],
    }
}


def _int_param(request: Any, name: str, default: int, minimum: int, maximum: int) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise invalid(name, "Enter a whole number.") from None
    if not minimum <= value <= maximum:
        raise invalid(name, f"Enter a number from {minimum} to {maximum}.")
    return value


class InvoiceImportCollectionView(APIView):
    @endpoint("E033", request=_UPLOAD_BODY, responses={201: ImportBatchOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            raise invalid("file", "Choose a CSV file to upload.")
        return Response(service.upload_invoices(request.ctx, upload.name, upload.read()), status=201)


class ImportMappingView(APIView):
    @endpoint("E034", request=ImportMappingIn, responses={200: ImportBatchOut})
    def put(self, request: Any, ws: UUID, import_id: UUID) -> Response:
        body = validated(ImportMappingIn, request)
        return Response(service.set_mapping(request.ctx, import_id, body["mapping"], body.get("date_format")))


class ImportCommitView(APIView):
    @idempotent
    def _commit(self, request: Any, ws: UUID, import_id: UUID) -> Response:
        body = validated(ImportCommitIn, request)
        return Response(service.commit_import(request.ctx, import_id, body.get("decisions", {})))

    @endpoint("E035", request=ImportCommitIn, responses={200: ImportBatchOut})
    def post(self, request: Any, ws: UUID, import_id: UUID) -> Response:
        """The failure is recorded outside the rolled-back transaction, so that it survives."""
        try:
            return self._commit(request, ws, import_id)
        except service.ImportCommitFailed as failure:
            # The class only: a database error can quote the row, and rows do not belong in logs.
            logger.error("import commit failed: %s (%s)", import_id, type(failure.__cause__).__name__)
            service.record_failure(request.ctx, import_id)
            raise ProblemError("INTERNAL_ERROR", 500, service.FAILED_REASON) from None


class ImportDetailView(APIView):
    @endpoint(
        "E037",
        responses={200: ImportBatchOut},
        parameters=[OpenApiParameter("limit", int), OpenApiParameter("after_row", int)],
    )
    def get(self, request: Any, ws: UUID, import_id: UUID) -> Response:
        limit = _int_param(request, "limit", service.DEFAULT_ROW_LIMIT, 1, _MAX_ROW_LIMIT)
        after_row = _int_param(request, "after_row", 0, 0, 2**31 - 1)
        return Response(service.get_import(request.ctx, import_id, limit, after_row))

    @endpoint("E036", responses={204: None})
    def delete(self, request: Any, ws: UUID, import_id: UUID) -> Response:
        service.discard_import(request.ctx, import_id)
        return Response(status=204)


class _AnyAccept(BaseContentNegotiation):
    """The report is a CSV file whatever the browser asks for, and refusals are still problem documents."""

    def select_parser(self, request: Any, parsers: Any) -> Any:
        return parsers[0]

    def select_renderer(self, request: Any, renderers: Any, format_suffix: Any = None) -> Any:
        return renderers[0], renderers[0].media_type


class ImportErrorReportView(APIView):
    content_negotiation_class = _AnyAccept

    @endpoint("E116", responses={(200, "text/csv"): OpenApiTypes.STR})
    def get(self, request: Any, ws: UUID, import_id: UUID) -> HttpResponse:
        report = service.error_report(request.ctx, import_id)
        response = HttpResponse(report, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="import-errors.csv"'
        return response
