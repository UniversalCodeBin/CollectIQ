import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../src/app/router";

const WS = "11111111-1111-4111-8111-111111111111";
const INV = "33333333-3333-4333-8333-333333333333";
const REM = "99999999-9999-4999-8999-999999999999";
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

const reminder = (over: Record<string, unknown> = {}) => ({
  id: REM,
  invoice_id: INV,
  invoice_number: "INV-2035",
  contact_id: "c1",
  recipient: "accounts@kestrel.example.test",
  sequence: 1,
  intended_date: "2026-01-20",
  status: "DRAFT",
  subject: "Payment reminder — Invoice INV-2035",
  body: "Hello,\n\nA gentle reminder that INV-2035 is open.",
  fact_block: { outstanding_minor: 120000, currency: "INR" },
  approved_by: null,
  approved_at: null,
  sent_at: null,
  method: null,
  marked_by: null,
  reason: null,
  version: 1,
  created_at: "2026-01-20T09:00:00Z",
  ...over,
});
const clear = { outcome: "REQUIRE_APPROVAL", reasons: [], gate_results: [] };
const detail = (over: Record<string, unknown> = {}, gates: unknown = clear) => ({ status: 200, body: { ...reminder(over), gates }, headers: { ETag: `"${(over.version as number) ?? 1}"` } });

beforeEach(() => window.sessionStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Follow-ups (SCR-09)", () => {
  it("groups reminders by what a person must do next and links each to its page", async () => {
    stub({
      [`GET ${API}/reminders`]: {
        status: 200,
        body: {
          items: [
            reminder(),
            reminder({ id: "a2", status: "APPROVED", invoice_number: "INV-1" }),
            reminder({ id: "a3", status: "MARKED_SENT", invoice_number: "INV-2", sent_at: "2026-01-21T10:00:00Z" }),
            reminder({ id: "a4", status: "CANCELLED", invoice_number: "INV-3", reason: "A payment arrived." }),
          ],
          next_cursor: null,
        },
      },
    });
    open("followups");
    expect(await screen.findByRole("heading", { name: "Follow-ups" })).toBeInTheDocument();
    const tabs = screen.getByRole("navigation", { name: "Follow-up groups" });
    expect(await within(tabs).findByRole("link", { name: /Drafts awaiting approval 1/ })).toBeInTheDocument();
    expect(within(tabs).getByRole("link", { name: /Ready to send 1/ })).toBeInTheDocument();
    expect(within(tabs).getByRole("link", { name: /Sent history 1/ })).toBeInTheDocument();
    expect(within(tabs).getByRole("link", { name: /Closed 1/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /INV-2035/ })).toHaveAttribute("href", `/w/${WS}/reminders/${REM}`);
    expect(screen.queryByText(/formal notice|send template|extend hold/i)).not.toBeInTheDocument();
  });

  it("offers an empty state instead of a blank list", async () => {
    stub({ [`GET ${API}/reminders`]: { status: 200, body: { items: [], next_cursor: null } } });
    open("followups");
    expect(await screen.findByText("No follow-ups here")).toBeInTheDocument();
  });
});

