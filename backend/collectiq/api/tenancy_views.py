"""E010–E015, E114, E115: workspaces, members and invitations."""
from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.platform.context import RequestContext
from collectiq.platform.errors import ProblemError
from collectiq.platform.idempotency import idempotent
from collectiq.tenancy import service

from .common import correlation_id, etag, expected_version, page_params, validated
from .registry import endpoint
from .serializers import (
    InvitationAcceptedOut,
    InvitationIn,
    InvitationOut,
    MemberOut,
    MemberPageOut,
    MemberRoleIn,
    TokenIn,
    WorkspaceCreateIn,
    WorkspaceOut,
    WorkspaceUpdateIn,
)


def _unverified() -> ProblemError:
    return ProblemError("FORBIDDEN", 403, "Verify your email address to continue.")


def _new_workspace_context(request: Any, key: UUID) -> RequestContext:
    principal = request.principal
    if not principal.verified:
        raise _unverified()
    workspace_id = service.new_workspace_id(principal.user_id, key)
    return RequestContext(workspace_id, principal.user_id, "OWNER", correlation_id(request), "USER")


def _workspace_response(workspace: dict[str, Any], status: int = 200) -> Response:
    return Response(workspace, status=status, headers={"ETag": etag(workspace["version"])})


class WorkspaceCollectionView(APIView):
    @endpoint("E010", request=WorkspaceCreateIn, responses={201: WorkspaceOut})
    @idempotent(ctx_from=_new_workspace_context)
    def post(self, request: Any) -> Response:
        workspace = service.create_workspace(request.ctx, validated(WorkspaceCreateIn, request))
        return _workspace_response(workspace, 201)


class WorkspaceDetailView(APIView):
    @endpoint("E011", responses={200: WorkspaceOut})
    def get(self, request: Any, ws: UUID) -> Response:
        return _workspace_response(service.get_workspace(request.ctx))

    @endpoint("E012", request=WorkspaceUpdateIn, responses={200: WorkspaceOut})
    def patch(self, request: Any, ws: UUID) -> Response:
        version = expected_version(request)
        changes = validated(WorkspaceUpdateIn, request)
        return _workspace_response(service.update_workspace(request.ctx, version, changes))


class MemberCollectionView(APIView):
    @endpoint(
        "E013",
        responses={200: MemberPageOut},
        parameters=[OpenApiParameter("limit", int), OpenApiParameter("cursor", str)],
    )
    def get(self, request: Any, ws: UUID) -> Response:
        limit, cursor = page_params(request)
        return Response(service.list_members(request.ctx, limit, cursor))


class InvitationCollectionView(APIView):
    @endpoint("E014", request=InvitationIn, responses={201: InvitationOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        data = validated(InvitationIn, request)
        return Response(service.invite(request.ctx, data["email"], data["role"]), status=201)


class MemberDetailView(APIView):
    @endpoint("E015", request=None, responses={204: None})
    @idempotent
    def delete(self, request: Any, ws: UUID, member_id: UUID) -> Response:
        service.remove_member(request.ctx, member_id)
        return Response(status=204)

    @endpoint("E115", request=MemberRoleIn, responses={200: MemberOut})
    def patch(self, request: Any, ws: UUID, member_id: UUID) -> Response:
        role = validated(MemberRoleIn, request)["role"]
        return Response(service.change_role(request.ctx, member_id, role))


class InvitationAcceptView(APIView):
    @endpoint("E114", request=TokenIn, responses={200: InvitationAcceptedOut})
    def post(self, request: Any) -> Response:
        principal = request.principal
        if not principal.verified:
            raise _unverified()
        token = validated(TokenIn, request)["token"]
        return Response(
            service.accept_invitation(token, principal.user_id, principal.email, correlation_id(request))
        )
