"""Notifications and the review inbox (E106-E108)."""

from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.notifications import review_inbox, service
from collectiq.platform.idempotency import idempotent

from .common import page_params, validated
from .registry import endpoint
from .serializers import InboxOut, NotificationPageOut, NotificationPreferencesIn, NotificationPreferencesOut


class NotificationCollectionView(APIView):
    @endpoint(
        "E106",
        responses={200: NotificationPageOut},
        parameters=[OpenApiParameter("limit", int), OpenApiParameter("cursor", str)],
    )
    def get(self, request: Any, ws: UUID) -> Response:
        limit, cursor = page_params(request)
        return Response(service.list_notifications(request.ctx, limit, cursor))


class NotificationReadView(APIView):
    @endpoint("E107", responses={204: None})
    def post(self, request: Any, ws: UUID, notification_id: UUID) -> Response:
        service.mark_read(request.ctx, notification_id)
        return Response(status=204)


class NotificationPreferencesView(APIView):
    @endpoint("E125", responses={200: NotificationPreferencesOut})
    def get(self, request: Any, ws: UUID) -> Response:
        return Response(service.get_preferences(request.ctx))

    @endpoint("E126", request=NotificationPreferencesIn, responses={200: NotificationPreferencesOut})
    @idempotent
    def put(self, request: Any, ws: UUID) -> Response:
        data = validated(NotificationPreferencesIn, request)
        return Response(service.put_preferences(request.ctx, data["in_app"]))


class ReviewInboxView(APIView):
    @endpoint("E108", responses={200: InboxOut})
    def get(self, request: Any, ws: UUID) -> Response:
        return Response(review_inbox.review_inbox(request.ctx))