describe("A draft (SCR-09 review)", () => {
  it("edits the wording with the version it was opened at", async () => {
    stub({
      [`GET ${API}/reminders/${REM}`]: detail(),
      [`PATCH ${API}/reminders/${REM}`]: { status: 200, body: reminder({ version: 2, body: "Shorter." }), headers: { ETag: '"2"' } },
    });
    open(`reminders/${REM}`);
    const box = await screen.findByLabelText("Message text");
    await userEvent.clear(box);
    await userEvent.type(box, "Shorter.");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await vi.waitFor(() => expect(called(`PATCH ${API}/reminders/${REM}`)).toHaveLength(1));
    const patch = called(`PATCH ${API}/reminders/${REM}`)[0]!;
    expect(patch.body).toEqual({ body: "Shorter." });
    expect(patch.headers.get("If-Match")).toBe('"1"');
  });

  it("approving says Ready to send and never says sent", async () => {
    stub({
      [`GET ${API}/reminders/${REM}`]: [detail(), detail({ status: "APPROVED", version: 2, approved_by: "u1", approved_at: "2026-01-20T10:00:00Z" })],
      [`POST ${API}/reminders/${REM}/approve`]: { status: 200, body: reminder({ status: "APPROVED", version: 2 }) },
    });
    open(`reminders/${REM}`);
    await userEvent.click(await screen.findByRole("button", { name: "Approve and mark ready to send" }));
    expect(await screen.findByText("Ready to send")).toBeInTheDocument();
    expect(screen.getByText(/CollectIQ has not sent this/i)).toBeInTheDocument();
    expect(called(`POST ${API}/reminders/${REM}/approve`)[0]!.headers.get("Idempotency-Key")).toBeTruthy();
    expect(screen.queryByText(/^sent$/i)).not.toBeInTheDocument();
  });

  it("copies the text and then records 'I sent it' as marked sent by the person", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    stub({
      [`GET ${API}/reminders/${REM}`]: [
        detail({ status: "APPROVED", version: 2 }),
        detail({ status: "MARKED_SENT", version: 3, sent_at: "2026-01-21T10:00:00Z", method: "EMAIL", marked_by: "u1" }),
      ],
      [`POST ${API}/reminders/${REM}/mark-sent`]: { status: 201, body: reminder({ status: "MARKED_SENT", version: 3 }) },
    });
    open(`reminders/${REM}`);
    await userEvent.click(await screen.findByRole("button", { name: "Copy message text" }));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("A gentle reminder"));
    await userEvent.click(screen.getByRole("button", { name: "I sent it" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.selectOptions(within(dialog).getByLabelText("How you sent it"), "EMAIL");
    await userEvent.click(within(dialog).getByRole("button", { name: "Record that I sent it" }));
    await vi.waitFor(() => expect(called(`POST ${API}/reminders/${REM}/mark-sent`)).toHaveLength(1));
    const sent = called(`POST ${API}/reminders/${REM}/mark-sent`)[0]!;
    expect((sent.body as { method: string }).method).toBe("EMAIL");
    expect(typeof (sent.body as { sent_at: string }).sent_at).toBe("string");
    expect(sent.headers.get("Idempotency-Key")).toBeTruthy();
    expect(await screen.findByText(/Marked sent by you/)).toBeInTheDocument();
  });

  it("a blocked draft explains why in plain words, with no gate code, and cannot be approved", async () => {
    stub({
      [`GET ${API}/reminders/${REM}`]: detail(
        {},
        {
          outcome: "PAUSE_FOR_REVIEW",
          reasons: ["G4_DISPUTE"],
          gate_results: [
            { gate: "G4", passed: false, reason: "G4_DISPUTE" },
            { gate: "G1", passed: true, reason: null },
          ],
        },
      ),
    });
    open(`reminders/${REM}`);
    expect(await screen.findByText(/dispute on this invoice that is not settled/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bG\d{1,2}\b|G4_DISPUTE/);
    expect(screen.getByRole("button", { name: "Approve and mark ready to send" })).toHaveAttribute("aria-disabled", "true");
  });

  it("rejecting keeps the draft for the record and asks for no gate or template", async () => {
    stub({
      [`GET ${API}/reminders/${REM}`]: [detail(), detail({ status: "REJECTED", version: 2, reason: "Wrong tone" })],
      [`POST ${API}/reminders/${REM}/reject`]: { status: 200, body: reminder({ status: "REJECTED", version: 2 }) },
    });
    open(`reminders/${REM}`);
    await userEvent.click(await screen.findByRole("button", { name: "Reject draft" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Reason (optional)"), "Wrong tone");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reject draft" }));
    await vi.waitFor(() => expect(called(`POST ${API}/reminders/${REM}/reject`)).toHaveLength(1));
    expect(called(`POST ${API}/reminders/${REM}/reject`)[0]!.body).toEqual({ reason: "Wrong tone" });
  });
});

describe("Preparing a reminder from an invoice", () => {
  const invoice = {
    facts: { id: INV, invoice_number: "INV-2035", client_id: "c1", client_name: "Kestrel Digital", status: "ISSUED", currency: "INR", gross_minor: 120000, subtotal_minor: null, tax_minor: null, issue_date: null, due_date: "2026-01-01", payment_terms: null, po_number: null, project_ref: null, description: null },
    derived: {},
    allowed_actions: [],
    recommended_action: null,
  };
  const evaluate = `POST ${API}/invoices/${INV}/reminders/evaluate`;
  const pauses = `GET ${API}/reminder-pauses`;
  const none = { status: 200, body: { items: [] } };

  it("creates a draft only when a person asks, then links to review it", async () => {
    stub({
      [`GET ${API}/invoices/${INV}`]: { status: 200, body: invoice },
      [pauses]: none,
      [evaluate]: { status: 200, body: { ...clear, invoice_id: INV, reminder: reminder() } },
    });
    open(`invoices/${INV}/followups`);
    expect(called(evaluate)).toHaveLength(0);
    await userEvent.click(await screen.findByRole("button", { name: "Prepare a reminder" }));
    const link = await screen.findByRole("link", { name: "Review the draft" });
    expect(link).toHaveAttribute("href", `/w/${WS}/reminders/${REM}`);
    expect(called(evaluate)[0]!.headers.get("Idempotency-Key")).toBeTruthy();
  });

  it("says in plain words why no draft was made", async () => {
    stub({
      [`GET ${API}/invoices/${INV}`]: { status: 200, body: invoice },
      [pauses]: none,
      [evaluate]: {
        status: 200,
        body: { outcome: "PAUSE_FOR_REVIEW", reasons: ["G4_DISPUTE"], gate_results: [{ gate: "G4", passed: false, reason: "G4_DISPUTE" }], invoice_id: INV, reminder: null },
      },
    });
    open(`invoices/${INV}/followups`);
    await userEvent.click(await screen.findByRole("button", { name: "Prepare a reminder" }));
    expect(await screen.findByText(/dispute on this invoice that is not settled/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review the draft" })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bG\d{1,2}\b|G4_DISPUTE/);
  });
  const PAUSE = "55555555-5555-4555-8555-555555555555";
  const row = { id: PAUSE, scope: "INVOICE", client_id: null, invoice_id: INV, reason: "Dispute under review", status: "ACTIVE", paused_by: "u1", paused_at: "2026-10-01T10:00:00Z", resumed_by: null, resumed_at: null };

  it("pauses reminders for the invoice with a reason, then shows the pause", async () => {
    stub({
      [`GET ${API}/invoices/${INV}`]: { status: 200, body: invoice },
      [pauses]: [none, { status: 200, body: { items: [row] } }],
      [`POST ${API}/reminder-pauses`]: { status: 201, body: row },
    });
    open(`invoices/${INV}/followups`);
    await userEvent.type(await screen.findByLabelText("Reason (optional)"), "Dispute under review");
    await userEvent.click(screen.getByRole("button", { name: "Pause reminders" }));
    expect(await screen.findByText(/Reminders are paused for this invoice/)).toBeInTheDocument();
    expect(called(`POST ${API}/reminder-pauses`)[0]!.body).toEqual({ scope: "INVOICE", target_id: INV, reason: "Dispute under review" });
    expect(called(`POST ${API}/reminder-pauses`)[0]!.headers.get("Idempotency-Key")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Resume reminders" })).toBeInTheDocument();
  });

  it("resumes an active pause and keeps ended ones as history", async () => {
    const ended = { ...row, id: "66666666-6666-4666-8666-666666666666", status: "RESUMED", resumed_at: "2026-10-02T10:00:00Z", reason: "Old hold" };
    stub({
      [`GET ${API}/invoices/${INV}`]: { status: 200, body: invoice },
      [pauses]: [{ status: 200, body: { items: [row, ended] } }, { status: 200, body: { items: [{ ...row, status: "RESUMED", resumed_at: "2026-10-03T10:00:00Z" }, ended] } }],
      [`POST ${API}/reminder-pauses/${PAUSE}/resume`]: { status: 200, body: { ...row, status: "RESUMED" } },
    });
    open(`invoices/${INV}/followups`);
    expect(await screen.findByText(/Old hold/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Resume reminders" }));
    expect(await screen.findByRole("button", { name: "Pause reminders" })).toBeInTheDocument();
    expect(called(`POST ${API}/reminder-pauses/${PAUSE}/resume`)).toHaveLength(1);
  });
  describe("sending with Gmail", () => {
    const gmail = (state: string) => ({
      status: 200,
      body: { items: [{ key: "GMAIL", label: "Gmail", kind: "PROVIDER", state, note: "", verified_at: null, last_error: null }] },
    });

    it("sends only through the Send button, and only when Gmail is connected", async () => {
      stub({
        [`GET ${API}/integrations`]: gmail("CONNECTED_VERIFIED"),
        [`GET ${API}/reminders/${REM}`]: [detail({ status: "APPROVED", version: 2 }), detail({ status: "SUBMITTED", version: 4 })],
        [`POST ${API}/reminders/${REM}/send`]: { status: 202, body: reminder({ status: "SUBMITTED", version: 4 }) },
      });
      open(`reminders/${REM}`);
      await userEvent.click(await screen.findByRole("button", { name: "Send with Gmail" }));
      expect(await screen.findByText("Handed to Gmail. Delivery is not confirmed.")).toBeInTheDocument();
      expect(called(`POST ${API}/reminders/${REM}/send`)[0]!.headers.get("Idempotency-Key")).toBeTruthy();
    });

    it("explains how to enable sending when Gmail is not connected", async () => {
      stub({
        [`GET ${API}/integrations`]: gmail("NEEDS_CONFIGURATION"),
        [`GET ${API}/reminders/${REM}`]: detail({ status: "APPROVED", version: 2 }),
      });
      open(`reminders/${REM}`);
      expect(await screen.findByText(/connect Gmail under Integrations/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Send with Gmail" })).not.toBeInTheDocument();
    });

    it("lets a person settle an unknown send and never offers a retry", async () => {
      stub({
        [`GET ${API}/integrations`]: gmail("CONNECTED_VERIFIED"),
        [`GET ${API}/reminders/${REM}`]: [detail({ status: "SUBMISSION_UNKNOWN", version: 4 }), detail({ status: "SUBMITTED", version: 5 })],
        [`POST ${API}/reminders/${REM}/confirm-unknown`]: { status: 200, body: reminder({ status: "SUBMITTED", version: 5 }) },
      });
      open(`reminders/${REM}`);
      expect(await screen.findByText("We could not tell whether Gmail took it")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Send with Gmail" })).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "It was sent" }));
      await vi.waitFor(() => expect(called(`POST ${API}/reminders/${REM}/confirm-unknown`)).toHaveLength(1));
      expect(called(`POST ${API}/reminders/${REM}/confirm-unknown`)[0]!.body).toEqual({ outcome: "WAS_SENT" });
    });
  });

  it("brings reminders back after a resolved dispute only in three deliberate steps", async () => {
    const APPROVAL = "66666666-6666-4666-8666-666666666666";
    const resolved = { ...invoice, derived: { dispute_status: "RESOLVED" } };
    stub({
      [`GET ${API}/invoices/${INV}`]: { status: 200, body: resolved },
      [pauses]: none,
      [`POST ${API}/invoices/${INV}/followups/resume-request`]: {
        status: 200,
        body: { id: "d1", outcome: "REQUIRE_APPROVAL", reasons: [], gate_results: [], approval_id: APPROVAL, expires_at: "2026-11-08T00:00:00Z" },
      },
      [`POST ${API}/approvals/${APPROVAL}/decide`]: { status: 200, body: {} },
      [`POST ${API}/invoices/${INV}/followups/resume`]: { status: 200, body: { invoice_id: INV, dispute_status: "NONE", reminder_status: "NOT_CONTACTED" } },
    });
    open(`invoices/${INV}/followups`);
    await userEvent.click(await screen.findByRole("button", { name: "Check whether reminders can resume" }));
    expect(called(`POST ${API}/invoices/${INV}/followups/resume`)).toHaveLength(0);
    await userEvent.click(await screen.findByRole("button", { name: "Approve bringing reminders back" }));
    await userEvent.click(await screen.findByRole("button", { name: "Resume after resolution" }));
    expect(await screen.findByText(/Reminders are back on for this invoice/)).toBeInTheDocument();
    expect(called(`POST ${API}/approvals/${APPROVAL}/decide`)[0]!.body).toEqual({ decision: "APPROVED" });
    expect(called(`POST ${API}/invoices/${INV}/followups/resume`)[0]!.body).toEqual({ approval_id: APPROVAL });
  });

  it("offers no resume step unless the dispute is resolved", async () => {
    stub({ [`GET ${API}/invoices/${INV}`]: { status: 200, body: invoice }, [pauses]: none });
    open(`invoices/${INV}/followups`);
    await screen.findByRole("button", { name: "Prepare a reminder" });
    expect(screen.queryByRole("button", { name: "Check whether reminders can resume" })).not.toBeInTheDocument();
  });
});
