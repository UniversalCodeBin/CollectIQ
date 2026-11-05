"""Payments, allocations and decisions on proposals (E049-E052, E057-E061). A person makes every one."""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.evidence import service_allocation as ledger
from collectiq.evidence import service_matching as matching
from collectiq.platform.idempotency import idempotent

from .common import page_params, validated
from .registry import endpoint
from .serializers import (
    AllocationIn,
    DuplicateIn,
    LedgerResultOut,
    PaymentDetailOut,
    PaymentIn,
    PaymentPageOut,
    ProposalConfirmIn,
    ProposalRejectedOut,
    ProposalRejectIn,
    ReasonIn,
)

_PAGING = [OpenApiParameter("limit", int), OpenApiParameter("cursor", str)]


def _lines(items: Iterable[dict[str, Any]]) -> list[ledger.Line]:
    return [ledger.Line(i["invoice_id"], i["amount_minor"], i["overpayment_confirmed"]) for i in items]


class PaymentsView(APIView):
    @endpoint("E050", responses={200: PaymentPageOut}, parameters=_PAGING)
    def get(self, request: Any, ws: UUID) -> Response:
        limit, cursor = page_params(request)
        return Response(ledger.list_payments(request.ctx, limit, cursor))

    @endpoint("E049", request=PaymentIn, responses={201: LedgerResultOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        data = validated(PaymentIn, request)
        result = ledger.record_payment(
            request.ctx,
            data["method"],
            data["amount"]["amount_minor"],
            data["amount"]["currency"],
            data["value_date"],
            reference=data.get("reference"),
            payer=data.get("payer"),
            notes=data.get("notes"),
            lines=_lines(data.get("allocations", [])),
        )
        return Response(result, status=201)


class PaymentDetailView(APIView):
    @endpoint("E051", responses={200: PaymentDetailOut})
    def get(self, request: Any, ws: UUID, payment_id: UUID) -> Response:
        return Response(ledger.get_payment(request.ctx, payment_id))


class PaymentVoidView(APIView):
    @endpoint("E052", request=ReasonIn, responses={200: LedgerResultOut})
    @idempotent
    def post(self, request: Any, ws: UUID, payment_id: UUID) -> Response:
        data = validated(ReasonIn, request)
        return Response(ledger.void_payment(request.ctx, payment_id, data["reason"]))


class ProposalConfirmView(APIView):
    @endpoint("E057", request=ProposalConfirmIn, responses={200: LedgerResultOut})
    @idempotent
    def post(self, request: Any, ws: UUID, proposal_id: UUID) -> Response:
        data = validated(ProposalConfirmIn, request)
        return Response(ledger.confirm_proposal(request.ctx, proposal_id, _lines(data["allocations"])))


class ProposalRejectView(APIView):
    @endpoint("E058", request=ProposalRejectIn, responses={200: ProposalRejectedOut})
    @idempotent
    def post(self, request: Any, ws: UUID, proposal_id: UUID) -> Response:
        data = validated(ProposalRejectIn, request)
        return Response(matching.reject(request.ctx, proposal_id, data.get("reason")))


class AllocationsView(APIView):
    @endpoint("E059", request=AllocationIn, responses={200: LedgerResultOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        data = validated(AllocationIn, request)
        return Response(
            ledger.confirm_allocation(request.ctx, data["transaction_id"], _lines(data["allocations"]))
        )


class AllocationReverseView(APIView):
    @endpoint("E060", request=ReasonIn, responses={200: LedgerResultOut})
    @idempotent
    def post(self, request: Any, ws: UUID, allocation_id: UUID) -> Response:
        data = validated(ReasonIn, request)
        return Response(ledger.reverse_allocation(request.ctx, allocation_id, data["reason"]))


class TransactionDuplicateView(APIView):
    @endpoint("E061", request=DuplicateIn, responses={200: LedgerResultOut})
    @idempotent
    def post(self, request: Any, ws: UUID, transaction_id: UUID) -> Response:
        data = validated(DuplicateIn, request)
        return Response(ledger.mark_duplicate(request.ctx, transaction_id, data["duplicate_of"]))
