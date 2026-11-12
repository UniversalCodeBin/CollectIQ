// FILE GUIDE: every route in the app. Each screen is its own chunk, fetched the first time its route opens, so the
// first load carries only the shell and the screen in view. A route with no screen answers not-found.
import { type ComponentType, Suspense, use } from "react";
import type { RouteObject } from "react-router";
import { NotFoundPage } from "./NotFoundPage";
import { WorkspaceLayout } from "./WorkspaceLayout";

type Loader = () => Promise<ComponentType>;

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

/** Where the code for each screen lives. */
const SCREEN_LOADERS: Record<string, Loader> = {
  "/": () => import("../features/auth/RootPage").then((m) => m.RootPage),
  "/signup": () => import("../features/auth/SignupPage").then((m) => m.SignupPage),
  "/login": () => import("../features/auth/LoginPage").then((m) => m.LoginPage),
  "/verify-email": () => import("../features/auth/VerifyEmailPage").then((m) => m.VerifyEmailPage),
  "/forgot-password": () => import("../features/auth/PasswordPages").then((m) => m.ForgotPasswordPage),
  "/reset-password": () => import("../features/auth/PasswordPages").then((m) => m.ResetPasswordPage),
  "/invitations/accept": () => import("../features/auth/AcceptInvitationPage").then((m) => m.AcceptInvitationPage),
  "/onboarding/:step": () => import("../features/onboarding/OnboardingPage").then((m) => m.OnboardingPage),
  dashboard: () => import("../features/dashboard/DashboardPage").then((m) => m.DashboardPage),
  "import/invoices": () => import("../features/import/ImportPage").then((m) => m.ImportPage),
  "import/pdf": () => import("../features/ai/PdfExtractionPage").then((m) => m.PdfExtractionPage),
  receivables: () => import("../features/receivables/ReceivablesPage").then((m) => m.ReceivablesPage),
  "invoices/:id/:tab": () => import("../features/invoice/InvoicePage").then((m) => m.InvoicePage),
  "clients/:id": () => import("../features/client/ClientPage").then((m) => m.ClientPage),
  "reconciliation/:tab": () =>
    import("../features/reconciliation/ReconciliationPage").then((m) => m.ReconciliationPage),
  accounts: () => import("../features/accounts/AccountsPage").then((m) => m.AccountsPage),
  conversations: () => import("../features/conversations/ConversationsPage").then((m) => m.ConversationsPage),
  "messages/:id": () => import("../features/conversations/MessagePage").then((m) => m.MessagePage),
  interpretations: () =>
    import("../features/conversations/PendingInterpretationsPage").then((m) => m.PendingInterpretationsPage),
  cases: () => import("../features/cases/CasesPage").then((m) => m.CasesPage),
  followups: () => import("../features/followups/FollowupsPage").then((m) => m.FollowupsPage),
  "reminders/:id": () => import("../features/followups/ReminderPage").then((m) => m.ReminderPage),
  inbox: () => import("../features/inbox/InboxPage").then((m) => m.InboxPage),
  integrations: () => import("../features/integrations/IntegrationsPage").then((m) => m.IntegrationsPage),
  audit: () => import("../features/audit/AuditPage").then((m) => m.AuditPage),
  "settings/:tab": () => import("../features/automation/AutomationPage").then((m) => m.AutomationPage),
};

/** Screens whose code has arrived, and the one request in flight for each that has not. */
const requests = new Map<string, Promise<ComponentType>>();

/** One request per route, kept for good, so the same promise comes back every time it is asked for. */
function remember(route: string, load: Loader): Loader {
  return () => {
    let request = requests.get(route);
    if (!request) {
      const pending = load();
      request = pending;
      // React reads these two fields from a promise it has not seen yet, so a screen already loaded renders at once.
      const tracked = pending as Promise<ComponentType> & { status?: string; value?: ComponentType };
      pending.then(
        (component) => {
          tracked.status = "fulfilled";
          tracked.value = component;
        },
        () => requests.delete(route),
      );
      requests.set(route, pending);
    }
    return request;
  };
}

/** Screens built so far, by route, each fetched the first time it opens. A route with no screen answers not-found. */
export const BUILT_SCREENS: Record<string, Loader> = Object.fromEntries(
  Object.entries(SCREEN_LOADERS).map(([route, load]) => [route, remember(route, load)]),
);

/** Shown in place of a screen for the moment its code is on the way. Quiet, and announced once. */
function ScreenLoading() {
  return (
    <p role="status" className="visually-hidden">
      Loading…
    </p>
  );
}

/** A screen waits under Suspense the first time its code is fetched, and renders at once after that. */
function screen(route: string): ComponentType {
  const found = BUILT_SCREENS[route];
  if (!found) return NotFoundPage;
  const load: Loader = found;
  function Resolved() {
    const Component = use(load());
    return <Component />;
  }
  return function LoadedScreen() {
    return (
      <Suspense fallback={<ScreenLoading />}>
        <Resolved />
      </Suspense>
    );
  };
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
