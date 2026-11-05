"""Integration status (E093). Connect and disconnect are service calls until a provider adapter exists."""

from typing import Any
from uuid import UUID

from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.integrations import service

from .registry import endpoint
from .serializers import IntegrationListOut


class IntegrationsView(APIView):
    @endpoint("E093", responses={200: IntegrationListOut})
    def get(self, request: Any, ws: UUID) -> Response:
        return Response(service.list_integrations(request.ctx))
