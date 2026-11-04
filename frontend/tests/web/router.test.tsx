import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { appRoutes, ROUTE_PATHS } from "../../src/app/router";

const WS = "11111111-1111-4111-8111-111111111111";
const FOREIGN = "22222222-2222-4222-8222-222222222222";

const SESSION = {
  user: { id: "u1", email: "a@example.test", email_verified: true },
  workspaces: [{ id: WS, name: "Acme Studio", role: "OWNER" }],
  csrf_token: "t",
};

function stubSession(status: number) {
  vi.stubGlobal("fetch", () =>
    Promise.resolve(
      status === 200
        ? new Response(JSON.stringify(SESSION), { status: 200, headers: { "Content-Type": "application/json" } })
        : new Response(JSON.stringify({ status, code: "AUTH_REQUIRED", detail: "Sign in.", correlation_id: "c" }), {
            status,
            headers: { "Content-Type": "application/problem+json" },
          }),
    ),
  );
}

function open(path: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, view };
}

describe("routes", () => {
  it("declares every route in the brief", () => {
    for (const path of [
      "/signup",
      "/login",
      "/verify-email",
      "/onboarding/:step",
      "/w/:ws/dashboard",
      "/w/:ws/receivables",
      "/w/:ws/invoices/:id/:tab",
      "/w/:ws/clients/:id",
      "/w/:ws/import/invoices",
      "/w/:ws/reconciliation/:tab",
      "/w/:ws/accounts",
      "/w/:ws/conversations",
      "/w/:ws/messages/:id",
      "/w/:ws/cases",
      "/w/:ws/followups",
      "/w/:ws/reminders/:id",
      "/w/:ws/inbox",
      "/w/:ws/integrations",
      "/w/:ws/audit",
      "/w/:ws/settings/:tab",
    ]) {
      expect(ROUTE_PATHS).toContain(path);
    }
  });

  it("a foreign workspace and an unknown path render the same not-found page", async () => {
    stubSession(200);
    const foreign = open(`/w/${FOREIGN}/dashboard`);
    const heading = await screen.findByRole("heading", { name: /can't find that page/i });
    const foreignText = heading.closest("[data-page]")?.textContent;
    foreign.view.unmount();

    open("/no/such/place");
    const other = await screen.findByRole("heading", { name: /can't find that page/i });
    expect(other.closest("[data-page]")?.textContent).toBe(foreignText);
    expect(foreignText).not.toContain(FOREIGN);
  });

  it("an unknown record inside a member workspace reads the same, in the shell", async () => {
    stubSession(200);
    open(`/w/${WS}/no-such-screen`);
    expect(await screen.findByRole("heading", { name: /can't find that page/i })).toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent("Acme Studio");
  });

  it("a signed-out visitor goes to sign in", async () => {
    stubSession(401);
    const { router } = open(`/w/${WS}/dashboard`);
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
  });
});
