import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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

beforeEach(() => stub({}));
afterEach(() => vi.unstubAllGlobals());

describe("Integrations", () => {
  it("shows file-based paths truthfully and never a connected provider by default", async () => {
    stub({
      [`GET ${API}/integrations`]: {
        status: 200,
        body: {
          items: [
            { key: "INVOICE_CSV", label: "Invoice CSV import", kind: "FILE_BASED", state: "FILE_BASED", note: "Upload a CSV file.", verified_at: null, last_error: null },
            { key: "GMAIL", label: "Gmail (send only)", kind: "PROVIDER", state: "NEEDS_CONFIGURATION", note: "Not verified.", verified_at: null, last_error: null },
          ],
        },
      },
    });
    open("integrations");
    expect(await screen.findByText("Invoice CSV import")).toBeInTheDocument();
    expect(screen.getByText("File based")).toBeInTheDocument();
    expect(screen.getByText("Needs configuration")).toBeInTheDocument();
    expect(screen.queryByText(/connected and verified/i)).toBeNull();
    expect(screen.queryByText(/zoho|quickbooks/i)).toBeNull();
    await waitFor(() => expect(called(`GET ${API}/integrations`)).toHaveLength(1));
  });
});
