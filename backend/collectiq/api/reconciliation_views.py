"""Unallocated transactions and match proposals (E055, E056). Reading never changes a balance."""

from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.evidence import service_matching as service

from .common import page_params
from .registry import endpoint
from .serializers import ProposalPageOut, UnmatchedPageOut

_PAGING = [OpenApiParameter("limit", int), OpenApiParameter("cursor", str)]


class UnmatchedTransactionsView(APIView):
    @endpoint("E055", responses={200: UnmatchedPageOut}, parameters=_PAGING)
    def get(self, request: Any, ws: UUID) -> Response:
        limit, cursor = page_params(request)
        return Response(service.list_unmatched(request.ctx, limit, cursor))


class ProposalsView(APIView):
    @endpoint("E056", responses={200: ProposalPageOut}, parameters=_PAGING)
    def get(self, request: Any, ws: UUID) -> Response:
        limit, cursor = page_params(request)
        return Response(service.list_proposals(request.ctx, limit, cursor))
