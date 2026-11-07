"""Reminders, manual handoff and per-client/invoice pauses (E083-E089, E121-E123). Approving never sends."""

from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.comms import service_pause
from collectiq.comms import service_reminders as service
from collectiq.platform.idempotency import idempotent

from .common import etag, expected_version, page_params, validated
from .registry import endpoint
from .serializers import (
    ReminderDetailOut,
    ReminderEditIn,
    ReminderEvaluationOut,
    ReminderOut,
    ReminderPageOut,
    ReminderPauseIn,
    ReminderPauseListOut,
    ReminderPauseOut,
    ReminderRejectIn,
    ReminderSentIn,
)


def _versioned(reminder: dict[str, Any], status: int = 200) -> Response:
    return Response(reminder, status=status, headers={"ETag": etag(reminder["version"])})


class ReminderCollectionView(APIView):
    @endpoint(
        "E083",
        responses={200: ReminderPageOut},
        parameters=[OpenApiParameter("limit", int), OpenApiParameter("cursor", str)],
    )
    def get(self, request: Any, ws: UUID) -> Response:
        limit, cursor = page_params(request)
        return Response(service.list_reminders(request.ctx, limit, cursor))


class ReminderDetailView(APIView):
    @endpoint("E084", responses={200: ReminderDetailOut})
    def get(self, request: Any, ws: UUID, reminder_id: UUID) -> Response:
        return _versioned(service.get_reminder(request.ctx, reminder_id))

    @endpoint("E086", request=ReminderEditIn, responses={200: ReminderOut})
    def patch(self, request: Any, ws: UUID, reminder_id: UUID) -> Response:
        version = expected_version(request)
        data = validated(ReminderEditIn, request)
        return _versioned(service.edit_reminder(request.ctx, reminder_id, version, data["body"]))


class ReminderEvaluateView(APIView):
    @endpoint("E085", responses={200: ReminderEvaluationOut})
    @idempotent
    def post(self, request: Any, ws: UUID, invoice_id: UUID) -> Response:
        return Response(service.evaluate_invoice(request.ctx, invoice_id))


class ReminderApproveView(APIView):
    @endpoint("E087", responses={200: ReminderOut})
    @idempotent
    def post(self, request: Any, ws: UUID, reminder_id: UUID) -> Response:
        return _versioned(service.approve_reminder(request.ctx, reminder_id))


class ReminderRejectView(APIView):
    @endpoint("E088", request=ReminderRejectIn, responses={200: ReminderOut})
    @idempotent
    def post(self, request: Any, ws: UUID, reminder_id: UUID) -> Response:
        data = validated(ReminderRejectIn, request)
        return _versioned(service.reject_reminder(request.ctx, reminder_id, data.get("reason")))


class ReminderMarkSentView(APIView):
    @endpoint("E089", request=ReminderSentIn, responses={201: ReminderOut})
    @idempotent
    def post(self, request: Any, ws: UUID, reminder_id: UUID) -> Response:
        data = validated(ReminderSentIn, request)
        return _versioned(service.mark_sent(request.ctx, reminder_id, data["sent_at"], data["method"]), 201)


class ReminderPauseCollectionView(APIView):
    @endpoint(
        "E121",
        responses={200: ReminderPauseListOut},
        parameters=[
            OpenApiParameter("invoice_id", str),
            OpenApiParameter("client_id", str),
            OpenApiParameter("history", bool),
        ],
    )
    def get(self, request: Any, ws: UUID) -> Response:
        params = request.query_params
        return Response(
            service_pause.list_pauses(
                request.ctx,
                params.get("invoice_id"),
                params.get("client_id"),
                params.get("history") == "true",
            )
        )

    @endpoint("E122", request=ReminderPauseIn, responses={201: ReminderPauseOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        data = validated(ReminderPauseIn, request)
        made = service_pause.pause(request.ctx, data["scope"], data["target_id"], data.get("reason"))
        return Response(made, status=201)


class ReminderPauseResumeView(APIView):
    @endpoint("E123", responses={200: ReminderPauseOut})
    @idempotent
    def post(self, request: Any, ws: UUID, pause_id: UUID) -> Response:
        return Response(service_pause.resume(request.ctx, pause_id))
