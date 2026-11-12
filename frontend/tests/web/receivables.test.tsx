import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../src/app/router";
import { statusOf } from "../../src/lib/statusMap";

const WS = "11111111-1111-4111-8111-111111111111";
const INV = "33333333-3333-4333-8333-333333333333";
const CLIENT = "44444444-4444-4444-8444-444444444444";
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
  const replies: Record<string, Reply | Reply[]> = {
    "GET /api/v1/auth/session": { status: 200, body: SESSION },
    [`GET ${API}/reminder-pauses`]: { status: 200, body: { items: [] } },
    ...routes,
  };
  calls = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
    const [path = "", query = ""] = String(url).split("?");
    const key = `${(init.method ?? "GET").toUpperCase()} ${path}`;
    calls.push({ key, body: init.body ? JSON.parse(String(init.body)) : undefined, headers: new Headers(init.headers), query });
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
  return { router, url: () => `${router.state.location.pathname}${router.state.location.search}` };
}
const called = (key: string) => calls.filter((call) => call.key === key);

beforeEach(() => window.sessionStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const action = (name: string, allowed = true, reason: string | null = null) => ({ action: name, allowed, reason });
const row = (over: Record<string, unknown> = {}) => ({
  id: INV,
  invoice_number: "INV-2041",
  client_id: CLIENT,
  client_name: "Northwind Traders",
  currency: "INR",
  status: "ACTIVE",
  due_date: "2026-10-01",
  outstanding_minor: 150000,
  paid_minor: 0,
  payment_status: "OUTSTANDING",
  dispute_status: "NONE",
  reminder_status: "NONE",
  evidence_coverage: "MISSING",
  evidence_as_of: null,
  days_overdue: 35,
  due_bucket: "OVERDUE",
  allowed_actions: [],
  ...over,
});
const queueItem = (over: Record<string, unknown> = {}) => ({
  ...row(),
  tier: 1,
  reasons: [{ code: "EVIDENCE_MISSING", label: "No payment evidence yet", link: "payment-evidence" }],
  why_not: [],
  recommended_action: { code: "VERIFY_PAYMENT", label: "Check whether this was paid", can_act: true, performed_by: "YOU", reason: null },
  sample: false,
  ...over,
});

const tile = (key: string, count: number, amount: number, currency: string) => ({
  key,
  count,
  amount_minor: amount,
  filter: { tile: key, currency },
});
const bucket = (key: string, count: number, amount: number, currency: string) => ({
  bucket: key,
  count,
  amount_minor: amount,
  filter: { aging: key, currency },
});
const dashboard = (over: Record<string, unknown> = {}) => ({
  currencies: [
    {
      currency: "INR",
      tiles: [tile("outstanding", 4, 600000, "INR"), tile("overdue", 3, 450000, "INR"), tile("disputed", 1, 150000, "INR")],
      aging: [bucket("not_due", 1, 150000, "INR"), bucket("1-30", 2, 300000, "INR")],
    },
    { currency: "USD", tiles: [tile("outstanding", 2, 250000, "USD")], aging: [bucket("90+", 2, 250000, "USD")] },
  ],
  has_sample_data: false,
  as_of_date: "2026-11-05",
  ...over,
});

describe("Dashboard (SCR-02)", () => {
  it("shows every currency on its own and never one combined total", async () => {
    stub({ [`GET ${API}/dashboard`]: { status: 200, body: dashboard() } });
    open("dashboard");
    const inr = await screen.findByRole("region", { name: "INR" });
    const usd = screen.getByRole("region", { name: "USD" });
    expect(within(inr).getByText("₹6,000.00")).toBeInTheDocument();
    expect(within(usd).getByRole("link", { name: /outstanding/i })).toHaveTextContent("$2,500.00");
    expect(screen.queryByText(/total across/i)).not.toBeInTheDocument();
  });

  it("links each tile and aging bucket to the list filtered the way the server counted it", async () => {
    stub({ [`GET ${API}/dashboard`]: { status: 200, body: dashboard() } });
    open("dashboard");
    const inr = await screen.findByRole("region", { name: "INR" });
    const overdue = within(inr).getByRole("link", { name: /overdue/i });
    expect(overdue).toHaveAttribute("href", `/w/${WS}/receivables?view=all&tile=overdue&currency=INR`);
    const aging = within(inr).getByRole("link", { name: /1-30 days/i });
    expect(aging).toHaveAttribute("href", `/w/${WS}/receivables?view=all&aging=1-30&currency=INR`);
  });

  it("labels sample data so it is never mistaken for real invoices", async () => {
    stub({ [`GET ${API}/dashboard`]: { status: 200, body: dashboard({ has_sample_data: true }) } });
    open("dashboard");
    expect(await screen.findByText(/Sample data\. These records are made up/)).toBeInTheDocument();
  });

  it("shows the getting-started list when there are no invoices yet", async () => {
    stub({ [`GET ${API}/dashboard`]: { status: 200, body: dashboard({ currencies: [] }) } });
    open("dashboard");
    expect(await screen.findByRole("link", { name: "Import your invoices" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "INR" })).not.toBeInTheDocument();
  });

  it("says it is loading, then says what went wrong with a way to retry", async () => {
    stub({ [`GET ${API}/dashboard`]: [{ status: 500, body: { status: 500, code: "INTERNAL", detail: "", correlation_id: "cid-1" } }, { status: 200, body: dashboard() }] });
    open("dashboard");
    expect(screen.getByRole("status")).toHaveTextContent(/loading/i);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("region", { name: "INR" })).toBeInTheDocument();
  });

  it("has no accessibility violations once loaded", async () => {
    stub({ [`GET ${API}/dashboard`]: { status: 200, body: dashboard() } });
    open("dashboard");
    await screen.findByRole("region", { name: "INR" });
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
  });
});

