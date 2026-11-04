import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NAV_ITEMS } from "../../src/app/nav";
import { appRoutes } from "../../src/app/router";
import { safeNext } from "../../src/features/auth/routing";

const WS = "11111111-1111-4111-8111-111111111111";
const USER = { id: "u1", email: "a@example.test", email_verified: true };
const SESSION = { user: USER, workspaces: [{ id: WS, name: "Acme Studio", role: "OWNER" }], csrf_token: "t" };
const PROBLEM = (status: number, code: string, detail: string, errors?: object[]) => ({
  status,
  body: { status, code, detail, correlation_id: "cid-1", errors },
});

type Reply = { status: number; body?: unknown } | "network" | "hold";
type Call = { key: string; body: unknown; headers: Headers };

let replies: Record<string, Reply | Reply[]>;
let calls: Call[];
let release: (reply: { status: number; body?: unknown }) => void;

function respond(reply: { status: number; body?: unknown }) {
  const problem = reply.status >= 400;
  return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), {
    status: reply.status,
    headers: { "Content-Type": problem ? "application/problem+json" : "application/json" },
  });
}

function stub(routes: Record<string, Reply | Reply[]>) {
  replies = routes;
  calls = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
    const key = `${(init.method ?? "GET").toUpperCase()} ${String(url).split("?")[0]}`;
    calls.push({
      key,
      body: init.body ? JSON.parse(String(init.body)) : undefined,
      headers: new Headers(init.headers),
    });
    const planned = replies[key];
    const reply = Array.isArray(planned) ? (planned.length > 1 ? planned.shift() : planned[0]) : planned;
    if (reply === undefined) throw new Error(`no stub for ${key}`);
    if (reply === "network") return Promise.reject(new TypeError("offline"));
    if (reply === "hold") return new Promise((resolve) => (release = (held) => resolve(respond(held))));
    return Promise.resolve(respond(reply));
  });
}

function open(path: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  const url = () => `${router.state.location.pathname}${router.state.location.search}`;
  return { router, client, view, url };
}

const SIGNED_OUT = PROBLEM(401, "AUTH_REQUIRED", "Sign in to continue.");

