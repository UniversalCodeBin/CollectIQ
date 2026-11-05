from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.invoices import read_models, service_invoice
from collectiq.invoices.domain.queue import AGING_BUCKETS, TILES
from collectiq.platform.idempotency import idempotent
from collectiq.platform.money import ISO_4217_CODES

from .common import etag, expected_version, invalid, limit_param, query_values, validated
from .registry import endpoint
from .serializers import (
    DashboardOut,
    InvoiceCorrectionIn,
    InvoiceDetailOut,
    InvoicePageOut,
    InvoiceReasonIn,
    QueuePageOut,
)

_ENUMS = {
    "payment_status": {
        "OUTSTANDING",
        "PARTIALLY_PAID",
        "PAID_VERIFIED",
        "AWAITING_VERIFICATION",
        "UNCERTAIN",
    },
    "reminder_status": {
        "NOT_CONTACTED",
        "DRAFT_READY",
        "SCHEDULED",
        "SNOOZED",
        "WAITING_FOR_CUSTOMER",
        "NEEDS_REVIEW",
        "SUPPRESSED",
        "RESOLVED",
    },  # fmt: skip
    "dispute_status": {"NONE", "OPEN", "IN_REVIEW", "AWAITING_CUSTOMER", "RESOLVED"},
    "tile": set(TILES),
    "aging": set(AGING_BUCKETS),
}
_UUIDS = ("client_id", "assignee", "import_batch")
_PARAMS = [
    *_ENUMS,
    *_UUIDS,
    "currency", "due_from", "due_to", "amount_min", "amount_max", "q", "sort", "limit", "cursor",
]  # fmt: skip
_Q_MAX = 100


def _uuid(name: str, raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError:
        raise invalid(name, "Use an id.") from None


def _day(name: str, raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise invalid(name, "Use a date as YYYY-MM-DD.") from None


def _amount(name: str, raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise invalid(name, "Use an amount such as 20.50.") from None
    if not value.is_finite() or value < 0 or "e" in raw.lower():
        raise invalid(name, "Use an amount such as 20.50.")
    return value


def list_query(request: Any) -> read_models.ListQuery:
    raw = query_values(request, _PARAMS)
    fields: dict[str, Any] = {}
    for name, allowed in _ENUMS.items():
        if name in raw:
            if raw[name] not in allowed:
                raise invalid(name, "This is not one of the accepted values.")
            fields[name] = raw[name]
    for name in _UUIDS:
        if name in raw:
            fields[name] = _uuid(name, raw[name])
    if "currency" in raw:
        if raw["currency"] not in ISO_4217_CODES:
            raise invalid("currency", "Use a three-letter currency code.")
        fields["currency"] = raw["currency"]
    for name in ("due_from", "due_to"):
        if name in raw:
            fields[name] = _day(name, raw[name])
    for name in ("amount_min", "amount_max"):
        if name in raw:
            fields[name] = _amount(name, raw[name])
    if "q" in raw:
        if len(raw["q"]) > _Q_MAX:
            raise invalid("q", f"Use at most {_Q_MAX} characters.")
        fields["q"] = raw["q"].strip() or None
    if "sort" in raw:
        if raw["sort"] not in read_models.SORTS:
            raise invalid("sort", "This is not an accepted sort.")
        fields["sort"] = raw["sort"]
    fields["limit"] = limit_param(raw.get("limit"))
    fields["cursor"] = raw.get("cursor")
    return read_models.ListQuery(**fields)


def _filters() -> list[OpenApiParameter]:
    return [OpenApiParameter(name, str) for name in _PARAMS]


def _detail(detail: dict[str, Any]) -> Response:
    return Response(detail, headers={"ETag": etag(detail["version"])})


class InvoiceCollectionView(APIView):
    @endpoint("E042", responses={200: InvoicePageOut}, parameters=_filters())
    def get(self, request: Any, ws: UUID) -> Response:
        return Response(read_models.list_invoices(request.ctx, list_query(request)))


class InvoiceDetailView(APIView):
    @endpoint("E043", responses={200: InvoiceDetailOut})
    def get(self, request: Any, ws: UUID, invoice_id: UUID) -> Response:
        return _detail(read_models.invoice_detail(request.ctx, invoice_id))

    @endpoint("E044", request=InvoiceCorrectionIn, responses={200: InvoiceDetailOut})
    def patch(self, request: Any, ws: UUID, invoice_id: UUID) -> Response:
        version = expected_version(request)
        body = validated(InvoiceCorrectionIn, request)
        reason = body.pop("reason")
        return _detail(service_invoice.correct_invoice(request.ctx, invoice_id, version, body, reason))


class InvoiceCancelView(APIView):
    @endpoint("E045", request=InvoiceReasonIn, responses={200: InvoiceDetailOut})
    @idempotent
    def post(self, request: Any, ws: UUID, invoice_id: UUID) -> Response:
        reason = validated(InvoiceReasonIn, request)["reason"]
        return _detail(service_invoice.cancel_invoice(request.ctx, invoice_id, reason))


class InvoiceArchiveView(APIView):
    @endpoint("E046", request=InvoiceReasonIn, responses={200: InvoiceDetailOut})
    @idempotent
    def post(self, request: Any, ws: UUID, invoice_id: UUID) -> Response:
        reason = validated(InvoiceReasonIn, request)["reason"]
        return _detail(service_invoice.archive_invoice(request.ctx, invoice_id, reason))


class QueueView(APIView):
    @endpoint("E047", responses={200: QueuePageOut}, parameters=_filters())
    def get(self, request: Any, ws: UUID) -> Response:
        return Response(read_models.queue(request.ctx, list_query(request)))


class DashboardView(APIView):
    @endpoint("E048", responses={200: DashboardOut})
    def get(self, request: Any, ws: UUID) -> Response:
        query_values(request, [])
        return Response(read_models.dashboard(request.ctx))
