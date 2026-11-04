import type { ComponentType } from "react";
import type { RouteObject } from "react-router";
import { NotFoundPage } from "./NotFoundPage";
import { WorkspaceLayout } from "./WorkspaceLayout";

const PUBLIC_ROUTES = ["/signup", "/login", "/verify-email", "/onboarding/:step"];

const WORKSPACE_ROUTES = [
  "dashboard",
  "receivables",
  "invoices/:id/:tab",
  "clients/:id",
  "import/invoices",
  "reconciliation/:tab",
  "accounts",
  "conversations",
  "messages/:id",
  "cases",
  "followups",
  "reminders/:id",
  "inbox",
  "integrations",
  "audit",
  "settings/:tab",
];

/** Screens built so far, by route. A route with no screen yet answers not-found, never a placeholder. */
export const BUILT_SCREENS: Record<string, ComponentType> = {};

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
