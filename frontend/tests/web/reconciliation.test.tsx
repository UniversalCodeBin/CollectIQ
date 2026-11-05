import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../src/app/router";

const WS = "11111111-1111-4111-8111-111111111111";
const TXN = "55555555-5555-4555-8555-555555555555";
const INV_A = "33333333-3333-4333-8333-333333333333";
const INV_B = "33333333-3333-4333-8333-333333333334";
const MATCH_A = "66666666-6666-4666-8666-666666666666";
const MATCH_B = "66666666-6666-4666-8666-666666666667";
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

const txn = { id: TXN, amount_minor: 500000, currency: "INR", value_date: "2026-10-12", payer_descriptor: "NORTHWIND TRADERS", reference: "UTR998" };
const proposal = (id: string, invoice: string, number: string, over: Record<string, unknown> = {}) => ({
  id,
  label: "Strong",
  ambiguous: false,
  reasons: [
    { code: "AMOUNT_EXACT", text: "The amount equals the invoice balance." },
    { code: "PAYER_NAME", text: "The payer name resembles the client." },
  ],
  transaction: txn,
  invoice: { id: invoice, invoice_number: number, client_name: "Northwind Traders", outstanding_minor: 500000, due_date: "2026-10-01" },
  ...over,
});
const page = (items: unknown[]) => ({ status: 200, body: { items, next_cursor: null } });
const done = { status: 200, body: { payment: {}, allocations: [], invoice_states: [] } };

function review(proposals: unknown[], extra: Record<string, Reply | Reply[]> = {}) {
  stub({
    [`GET ${API}/reconciliation/proposals`]: page(proposals),
    [`GET ${API}/payments`]: page([]),
    [`GET ${API}/transactions/unmatched`]: page([]),
    ...extra,
  });
  return open("reconciliation/review");
}

