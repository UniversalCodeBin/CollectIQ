"""Customer replies, promises and snoozes (E062-E066, E071-E075)."""

import json
from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.conversations import service, service_commitments, service_interpretation
from collectiq.platform.idempotency import idempotent

from .common import etag, expected_version, invalid, page_params, validated
from .registry import endpoint
from .serializers import (
    AssociationIn,
    AssociationsIn,
    CommitmentIn,
    CommitmentOut,
    CommitmentPageOut,
    CommitmentRecordedOut,
    CommitmentUpdateIn,
    InterpretationCorrectIn,
    InterpretationNoteIn,
    InterpretationOut,
    MessageOut,
    MessagePageOut,
    PendingInterpretationListOut,
    SnoozeApproveIn,
    SnoozeStartedOut,
    SnoozeUndoIn,
    SnoozeUndoneOut,
    TimelinePageOut,
)

MAX_UPLOAD = 1_000_000

_CAPTURE_BODY = {
    "multipart/form-data": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "enum": ["PASTE", "EML", "TXT"]},
            "text": {"type": "string"},
            "file": {"type": "string", "format": "binary"},
            "sender": {"type": "string"},
            "subject": {"type": "string"},
            "received_at": {"type": "string", "format": "date-time"},
            "invoice_ids": {"type": "array", "items": {"type": "string"}, "description": "JSON objects"},
        },
        "required": ["source"],
    }
}


def _associations(request: Any) -> list[dict[str, Any]]:
    """Each repeated invoice_ids field is a JSON object: {"invoice_id": ..., "labels": [...]}."""
    items: list[dict[str, Any]] = []
    for raw in request.data.getlist("invoice_ids"):
        try:
            value = json.loads(raw)
        except ValueError:
            raise invalid("invoice_ids", "Each invoice must be a JSON object with an invoice_id.") from None
        if not isinstance(value, dict):
            raise invalid("invoice_ids", "Each invoice must be a JSON object with an invoice_id.")
        serializer = AssociationIn(data=value)
        serializer.is_valid(raise_exception=True)
        items.append(dict(serializer.validated_data))
    return items


