"""Policy versions, the emergency pause, approvals and the why-view (E016-E020, E092, E101)."""

from typing import Any
from uuid import UUID

from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.platform.idempotency import idempotent
from collectiq.policy import service

from .common import invalid, validated
from .registry import endpoint
from .serializers import (
    ApprovalDecisionIn,
    ApprovalOut,
    PauseIn,
    PolicyDecisionOut,
    PolicyIn,
    PolicyOut,
    PolicyVersionsOut,
)


class PolicyView(APIView):
    @endpoint("E016", responses={200: PolicyOut})
    def get(self, request: Any, ws: UUID) -> Response:
        return Response(service.get_policy(request.ctx))

    @endpoint("E017", request=PolicyIn, responses={200: PolicyOut})
    @idempotent
    def put(self, request: Any, ws: UUID) -> Response:
        data = validated(PolicyIn, request)
        if data.get("auto_snooze_enabled"):
            raise invalid(
                "auto_snooze_enabled", "Automatic snoozing cannot be turned on until it has been evaluated."
            )
        if "limits" in data:
            data["limits"] = dict(data["limits"])
        return Response(service.update_policy(request.ctx, data))


class PolicyVersionsView(APIView):
    @endpoint("E018", responses={200: PolicyVersionsOut})
    def get(self, request: Any, ws: UUID) -> Response:
        return Response(service.list_versions(request.ctx))


class AutomationPauseView(APIView):
    @endpoint("E019", request=PauseIn, responses={200: PolicyOut})
    def post(self, request: Any, ws: UUID) -> Response:
        data = validated(PauseIn, request)
        return Response(service.pause(request.ctx, data.get("reason")))


class AutomationResumeView(APIView):
    @endpoint("E020", responses={200: PolicyOut})
    def post(self, request: Any, ws: UUID) -> Response:
        return Response(service.resume(request.ctx))


class ApprovalDecideView(APIView):
    @endpoint("E092", request=ApprovalDecisionIn, responses={200: ApprovalOut})
    @idempotent
    def post(self, request: Any, ws: UUID, approval_id: UUID) -> Response:
        data = validated(ApprovalDecisionIn, request)
        return Response(service.decide_approval(request.ctx, approval_id, data["decision"], data.get("note")))


class PolicyDecisionView(APIView):
    @endpoint("E101", responses={200: PolicyDecisionOut})
    def get(self, request: Any, ws: UUID, decision_id: UUID) -> Response:
        return Response(service.get_decision(request.ctx, decision_id))
