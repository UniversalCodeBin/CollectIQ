import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { DIRECTIVE_NAV, NAV_ITEMS } from "../../src/app/nav";
import { Shell } from "../../src/app/Shell";

const LABELS = [
  "Dashboard",
  "Receivables",
  "Payment Reconciliation",
  "Conversations",
  "Disputes & Blockers",
  "Follow-ups",
  "Review Inbox",
  "Integrations",
  "Payment Accounts",
  "Audit History",
  "Settings",
];

describe("navigation", () => {
  it("the directive list is the 11 labels in order", () => {
    expect(DIRECTIVE_NAV).toEqual(LABELS);
  });

  it("the shell lists exactly the 11 labels", () => {
    expect(NAV_ITEMS.map((item) => item.label)).toEqual(LABELS);
  });

  it("nav items are a subset of the 11 directive labels, in directive order", () => {
    const positions = NAV_ITEMS.map((item) => LABELS.indexOf(item.label));
    expect(positions.every((position) => position >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it("every nav item is backed by a built screen", async () => {
    const { BUILT_SCREENS } = await import("../../src/app/router");
    for (const item of NAV_ITEMS) expect(BUILT_SCREENS).toHaveProperty(item.route);
  });

  it("the shell has the landmarks and a skip link", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <Shell workspaceId="w1" workspaceName="Acme Studio">
            <p>content</p>
          </Shell>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("banner")).toHaveTextContent("Acme Studio");
    expect(within(screen.getByRole("main")).getByText("content")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /skip to content/i })).toHaveAttribute("href", "#main");
  });
});
