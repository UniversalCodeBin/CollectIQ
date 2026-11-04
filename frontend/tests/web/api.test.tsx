import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { MutationFeedback } from "../../src/components/ui/MutationFeedback";
import { ProblemMessage } from "../../src/components/ui/ProblemMessage";
import { apiRequest, ApiProblem, plainProblem, useApiMutation } from "../../src/lib/api";

const WS = "11111111-1111-4111-8111-111111111111";
const INVITE = { method: "post", path: "/api/v1/workspaces/{ws}/invitations" } as const;
const UPDATE = { method: "patch", path: "/api/v1/workspaces/{ws}" } as const;
const BODY = { email: "a@example.test", role: "FINANCE_ADMIN" } as const;

function json(status: number, body: unknown, type = "application/json") {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": type } });
}

function problem(status: number, code: string, detail: string, extra: object = {}) {
  return json(
    status,
    { type: `/problems/${code.toLowerCase()}`, title: code, status, code, detail, correlation_id: "corr-123", ...extra },
    "application/problem+json",
  );
}

function stubFetch(...replies: Array<Response | Error>) {
  const calls: Array<{ url: string; init: RequestInit; headers: Headers }> = [];
  const queue = [...replies];
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    calls.push({ url, init, headers: new Headers(init.headers) });
    const next = queue.shift();
    if (!next) throw new Error("unexpected fetch");
    return next instanceof Error ? Promise.reject(next) : Promise.resolve(next);
  });
  return calls;
}

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function Invite({ body = BODY }: { body?: { email: string; role: "FINANCE_ADMIN" } }) {
  const mutation = useApiMutation(INVITE, { idempotent: true });
  return (
    <div>
      {mutation.status !== "unknown" && (
        <button onClick={() => mutation.submit({ path: { ws: WS }, body })}>Send invitation</button>
      )}
      <button onClick={() => mutation.submit({ path: { ws: WS }, body: { ...body, email: "b@example.test" } })}>
        Send different
      </button>
      <MutationFeedback mutation={mutation} />
      {mutation.status === "success" && <p>Sent</p>}
    </div>
  );
}

describe("useApiMutation", () => {
  it("retains idempotency key across a retry after network failure", async () => {
    const calls = stubFetch(new TypeError("Failed to fetch"), json(201, { id: "x" }));
    render(wrap(<Invite />));
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    await userEvent.click(await screen.findByRole("button", { name: "Check status" }));
    await screen.findByText("Sent");
    const first = calls[0]?.headers.get("Idempotency-Key");
    expect(first).toMatch(/^[0-9a-f-]{36}$/);
    expect(calls[1]?.headers.get("Idempotency-Key")).toBe(first);
    expect(calls[1]?.init.body).toBe(calls[0]?.init.body);
  });

  it("keeps the key when the page reloads before an answer arrives", async () => {
    const calls = stubFetch(new TypeError("Failed to fetch"), json(201, { id: "x" }));
    const first = render(wrap(<Invite />));
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    await screen.findByRole("button", { name: "Check status" });
    first.unmount();
    render(wrap(<Invite />));
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    await screen.findByText("Sent");
    expect(calls[1]?.headers.get("Idempotency-Key")).toBe(calls[0]?.headers.get("Idempotency-Key"));
  });

  it("uses a new key after a definite answer", async () => {
    const calls = stubFetch(json(201, { id: "x" }), json(201, { id: "y" }));
    render(wrap(<Invite />));
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    await screen.findByText("Sent");
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1]?.headers.get("Idempotency-Key")).not.toBe(calls[0]?.headers.get("Idempotency-Key"));
  });

  it("shows Check status when outcome is unknown", async () => {
    stubFetch(new TypeError("Failed to fetch"));
    render(wrap(<Invite />));
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByRole("button", { name: "Check status" })).toBeInTheDocument();
    expect(screen.getByText(/could not confirm/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send invitation" })).not.toBeInTheDocument();
  });

  it("treats a server failure as an unknown outcome", async () => {
    stubFetch(problem(500, "INTERNAL_ERROR", "boom"));
    render(wrap(<Invite />));
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByRole("button", { name: "Check status" })).toBeInTheDocument();
  });

  it("refuses a different submission while the outcome is unknown", async () => {
    const calls = stubFetch(new TypeError("Failed to fetch"));
    render(wrap(<Invite />));
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    await screen.findByRole("button", { name: "Check status" });
    await userEvent.click(screen.getByRole("button", { name: "Send different" }));
    expect(calls).toHaveLength(1);
  });

  it("a session lost while checking keeps the outcome unknown and the same key", async () => {
    const calls = stubFetch(
      new TypeError("Failed to fetch"),
      problem(401, "AUTH_REQUIRED", "Sign in to continue."),
      json(201, { id: "x" }),
    );
    render(wrap(<Invite />));
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    await userEvent.click(await screen.findByRole("button", { name: "Check status" }));
    expect(await screen.findByText("Sign in to continue.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Check status" }));
    await screen.findByText("Sent");
    expect(new Set(calls.map((call) => call.headers.get("Idempotency-Key"))).size).toBe(1);
  });

  it("a second press while the request is in flight sends nothing", async () => {
    let answer: (reply: Response) => void = () => {};
    const fetched = vi.fn(() => new Promise<Response>((resolve) => (answer = resolve)));
    vi.stubGlobal("fetch", fetched);
    render(wrap(<Invite />));
    const button = screen.getByRole("button", { name: "Send invitation" });
    await userEvent.click(button);
    await userEvent.click(button);
    expect(fetched).toHaveBeenCalledTimes(1);
    answer(json(201, { id: "x" }));
    await screen.findByText("Sent");
  });

  it("an action with no safe retry reports the failure and allows another try", async () => {
    stubFetch(new TypeError("Failed to fetch"));
    function Plain() {
      const mutation = useApiMutation({ method: "post", path: "/api/v1/auth/logout" } as const);
      return (
        <div>
          <button onClick={() => mutation.submit({})}>Sign out</button>
          <MutationFeedback mutation={mutation} />
        </div>
      );
    }
    render(wrap(<Plain />));
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/connection/i);
    expect(screen.queryByRole("button", { name: "Check status" })).not.toBeInTheDocument();
  });

  it("refuses an If-Match action that was given no version", () => {
    function Rename() {
      const mutation = useApiMutation(UPDATE, { ifMatch: true });
      return <button onClick={() => mutation.submit({ path: { ws: WS }, body: { name: "New" } })}>Rename</button>;
    }
    const errors: unknown[] = [];
    const listener = (event: ErrorEvent) => {
      errors.push(event.error);
      event.preventDefault();
    };
    window.addEventListener("error", listener);
    render(wrap(<Rename />));
    screen.getByRole("button", { name: "Rename" }).click();
    window.removeEventListener("error", listener);
    expect(String(errors[0])).toMatch(/version/);
  });

  it("a validation failure is a definite answer with no Check status", async () => {
    stubFetch(problem(422, "VALIDATION_FAILED", "Check the highlighted fields."));
    render(wrap(<Invite />));
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByText("Check the highlighted fields.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check status" })).not.toBeInTheDocument();
  });

  it("sends If-Match from the version it is given, and the CSRF cookie", async () => {
    document.cookie = "collectiq_csrf=tok123";
    const calls = stubFetch(json(200, { id: "x" }));
    function Rename() {
      const mutation = useApiMutation(UPDATE, { ifMatch: true });
      return (
        <button onClick={() => mutation.submit({ path: { ws: WS }, body: { name: "New" }, version: 7 })}>
          Rename
        </button>
      );
    }
    render(wrap(<Rename />));
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]?.headers.get("If-Match")).toBe('"7"');
    expect(calls[0]?.headers.get("X-CSRFToken")).toBe("tok123");
    expect(calls[0]?.url).toBe(`/api/v1/workspaces/${WS}`);
    expect(calls[0]?.headers.get("Idempotency-Key")).toBeNull();
    document.cookie = "collectiq_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });
});