async function signIn(email = "a@example.test", password = "correct horse battery") { // pragma: allowlist secret
  await userEvent.type(screen.getByLabelText("Email"), email);
  await userEvent.type(screen.getByLabelText("Password"), password);
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

beforeEach(() => window.sessionStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("sign in", () => {
  it("goes to the dashboard of the user's workspace", async () => {
    stub({
      "POST /api/v1/auth/login": { status: 200, body: { user: USER, workspaces: SESSION.workspaces } },
      "GET /api/v1/auth/session": { status: 200, body: SESSION },
    });
    const { url } = open("/login");
    await signIn();
    await waitFor(() => expect(url()).toBe(`/w/${WS}/dashboard`));
    expect(calls[0]?.body).toEqual({ email: "a@example.test", password: "correct horse battery" }); // pragma: allowlist secret
  });

  it("goes to workspace setup when the user has no workspace", async () => {
    stub({
      "POST /api/v1/auth/login": { status: 200, body: { user: USER, workspaces: [] } },
      "GET /api/v1/auth/session": { status: 200, body: { ...SESSION, workspaces: [] } },
    });
    const { url } = open("/login");
    await signIn();
    await waitFor(() => expect(url()).toBe("/onboarding/workspace"));
  });

  it("sends an unverified user to the email wait with their address filled in", async () => {
    stub({
      "POST /api/v1/auth/login": {
        status: 200,
        body: { user: { ...USER, email_verified: false }, workspaces: [] },
      },
    });
    const { url } = open("/login");
    await signIn();
    await waitFor(() => expect(url()).toBe("/verify-email"));
    expect(screen.getByLabelText("Email")).toHaveValue("a@example.test");
  });

  it("shows a refusal in plain words with the reference and keeps what was typed", async () => {
    stub({ "POST /api/v1/auth/login": PROBLEM(401, "AUTH_REQUIRED", "Email or password is incorrect.") });
    open("/login");
    await signIn();
    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
    expect(screen.getByRole("alert")).toHaveTextContent("cid-1");
    expect(screen.getByLabelText("Email")).toHaveValue("a@example.test");
  });

  it("returns to a local next address after signing in", async () => {
    stub({
      "POST /api/v1/auth/login": { status: 200, body: { user: USER, workspaces: SESSION.workspaces } },
      "GET /api/v1/auth/session": { status: 200, body: SESSION },
    });
    const { url } = open(`/login?next=${encodeURIComponent(`/invitations/accept?token=abc`)}`);
    await signIn();
    await waitFor(() => expect(url()).toBe("/invitations/accept?token=abc"));
  });

  it("refuses a next address that leaves the app", () => {
    for (const hostile of ["https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)", ""]) {
      expect(safeNext(hostile)).toBeNull();
    }
    expect(safeNext(null)).toBeNull();
    expect(safeNext("/w/abc/dashboard?x=1")).toBe("/w/abc/dashboard?x=1");
  });

  it("refuses a next address that is not rooted at this app", () => {
    expect(safeNext("dashboard")).toBeNull();
  });

  it("does not follow a next address until the email is confirmed", async () => {
    stub({
      "POST /api/v1/auth/login": {
        status: 200,
        body: { user: { ...USER, email_verified: false }, workspaces: [] },
      },
    });
    const { url } = open("/login?next=%2Fw%2Fabc%2Fdashboard");
    await signIn();
    await waitFor(() => expect(url()).toBe("/verify-email"));
  });

  it("forgets the signed-out answer, so the page the person was heading for opens", async () => {
    stub({
      "GET /api/v1/auth/session": [SIGNED_OUT, { status: 200, body: SESSION }],
      "POST /api/v1/auth/login": { status: 200, body: { user: USER, workspaces: SESSION.workspaces } },
    });
    const { url } = open(`/w/${WS}/dashboard`);
    await waitFor(() => expect(url()).toContain("/login?next="));
    await signIn();
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(url()).toBe(`/w/${WS}/dashboard`);
  });

  it("never shows the previous person's session to whoever signs in next", async () => {
    stub({
      "GET /api/v1/auth/session": "hold",
      "POST /api/v1/auth/login": { status: 200, body: { user: USER, workspaces: SESSION.workspaces } },
    });
    const { client, url } = open("/login");
    client.setQueryData(["session"], {
      ...SESSION,
      workspaces: [{ id: WS, name: "Earlier Person Ltd", role: "OWNER" }],
    });
    await signIn();
    await waitFor(() => expect(url()).toBe(`/w/${WS}/dashboard`));
    expect(screen.queryByText("Earlier Person Ltd")).toBeNull();
    act(() => release({ status: 200, body: SESSION }));
    expect(await screen.findByText("Acme Studio")).toBeInTheDocument();
  });

  it("lets a password manager fill and paste the fields", () => {
    stub({});
    open("/login");
    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByLabelText("Password")).not.toHaveAttribute("onpaste");
  });
});

describe("sign up", () => {
  async function createAccount() {
    await userEvent.type(screen.getByLabelText("Email"), "new@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
  }

  it("shows the password rule before anything is typed", () => {
    stub({});
    open("/signup");
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(/at least 12 characters/i);
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "new-password");
  });

  it("sends a key, then waits for the email and offers to send it again", async () => {
    stub({
      "POST /api/v1/auth/register": { status: 201, body: { detail: "Check your email to continue." } },
      "POST /api/v1/auth/verify-email/resend": { status: 204 },
    });
    open("/signup");
    await createAccount();
    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(calls[0]?.headers.get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
    await userEvent.click(screen.getByRole("button", { name: "Send it again" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/sent/i);
    expect(calls[1]?.body).toEqual({ email: "new@example.test" });
  });

  it("puts the server's field message beside the field", async () => {
    stub({
      "POST /api/v1/auth/register": PROBLEM(422, "VALIDATION_FAILED", "Some fields are invalid.", [
        { field: "password", message: "Use between 12 and 128 characters." },
      ]),
    });
    open("/signup");
    await createAccount();
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(/Use between 12 and 128/);
  });

  it("keeps nothing derived from the password in browser storage when the outcome is unknown", async () => {
    stub({ "POST /api/v1/auth/register": "network" });
    open("/signup");
    await createAccount();
    expect(await screen.findByRole("button", { name: "Check status" })).toBeInTheDocument();
    expect(window.sessionStorage.length).toBe(0);
  });

  it("offers Check status, not a second submit, when the outcome is unknown", async () => {
    stub({ "POST /api/v1/auth/register": "network" });
    open("/signup");
    await createAccount();
    expect(await screen.findByRole("button", { name: "Check status" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create account" })).toBeNull();
  });

  it("moves focus to the heading of the new step", async () => {
    stub({ "POST /api/v1/auth/register": { status: 201, body: { detail: "Check your email to continue." } } });
    open("/signup");
    await createAccount();
    expect(await screen.findByRole("heading", { name: "Check your email" })).toHaveFocus();
  });

  it("retries an unknown outcome with the same key", async () => {
    stub({
      "POST /api/v1/auth/register": ["network", { status: 201, body: { detail: "Check your email to continue." } }],
    });
    open("/signup");
    await createAccount();
    await userEvent.click(await screen.findByRole("button", { name: "Check status" }));
    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(calls).toHaveLength(2);
    expect(calls[1]?.headers.get("Idempotency-Key")).toBe(calls[0]?.headers.get("Idempotency-Key"));
  });
});

describe("email confirmation", () => {
  it("spends the token only when the person presses the button", async () => {
    stub({ "POST /api/v1/auth/verify-email": { status: 204 } });
    open("/verify-email?token=tok-1");
    const button = await screen.findByRole("button", { name: "Confirm my email" });
    expect(calls).toHaveLength(0);
    await userEvent.click(button);
    expect(await screen.findByRole("heading", { name: "Email confirmed" })).toBeInTheDocument();
    expect(calls[0]?.body).toEqual({ token: "tok-1" });
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it("offers a new email when the link no longer works", async () => {
    stub({ "POST /api/v1/auth/verify-email": PROBLEM(422, "VALIDATION_FAILED", "This link has expired.") });
    open("/verify-email?token=old");
    await userEvent.click(await screen.findByRole("button", { name: "Confirm my email" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This link has expired.");
    expect(screen.getByRole("button", { name: "Send it again" })).toBeInTheDocument();
  });

  it("waits without a token and asks for the address when it is not known", () => {
    stub({});
    open("/verify-email");
    expect(screen.getByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveValue("");
  });
});

describe("password reset", () => {
  it("says the same thing whether or not the address has an account", async () => {
    stub({ "POST /api/v1/auth/password-reset/request": { status: 204 } });
    open("/forgot-password");
    await userEvent.type(screen.getByLabelText("Email"), "a@example.test");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/if an account exists/i);
  });

  it("sets the new password from the emailed link and sends the person to sign in", async () => {
    stub({ "POST /api/v1/auth/password-reset/confirm": { status: 204 } });
    open("/reset-password?token=r-1");
    await userEvent.type(screen.getByLabelText("New password"), "a new long password");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByRole("heading", { name: "Password changed" })).toBeInTheDocument();
    expect(calls[0]?.body).toEqual({ token: "r-1", new_password: "a new long password" }); // pragma: allowlist secret
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it("a reset page with no token says the link is incomplete and sends nothing", () => {
    stub({});
    open("/reset-password");
    expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute("href", "/forgot-password");
    expect(screen.queryByLabelText("New password")).toBeNull();
  });

  it("the sign-in page links to it", () => {
    stub({});
    open("/login");
    expect(screen.getByRole("link", { name: "Forgot your password?" })).toHaveAttribute("href", "/forgot-password");
  });
});

describe("invitation", () => {
  it("joins the workspace and opens it", async () => {
    stub({
      "POST /api/v1/invitations/accept": { status: 200, body: { workspace_id: WS, role: "FINANCE_ADMIN" } },
      "GET /api/v1/auth/session": { status: 200, body: SESSION },
    });
    const { url } = open("/invitations/accept?token=i-1");
    await userEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
    await waitFor(() => expect(url()).toBe(`/w/${WS}/dashboard`));
    expect(calls[0]?.body).toEqual({ token: "i-1" });
  });

  it("never shows not-found while the new membership loads", async () => {
    stub({
      "POST /api/v1/invitations/accept": { status: 200, body: { workspace_id: WS, role: "FINANCE_ADMIN" } },
      "GET /api/v1/auth/session": "hold",
    });
    const { client, url } = open("/invitations/accept?token=i-1");
    client.setQueryData(["session"], { ...SESSION, workspaces: [] });
    await userEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
    await waitFor(() => expect(url()).toBe(`/w/${WS}/dashboard`));
    expect(screen.queryByRole("heading", { name: "We can't find that page" })).toBeNull();
    act(() => release({ status: 200, body: SESSION }));
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("when signed out, sends the person to sign in and back to the same invitation", async () => {
    stub({ "POST /api/v1/invitations/accept": SIGNED_OUT });
    const { url } = open("/invitations/accept?token=i-1");
    await userEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
    await waitFor(() => expect(url()).toBe(`/login?next=${encodeURIComponent("/invitations/accept?token=i-1")}`));
  });
});

describe("workspace setup", () => {
  const verifiedNoWorkspace = { status: 200, body: { ...SESSION, workspaces: [] } };

  it("prefills the browser's timezone and creates the workspace with a key", async () => {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    stub({
      "GET /api/v1/auth/session": [verifiedNoWorkspace, { status: 200, body: SESSION }],
      "POST /api/v1/workspaces": {
        status: 201,
        body: { id: WS, name: "Acme Studio", country: "IN", timezone: zone, default_currency: "INR", version: 1 },
      },
    });
    const { url } = open("/onboarding/workspace");
    await userEvent.type(await screen.findByLabelText("Business name"), "Acme Studio");
    expect(screen.getByLabelText("Timezone")).toHaveValue(zone);
    await userEvent.click(screen.getByRole("button", { name: "Create workspace" }));
    await waitFor(() => expect(url()).toBe(`/w/${WS}/dashboard`));
    const post = calls.find((call) => call.key === "POST /api/v1/workspaces");
    expect(post?.headers.get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
    expect(post?.body).toEqual({ name: "Acme Studio", country: "IN", timezone: zone, default_currency: "INR" });
  });

  it("never shows not-found while the new workspace joins the session", async () => {
    stub({
      "GET /api/v1/auth/session": [{ status: 200, body: { ...SESSION, workspaces: [] } }, "hold"],
      "POST /api/v1/workspaces": { status: 201, body: { id: WS } },
    });
    const { url } = open("/onboarding/workspace");
    await userEvent.type(await screen.findByLabelText("Business name"), "Acme Studio");
    await userEvent.click(screen.getByRole("button", { name: "Create workspace" }));
    await waitFor(() => expect(calls.filter((call) => call.key === "GET /api/v1/auth/session")).toHaveLength(2));
    expect(screen.queryByRole("heading", { name: "We can't find that page" })).toBeNull();
    act(() => release({ status: 200, body: SESSION }));
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(url()).toBe(`/w/${WS}/dashboard`);
  });

  it("shows a save failure beside the field and keeps what was typed", async () => {
    stub({
      "GET /api/v1/auth/session": verifiedNoWorkspace,
      "POST /api/v1/workspaces": PROBLEM(422, "VALIDATION_FAILED", "Some fields are invalid.", [
        { field: "name", message: "Enter a name." },
      ]),
    });
    open("/onboarding/workspace");
    await userEvent.type(await screen.findByLabelText("Business name"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Create workspace" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Business name")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Business name")).toHaveValue("x");
  });

  it("offers Check status, not a second create, when the outcome is unknown", async () => {
    stub({ "GET /api/v1/auth/session": verifiedNoWorkspace, "POST /api/v1/workspaces": "network" });
    open("/onboarding/workspace");
    await userEvent.type(await screen.findByLabelText("Business name"), "Acme");
    await userEvent.click(screen.getByRole("button", { name: "Create workspace" }));
    expect(await screen.findByRole("button", { name: "Check status" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create workspace" })).toBeNull();
  });

  it("sends a signed-out visitor to sign in", async () => {
    stub({ "GET /api/v1/auth/session": SIGNED_OUT });
    const { url } = open("/onboarding/workspace");
    await waitFor(() => expect(url()).toMatch(/^\/login\?next=/));
  });

  it("sends an unverified user to confirm their email first", async () => {
    stub({
      "GET /api/v1/auth/session": {
        status: 200,
        body: { ...SESSION, user: { ...USER, email_verified: false }, workspaces: [] },
      },
    });
    const { url } = open("/onboarding/workspace");
    await waitFor(() => expect(url()).toBe("/verify-email"));
  });

  it("an unknown step is not found", async () => {
    stub({ "GET /api/v1/auth/session": verifiedNoWorkspace });
    open("/onboarding/nonsense");
    expect(await screen.findByRole("heading", { name: /not found|can't find/i })).toBeInTheDocument();
  });
});

describe("the app root", () => {
  it("sends a signed-out visitor to sign in", async () => {
    stub({ "GET /api/v1/auth/session": SIGNED_OUT });
    const { url } = open("/");
    await waitFor(() => expect(url()).toBe("/login"));
  });

  it("opens the first workspace of a signed-in user", async () => {
    stub({ "GET /api/v1/auth/session": { status: 200, body: SESSION } });
    const { url } = open("/");
    await waitFor(() => expect(url()).toBe(`/w/${WS}/dashboard`));
  });

  it("sends a signed-in user with no workspace to setup", async () => {
    stub({ "GET /api/v1/auth/session": { status: 200, body: { ...SESSION, workspaces: [] } } });
    const { url } = open("/");
    await waitFor(() => expect(url()).toBe("/onboarding/workspace"));
  });
});

describe("the workspace shell", () => {
  it("a logged-out visitor is sent to sign in, remembering where they were going", async () => {
    stub({ "GET /api/v1/auth/session": SIGNED_OUT });
    const { url } = open(`/w/${WS}/dashboard`);
    await waitFor(() => expect(url()).toBe(`/login?next=${encodeURIComponent(`/w/${WS}/dashboard`)}`));
  });

  it("the dashboard is reachable from the nav", async () => {
    stub({ "GET /api/v1/auth/session": { status: 200, body: SESSION } });
    open(`/w/${WS}/dashboard`);
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(NAV_ITEMS.map((item) => item.label)).toContain("Dashboard");
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("href", `/w/${WS}/dashboard`);
  });

  it("signing out forgets the session, so the next person never sees the last one's workspaces", async () => {
    stub({ "GET /api/v1/auth/session": { status: 200, body: SESSION }, "POST /api/v1/auth/logout": { status: 204 } });
    const { client, url } = open(`/w/${WS}/dashboard`);
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(url()).toBe("/login"));
    expect(client.getQueryData(["session"])).toBeUndefined();
  });
});

describe("accessibility", () => {
  const pages: [string, string, Record<string, Reply>][] = [
    ["/login", "Sign in", {}],
    ["/signup", "Create your account", {}],
    ["/verify-email", "Check your email", {}],
    ["/verify-email?token=t", "Confirm your email", {}],
    ["/forgot-password", "Reset your password", {}],
    ["/reset-password?token=t", "Choose a new password", {}],
    ["/invitations/accept?token=t", "Join this workspace", {}],
    ["/onboarding/workspace", "Set up your workspace", { "GET /api/v1/auth/session": { status: 200, body: SESSION } }],
    [`/w/${WS}/dashboard`, "Dashboard", { "GET /api/v1/auth/session": { status: 200, body: SESSION } }],
  ];
  for (const [path, heading, routes] of pages) {
    it(`${path} has no axe violations`, async () => {
      stub(routes);
      const { view } = open(path);
      await screen.findByRole("heading", { name: heading, level: 1 });
      let result: axe.AxeResults | undefined;
      await act(async () => {
        result = await axe.run(view.container, { rules: { region: { enabled: false } } });
      });
      expect(result?.violations.map((violation) => violation.id)).toEqual([]);
    });
  }
});
