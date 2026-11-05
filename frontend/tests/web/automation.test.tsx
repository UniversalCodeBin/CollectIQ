import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../src/app/router";

const WS = "11111111-1111-4111-8111-111111111111";
const SESSION = {
  user: { id: "u1", email: "a@example.test", email_verified: true },
  workspaces: [{ id: WS, name: "Acme Studio", role: "OWNER" }],
  csrf_token: "t",
};
const API = `/api/v1/workspaces/${WS}`;

type Reply = { status: number; body?: unknown } | "network";
type Call = { key: string; body: unknown; headers: Headers; query: string };
let calls: Call[];

function stub(routes: Record<string, Reply | Reply[]>) {
  const replies: Record<string, Reply | Reply[]> = { "GET /api/v1/auth/session": { status: 200, body: SESSION }, ...routes };
  calls = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
    const [path = "", query = ""] = String(url).split("?");
    const key = `${(init.method ?? "GET").toUpperCase()} ${path}`;
    calls.push({ key, body: init.body && typeof init.body === "string" ? JSON.parse(init.body) : init.body, headers: new Headers(init.headers), query });
    const planned = replies[key];
    const reply = Array.isArray(planned) ? (planned.length > 1 ? planned.shift() : planned[0]) : planned;
    if (reply === undefined) throw new Error(`no stub for ${key}`);
    if (reply === "network") return Promise.reject(new TypeError("offline"));
    return Promise.resolve(
      new Response(reply.body === undefined ? null : JSON.stringify(reply.body), {
        status: reply.status,
        headers: { "Content-Type": reply.status >= 400 ? "application/problem+json" : "application/json" },
      }),
    );
  });
}

function open(path: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [`/w/${WS}/${path}`] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}
const called = (key: string) => calls.filter((call) => call.key === key);
const POLICY = {
  version: 1,
  mode: "MANUAL",
  automation_paused: false,
  auto_snooze_enabled: false,
  auto_snooze_available: false,
  cadence: {},
  limits: { max_contacts: 3 },
  business_hours: {},
  sensitivity_defaults: {},
  changed_by: null,
  effective_from: "2026-11-01T00:00:00Z",
};

beforeEach(() => window.sessionStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("automation", () => {
  it("pauses from any screen and shows the paused state", async () => {
    stub({
      [`GET ${API}/policy`]: [{ status: 200, body: POLICY }, { status: 200, body: { ...POLICY, version: 2, automation_paused: true } }],
      [`POST ${API}/automation/pause`]: { status: 200, body: { ...POLICY, version: 2, automation_paused: true } },
    });
    open("accounts");
    await userEvent.click(await screen.findByRole("button", { name: "Pause automation" }));
    expect(await screen.findByText(/Automation is paused/)).toBeTruthy();
    expect(called(`POST ${API}/automation/pause`)).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Resume automation" })).toBeTruthy();
  });

  it("shows no control when the policy cannot be read", async () => {
    stub({ [`GET ${API}/policy`]: { status: 403, body: { code: "FORBIDDEN", status: 403, detail: "no" } }, [`GET ${API}/payment-accounts`]: { status: 200, body: { items: [], next_cursor: null } } });
    open("accounts");
    await screen.findByText("No accounts yet");
    expect(screen.queryByRole("button", { name: /automation/i })).toBeNull();
  });

  it("saves the settings and says snoozing is not available", async () => {
    stub({
      [`GET ${API}/policy`]: { status: 200, body: POLICY },
      [`GET ${API}/policy/versions`]: { status: 200, body: { items: [POLICY], next_cursor: null } },
      [`PUT ${API}/policy`]: { status: 200, body: { ...POLICY, version: 2, mode: "ASSISTED" } },
    });
    open("settings/automation");
    expect(await screen.findByText(/not available yet/)).toBeTruthy();
    await userEvent.selectOptions(await screen.findByLabelText("Mode"), "ASSISTED");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(called(`PUT ${API}/policy`)).toHaveLength(1));
    expect(called(`PUT ${API}/policy`)[0]?.body).toEqual({ mode: "ASSISTED", limits: { max_contacts: 3 } });
  });

  it("refuses a contact limit that is not a whole number", async () => {
    stub({ [`GET ${API}/policy`]: { status: 200, body: POLICY }, [`GET ${API}/policy/versions`]: { status: 200, body: { items: [POLICY], next_cursor: null } } });
    open("settings/automation");
    const field = await screen.findByLabelText("Most reminders to one customer");
    await userEvent.clear(field);
    await userEvent.type(field, "x");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Enter a whole number from 1 to 20.")).toBeTruthy();
    expect(called(`PUT ${API}/policy`)).toHaveLength(0);
  });

  it("answers not-found for an unknown settings tab", async () => {
    stub({ [`GET ${API}/policy`]: { status: 200, body: POLICY } });
    open("settings/nothing");
    expect(await screen.findByRole("heading", { name: /not found|page/i })).toBeTruthy();
  });
});
