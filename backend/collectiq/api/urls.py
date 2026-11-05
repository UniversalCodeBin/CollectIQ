from django.urls import path

from . import account_views as accounts
from . import client_views as clients
from . import identity_views as identity
from . import import_views as imports
from . import invoice_views as invoices
from . import payment_views as payments
from . import reconciliation_views as reconciliation
from . import statement_views as statements
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
    path(f"{_V1}workspaces/<uuid:ws>/clients", clients.ClientCollectionView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/clients/<uuid:client_id>", clients.ClientDetailView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/clients/<uuid:client_id>/contacts",
        clients.ContactCollectionView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/clients/<uuid:client_id>/contacts/<uuid:contact_id>",
        clients.ContactDetailView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/contacts/<uuid:contact_id>/suppression",
        clients.ContactSuppressionView.as_view(),
    ),
    path(f"{_V1}workspaces/<uuid:ws>/imports/transactions", statements.StatementImportView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/imports/invoices", imports.InvoiceImportCollectionView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/imports/<uuid:import_id>", imports.ImportDetailView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/imports/<uuid:import_id>/mapping", imports.ImportMappingView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/imports/<uuid:import_id>/commit", imports.ImportCommitView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/imports/<uuid:import_id>/error-report",
        imports.ImportErrorReportView.as_view(),
    ),
    path(f"{_V1}workspaces/<uuid:ws>/invoices", invoices.InvoiceCollectionView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/invoices/<uuid:invoice_id>", invoices.InvoiceDetailView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/invoices/<uuid:invoice_id>/cancel", invoices.InvoiceCancelView.as_view()
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/invoices/<uuid:invoice_id>/archive", invoices.InvoiceArchiveView.as_view()
    ),
    path(f"{_V1}workspaces/<uuid:ws>/queue", invoices.QueueView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/dashboard", invoices.DashboardView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/payment-accounts", accounts.PaymentAccountCollectionView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/payment-accounts/<uuid:account_id>",
        accounts.PaymentAccountDetailView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/payment-accounts/<uuid:account_id>/coverage",
        accounts.AccountCoverageView.as_view(),
    ),
    path(f"{_V1}workspaces/<uuid:ws>/attestations", accounts.AttestationView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/transactions/unmatched",
        reconciliation.UnmatchedTransactionsView.as_view(),
    ),
    path(f"{_V1}workspaces/<uuid:ws>/reconciliation/proposals", reconciliation.ProposalsView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/payments", payments.PaymentsView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/payments/<uuid:payment_id>", payments.PaymentDetailView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/payments/<uuid:payment_id>/void", payments.PaymentVoidView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/reconciliation/proposals/<uuid:proposal_id>/confirm",
        payments.ProposalConfirmView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/reconciliation/proposals/<uuid:proposal_id>/reject",
        payments.ProposalRejectView.as_view(),
    ),
    path(f"{_V1}workspaces/<uuid:ws>/allocations", payments.AllocationsView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/allocations/<uuid:allocation_id>/reverse",
        payments.AllocationReverseView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/transactions/<uuid:transaction_id>/mark-duplicate",
        payments.TransactionDuplicateView.as_view(),
    ),
    path(f"{_V1}health/live", identity.HealthLiveView.as_view()),
    path(f"{_V1}health/ready", identity.HealthReadyView.as_view()),
]
