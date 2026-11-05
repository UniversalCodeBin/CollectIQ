"""AI opt-ins and flagged PDF extraction (E038-E041, E109, E110). The rules are in the services."""

from typing import Any
from uuid import UUID

from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.invoices import service_extraction as extraction
from collectiq.platform.idempotency import idempotent
from collectiq.tenancy import service_ai_settings as ai_settings

from .common import etag, expected_version, invalid, validated
from .registry import endpoint
from .serializers import (
    AiSettingsIn,
    AiSettingsOut,
    ExtractionConfirmIn,
    ExtractionEditIn,
    ExtractionOut,
)

_UPLOAD_BODY = {
    "multipart/form-data": {
        "type": "object",
        "properties": {"file": {"type": "string", "format": "binary"}},
        "required": ["file"],
    }
}


def _versioned(body: dict[str, Any], status: int = 200) -> Response:
    return Response(body, status=status, headers={"ETag": etag(body["version"])})


class AiSettingsView(APIView):
    @endpoint("E109", responses={200: AiSettingsOut})
    def get(self, request: Any, ws: UUID) -> Response:
        return Response(ai_settings.get_settings(request.ctx))

    @endpoint("E110", request=AiSettingsIn, responses={200: AiSettingsOut})
    @idempotent
    def put(self, request: Any, ws: UUID) -> Response:
        return Response(ai_settings.put_settings(request.ctx, dict(validated(AiSettingsIn, request))))


class InvoicePdfView(APIView):
    @endpoint("E038", request=_UPLOAD_BODY, responses={202: ExtractionOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            raise invalid("file", "Choose a PDF file to upload.")
        return _versioned(extraction.upload_pdf(request.ctx, upload.name, upload.read()), status=202)


class ExtractionView(APIView):
    @endpoint("E039", responses={200: ExtractionOut})
    def get(self, request: Any, ws: UUID, extraction_id: UUID) -> Response:
        return _versioned(extraction.get_extraction(request.ctx, extraction_id))

    @endpoint("E040", request=ExtractionEditIn, responses={200: ExtractionOut})
    def patch(self, request: Any, ws: UUID, extraction_id: UUID) -> Response:
        version = expected_version(request)
        body = validated(ExtractionEditIn, request)
        return _versioned(
            extraction.edit_extraction(request.ctx, extraction_id, version, dict(body["fields"]))
        )


class ExtractionConfirmView(APIView):
    @endpoint("E041", request=ExtractionConfirmIn, responses={201: ExtractionOut})
    @idempotent
    def post(self, request: Any, ws: UUID, extraction_id: UUID) -> Response:
        body = validated(ExtractionConfirmIn, request)
        return _versioned(
            extraction.confirm_extraction(request.ctx, extraction_id, dict(body.get("decisions", {}))),
            status=201,
        )