class MessageCollectionView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    @endpoint(
        "E063",
        responses={200: MessagePageOut},
        parameters=[OpenApiParameter("limit", int), OpenApiParameter("cursor", str)],
    )
    def get(self, request: Any, ws: UUID) -> Response:
        limit, cursor = page_params(request)
        return Response(service.list_messages(request.ctx, limit, cursor))

    @endpoint("E062", request=_CAPTURE_BODY, responses={201: MessageOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        source = request.data.get("source", "")
        upload = request.FILES.get("file")
        if upload is not None and upload.size > MAX_UPLOAD:
            raise invalid("file", "That file is larger than 1 MB.")
        received = request.data.get("received_at")
        when = None
        if received:
            from django.utils.dateparse import parse_datetime

            when = parse_datetime(received)
            if when is None or when.tzinfo is None:
                raise invalid("received_at", "Use a date and time with a time zone.")
        if source == "PASTE" and not request.data.get("text"):
            raise invalid("text", "Paste the customer's reply.")
        if source != "PASTE" and upload is None:
            raise invalid("file", "Choose the .eml or .txt file.")
        message = service.capture(
            request.ctx,
            source,
            text=request.data.get("text"),
            filename=upload.name if upload else None,
            data=upload.read() if upload else None,
            sender=request.data.get("sender"),
            subject=request.data.get("subject"),
            received_at=when,
            associations=_associations(request),
        )
        # A reply a person already read is left to them; otherwise a model offers a reading to review.
        if message["associations"] and not any(a["labels"] for a in message["associations"]):
            service_interpretation.interpret(request.ctx, UUID(message["id"]))
        return Response(message, status=201)


class MessageDetailView(APIView):
    @endpoint("E064", responses={200: MessageOut})
    def get(self, request: Any, ws: UUID, message_id: UUID) -> Response:
        return Response(service.get_message(request.ctx, message_id))


class InvoiceTimelineView(APIView):
    @endpoint(
        "E065",
        responses={200: TimelinePageOut},
        parameters=[OpenApiParameter("limit", int), OpenApiParameter("cursor", str)],
    )
    def get(self, request: Any, ws: UUID, invoice_id: UUID) -> Response:
        limit, _ = page_params(request)
        return Response(service.invoice_timeline(request.ctx, invoice_id, limit))


class MessageAssociationView(APIView):
    parser_classes = [JSONParser]

    @endpoint("E066", request=AssociationsIn, responses={200: MessageOut})
    @idempotent
    def post(self, request: Any, ws: UUID, message_id: UUID) -> Response:
        data = validated(AssociationsIn, request)
        return Response(service.associate(request.ctx, message_id, list(data["invoice_ids"])))


class MessageInterpretationView(APIView):
    @endpoint("E067", responses={200: InterpretationOut})
    def get(self, request: Any, ws: UUID, message_id: UUID) -> Response:
        return Response(service_interpretation.get_for_message(request.ctx, message_id))


class PendingInterpretationsView(APIView):
    @endpoint("E124", responses={200: PendingInterpretationListOut})
    def get(self, request: Any, ws: UUID) -> Response:
        return Response(service_interpretation.list_pending(request.ctx))


class InterpretationAcceptView(APIView):
    parser_classes = [JSONParser]

    @endpoint("E068", request=InterpretationNoteIn, responses={200: InterpretationOut})
    @idempotent
    def post(self, request: Any, ws: UUID, interpretation_id: UUID) -> Response:
        data = validated(InterpretationNoteIn, request)
        return Response(service_interpretation.accept(request.ctx, interpretation_id, data.get("note")))


class InterpretationDismissView(APIView):
    parser_classes = [JSONParser]

    @endpoint("E069", request=InterpretationNoteIn, responses={200: InterpretationOut})
    @idempotent
    def post(self, request: Any, ws: UUID, interpretation_id: UUID) -> Response:
        data = validated(InterpretationNoteIn, request)
        return Response(service_interpretation.dismiss(request.ctx, interpretation_id, data.get("note")))


class InterpretationCorrectView(APIView):
    parser_classes = [JSONParser]

    @endpoint("E070", request=InterpretationCorrectIn, responses={200: InterpretationOut})
    @idempotent
    def post(self, request: Any, ws: UUID, interpretation_id: UUID) -> Response:
        data = validated(InterpretationCorrectIn, request)
        return Response(
            service_interpretation.correct(
                request.ctx,
                interpretation_id,
                data.get("intent"),
                data.get("date"),
                data.get("invoice_ids"),
                data["note"],
            )
        )


class InvoiceCommitmentsView(APIView):
    @endpoint(
        "E071",
        responses={200: CommitmentPageOut},
        parameters=[OpenApiParameter("limit", int), OpenApiParameter("cursor", str)],
    )
    def get(self, request: Any, ws: UUID, invoice_id: UUID) -> Response:
        limit, cursor = page_params(request)
        return Response(service_commitments.list_commitments(request.ctx, invoice_id, limit, cursor))


class CommitmentCollectionView(APIView):
    @endpoint("E072", request=CommitmentIn, responses={201: CommitmentRecordedOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        data = validated(CommitmentIn, request)
        made = service_commitments.record_commitment(
            request.ctx,
            data["invoice_id"],
            data["strength"],
            data.get("date"),
            data.get("window_start"),
            data.get("window_end"),
            data.get("note"),
        )
        return Response(made, status=201, headers={"ETag": etag(made["version"])})


class CommitmentDetailView(APIView):
    @endpoint("E073", request=CommitmentUpdateIn, responses={200: CommitmentOut})
    def patch(self, request: Any, ws: UUID, commitment_id: UUID) -> Response:
        data = validated(CommitmentUpdateIn, request)
        updated = service_commitments.update_commitment(
            request.ctx, commitment_id, expected_version(request), data.get("status"), data.get("note")
        )
        return Response(updated, headers={"ETag": etag(updated["version"])})


class SnoozeApproveView(APIView):
    @endpoint("E074", request=SnoozeApproveIn, responses={200: SnoozeStartedOut})
    @idempotent
    def post(self, request: Any, ws: UUID, invoice_id: UUID) -> Response:
        data = validated(SnoozeApproveIn, request)
        return Response(service_commitments.approve_snooze(request.ctx, invoice_id, data["approval_id"]))


class SnoozeUndoView(APIView):
    @endpoint("E075", request=SnoozeUndoIn, responses={200: SnoozeUndoneOut})
    @idempotent
    def post(self, request: Any, ws: UUID, invoice_id: UUID) -> Response:
        data = validated(SnoozeUndoIn, request)
        return Response(service_commitments.undo_snooze(request.ctx, invoice_id, data.get("reason")))
