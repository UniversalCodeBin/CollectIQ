from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.evidence import service_accounts as service
from collectiq.platform.idempotency import idempotent

from .common import etag, expected_version, page_params, validated
from .registry import endpoint
from .serializers import (
    AccountCoverageOut,
    AttestationIn,
    AttestationOut,
    PaymentAccountIn,
    PaymentAccountOut,
    PaymentAccountPageOut,
    PaymentAccountUpdateIn,
)


def _versioned(account: dict[str, Any], status: int = 200) -> Response:
    return Response(account, status=status, headers={"ETag": etag(account["version"])})


class PaymentAccountCollectionView(APIView):
    @endpoint(
        "E029",
        responses={200: PaymentAccountPageOut},
        parameters=[OpenApiParameter("limit", int), OpenApiParameter("cursor", str)],
    )
    def get(self, request: Any, ws: UUID) -> Response:
        limit, cursor = page_params(request)
        return Response(service.list_accounts(request.ctx, limit, cursor))

    @endpoint("E030", request=PaymentAccountIn, responses={201: PaymentAccountOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        data = validated(PaymentAccountIn, request)
        return _versioned(
            service.create_account(request.ctx, data["kind"], data["label"], data["currency"]), status=201
        )


class PaymentAccountDetailView(APIView):
    @endpoint("E031", request=PaymentAccountUpdateIn, responses={200: PaymentAccountOut})
    def patch(self, request: Any, ws: UUID, account_id: UUID) -> Response:
        version = expected_version(request)
        changes = validated(PaymentAccountUpdateIn, request)
        return _versioned(service.update_account(request.ctx, account_id, version, changes))


class AccountCoverageView(APIView):
    @endpoint("E032", responses={200: AccountCoverageOut})
    def get(self, request: Any, ws: UUID, account_id: UUID) -> Response:
        return Response(service.account_coverage_detail(request.ctx, account_id))


class AttestationView(APIView):
    @endpoint("E054", request=AttestationIn, responses={201: AttestationOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        data = validated(AttestationIn, request)
        result = service.attest(
            request.ctx,
            data["scope"],
            data["as_of"],
            data.get("note"),
            account_id=data.get("account_id"),
            invoice_ids=data.get("invoice_ids", ()),
        )
        return Response(result, status=201)