describe("Receivables (SCR-03)", () => {
  const page = (items: unknown[], next: string | null = null) => ({ status: 200, body: { items, next_cursor: next } });

  it("opens on the queue, with the reason and the recommended action for each invoice", async () => {
    stub({ [`GET ${API}/queue`]: page([queueItem()]) });
    open("receivables");
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("link", { name: "INV-2041" })).toHaveAttribute("href", `/w/${WS}/invoices/${INV}/overview`);
    expect(within(table).getByText("No payment evidence yet")).toBeInTheDocument();
    expect(within(table).getByText("Check whether this was paid")).toBeInTheDocument();
  });

  it("reads the filters from the address and sends them to the server", async () => {
    stub({ [`GET ${API}/invoices`]: page([row()]) });
    open("receivables?view=all&tile=overdue&currency=INR");
    await screen.findByRole("table");
    const query = new URLSearchParams(called(`GET ${API}/invoices`)[0]?.query);
    expect(query.get("tile")).toBe("overdue");
    expect(query.get("currency")).toBe("INR");
  });

  it("switches between the queue and all invoices", async () => {
    stub({ [`GET ${API}/queue`]: page([queueItem()]), [`GET ${API}/invoices`]: page([row({ invoice_number: "INV-9" })]) });
    const view = open("receivables");
    await screen.findByRole("table");
    await userEvent.click(screen.getByRole("link", { name: "All invoices" }));
    expect(await screen.findByRole("link", { name: "INV-9" })).toBeInTheDocument();
    expect(view.url()).toContain("view=all");
  });

  it("loads the next page with the cursor the server gave", async () => {
    stub({
      [`GET ${API}/queue`]: [page([queueItem()], "cur-2"), page([queueItem({ id: "i2", invoice_number: "INV-2042" })])],
    });
    open("receivables");
    await screen.findByRole("link", { name: "INV-2041" });
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("link", { name: "INV-2042" })).toBeInTheDocument();
    expect(new URLSearchParams(called(`GET ${API}/queue`)[1]?.query).get("cursor")).toBe("cur-2");
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("says why an invoice is not in the queue's action list instead of leaving a blank", async () => {
    const waiting = queueItem({
      recommended_action: null,
      reasons: [],
      why_not: [{ code: "SNOOZED", label: "Reminders are paused until 16 Nov" }],
    });
    stub({ [`GET ${API}/queue`]: page([waiting]) });
    open("receivables");
    expect(await screen.findByText("Reminders are paused until 16 Nov")).toBeInTheDocument();
  });

  it("shows an empty state, not an empty table", async () => {
    stub({ [`GET ${API}/queue`]: page([]) });
    open("receivables");
    expect(await screen.findByText("Nothing needs your attention")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows the problem and a retry when the list cannot load", async () => {
    stub({ [`GET ${API}/queue`]: "network" });
    open("receivables");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("never offers a way to mark an invoice paid", async () => {
    stub({ [`GET ${API}/queue`]: page([queueItem()]) });
    open("receivables");
    await screen.findByRole("table");
    expect(screen.queryByText(/mark (as )?paid/i)).not.toBeInTheDocument();
  });
});

const detail = (over: Record<string, unknown> = {}) => ({
  version: 3,
  facts: {
    id: INV,
    invoice_number: "INV-2041",
    client_id: CLIENT,
    client_name: "Northwind Traders",
    status: "ACTIVE",
    currency: "INR",
    issue_date: "2026-09-01",
    due_date: "2026-10-01",
    gross_minor: 150000,
    subtotal_minor: 127119,
    tax_minor: 22881,
    payment_terms: "Net 30",
    po_number: "PO-77",
    project_ref: null,
    description: "Design retainer",
    line_items: [],
    diverges_from_source: false,
    corrected_fields: [],
    assignee_id: null,
  },
  derived: {
    payment_status: "OUTSTANDING",
    evidence_coverage: "MISSING",
    evidence_as_of: null,
    outstanding_minor: 150000,
    paid_minor: 0,
    overpayment_flag: false,
    dispute_status: "NONE",
    reminder_status: "NONE",
    days_overdue: 35,
    due_bucket: "OVERDUE",
  },
  ai_claims: [],
  provenance: { source_system: "CSV", file_name: "invoices.csv", source_row: 2, import_id: "imp-1" },
  recommended_action: { code: "VERIFY_PAYMENT", label: "Check whether this was paid", can_act: true, performed_by: "YOU", reason: null },
  reasons: [{ code: "EVIDENCE_MISSING", label: "No payment evidence yet", link: "payment-evidence" }],
  why_not: [],
  allowed_actions: [action("CORRECT"), action("CANCEL"), action("ARCHIVE")],
  ...over,
});

describe("Invoice details (SCR-04)", () => {
  const DETAIL = `GET ${API}/invoices/${INV}`;

  it("shows the invoice facts apart from what the system worked out", async () => {
    stub({ [DETAIL]: { status: 200, body: detail() } });
    open(`invoices/${INV}/overview`);
    expect(await screen.findByRole("heading", { name: "Invoice INV-2041" })).toBeInTheDocument();
    const facts = screen.getByRole("region", { name: "From the invoice" });
    expect(within(facts).getByText("₹1,500.00")).toBeInTheDocument();
    expect(within(facts).getByText("Net 30")).toBeInTheDocument();
    const derived = screen.getByRole("region", { name: "What CollectIQ worked out" });
    expect(within(derived).getByText("Outstanding")).toBeInTheDocument();
    expect(within(derived).getByText(/35 days overdue/)).toBeInTheDocument();
  });

  it("lists applied payments and reversals, oldest first (FR-056)", async () => {
    const row = (id: string, kind: string, amount_minor: number, note: string | null) => ({
      id, kind, amount_minor, currency: "INR", created_at: "2026-02-01T10:00:00Z", value_date: "2026-01-30",
      payer_descriptor: "Acme Ltd", evidence_type: "BANK_STATEMENT", overpayment_confirmed: false, note, transaction_id: "t1", invoice_id: INV,
    });
    stub({
      [DETAIL]: { status: 200, body: detail() },
      [`GET ${API}/invoices/${INV}/payments`]: { status: 200, body: { items: [row("a1", "ALLOCATION", 100000, null), row("a2", "REVERSAL", -100000, "Wrong invoice")] } },
    });
    open(`invoices/${INV}/history`);
    const list = await screen.findByRole("list", { name: "Payment history" });
    const items = within(list).getAllByRole("listitem") as [HTMLElement, HTMLElement];
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("Applied")).toBeInTheDocument();
    expect(within(items[1]).getByText("Reversed")).toBeInTheDocument();
    expect(within(items[1]).getByText(/Wrong invoice/)).toBeInTheDocument();
  });

  it("says when no payment has been applied", async () => {
    stub({ [DETAIL]: { status: 200, body: detail() }, [`GET ${API}/invoices/${INV}/payments`]: { status: 200, body: { items: [] } } });
    open(`invoices/${INV}/history`);
    expect(await screen.findByText("No payments applied yet")).toBeInTheDocument();
  });

  it("shows where the invoice came from", async () => {
    stub({ [DETAIL]: { status: 200, body: detail() } });
    open(`invoices/${INV}/overview`);
    const source = await screen.findByRole("region", { name: "Where this came from" });
    expect(within(source).getByText(/invoices\.csv/)).toBeInTheDocument();
    expect(within(source).getByText(/row 2/i)).toBeInTheDocument();
  });

  it("says routine reminders are paused only when the server holds them", async () => {
    const base = detail().derived;
    stub({ [DETAIL]: { status: 200, body: detail({ derived: { ...base, reminder_status: "SUPPRESSED" } }) } });
    open(`invoices/${INV}/overview`);
    expect(await screen.findByText("Routine reminders are paused for this invoice.")).toBeInTheDocument();
  });

  it("names an open dispute as the reason reminders are held", async () => {
    const base = detail().derived;
    stub({
      [DETAIL]: {
        status: 200,
        body: detail({ derived: { ...base, dispute_status: "OPEN", reminder_status: "SUPPRESSED" } }),
      },
    });
    open(`invoices/${INV}/overview`);
    expect(await screen.findByText("A dispute is open on this invoice.")).toBeInTheDocument();
    expect(screen.getByText(/Routine reminders are paused meanwhile/)).toBeInTheDocument();
  });

  it("keeps a customer's payment claim unpaid until bank evidence is checked", async () => {
    const base = detail().derived;
    stub({ [DETAIL]: { status: 200, body: detail({ derived: { ...base, payment_status: "AWAITING_VERIFICATION" } }) } });
    open(`invoices/${INV}/overview`);
    expect(await screen.findByText("The customer says this has been paid.")).toBeInTheDocument();
    expect(screen.getByText(/stays unpaid until someone checks the bank evidence/)).toBeInTheDocument();
    expect(screen.queryByText(/reminders are paused/i)).not.toBeInTheDocument();
  });

  it("shows no hold notice for an ordinary outstanding invoice", async () => {
    stub({ [DETAIL]: { status: 200, body: detail() } });
    open(`invoices/${INV}/overview`);
    await screen.findByRole("heading", { name: "Invoice INV-2041" });
    expect(screen.queryByText(/reminders are paused/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/dispute is open/i)).not.toBeInTheDocument();
  });

  it("shows the recommended action, who performs it and why", async () => {
    stub({ [DETAIL]: { status: 200, body: detail() } });
    open(`invoices/${INV}/overview`);
    const next = await screen.findByRole("region", { name: "What to do next" });
    expect(within(next).getByText("Check whether this was paid")).toBeInTheDocument();
    expect(within(next).getByText("No payment evidence yet")).toBeInTheDocument();
  });

  it("shows only the tabs that exist, and never a Mark as paid control", async () => {
    stub({ [DETAIL]: { status: 200, body: detail() } });
    open(`invoices/${INV}/overview`);
    await screen.findByRole("heading", { name: "Invoice INV-2041" });
    const tabs = screen.getByRole("navigation", { name: "Invoice sections" });
    expect(within(tabs).getAllByRole("link").map((link) => link.textContent)).toEqual(["Overview", "Payment history", "Conversation", "Follow-up", "AI brief"]);
    for (const hidden of [/payment evidence/i, /timeline/i, /reconciliation/i, /tasks/i]) {
      expect(within(tabs).queryByText(hidden)).not.toBeInTheDocument();
    }
    expect(screen.queryByText(/mark (as )?paid/i)).not.toBeInTheDocument();
  });

  it("answers not-found for a section that has not been built", async () => {
    stub({ [DETAIL]: { status: 200, body: detail() } });
    open(`invoices/${INV}/evidence`);
    expect(await screen.findByRole("heading", { name: /can't find that page/i })).toBeInTheDocument();
  });

  it("explains a refused action instead of hiding it", async () => {
    const viewer = detail({
      allowed_actions: [action("CORRECT", false, "Only an owner or finance admin can change an invoice."), action("CANCEL", false, "Only an owner or finance admin can change an invoice."), action("ARCHIVE", false, "Only an owner or finance admin can change an invoice.")],
    });
    stub({ [DETAIL]: { status: 200, body: viewer } });
    open(`invoices/${INV}/overview`);
    await screen.findByRole("heading", { name: "Invoice INV-2041" });
    expect(screen.getAllByText("Only an owner or finance admin can change an invoice.")).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Cancel invoice" })).toHaveAttribute("aria-disabled", "true");
  });

  it("cancels with a reason, sending the version and an idempotency key", async () => {
    const cancelled = detail({ version: 4, facts: { ...detail().facts, status: "CANCELLED" }, allowed_actions: [action("CORRECT", false, "A cancelled invoice cannot be changed."), action("CANCEL", false, "Already cancelled."), action("ARCHIVE")] });
    stub({
      [DETAIL]: [{ status: 200, body: detail() }, { status: 200, body: cancelled }],
      [`POST ${API}/invoices/${INV}/cancel`]: { status: 200, body: cancelled },
    });
    open(`invoices/${INV}/overview`);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel invoice" }));
    const dialog = await screen.findByRole("alertdialog");
    const confirm = within(dialog).getByRole("button", { name: "Cancel this invoice" });
    await userEvent.click(confirm);
    expect(within(dialog).getByText(/before cancelling/i)).toBeInTheDocument();
    expect(called(`POST ${API}/invoices/${INV}/cancel`)).toHaveLength(0);
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Raised twice by mistake");
    await userEvent.click(confirm);
    const sent = called(`POST ${API}/invoices/${INV}/cancel`)[0];
    expect(sent?.body).toEqual({ reason: "Raised twice by mistake" });
    expect(sent?.headers.get("Idempotency-Key")).toBeTruthy();
    expect(await screen.findByText("Cancelled")).toBeInTheDocument();
  });

  it("corrects a field with the version it was read at", async () => {
    const corrected = detail({ version: 4, facts: { ...detail().facts, po_number: "PO-88", corrected_fields: ["po_number"], diverges_from_source: true } });
    stub({
      [DETAIL]: [{ status: 200, body: detail() }, { status: 200, body: corrected }],
      [`PATCH ${API}/invoices/${INV}`]: { status: 200, body: corrected },
    });
    open(`invoices/${INV}/overview`);
    await userEvent.click(await screen.findByRole("button", { name: "Correct details" }));
    const dialog = await screen.findByRole("dialog");
    const po = within(dialog).getByLabelText("PO number");
    await userEvent.clear(po);
    await userEvent.type(po, "PO-88");
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Client sent a new PO");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save correction" }));
    const sent = called(`PATCH ${API}/invoices/${INV}`)[0];
    expect(sent?.headers.get("If-Match")).toBe('"3"');
    expect(sent?.body).toMatchObject({ po_number: "PO-88", reason: "Client sent a new PO" });
    expect(await screen.findByText(/corrected after import/i)).toBeInTheDocument();
  });

  it("shows a problem with the correlation id when the invoice is not found", async () => {
    stub({ [DETAIL]: { status: 404, body: { status: 404, code: "NOT_FOUND", detail: "", correlation_id: "cid-4" } } });
    open(`invoices/${INV}/overview`);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/cid-4/)).toBeInTheDocument();
  });

  it("links to the client profile", async () => {
    stub({ [DETAIL]: { status: 200, body: detail() } });
    open(`invoices/${INV}/overview`);
    expect(await screen.findByRole("link", { name: "Northwind Traders" })).toHaveAttribute("href", `/w/${WS}/clients/${CLIENT}`);
  });

  it("has no accessibility violations once loaded", async () => {
    stub({ [DETAIL]: { status: 200, body: detail() } });
    open(`invoices/${INV}/overview`);
    await screen.findByRole("heading", { name: "Invoice INV-2041" });
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
  });
});

