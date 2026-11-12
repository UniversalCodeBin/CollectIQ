"""Integration status and the gated Gmail and PayPal adapters (E093-E095, E097-E098, E090-E091)."""

from typing import Any
from uuid import UUID

from django.http import HttpResponseRedirect
from drf_spectacular.utils import OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.comms import service_send
from collectiq.integrations import service
from collectiq.integrations.gmail import service as gmail
from collectiq.integrations.paypal import service as paypal
from collectiq.platform.idempotency import idempotent

from .common import correlation_id, validated
from .registry import endpoint
from .serializers import (
    AuthorizationOut,
    ConfirmUnknownIn,
    IntegrationItemOut,
    IntegrationListOut,
    PayPalConnectIn,
    ReminderOut,
)


class IntegrationsView(APIView):
    @endpoint("E093", responses={200: IntegrationListOut})
    def get(self, request: Any, ws: UUID) -> Response:
        return Response(service.list_integrations(request.ctx))


class GmailConnectView(APIView):
    @endpoint("E094", responses={200: AuthorizationOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        response = Response(gmail.start(request.ctx))
        response._no_mutation = True
        return response


class GmailCallbackView(APIView):
    @endpoint(
        "E095",
        responses={302: None},
        parameters=[OpenApiParameter("state", str), OpenApiParameter("code", str)],
    )
    def get(self, request: Any) -> Any:
        workspace = gmail.complete(
            request.principal.user_id,
            correlation_id(request),
            str(request.query_params.get("state", "")),
            str(request.query_params.get("code", "")),
        )
        return HttpResponseRedirect(f"/w/{workspace}/integrations")


class GmailMonitoringView(APIView):
    @endpoint("E096", responses={200: IntegrationItemOut})
    def post(self, request: Any, ws: UUID) -> Response:
        return Response(gmail.start_monitoring(request.ctx))


class PayPalConnectView(APIView):
    @endpoint("E129", request=PayPalConnectIn, responses={200: IntegrationItemOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        data = validated(PayPalConnectIn, request)
        return Response(paypal.connect(request.ctx, data.get("merchant_id")))


class IntegrationItemView(APIView):
    @endpoint("E097", responses={200: IntegrationItemOut})
    @idempotent
    def delete(self, request: Any, ws: UUID, key: str) -> Response:
        if key == "GMAIL":
            return Response(gmail.disconnect(request.ctx))
        return Response(service.disconnect(request.ctx, key))


class PayPalWebhookView(APIView):
    @endpoint("E098", responses={200: None})
    def post(self, request: Any) -> Response:
        res = paypal.receive({k: v for k, v in request.headers.items()}, request.body)
        response = Response(res or {"received": True})
        if res and res.get("status") == "IGNORED":
            response._no_mutation = True
        return response


class ReminderSendView(APIView):
    @endpoint("E090", responses={202: ReminderOut})
    @idempotent
    def post(self, request: Any, ws: UUID, reminder_id: UUID) -> Response:
        return Response(gmail.send_reminder(request.ctx, reminder_id), status=202)


class ReminderConfirmUnknownView(APIView):
    @endpoint("E091", request=ConfirmUnknownIn, responses={200: ReminderOut})
    @idempotent
    def post(self, request: Any, ws: UUID, reminder_id: UUID) -> Response:
        data = validated(ConfirmUnknownIn, request)
        return Response(service_send.resolve_unknown(request.ctx, reminder_id, data["outcome"]))
