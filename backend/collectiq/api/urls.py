from django.urls import path

from . import account_views as accounts
from . import ai_views as ai
from . import case_views as cases
from . import client_views as clients
from . import conversation_views as conversations
from . import identity_views as identity
from . import import_views as imports
from . import inbox_views as inbox
from . import invoice_views as invoices
from . import payment_views as payments
from . import policy_views as policy
from . import reconciliation_views as reconciliation
from . import reminder_views as reminders
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
    path(
        f"{_V1}workspaces/<uuid:ws>/invoices/<uuid:invoice_id>/payments",
        payments.InvoicePaymentHistoryView.as_view(),
    ),
    path(f"{_V1}workspaces/<uuid:ws>/payments/<uuid:payment_id>/void", payments.PaymentVoidView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/messages", conversations.MessageCollectionView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/messages/<uuid:message_id>", conversations.MessageDetailView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/messages/<uuid:message_id>/associations",
        conversations.MessageAssociationView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/messages/<uuid:message_id>/interpretation",
        conversations.MessageInterpretationView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/interpretations/<uuid:interpretation_id>/accept",
        conversations.InterpretationAcceptView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/interpretations/<uuid:interpretation_id>/dismiss",
        conversations.InterpretationDismissView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/interpretations/<uuid:interpretation_id>/correct",
        conversations.InterpretationCorrectView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/invoices/<uuid:invoice_id>/messages",
        conversations.InvoiceTimelineView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/invoices/<uuid:invoice_id>/commitments",
        conversations.InvoiceCommitmentsView.as_view(),
    ),
    path(f"{_V1}workspaces/<uuid:ws>/commitments", conversations.CommitmentCollectionView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/commitments/<uuid:commitment_id>",
        conversations.CommitmentDetailView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/invoices/<uuid:invoice_id>/snooze/approve",
        conversations.SnoozeApproveView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/invoices/<uuid:invoice_id>/snooze/undo",
        conversations.SnoozeUndoView.as_view(),
    ),
    path(f"{_V1}workspaces/<uuid:ws>/cases", cases.CaseCollectionView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/cases/<uuid:case_id>", cases.CaseDetailView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/cases/<uuid:case_id>/resolve", cases.CaseResolveView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/cases/<uuid:case_id>/reopen", cases.CaseReopenView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/invoices/<uuid:invoice_id>/followups/resume",
        cases.FollowupsResumeView.as_view(),
    ),
    path(f"{_V1}workspaces/<uuid:ws>/policy", policy.PolicyView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/policy/versions", policy.PolicyVersionsView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/automation/pause", policy.AutomationPauseView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/automation/resume", policy.AutomationResumeView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/approvals/<uuid:approval_id>/decide",
        policy.ApprovalDecideView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/policy-decisions/<uuid:decision_id>",
        policy.PolicyDecisionView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/payments/<uuid:payment_id>/attachment",
        payments.PaymentAttachmentView.as_view(),
    ),
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
    path(f"{_V1}workspaces/<uuid:ws>/reminders", reminders.ReminderCollectionView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/reminders/<uuid:reminder_id>", reminders.ReminderDetailView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/invoices/<uuid:invoice_id>/reminders/evaluate",
        reminders.ReminderEvaluateView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/reminders/<uuid:reminder_id>/approve",
        reminders.ReminderApproveView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/reminders/<uuid:reminder_id>/reject",
        reminders.ReminderRejectView.as_view(),
    ),
    path(
        f"{_V1}workspaces/<uuid:ws>/reminders/<uuid:reminder_id>/mark-sent",
        reminders.ReminderMarkSentView.as_view(),
    ),
    path(f"{_V1}health/live", identity.HealthLiveView.as_view()),
    path(f"{_V1}health/ready", identity.HealthReadyView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/notifications", inbox.NotificationCollectionView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/notifications/<uuid:notification_id>/read",
        inbox.NotificationReadView.as_view(),
    ),
    path(f"{_V1}workspaces/<uuid:ws>/ai/settings", ai.AiSettingsView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/invoices/pdf", ai.InvoicePdfView.as_view()),
    path(f"{_V1}workspaces/<uuid:ws>/extractions/<uuid:extraction_id>", ai.ExtractionView.as_view()),
    path(
        f"{_V1}workspaces/<uuid:ws>/extractions/<uuid:extraction_id>/confirm",
        ai.ExtractionConfirmView.as_view(),
    ),
    path(f"{_V1}workspaces/<uuid:ws>/review-inbox", inbox.ReviewInboxView.as_view()),
]
