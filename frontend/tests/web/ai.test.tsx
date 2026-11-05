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
const SETTINGS = { pdf_extraction_enabled: false, reply_interpretation_enabled: false, kill_switch: false, provider_configured: false };
const EXTRACTION = {
  id: "22222222-2222-4222-8222-222222222222",
  status: "READY",
  fields: { invoice_number: "INV-900", client_name: "Northwind Traders", issue_date: "2026-10-01", due_date: "2026-10-31", currency: "INR", total: "1500.50" },
  ai_fields: {},
  missing: [],
  dropped_fields: ["total"],
  failure_code: null,
  invoice_id: null,
  version: 1,
  ai_derived: true,
  verified: false,
  created_at: "2026-11-05T00:00:00Z",
  updated_at: "2026-11-05T00:00:00Z",
};

beforeEach(() => window.sessionStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AI settings", () => {
  it("says AI is not configured and saves an opt-in", async () => {
    stub({
      [`GET ${API}/ai/settings`]: { status: 200, body: SETTINGS },
      [`PUT ${API}/ai/settings`]: { status: 200, body: { ...SETTINGS, pdf_extraction_enabled: true } },
    });
    open("settings/ai");
    expect(await screen.findByText(/AI is not configured on this server/)).toBeTruthy();
    const box = screen.getByLabelText(/read uploaded invoice PDFs/) as HTMLInputElement;
    expect(box.checked).toBe(false);
    await userEvent.click(box);
    await userEvent.click(screen.getByRole("button", { name: "Save AI settings" }));
    await waitFor(() => expect(called(`PUT ${API}/ai/settings`)).toHaveLength(1));
    expect(called(`PUT ${API}/ai/settings`)[0]?.body).toMatchObject({ pdf_extraction_enabled: true, kill_switch: false });
  });
});

describe("PDF extraction", () => {
  it("shows the reading as unverified, says what was left blank, and confirms only on click", async () => {
    stub({
      [`POST ${API}/invoices/pdf`]: { status: 202, body: EXTRACTION },
      [`POST ${API}/extractions/${EXTRACTION.id}/confirm`]: { status: 201, body: { ...EXTRACTION, status: "CONFIRMED" } },
    });
    open("import/pdf");
    const file = new File(["%PDF-1.4"], "inv.pdf", { type: "application/pdf" });
    await userEvent.upload(await screen.findByLabelText("Choose a PDF file"), file);
    await userEvent.click(screen.getByRole("button", { name: "Read PDF" }));
    expect(await screen.findByText(/unverified until you confirm/)).toBeTruthy();
    expect(screen.getByText(/Left blank because the document does not support them: Total/)).toBeTruthy();
    expect(screen.queryByText(/%|confidence/i)).toBeNull();
    expect(called(`POST ${API}/extractions/${EXTRACTION.id}/confirm`)).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Confirm and create invoice" }));
    expect(await screen.findByText("Invoice created")).toBeTruthy();
  });

  it("shows the refusal when AI is off", async () => {
    stub({ [`POST ${API}/invoices/pdf`]: { status: 409, body: { code: "AI_DISABLED", status: 409, detail: "AI reading of PDFs is turned off for this workspace." } } });
    open("import/pdf");
    await userEvent.upload(await screen.findByLabelText("Choose a PDF file"), new File(["%PDF-1.4"], "inv.pdf", { type: "application/pdf" }));
    await userEvent.click(screen.getByRole("button", { name: "Read PDF" }));
    expect(await screen.findByText(/turned off/)).toBeTruthy();
  });
});
