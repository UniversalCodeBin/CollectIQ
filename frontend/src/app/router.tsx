import type { ComponentType } from "react";
import type { RouteObject } from "react-router";
import { AcceptInvitationPage } from "../features/auth/AcceptInvitationPage";
import { LoginPage } from "../features/auth/LoginPage";
import { ForgotPasswordPage, ResetPasswordPage } from "../features/auth/PasswordPages";
import { RootPage } from "../features/auth/RootPage";
import { SignupPage } from "../features/auth/SignupPage";
import { VerifyEmailPage } from "../features/auth/VerifyEmailPage";
import { CasesPage } from "../features/cases/CasesPage";
import { ConversationsPage } from "../features/conversations/ConversationsPage";
import { MessagePage } from "../features/conversations/MessagePage";
import { PendingInterpretationsPage } from "../features/conversations/PendingInterpretationsPage";
import { FollowupsPage } from "../features/followups/FollowupsPage";
import { ReminderPage } from "../features/followups/ReminderPage";
import { InboxPage } from "../features/inbox/InboxPage";
import { ClientPage } from "../features/client/ClientPage";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { PdfExtractionPage } from "../features/ai/PdfExtractionPage";
import { ImportPage } from "../features/import/ImportPage";
import { InvoicePage } from "../features/invoice/InvoicePage";
import { OnboardingPage } from "../features/onboarding/OnboardingPage";
import { IntegrationsPage } from "../features/integrations/IntegrationsPage";
import { AuditPage } from "../features/audit/AuditPage";
import { AutomationPage } from "../features/automation/AutomationPage";
import { AccountsPage } from "../features/accounts/AccountsPage";
import { ReconciliationPage } from "../features/reconciliation/ReconciliationPage";
import { ReceivablesPage } from "../features/receivables/ReceivablesPage";
import { NotFoundPage } from "./NotFoundPage";
import { WorkspaceLayout } from "./WorkspaceLayout";

const PUBLIC_ROUTES = [
  "/",
  "/signup",
  "/login",
  "/verify-email",
  "/forgot-password",
  "/reset-password",
  "/invitations/accept",
  "/onboarding/:step",
];

const WORKSPACE_ROUTES = [
  "dashboard",
  "receivables",
  "invoices/:id/:tab",
  "clients/:id",
  "import/invoices",
  "import/pdf",
  "reconciliation/:tab",
  "accounts",
  "conversations",
  "messages/:id",
  "interpretations",
  "cases",
  "followups",
  "reminders/:id",
  "inbox",
  "integrations",
  "audit",
  "settings/:tab",
];

/** Screens built so far, by route. A route with no screen yet answers not-found, never a placeholder. */
export const BUILT_SCREENS: Record<string, ComponentType> = {
  "/": RootPage,
  "/signup": SignupPage,
  "/login": LoginPage,
  "/verify-email": VerifyEmailPage,
  "/forgot-password": ForgotPasswordPage,
  "/reset-password": ResetPasswordPage,
  "/invitations/accept": AcceptInvitationPage,
  "/onboarding/:step": OnboardingPage,
  dashboard: DashboardPage,
  "import/invoices": ImportPage,
  "import/pdf": PdfExtractionPage,
  receivables: ReceivablesPage,
  "invoices/:id/:tab": InvoicePage,
  "clients/:id": ClientPage,
  "reconciliation/:tab": ReconciliationPage,
  accounts: AccountsPage,
  conversations: ConversationsPage,
  "messages/:id": MessagePage,
  interpretations: PendingInterpretationsPage,
  cases: CasesPage,
  followups: FollowupsPage,
  "reminders/:id": ReminderPage,
  inbox: InboxPage,
  integrations: IntegrationsPage,
  audit: AuditPage,
  "settings/:tab": AutomationPage,
};

function screen(route: string): ComponentType {
  return BUILT_SCREENS[route] ?? NotFoundPage;
}

export const ROUTE_PATHS = [...PUBLIC_ROUTES, ...WORKSPACE_ROUTES.map((route) => `/w/:ws/${route}`)];

export const appRoutes: RouteObject[] = [
  ...PUBLIC_ROUTES.map((path) => ({ path, Component: screen(path) })),
  {
    path: "/w/:ws",
    Component: WorkspaceLayout,
    children: [
      ...WORKSPACE_ROUTES.map((path) => ({ path, Component: screen(path) })),
      { path: "*", Component: NotFoundPage },
    ],
  },
  { path: "*", Component: NotFoundPage },
];
