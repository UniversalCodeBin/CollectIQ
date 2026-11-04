"""E001–E006, E009, E111–E113: accounts, sessions and health."""
from typing import Any

from django.conf import settings
from django.middleware.csrf import get_token, rotate_token
from drf_spectacular.utils import OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.identity import service
from collectiq.platform.health import check_ready
from collectiq.platform.idempotency import require_key
from collectiq.tenancy.service import workspaces_for

from .common import correlation_id, invalid, validated
from .registry import endpoint
from .serializers import (
    CredentialsIn,
    DetailOut,
    EmailIn,
    HealthOut,
    LoginOut,
    PasswordResetConfirmIn,
    SessionOut,
    TokenIn,
)

_LOGOUT_SCOPES = {"current": False, "all": True}


class RegisterView(APIView):
    @endpoint("E001", request=CredentialsIn, responses={201: DetailOut})
    def post(self, request: Any) -> Response:
        # The same body whether the address is new or known, so this call reveals nothing about accounts.
        require_key(request)
        data = validated(CredentialsIn, request)
        service.register(data["email"], data["password"], correlation_id(request))
        return Response({"detail": "Check your email to continue."}, status=201)


class VerifyEmailView(APIView):
    @endpoint("E002", request=TokenIn, responses={204: None})
    def post(self, request: Any) -> Response:
        service.verify_email(validated(TokenIn, request)["token"], correlation_id(request))
        return Response(status=204)


class ResendVerificationView(APIView):
    @endpoint("E113", request=EmailIn, responses={204: None})
    def post(self, request: Any) -> Response:
        service.resend_verification(validated(EmailIn, request)["email"], correlation_id(request))
        return Response(status=204)


class LoginView(APIView):
    @endpoint("E003", request=CredentialsIn, responses={200: LoginOut})
    def post(self, request: Any) -> Response:
        data = validated(CredentialsIn, request)
        token, user = service.login(
            data["email"],
            data["password"],
            correlation_id(request),
            request.COOKIES.get(settings.SESSION_COOKIE_NAME),
        )
        response = Response({"user": user, "workspaces": workspaces_for(user["id"])})
        response.set_cookie(
            settings.SESSION_COOKIE_NAME,
            token,
            max_age=int(settings.SESSION_ABSOLUTE_TTL.total_seconds()),
            httponly=True,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite=settings.SESSION_COOKIE_SAMESITE,
            path="/",
        )
        rotate_token(request._request)
        return response


class LogoutView(APIView):
    @endpoint(
        "E004",
        request=None,
        responses={204: None},
        parameters=[OpenApiParameter("scope", str, enum=sorted(_LOGOUT_SCOPES))],
    )
    def post(self, request: Any) -> Response:
        scope = request.query_params.get("scope", "current")
        if scope not in _LOGOUT_SCOPES:
            raise invalid("scope", "Use current or all.")
        service.logout(
            request.principal,
            request.COOKIES[settings.SESSION_COOKIE_NAME],
            _LOGOUT_SCOPES[scope],
            correlation_id(request),
        )
        response = Response(status=204)
        response.delete_cookie(
            settings.SESSION_COOKIE_NAME, path="/", samesite=settings.SESSION_COOKIE_SAMESITE
        )
        return response


class PasswordResetRequestView(APIView):
    @endpoint("E005", request=EmailIn, responses={204: None})
    def post(self, request: Any) -> Response:
        service.request_password_reset(validated(EmailIn, request)["email"], correlation_id(request))
        return Response(status=204)


class PasswordResetConfirmView(APIView):
    @endpoint("E006", request=PasswordResetConfirmIn, responses={204: None})
    def post(self, request: Any) -> Response:
        data = validated(PasswordResetConfirmIn, request)
        service.confirm_password_reset(data["token"], data["new_password"], correlation_id(request))
        return Response(status=204)


class SessionView(APIView):
    @endpoint("E009", responses={200: SessionOut})
    def get(self, request: Any) -> Response:
        principal = request.principal
        return Response(
            {
                "user": service.public_user(principal.user_id, principal.email, principal.verified),
                "workspaces": workspaces_for(principal.user_id),
                "csrf_token": get_token(request._request),
            }
        )


class HealthLiveView(APIView):
    @endpoint("E111", responses={200: HealthOut})
    def get(self, request: Any) -> Response:
        return Response({"status": "ok"})


class HealthReadyView(APIView):
    @endpoint("E112", responses={200: HealthOut, 503: HealthOut})
    def get(self, request: Any) -> Response:
        if check_ready():
            return Response({"status": "ok"})
        return Response({"status": "unavailable"}, status=503)