describe("apiRequest", () => {
  it("encodes path and query values", async () => {
    const calls = stubFetch(json(200, { items: [], next_cursor: null }));
    await apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/members" }, {
      path: { ws: "a/b" },
      query: { limit: 5, cursor: "x y" },
    });
    expect(calls[0]?.url).toBe("/api/v1/workspaces/a%2Fb/members?limit=5&cursor=x+y");
  });

  it("returns nothing for 204", async () => {
    stubFetch(new Response(null, { status: 204 }));
    await expect(apiRequest({ method: "post", path: "/api/v1/auth/logout" }, {})).resolves.toBeUndefined();
  });

  it("raises a plain problem for a non-JSON error page", async () => {
    stubFetch(new Response("<html>Bad gateway</html>", { status: 400, headers: { "Content-Type": "text/html" } }));
    const failure = await apiRequest({ method: "post", path: "/api/v1/auth/logout" }, {}).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiProblem);
    expect(plainProblem(failure as ApiProblem).message).not.toMatch(/html|gateway/i);
  });
});

describe("ProblemMessage", () => {
  async function failure(reply: Response) {
    stubFetch(reply);
    return (await apiRequest({ method: "post", path: "/api/v1/auth/logout" }, {}).catch((e: unknown) => e)) as ApiProblem;
  }

  it("maps problem+json to plain text and shows correlation ID", async () => {
    const error = await failure(problem(409, "CONFLICT_VERSION", "stale etag 3 vs 4"));
    render(<ProblemMessage problem={error} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/changed .* reload/i);
    expect(screen.getByText(/corr-123/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).not.toHaveTextContent(/CONFLICT_VERSION|etag|problems\//);
  });

  it("never shows internal detail on a server error", async () => {
    const error = await failure(problem(500, "INTERNAL_ERROR", "psycopg.errors.UniqueViolation at line 4"));
    render(<ProblemMessage problem={error} />);
    expect(screen.getByRole("alert")).not.toHaveTextContent(/psycopg/);
  });

  it("replaces a detail carrying a gate ID or a percentage", async () => {
    for (const detail of ["Blocked by gate G5", "Blocked by G12", "Only 94% sure"]) {
      const error = await failure(problem(409, "POLICY_BLOCKED", detail));
      const { unmount } = render(<ProblemMessage problem={error} />);
      expect(screen.getByRole("alert")).not.toHaveTextContent(/G5|G12|94%|gate/i);
      unmount();
    }
  });

  it("lists field errors and keeps a plain detail", async () => {
    const error = await failure(
      problem(422, "VALIDATION_FAILED", "Check the highlighted fields.", {
        errors: [{ field: "email", message: "Enter a valid email address." }],
      }),
    );
    render(<ProblemMessage problem={error} />);
    expect(screen.getByText("Check the highlighted fields.")).toBeInTheDocument();
    expect(screen.getByText(/Enter a valid email address/)).toBeInTheDocument();
  });
});
