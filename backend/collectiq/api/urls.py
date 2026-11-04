from django.urls import path

from . import identity_views as identity
from . import tenancy_views as tenancy

_V1 = "api/v1/"

urlpatterns: list = [
    path(f"{_V1}auth/register", identity.RegisterView.as_view()),
    path(f"{_V1}auth/verify-email", identity.VerifyEmailView.as_view()),
    path(f"{_V1}auth/verify-email/resend", identity.ResendVerificationView.as_view()),
    path(f"{_V1}auth/login", identity.LoginView.as_view()),
    path(f"{_V1}auth/logout", identity.LogoutView.as_view()),
    path(f"{_V1}auth/password-reset/request", identity.PasswordResetRequestView.as_view()),
    path(f"{_V1}auth/password-reset/confirm", identity.PasswordResetConfirmView.as_view()),
    path(f"{_V1}auth/session", identity.SessionView.as_view()),
    path(f"{_V1}invitations/accept", tenancy.InvitationAcceptView.as_view()),
    path(f"{_V1}workspaces", tenancy.WorkspaceCollectionView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>", tenancy.WorkspaceDetailView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/members", tenancy.MemberCollectionView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/members/<uuid:member_id>", tenancy.MemberDetailView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/invitations", tenancy.InvitationCollectionView.as_view()),
    path(f"{_V1}health/live", identity.HealthLiveView.as_view()),
    path(f"{_V1}health/ready", identity.HealthReadyView.as_view()),
]
