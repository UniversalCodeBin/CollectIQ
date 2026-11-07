import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
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
  const replies: Record<string, Reply | Reply[]> = {
    "GET /api/v1/auth/session": { status: 200, body: SESSION },
    ...routes,
  };
  calls = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
    const [path = "", query = ""] = String(url).split("?");
    const key = `${(init.method ?? "GET").toUpperCase()} ${path}`;
    calls.push({
      key,
      body:
        init.body && typeof init.body === "string"
          ? JSON.parse(init.body)
          : init.body,
      headers: new Headers(init.headers),
      query,
    });
    const planned = replies[key];
    const reply = Array.isArray(planned)
      ? planned.length > 1
        ? planned.shift()
        : planned[0]
      : planned;
    if (reply === undefined) throw new Error(`no stub for ${key}`);
    if (reply === "network") return Promise.reject(new TypeError("offline"));
    return Promise.resolve(
      new Response(
        reply.body === undefined ? null : JSON.stringify(reply.body),
        {
          status: reply.status,
          headers: {
            "Content-Type":
              reply.status >= 400
                ? "application/problem+json"
                : "application/json",
          },
        },
      ),
    );
  });
}

function open(path: string) {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: [`/w/${WS}/${path}`],
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
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

describe("Settings", () => {
  it("lists members and changes a role", async () => {
    stub({
      [`GET ${API}/members`]: {
        status: 200,
        body: {
          items: [
            {
              id: "m1",
              email: "a@example.test",
              role: "OWNER",
              status: "ACTIVE",
            },
          ],
          next_cursor: null,
        },
      },
      [`PATCH ${API}/members/m1`]: {
        status: 200,
        body: {
          id: "m1",
          email: "a@example.test",
          role: "FINANCE_ADMIN",
          status: "ACTIVE",
        },
      },
    });
    open("settings/members");
    const select = await screen.findByLabelText("Role for a@example.test");
    fireEvent.change(select, { target: { value: "FINANCE_ADMIN" } });
    await screen.findByText(/audit history/i);
    expect(called(`PATCH ${API}/members/m1`)[0]?.body).toEqual({
      role: "FINANCE_ADMIN",
    });
  });

  it("deletion needs the typed confirmation", async () => {
    stub({
      [`POST ${API}/deletion`]: {
        status: 201,
        body: { id: "d1", rows_remaining: 0, note: "Audit history kept." },
      },
    });
    open("settings/privacy");
    const button = await screen.findByRole("button", {
      name: "Delete workspace",
    });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/to confirm/i), {
      target: { value: "DELETE MY WORKSPACE" },
    });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await screen.findByText(/0 rows remain/);
    expect(called(`POST ${API}/deletion`)[0]?.body).toEqual({
      confirmation_text: "DELETE MY WORKSPACE",
    });
  });

  it("requests an export", async () => {
    stub({
      [`POST ${API}/exports`]: {
        status: 201,
        body: { id: "e1", status: "PENDING" },
      },
    });
    open("settings/privacy");
    fireEvent.click(
      await screen.findByRole("button", { name: "Request export" }),
    );
    await screen.findByText(/Export e1 requested/);
  });

  it("shows payloads as sent, with tokens", async () => {
    stub({
      [`GET ${API}/ai/payloads`]: {
        status: 200,
        body: {
          note: "Shown as sent.",
          items: [
            {
              id: "p1",
              task_id: "REPLY_INTERPRETATION",
              status: "OK",
              created_at: "2026-01-01",
              provider: "fake",
              input_sha256: "abc",
              dropped_fields: ["phone"],
              payload: { text: "Hi [PERSON_1]" },
            },
          ],
        },
      },
    });
    open("settings/payloads");
    expect(await screen.findByText(/\[PERSON_1\]/)).toBeInTheDocument();
    expect(screen.getByText(/Fields not sent: phone/)).toBeInTheDocument();
  });

  it("saves a notification choice", async () => {
    stub({
      [`GET ${API}/notification-preferences`]: {
        status: 200,
        body: { in_app: { CASE_OPENED: true, REMINDER_DRAFT_READY: true } },
      },
      [`PUT ${API}/notification-preferences`]: {
        status: 200,
        body: { in_app: { CASE_OPENED: false, REMINDER_DRAFT_READY: true } },
      },
    });
    open("settings/notifications");
    fireEvent.click(await screen.findByLabelText(/a case is opened/i));
    await vi.waitFor(() =>
      expect(called(`PUT ${API}/notification-preferences`)[0]?.body).toEqual({
        in_app: { CASE_OPENED: false },
      }),
    );
  });

  it("saves the legal and sender name with the workspace version", async () => {
    stub({
      [`GET ${API}`]: { status: 200, body: { id: WS, name: "Acme Studio", legal_name: null, sender_name: null, version: 3 } },
      [`PATCH ${API}`]: { status: 200, body: { id: WS, name: "Acme Studio", legal_name: "Acme Ltd", sender_name: "Priya", version: 4 } },
    });
    open("settings/business");
    fireEvent.change(await screen.findByLabelText("Legal name"), { target: { value: "Acme Ltd" } });
    fireEvent.change(screen.getByLabelText("Sender name"), { target: { value: "Priya" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(called(`PATCH ${API}`)).toHaveLength(1));
    const sent = called(`PATCH ${API}`)[0];
    expect(sent?.body).toEqual({ legal_name: "Acme Ltd", sender_name: "Priya" });
    expect(sent?.headers.get("If-Match")).toBe('"3"');
  });
});
