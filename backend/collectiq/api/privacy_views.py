"""Export, deletion and the AI payload inspector (E102-E105)."""

from typing import Any
from uuid import UUID

from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.platform.idempotency import idempotent
from collectiq.settings_privacy import service

from .common import validated
from .registry import endpoint
from .serializers import AiPayloadPageOut, DeletionIn, DeletionOut, ExportOut, ExportRequestIn


class ExportCollectionView(APIView):
    @endpoint("E102", request=ExportRequestIn, responses={201: ExportOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        validated(ExportRequestIn, request)
        return Response(service.request_export(request.ctx), status=201)


class ExportDetailView(APIView):
    @endpoint("E103", request=None, responses={200: ExportOut})
    def get(self, request: Any, ws: UUID, export_id: UUID) -> Response:
        return Response(service.get_export(request.ctx, export_id))


class DeletionView(APIView):
    @endpoint("E104", request=DeletionIn, responses={201: DeletionOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        data = validated(DeletionIn, request)
        return Response(service.delete_workspace(request.ctx, data["confirmation_text"]), status=201)


class AiPayloadsView(APIView):
    @endpoint("E105", request=None, responses={200: AiPayloadPageOut})
    def get(self, request: Any, ws: UUID) -> Response:
        return Response(service.list_payloads(request.ctx))
