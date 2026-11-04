from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.invoices import clients as service
from collectiq.platform.idempotency import idempotent

from .common import etag, expected_version, page_params, validated
from .registry import endpoint
from .serializers import (
    ClientIn,
    ClientOut,
    ClientPageOut,
    ClientProfileOut,
    ClientUpdateIn,
    ContactIn,
    ContactOut,
    ContactUpdateIn,
    SuppressionClearIn,
    SuppressionIn,
)


def _versioned(client: dict[str, Any], status: int = 200) -> Response:
    return Response(client, status=status, headers={"ETag": etag(client["version"])})


class ClientCollectionView(APIView):
    @endpoint(
        "E021",
        responses={200: ClientPageOut},
        parameters=[OpenApiParameter("limit", int), OpenApiParameter("cursor", str)],
    )
    def get(self, request: Any, ws: UUID) -> Response:
        limit, cursor = page_params(request)
        return Response(service.list_clients(request.ctx, limit, cursor))

    @endpoint("E022", request=ClientIn, responses={201: ClientOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        return _versioned(service.create_client(request.ctx, validated(ClientIn, request)), status=201)


class ClientDetailView(APIView):
    @endpoint("E023", responses={200: ClientProfileOut})
    def get(self, request: Any, ws: UUID, client_id: UUID) -> Response:
        return _versioned(service.client_profile(request.ctx, client_id))

    @endpoint("E024", request=ClientUpdateIn, responses={200: ClientOut})
    def patch(self, request: Any, ws: UUID, client_id: UUID) -> Response:
        version = expected_version(request)
        changes = validated(ClientUpdateIn, request)
        return _versioned(service.update_client(request.ctx, client_id, version, changes))


class ContactCollectionView(APIView):
    @endpoint("E025", request=ContactIn, responses={201: ContactOut})
    @idempotent
    def post(self, request: Any, ws: UUID, client_id: UUID) -> Response:
        data = validated(ContactIn, request)
        contact = service.add_contact(request.ctx, client_id, data["email"], data.get("name"))
        return Response(contact, status=201)


class ContactDetailView(APIView):
    @endpoint("E026", request=ContactUpdateIn, responses={200: ContactOut})
    def patch(self, request: Any, ws: UUID, client_id: UUID, contact_id: UUID) -> Response:
        changes = validated(ContactUpdateIn, request)
        return Response(service.update_contact(request.ctx, client_id, contact_id, changes))


class ContactSuppressionView(APIView):
    @endpoint("E027", request=SuppressionIn, responses={200: ContactOut})
    @idempotent
    def post(self, request: Any, ws: UUID, contact_id: UUID) -> Response:
        data = validated(SuppressionIn, request)
        return Response(service.suppress_contact(request.ctx, contact_id, data["reason"]))

    @endpoint("E028", request=SuppressionClearIn, responses={204: None})
    @idempotent
    def delete(self, request: Any, ws: UUID, contact_id: UUID) -> Response:
        data = validated(SuppressionClearIn, request)
        service.clear_suppression(request.ctx, contact_id, data.get("reason"))
        return Response(status=204)