describe("Payment Reconciliation", () => {
  it("shows live counts on the three tabs and the reasons for a suggestion", async () => {
    review([proposal(MATCH_A, INV_A, "INV-2041")]);
    expect(await screen.findByText("INV-2041")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Match review 1/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Confirmed Payments 0/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Unmatched 0/ })).toBeInTheDocument();
    expect(screen.getByText("The amount equals the invoice balance.")).toBeInTheDocument();
    expect(screen.getByText("The payer name resembles the client.")).toBeInTheDocument();
    expect(screen.getByText("Strong")).toBeInTheDocument();
  });

  it("confirms a match with one idempotent request for the exact amount", async () => {
    review([proposal(MATCH_A, INV_A, "INV-2041")], { [`POST ${API}/reconciliation/proposals/${MATCH_A}/confirm`]: done });
    await userEvent.click(await screen.findByRole("button", { name: "Confirm Match & Apply Allocation" }));
    await waitFor(() => expect(called(`POST ${API}/reconciliation/proposals/${MATCH_A}/confirm`)).toHaveLength(1));
    const [call] = called(`POST ${API}/reconciliation/proposals/${MATCH_A}/confirm`);
    expect(call?.body).toEqual({ allocations: [{ invoice_id: INV_A, amount_minor: 500000 }] });
    expect(call?.headers.get("Idempotency-Key")).toBeTruthy();
  });

  it("makes ambiguous candidates force a choice before anything can be confirmed", async () => {
    review([
      proposal(MATCH_A, INV_A, "INV-2041", { label: "Possible", ambiguous: true }),
      proposal(MATCH_B, INV_B, "INV-2042", { label: "Possible", ambiguous: true }),
    ], { [`POST ${API}/reconciliation/proposals/${MATCH_B}/confirm`]: done });
    const confirm = await screen.findByRole("button", { name: "Confirm Match & Apply Allocation" });
    expect(confirm).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText(/more than one invoice could match/i)).toBeInTheDocument();
    await userEvent.click(confirm);
    expect(calls.filter((call) => call.key.startsWith("POST"))).toHaveLength(0);
    await userEvent.click(screen.getByRole("radio", { name: /INV-2042/ }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm Match & Apply Allocation" }));
    await waitFor(() => expect(called(`POST ${API}/reconciliation/proposals/${MATCH_B}/confirm`)).toHaveLength(1));
  });

  it("lets a partial allocation be entered and sends that amount", async () => {
    review([proposal(MATCH_A, INV_A, "INV-2041")], { [`POST ${API}/reconciliation/proposals/${MATCH_A}/confirm`]: done });
    await userEvent.click(await screen.findByRole("button", { name: "Split / Partial Allocation..." }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.clear(within(dialog).getByLabelText(/Amount to apply/));
    await userEvent.type(within(dialog).getByLabelText(/Amount to apply/), "2000.00");
    await userEvent.click(within(dialog).getByRole("button", { name: /Apply allocation/ }));
    await waitFor(() => expect(called(`POST ${API}/reconciliation/proposals/${MATCH_A}/confirm`)).toHaveLength(1));
    expect(called(`POST ${API}/reconciliation/proposals/${MATCH_A}/confirm`)[0]?.body).toEqual({
      allocations: [{ invoice_id: INV_A, amount_minor: 200000 }],
    });
  });

  it("keeps a rejection: Not a Match is sent and the suggestion leaves the list", async () => {
    review([proposal(MATCH_A, INV_A, "INV-2041")], {
      [`POST ${API}/reconciliation/proposals/${MATCH_A}/reject`]: { status: 200, body: {} },
    });
    // After the rejection the server no longer returns it.
    await userEvent.click(await screen.findByRole("button", { name: "Not a Match" }));
    await waitFor(() => expect(called(`POST ${API}/reconciliation/proposals/${MATCH_A}/reject`)).toHaveLength(1));
  });

  it("offers Check status after a lost reply and retries with the same key, never a second confirm", async () => {
    const url = `POST ${API}/reconciliation/proposals/${MATCH_A}/confirm`;
    review([proposal(MATCH_A, INV_A, "INV-2041")], { [url]: ["network", done] as Reply[] });
    await userEvent.click(await screen.findByRole("button", { name: "Confirm Match & Apply Allocation" }));
    const check = await screen.findByRole("button", { name: "Check status" });
    expect(screen.getByRole("button", { name: "Confirm Match & Apply Allocation" })).toBeInTheDocument();
    await userEvent.click(check);
    await waitFor(() => expect(called(url)).toHaveLength(2));
    const [first, second] = called(url);
    expect(second?.headers.get("Idempotency-Key")).toBe(first?.headers.get("Idempotency-Key"));
    expect(second?.body).toEqual(first?.body);
  });

  it("shows confirmed payments with their allocations and reverses one with a reason", async () => {
    const ALLOC = "77777777-7777-4777-8777-777777777777";
    const payment = {
      id: TXN, source_type: "STATEMENT", method: null, amount_minor: 500000, currency: "INR", allocated_minor: 500000,
      unallocated_minor: 0, value_date: "2026-10-12", reference: "UTR998", payer_descriptor: "NORTHWIND TRADERS", notes: null,
      status: "ACTIVE", evidence_type: "BANK_STATEMENT", lower_assurance: false, account_label: "HDFC", entered_by: "u1",
      created_at: "2026-10-12T10:00:00Z", void_reason: null, duplicate_of_transaction_id: null, attachment: null,
    };
    const detail = {
      ...payment,
      allocations: [
        { id: ALLOC, invoice_id: INV_A, invoice_number: "INV-2041", amount_minor: 500000, kind: "ALLOCATION", reverses_allocation_id: null,
          match_id: null, overpayment_confirmed: false, evidence_type: "BANK_STATEMENT", confirmed_by: "u1", note: null, created_at: "2026-10-12T10:00:00Z" },
      ],
    };
    stub({
      [`GET ${API}/reconciliation/proposals`]: page([]),
      [`GET ${API}/payments`]: page([payment]),
      [`GET ${API}/payments/${TXN}`]: { status: 200, body: detail },
      [`GET ${API}/transactions/unmatched`]: page([]),
      [`POST ${API}/allocations/${ALLOC}/reverse`]: done,
    });
    open("reconciliation/confirmed");
    await userEvent.click(await screen.findByRole("button", { name: /Details/ }));
    expect(await screen.findByText("INV-2041")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Reverse allocation/ }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /Reverse allocation/ }));
    expect(called(`POST ${API}/allocations/${ALLOC}/reverse`)).toHaveLength(0);
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Applied to the wrong invoice");
    await userEvent.click(within(dialog).getByRole("button", { name: /Reverse allocation/ }));
    await waitFor(() => expect(called(`POST ${API}/allocations/${ALLOC}/reverse`)).toHaveLength(1));
    expect(called(`POST ${API}/allocations/${ALLOC}/reverse`)[0]?.body).toEqual({ reason: "Applied to the wrong invoice" });
  });

  it("records a manual payment, then attaches the proof as a second request", async () => {
    const payment = { id: TXN };
    stub({
      [`GET ${API}/reconciliation/proposals`]: page([]),
      [`GET ${API}/payments`]: page([]),
      [`GET ${API}/transactions/unmatched`]: page([]),
      [`POST ${API}/payments`]: { status: 201, body: { payment, allocations: [], invoice_states: [] } },
      [`POST ${API}/payments/${TXN}/attachment`]: { status: 201, body: { file_name: "proof.png", size_bytes: 4, content_type: "image/png" } },
    });
    open("reconciliation/unmatched");
    await userEvent.click(await screen.findByRole("button", { name: "Record a payment" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/^Amount/), "1500.50");
    await userEvent.type(within(dialog).getByLabelText(/Date received/), "2026-10-12");
    await userEvent.upload(within(dialog).getByLabelText(/Proof of payment/), new File([new Uint8Array([1, 2, 3, 4])], "proof.png", { type: "image/png" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save payment" }));
    await waitFor(() => expect(called(`POST ${API}/payments/${TXN}/attachment`)).toHaveLength(1));
    expect(called(`POST ${API}/payments`)[0]?.body).toMatchObject({ amount: { amount_minor: 150050, currency: "INR" }, value_date: "2026-10-12" });
  });
});

describe("Payment Accounts", () => {
  const account = {
    id: "88888888-8888-4888-8888-888888888888", kind: "BANK", label: "HDFC Current", currency: "INR", status: "ACTIVE", version: 1,
    covered_through: "2026-10-10", statements_through: "2026-10-10", attested_through: null, coverage_status: "STALE", gaps: [],
  };

  it("lists accounts with coverage and links to their transactions", async () => {
    stub({ [`GET ${API}/payment-accounts`]: page([account]) });
    open("accounts");
    expect(await screen.findByText("HDFC Current")).toBeInTheDocument();
    expect(screen.getByText(/10 Oct 2026/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View Transactions/ })).toHaveAttribute("href", expect.stringContaining("reconciliation/confirmed"));
  });

  it("declares an account", async () => {
    stub({
      [`GET ${API}/payment-accounts`]: page([]),
      [`POST ${API}/payment-accounts`]: { status: 201, body: { ...account, id: "x" } },
    });
    open("accounts");
    await userEvent.click(await screen.findByRole("button", { name: "Declare an account" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Account name/), "HDFC Current");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save account" }));
    await waitFor(() => expect(called(`POST ${API}/payment-accounts`)).toHaveLength(1));
    expect(called(`POST ${API}/payment-accounts`)[0]?.body).toMatchObject({ kind: "BANK", label: "HDFC Current", currency: "INR" });
  });

  it("refuses anything but a CSV statement before it is sent", async () => {
    stub({ [`GET ${API}/payment-accounts`]: page([account]) });
    open("accounts");
    await userEvent.click(await screen.findByRole("button", { name: /Upload statement/ }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.upload(within(dialog).getByLabelText(/Statement file/), new File(["x"], "statement.pdf", { type: "application/pdf" }), { applyAccept: false });
    await userEvent.click(within(dialog).getByRole("button", { name: /Check statement/ }));
    expect(await within(dialog).findByText(/Choose a CSV file/)).toBeInTheDocument();
    expect(calls.filter((call) => call.key.startsWith("POST"))).toHaveLength(0);
  });
});