describe("Invoice status words", () => {
  it.each(["ACTIVE", "PENDING_REVIEW", "CANCELLED", "WRITTEN_OFF", "ARCHIVED"])("%s has its own label, not 'Status unavailable'", (value) => {
    expect(statusOf("invoice", value).known).toBe(true);
  });
});

const profile = (over: Record<string, unknown> = {}) => ({
  id: CLIENT,
  display_name: "Northwind Traders",
  normalized_name: "northwind traders",
  sensitivity: "STANDARD",
  tone: "NEUTRAL",
  version: 2,
  contacts: [
    { id: "c1", client_id: CLIENT, email: "accounts@example.test", name: "Accounts", status: "ACTIVE", suppression_reason: null },
    { id: "c2", client_id: CLIENT, email: "old@example.test", name: null, status: "SUPPRESSED", suppression_reason: "Bounced" },
  ],
  aliases: [{ id: "a1", text: "Northwind Ltd", kind: "NAME" }],
  summary: { contacts_total: 2, contacts_active: 1, contacts_suppressed: 1 },
  ...over,
});

describe("Client profile (SCR-14)", () => {
  const CLIENT_GET = `GET ${API}/clients/${CLIENT}`;

  it("shows the contacts, with the reason a contact is suppressed", async () => {
    stub({ [CLIENT_GET]: { status: 200, body: profile() }, [`GET ${API}/invoices`]: { status: 200, body: { items: [row()], next_cursor: null } } });
    open(`clients/${CLIENT}`);
    expect(await screen.findByRole("heading", { name: "Northwind Traders" })).toBeInTheDocument();
    const contacts = screen.getByRole("region", { name: "Contacts" });
    expect(within(contacts).getByText("accounts@example.test")).toBeInTheDocument();
    expect(within(contacts).getByText(/Bounced/)).toBeInTheDocument();
    expect(within(contacts).getByText(/Suppressed/)).toBeInTheDocument();
  });

  it("shows other names this client is known by", async () => {
    stub({ [CLIENT_GET]: { status: 200, body: profile() }, [`GET ${API}/invoices`]: { status: 200, body: { items: [], next_cursor: null } } });
    open(`clients/${CLIENT}`);
    expect(await screen.findByText("Northwind Ltd")).toBeInTheDocument();
  });

  it("lists this client's invoices, fetched by client id", async () => {
    stub({ [CLIENT_GET]: { status: 200, body: profile() }, [`GET ${API}/invoices`]: { status: 200, body: { items: [row()], next_cursor: null } } });
    open(`clients/${CLIENT}`);
    expect(await screen.findByRole("link", { name: "INV-2041" })).toBeInTheDocument();
    expect(new URLSearchParams(called(`GET ${API}/invoices`)[0]?.query).get("client_id")).toBe(CLIENT);
  });

  it("says when the client has no invoices", async () => {
    stub({ [CLIENT_GET]: { status: 200, body: profile({ contacts: [], aliases: [], summary: { contacts_total: 0, contacts_active: 0, contacts_suppressed: 0 } }) }, [`GET ${API}/invoices`]: { status: 200, body: { items: [], next_cursor: null } } });
    open(`clients/${CLIENT}`);
    expect(await screen.findByText("No invoices for this client yet")).toBeInTheDocument();
    expect(screen.getByText("No contacts yet")).toBeInTheDocument();
  });

  it("shows an active client pause with its reason and lets a person resume it", async () => {
    const pause = { id: "77777777-7777-4777-8777-777777777777", scope: "CLIENT", client_id: CLIENT, invoice_id: null, reason: "Waiting on their finance team", status: "ACTIVE", paused_by: "u1", paused_at: "2026-10-01T10:00:00Z", resumed_by: null, resumed_at: null };
    stub({
      [CLIENT_GET]: { status: 200, body: profile() },
      [`GET ${API}/invoices`]: { status: 200, body: { items: [], next_cursor: null } },
      [`GET ${API}/reminder-pauses`]: { status: 200, body: { items: [pause] } },
      [`POST ${API}/reminder-pauses/${pause.id}/resume`]: { status: 200, body: { ...pause, status: "RESUMED" } },
    });
    open(`clients/${CLIENT}`);
    expect(await screen.findByText(/Waiting on their finance team/)).toBeInTheDocument();
    expect(new URLSearchParams(called(`GET ${API}/reminder-pauses`)[0]?.query).get("client_id")).toBe(CLIENT);
    await userEvent.click(screen.getByRole("button", { name: "Resume reminders" }));
    await vi.waitFor(() => expect(called(`POST ${API}/reminder-pauses/${pause.id}/resume`)).toHaveLength(1));
  });

  it("shows the problem when the client cannot be loaded", async () => {
    stub({ [CLIENT_GET]: { status: 404, body: { status: 404, code: "NOT_FOUND", detail: "", correlation_id: "cid-7" } } });
    open(`clients/${CLIENT}`);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
