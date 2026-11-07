import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../src/app/router";

const WS = "11111111-1111-4111-8111-111111111111";
const INV_A = "33333333-3333-4333-8333-333333333333";
const MSG = "77777777-7777-4777-8777-777777777777";
const CASE = "88888888-8888-4888-8888-888888888888";
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

beforeEach(() => window.sessionStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

import { TIMELINE_RENDERERS } from "../../src/features/conversations/Timeline";

const message = (over: Record<string, unknown> = {}) => ({
  id: MSG,
  source: "PASTE",
  sender: "ap@northwind.example.test",
  subject: "Re: INV-2041",
  received_at: "2026-11-03T09:00:00Z",
  uploaded_by: "u1",
  created_at: "2026-11-03T09:05:00Z",
  is_customer_statement: true,
  associations: [{ invoice_id: INV_A, invoice_number: "INV-2041", labels: ["PAYMENT_CLAIM"] }],
  body: "We have paid this already.",
  effects: [],
  ...over,
});
const page = (items: unknown[]) => ({ status: 200, body: { items, next_cursor: null } });
const theCase = (over: Record<string, unknown> = {}) => ({
  id: CASE,
  invoice_id: INV_A,
  invoice_number: "INV-2041",
  type: "DISPUTE",
  status: "OPEN",
  dispute_type: "AMOUNT",
  summary: "Customer says the amount is wrong.",
  summary_is_ai_derived: false,
  source_message_id: MSG,
  assignee_id: null,
  opened_by_kind: "USER",
  opened_at: "2026-11-03T09:10:00Z",
  resolution_outcome: null,
  resolution_note: null,
  resolved_by: null,
  resolved_at: null,
  reopen_count: 0,
  version: 1,
  ...over,
});

describe("Conversations", () => {
  it("lists replies as plain text with the invoices they are about", async () => {
    stub({ [`GET ${API}/messages`]: page([{ ...message(), preview: "We have paid this already." }]) });
    open("conversations");
    expect(await screen.findByText("Re: INV-2041")).toBeInTheDocument();
    expect(screen.getByText("We have paid this already.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Re: INV-2041/ })).toHaveAttribute("href", `/w/${WS}/messages/${MSG}`);
  });

  it("sends a pasted reply as a PASTE capture", async () => {
    stub({ [`GET ${API}/messages`]: page([]), [`POST ${API}/messages`]: { status: 201, body: message() } });
    open("conversations");
    await userEvent.type(await screen.findByLabelText(/Paste the customer's reply/), "Will pay Friday");
    await userEvent.click(screen.getByRole("button", { name: "Save reply" }));
    await waitFor(() => expect(called(`POST ${API}/messages`)).toHaveLength(1));
    const form = called(`POST ${API}/messages`)[0]?.body as FormData;
    expect(form.get("source")).toBe("PASTE");
    expect(form.get("text")).toBe("Will pay Friday");
    expect(called(`POST ${API}/messages`)[0]?.headers.get("Idempotency-Key")).toBeTruthy();
  });
});

describe("A customer reply", () => {
  it("keeps the three layers apart and says a claim is not verified", async () => {
    stub({ [`GET ${API}/messages/${MSG}`]: { status: 200, body: message() } });
    open(`messages/${MSG}`);
    expect(await screen.findByRole("heading", { name: "What the customer said" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What a person recorded" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What is verified" })).toBeInTheDocument();
    expect(screen.getByText("We have paid this already.")).toBeInTheDocument();
    expect(screen.getByText("Payment not verified")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "INV-2041" })).toHaveAttribute("href", `/w/${WS}/invoices/${INV_A}/overview`);
  });

  it("shows a pasted script tag as text, never as markup", async () => {
    const hostile = '<script>window.hacked = true</script><img src=x onerror="alert(1)">';
    stub({ [`GET ${API}/messages/${MSG}`]: { status: 200, body: message({ body: hostile }) } });
    const { container } = { container: document.body };
    open(`messages/${MSG}`);
    expect(await screen.findByText(hostile)).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("does not claim a verified payment when there is no claim", async () => {
    stub({ [`GET ${API}/messages/${MSG}`]: { status: 200, body: message({ associations: [{ invoice_id: INV_A, invoice_number: "INV-2041", labels: ["DOCUMENT_REQUEST"] }] }) } });
    open(`messages/${MSG}`);
    await screen.findByRole("heading", { name: "What is verified" });
    expect(screen.queryByText("Payment not verified")).not.toBeInTheDocument();
    expect(screen.getByText(/does not change any payment record/i)).toBeInTheDocument();
  });
});

describe("Invoice timeline", () => {
  it("has a renderer for every event type the server sends", () => {
    expect(Object.keys(TIMELINE_RENDERERS).sort()).toEqual(["CASE", "COMMITMENT", "MESSAGE", "SNOOZE", "VERIFICATION_TASK"]);
  });

  it("renders each event and survives a type it does not know", async () => {
    const at = "2026-11-03T09:00:00Z";
    const invoice = {
      facts: { id: INV_A, invoice_number: "INV-2041", client_id: "c1", client_name: "Northwind Traders", status: "ISSUED", currency: "INR", gross_minor: 100000, subtotal_minor: null, tax_minor: null, issue_date: null, due_date: "2026-10-01", payment_terms: null, po_number: null, project_ref: null, description: null },
      derived: {},
      allowed_actions: [],
      recommended_action: null,
    };
    stub({
      [`GET ${API}/invoices/${INV_A}`]: { status: 200, body: invoice },
      [`GET ${API}/invoices/${INV_A}/messages`]: page([
        { type: "MESSAGE", id: MSG, at, title: "Re: INV-2041", sender: "ap@northwind.example.test", excerpt: "We have paid.", labels: ["PAYMENT_CLAIM"], is_customer_statement: true },
        { type: "COMMITMENT", id: "c1", at, title: "Customer promise recorded", strength: "EXPLICIT", date: "2026-11-10", status: "ACTIVE" },
        { type: "CASE", id: CASE, at, title: "Dispute opened", case_type: "DISPUTE", status: "OPEN" },
        { type: "SNOOZE", id: "s1", at, title: "Follow-ups paused by a person", until: "2026-11-12", status: "ACTIVE" },
        { type: "VERIFICATION_TASK", id: "v1", at, title: "Payment not verified", status: "OPEN" },
        { type: "FUTURE_KIND", id: "x1", at, title: "Something new" },
      ]),
    });
    open(`invoices/${INV_A}/timeline`);
    const list = await screen.findByRole("list", { name: "Conversation timeline" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(6);
    expect(within(list).getByText("Dispute opened")).toBeInTheDocument();
    expect(within(list).getByText("Payment not verified")).toBeInTheDocument();
    expect(within(list).getByText("Something new")).toBeInTheDocument();
    expect(within(list).getByText(/Customer statement/)).toBeInTheDocument();
  });
});

describe("Disputes and questions", () => {
  it("lists cases and shows an AI-drafted summary as unverified", async () => {
    stub({ [`GET ${API}/cases`]: page([theCase({ summary_is_ai_derived: true })]) });
    open("cases");
    expect(await screen.findByText("Customer says the amount is wrong.")).toBeInTheDocument();
    expect(screen.getByText(/AI-drafted summary/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "INV-2041" })).toHaveAttribute("href", `/w/${WS}/invoices/${INV_A}/overview`);
  });

  it("will not resolve without an outcome", async () => {
    stub({ [`GET ${API}/cases`]: page([theCase()]), [`POST ${API}/cases/${CASE}/resolve`]: { status: 200, body: theCase({ status: "RESOLVED" }) } });
    open("cases");
    await userEvent.click(await screen.findByRole("button", { name: "Resolve" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Resolve case" }));
    expect(await within(dialog).findByText("Choose how this was resolved.")).toBeInTheDocument();
    expect(called(`POST ${API}/cases/${CASE}/resolve`)).toHaveLength(0);
  });

  it("resolves with the chosen outcome and a note, once", async () => {
    stub({ [`GET ${API}/cases`]: page([theCase()]), [`POST ${API}/cases/${CASE}/resolve`]: { status: 200, body: theCase({ status: "RESOLVED" }) } });
    open("cases");
    await userEvent.click(await screen.findByRole("button", { name: "Resolve" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.selectOptions(within(dialog).getByLabelText("Outcome"), "ADJUSTMENT_AGREED");
    await userEvent.type(within(dialog).getByLabelText(/Note/), "Credit note agreed");
    await userEvent.click(within(dialog).getByRole("button", { name: "Resolve case" }));
    await waitFor(() => expect(called(`POST ${API}/cases/${CASE}/resolve`)).toHaveLength(1));
    const [call] = called(`POST ${API}/cases/${CASE}/resolve`);
    expect(call?.body).toEqual({ outcome: "ADJUSTMENT_AGREED", note: "Credit note agreed" });
    expect(call?.headers.get("Idempotency-Key")).toBeTruthy();
  });

  it("offers reopen, not resolve, for a resolved case", async () => {
    stub({ [`GET ${API}/cases`]: page([theCase({ status: "RESOLVED", resolution_outcome: "NO_CHANGE" })]) });
    open("cases?status=RESOLVED");
    expect(await screen.findByRole("button", { name: "Reopen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resolve" })).not.toBeInTheDocument();
  });
});

describe("replies waiting for review", () => {
  const READING = "99999999-9999-4999-8999-999999999999";
  const reading = (over: Record<string, unknown> = {}) => ({
    id: READING,
    message_id: MSG,
    status: "PENDING_REVIEW",
    primary_label: "PAYMENT_CLAIM",
    confidence: "HIGH",
    evidence_span: "We paid last week.",
    date_note: null,
    ai_derived: true,
    verified: false,
    invoice_ids: [INV_A],
    ...over,
  });

  it("shows a reading as an unverified AI suggestion, never as a fact", async () => {
    stub({ [`GET ${API}/interpretations`]: { status: 200, body: { items: [reading()] } } });
    open("interpretations");
    expect(await screen.findByText("Customer says they paid")).toBeInTheDocument();
    expect(screen.getByText("AI suggestion, not verified")).toBeInTheDocument();
    expect(screen.getByText(/We paid last week/)).toBeInTheDocument();
  });

  it("accepting sends the decision and reloads the list", async () => {
    stub({
      [`GET ${API}/interpretations`]: [{ status: 200, body: { items: [reading()] } }, { status: 200, body: { items: [] } }],
      [`POST ${API}/interpretations/${READING}/accept`]: { status: 200, body: reading({ status: "ACCEPTED" }) },
    });
    open("interpretations");
    await userEvent.click(await screen.findByRole("button", { name: "Accept this reading" }));
    expect(await screen.findByText("Nothing to review")).toBeInTheDocument();
    expect(called(`POST ${API}/interpretations/${READING}/accept`)).toHaveLength(1);
  });

  it("a correction needs a reason before it can be saved", async () => {
    stub({
      [`GET ${API}/interpretations`]: { status: 200, body: { items: [reading()] } },
      [`POST ${API}/interpretations/${READING}/correct`]: { status: 200, body: reading({ status: "CORRECTED" }) },
    });
    open("interpretations");
    await userEvent.click(await screen.findByRole("button", { name: "Correct it" }));
    await userEvent.click(screen.getByRole("button", { name: "Save correction" }));
    expect(called(`POST ${API}/interpretations/${READING}/correct`)).toHaveLength(0);
    await userEvent.type(screen.getByLabelText(/Why you are changing it/), "It is a dispute.");
    await userEvent.click(screen.getByRole("button", { name: "Save correction" }));
    await waitFor(() => expect(called(`POST ${API}/interpretations/${READING}/correct`)).toHaveLength(1));
    expect(called(`POST ${API}/interpretations/${READING}/correct`)[0]?.body).toMatchObject({ note: "It is a dispute." });
  });
});
