import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../src/app/router";

const WS = "11111111-1111-4111-8111-111111111111";
const INV = "33333333-3333-4333-8333-333333333333";
const SESSION = {
  user: { id: "u1", email: "a@example.test", email_verified: true },
  workspaces: [{ id: WS, name: "Acme Studio", role: "OWNER" }],
  csrf_token: "t",
};
const API = `/api/v1/workspaces/${WS}`;

type Reply = { status: number; body?: unknown; headers?: Record<string, string> } | "network";
type Call = { key: string; body: unknown; headers: Headers; query: string };
let calls: Call[];

function stub(routes: Record<string, Reply | Reply[]>) {
  const replies: Record<string, Reply | Reply[]> = {
    "GET /api/v1/auth/session": { status: 200, body: SESSION },
    [`GET ${API}/policy`]: { status: 404, body: { code: "NOT_FOUND", detail: "x" } },
    ...routes,
  };
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
        headers: { "Content-Type": reply.status >= 400 ? "application/problem+json" : "application/json", ...(reply.headers ?? {}) },
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

const REM2 = "88888888-8888-4888-8888-888888888888";
const item = (kind: string, subject_ref: Record<string, string>, target_route: string, action: string, created_at = "2026-01-20T09:00:00Z") => ({
  kind,
  subject_ref,
  target_route,
  action,
  created_at,
});
const INBOX = {
  items: [
    item("CASE", { case_id: "c1", invoice_id: INV }, `invoices/${INV}/overview`, "Review the case"),
    item("REMINDER_DRAFT", { reminder_id: REM2, invoice_id: INV }, `reminders/${REM2}`, "Approve or reject the draft"),
    item("MATCH_PROPOSAL", { match_id: "m1", transaction_id: "t1", invoice_id: INV }, "reconciliation/review", "Confirm or reject the match"),
    item("PAYMENT_CLAIM", { task_id: "p1", invoice_id: INV, message_id: "ms1" }, `invoices/${INV}/overview`, "Verify the payment claim"),
    item("APPROVAL", { approval_id: "ap1", decision_id: "d1" }, "followups", "Approve or reject the request"),
  ],
  counts: { CASE: 1, REMINDER_DRAFT: 1, MATCH_PROPOSAL: 1, PAYMENT_CLAIM: 1, APPROVAL: 1 },
};
const NOTES = {
  items: [
    { id: "n1", type: "CASE_OPENED", subject_ref: { invoice_id: INV }, target_route: `invoices/${INV}/overview`, action: "Review the case", created_at: "2026-01-20T09:00:00Z", read_at: null },
    { id: "n2", type: "REMINDER_DRAFT_READY", subject_ref: { reminder_id: REM2 }, target_route: `reminders/${REM2}`, action: "Review the draft", created_at: "2026-01-19T09:00:00Z", read_at: "2026-01-19T10:00:00Z" },
  ],
  next_cursor: null,
};

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Review Inbox (SCR-17)", () => {
  it("lists every kind of waiting item under plain headings, each linking to where it is resolved", async () => {
    stub({ [`GET ${API}/review-inbox`]: { status: 200, body: INBOX }, [`GET ${API}/notifications`]: { status: 200, body: NOTES } });
    open("inbox");
    expect(await screen.findByRole("heading", { name: "Review Inbox" })).toBeInTheDocument();
    for (const name of ["Cases", "Reminder drafts", "Payment matches", "Payment claims", "Approvals"]) {
      expect(await screen.findByRole("heading", { name: new RegExp(`^${name}`) })).toBeInTheDocument();
    }
    // The notifications list below repeats some actions, so look only inside the group headings' lists.
    const hrefOf = (name: string) => screen.getAllByRole("link", { name })[0]?.getAttribute("href");
    expect(hrefOf("Approve or reject the draft")).toBe(`/w/${WS}/reminders/${REM2}`);
    expect(hrefOf("Confirm or reject the match")).toBe(`/w/${WS}/reconciliation/review`);
    expect(hrefOf("Review the case")).toBe(`/w/${WS}/invoices/${INV}/overview`);
    expect(hrefOf("Verify the payment claim")).toBe(`/w/${WS}/invoices/${INV}/overview`);
    expect(hrefOf("Approve or reject the request")).toBe(`/w/${WS}/followups`);
    expect(screen.queryByText(/G\d{1,2}_/)).toBeNull();
  });

  it("says plainly when nothing is waiting", async () => {
    stub({
      [`GET ${API}/review-inbox`]: { status: 200, body: { items: [], counts: {} } },
      [`GET ${API}/notifications`]: { status: 200, body: { items: [], next_cursor: null } },
    });
    open("inbox");
    expect(await screen.findByText("Nothing needs your review")).toBeInTheDocument();
  });

  it("marks a notification read and only unread ones offer the button", async () => {
    stub({
      [`GET ${API}/review-inbox`]: { status: 200, body: { items: [], counts: {} } },
      [`GET ${API}/notifications`]: { status: 200, body: NOTES },
      [`POST ${API}/notifications/n1/read`]: { status: 204 },
    });
    open("inbox");
    const buttons = await screen.findAllByRole("button", { name: "Mark as read" });
    expect(buttons).toHaveLength(1);
    await userEvent.click(buttons[0]!);
    await vi.waitFor(() => expect(called(`POST ${API}/notifications/n1/read`)).toHaveLength(1));
  });

  it("is reachable from the main navigation", async () => {
    stub({ [`GET ${API}/review-inbox`]: { status: 200, body: INBOX }, [`GET ${API}/notifications`]: { status: 200, body: NOTES } });
    open("inbox");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    for (const name of ["Receivables", "Conversations", "Disputes & Blockers", "Follow-ups", "Review Inbox"]) {
      expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    }
  });
});

describe("Onboarding checklist (SCR-01)", () => {
  const empty = { status: 200, body: { currencies: [], has_sample_data: false } };

  it("offers each step as a link or a skip, and remembers a skip", async () => {
    stub({ [`GET ${API}/dashboard`]: empty });
    open("dashboard");
    expect(await screen.findByRole("link", { name: "Import your invoices" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add payment evidence" })).toHaveAttribute("href", `/w/${WS}/accounts`);
    expect(screen.getByRole("link", { name: "Set your follow-up cadence" })).toHaveAttribute("href", `/w/${WS}/settings/automation`);
    await userEvent.click(screen.getByRole("button", { name: "Skip Add payment evidence" }));
    expect(screen.getByText("Skipped")).toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem(`collectiq.onboarding.${WS}`) ?? "[]")).toContain("evidence");
  });

  it("lets a person set the whole checklist aside and still reach the dashboard", async () => {
    stub({ [`GET ${API}/dashboard`]: empty });
    open("dashboard");
    await userEvent.click(await screen.findByRole("button", { name: "Hide this checklist" }));
    expect(screen.queryByRole("heading", { name: "Getting started" })).toBeNull();
    expect(screen.getByRole("link", { name: "Review the queue" })).toBeInTheDocument();
  });
});
