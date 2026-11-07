"""Disputes and blockers (E076-E082)."""

from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.cases import service
from collectiq.platform.idempotency import idempotent

from .common import etag, expected_version, invalid, page_params, query_values, validated
from .registry import endpoint
from .serializers import (
    CaseDetailOut,
    CaseIn,
    CasePageOut,
    CaseReopenIn,
    CaseResolveIn,
    CaseUpdateIn,
    ResumeIn,
    ResumeOut,
    ResumeRequestOut,
)


def _versioned(case: dict[str, Any], status: int = 200) -> Response:
    return Response(case, status=status, headers={"ETag": etag(case["version"])})


class CaseCollectionView(APIView):
    @endpoint(
        "E076",
        responses={200: CasePageOut},
        parameters=[
            OpenApiParameter("limit", int),
            OpenApiParameter("cursor", str),
            OpenApiParameter("status", str),
            OpenApiParameter("invoice_id", str),
        ],
    )
    def get(self, request: Any, ws: UUID) -> Response:
        filters = query_values(request, ("limit", "cursor", "status", "invoice_id"))
        limit, cursor = page_params(request)
        status = filters.get("status")
        invoice = filters.get("invoice_id")
        try:
            invoice_id = UUID(invoice) if invoice else None
        except ValueError:
            raise invalid("invoice_id", "This is not a valid invoice id.") from None
        return Response(service.list_cases(request.ctx, limit, cursor, status, invoice_id))

    @endpoint("E078", request=CaseIn, responses={201: CaseDetailOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        data = validated(CaseIn, request)
        case = service.open_case(
            request.ctx,
            data["invoice_id"],
            data["type"],
            data["summary"],
            data.get("dispute_type"),
            data.get("source_message_id"),
        )
        return _versioned(case, status=201)


class CaseDetailView(APIView):
    @endpoint("E077", responses={200: CaseDetailOut})
    def get(self, request: Any, ws: UUID, case_id: UUID) -> Response:
        return _versioned(service.get_case(request.ctx, case_id))

    @endpoint("E079", request=CaseUpdateIn, responses={200: CaseDetailOut})
    def patch(self, request: Any, ws: UUID, case_id: UUID) -> Response:
        version = expected_version(request)
        data = validated(CaseUpdateIn, request)
        case = service.update_case(
            request.ctx,
            case_id,
            version,
            assignee_id=data.get("assignee_id"),
            status=data.get("status"),
            note=data.get("note"),
            assignee_given="assignee_id" in data,
        )
        return _versioned(case)


class CaseResolveView(APIView):
    @endpoint("E080", request=CaseResolveIn, responses={200: CaseDetailOut})
    @idempotent
    def post(self, request: Any, ws: UUID, case_id: UUID) -> Response:
        data = validated(CaseResolveIn, request)
        return _versioned(service.resolve_case(request.ctx, case_id, data["outcome"], data.get("note")))


class CaseReopenView(APIView):
    @endpoint("E081", request=CaseReopenIn, responses={200: CaseDetailOut})
    @idempotent
    def post(self, request: Any, ws: UUID, case_id: UUID) -> Response:
        data = validated(CaseReopenIn, request)
        return _versioned(service.reopen_case(request.ctx, case_id, data["reason"]))


class FollowupsResumeView(APIView):
    @endpoint("E082", request=ResumeIn, responses={200: ResumeOut})
    @idempotent
    def post(self, request: Any, ws: UUID, invoice_id: UUID) -> Response:
        data = validated(ResumeIn, request)
        return Response(service.resume_followups(request.ctx, invoice_id, data["approval_id"]))


class FollowupsResumeRequestView(APIView):
    @endpoint("E127", responses={200: ResumeRequestOut})
    @idempotent
    def post(self, request: Any, ws: UUID, invoice_id: UUID) -> Response:
        return Response(service.request_resume(request.ctx, invoice_id))
