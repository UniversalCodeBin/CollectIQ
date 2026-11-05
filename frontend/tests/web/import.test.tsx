import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../src/app/router";

const WS = "11111111-1111-4111-8111-111111111111";
const BATCH = "22222222-2222-4222-8222-222222222222";
const SESSION = {
  user: { id: "u1", email: "a@example.test", email_verified: true },
  workspaces: [{ id: WS, name: "Acme Studio", role: "OWNER" }],
  csrf_token: "t",
};
const BASE = `/api/v1/workspaces/${WS}/imports`;
const HEADERS = ["Invoice No", "Customer", "Due", "Cur", "Amount"];

const COMMIT_ALLOWED = { action: "COMMIT", allowed: true, reason: null };
const DISCARD = { action: "DISCARD", allowed: true, reason: null };

function batch(over: Record<string, unknown> = {}) {
  return {
    id: BATCH,
    kind: "INVOICES",
    status: "PREVIEW",
    file_name: "invoices.csv",
    scan_status: "CLEAN",
    headers: HEADERS,
    suggested_mapping: {
      invoice_number: "Invoice No",
      client_name: "Customer",
      due_date: "Due",
      currency: "Cur",
      total: "Amount",
    },
    date_format_options: ["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"],
    mapping: null,
    date_format: null,
    counts: { total_rows: 3 },
    rows: [],
    next_row: null,
    client_matches: [],
    failure_reason: null,
    allowed_actions: [{ ...COMMIT_ALLOWED, allowed: false, reason: "Choose which column holds each field first." }, DISCARD],
    ...over,
  };
}

const MAPPING = batch().suggested_mapping;
const COUNTS = {
  total_rows: 3,
  new: 2,
  updated: 0,
  duplicate: 0,
  possible_duplicate: 0,
  invalid: 0,
  conflict: 0,
  awaiting_client: 0,
  client_decisions: 0,
};
const previewed = (over: Record<string, unknown> = {}) =>
  batch({ mapping: MAPPING, date_format: "DD/MM/YYYY", counts: COUNTS, allowed_actions: [COMMIT_ALLOWED, DISCARD], ...over });

const duplicateRow = {
  row: 2,
  status: "POSSIBLE_DUPLICATE",
  invoice_number: "INV-7",
  client_name: "Northwind Traders",
  currency: "INR",
  errors: [],
  diffs: [],
  matches: [{ invoice_id: "i1", invoice_number: "INV 7", issue_date: "2026-10-01", gross_minor: 150000, currency: "INR" }],
  allowed_decisions: ["KEEP_BOTH", "MERGE", "IGNORE"],
  conflict: null,
};
const withDuplicate = previewed({
  counts: { ...COUNTS, possible_duplicate: 1 },
  rows: [duplicateRow],
  allowed_actions: [
    { action: "COMMIT", allowed: false, reason: "Decide what to do with 1 row that matches an invoice." },
    DISCARD,
  ],
});

type Reply = { status: number; body?: unknown; text?: string } | "network";
type Call = { key: string; body: unknown; headers: Headers; query: string };

let replies: Record<string, Reply | Reply[]>;
let calls: Call[];

function respond(reply: { status: number; body?: unknown; text?: string }) {
  const problem = reply.status >= 400;
  const payload = reply.text ?? (reply.body === undefined ? null : JSON.stringify(reply.body));
  return new Response(payload, {
    status: reply.status,
    headers: { "Content-Type": reply.text ? "text/csv" : problem ? "application/problem+json" : "application/json" },
  });
}

function stub(routes: Record<string, Reply | Reply[]>) {
  replies = { "GET /api/v1/auth/session": { status: 200, body: SESSION }, ...routes };
  calls = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
    const [path = "", query = ""] = String(url).split("?");
    const key = `${(init.method ?? "GET").toUpperCase()} ${path}`;
    const body = init.body instanceof FormData ? init.body : init.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ key, body, headers: new Headers(init.headers), query });
    const planned = replies[key];
    const reply = Array.isArray(planned) ? (planned.length > 1 ? planned.shift() : planned[0]) : planned;
    if (reply === undefined) throw new Error(`no stub for ${key}`);
    if (reply === "network") return Promise.reject(new TypeError("offline"));
    return Promise.resolve(respond(reply));
  });
}

function open(search = "") {
  const router = createMemoryRouter(appRoutes, { initialEntries: [`/w/${WS}/import/invoices${search}`] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, view, url: () => `${router.state.location.pathname}${router.state.location.search}` };
}

const called = (key: string) => calls.filter((call) => call.key === key);
const problem = (status: number, code: string, detail: string) => ({
  status,
  body: { status, code, detail, correlation_id: "cid-9" },
});

beforeEach(() => {
  window.sessionStorage.clear();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Invoice import — where you are comes from the server", () => {
  it("shows the column step from E037 when the page is opened with an import id, as after a reload", async () => {
    stub({ [`GET ${BASE}/${BATCH}`]: { status: 200, body: batch() } });
    open(`?batch=${BATCH}`);
    expect(await screen.findByRole("heading", { name: "Match your columns" })).toBeInTheDocument();
    expect(screen.getByLabelText("Invoice number")).toHaveValue("Invoice No");
    expect(screen.getByText("invoices.csv")).toBeInTheDocument();
    expect(called(`GET ${BASE}/${BATCH}`)).toHaveLength(1);
  });

  it("goes straight to the review step when the import already has a mapping", async () => {
    stub({ [`GET ${BASE}/${BATCH}`]: { status: 200, body: previewed() } });
    open(`?batch=${BATCH}`);
    expect(await screen.findByRole("heading", { name: "Review before importing" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Commit Invoices" })).not.toHaveAttribute("aria-disabled");
  });

  it("uploads a file, then shows the column step and puts the import id in the address", async () => {
    stub({
      [`POST ${BASE}/invoices`]: { status: 201, body: batch() },
      [`GET ${BASE}/${BATCH}`]: { status: 200, body: batch() },
    });
    const page = open();
    const file = new File(["a,b\n1,2\n"], "invoices.csv", { type: "text/csv" });
    await userEvent.upload(await screen.findByLabelText("Choose a CSV file"), file);
    await userEvent.click(screen.getByRole("button", { name: "Upload file" }));
    expect(await screen.findByRole("heading", { name: "Match your columns" })).toBeInTheDocument();
    await waitFor(() => expect(page.url()).toContain(`batch=${BATCH}`));
    const sent = called(`POST ${BASE}/invoices`)[0];
    expect((sent?.body as FormData).get("file")).toBeInstanceOf(File);
    expect(sent?.headers.get("Idempotency-Key")).toBeTruthy();
  });

  it("sends the chosen columns and date format, then shows the review", async () => {
    stub({
      [`GET ${BASE}/${BATCH}`]: { status: 200, body: batch() },
      [`PUT ${BASE}/${BATCH}/mapping`]: { status: 200, body: previewed() },
    });
    open(`?batch=${BATCH}`);
    await screen.findByRole("heading", { name: "Match your columns" });
    await userEvent.selectOptions(screen.getByLabelText("Date format"), "YYYY-MM-DD");
    await userEvent.click(screen.getByRole("button", { name: "Continue to preview" }));
    expect(await screen.findByRole("heading", { name: "Review before importing" })).toBeInTheDocument();
    expect(called(`PUT ${BASE}/${BATCH}/mapping`)[0]?.body).toEqual({ mapping: MAPPING, date_format: "YYYY-MM-DD" });
  });

  it("will not continue while a required column is unchosen, and says which", async () => {
    stub({ [`GET ${BASE}/${BATCH}`]: { status: 200, body: batch({ suggested_mapping: {} }) } });
    open(`?batch=${BATCH}`);
    await screen.findByRole("heading", { name: "Match your columns" });
    await userEvent.click(screen.getByRole("button", { name: "Continue to preview" }));
    expect(await screen.findByText("Choose the column that holds the invoice number.")).toBeInTheDocument();
    expect(called(`PUT ${BASE}/${BATCH}/mapping`)).toHaveLength(0);
  });
});

describe("Invoice import — upload errors are plain", () => {
  it("refuses a file that is not a CSV before sending it", async () => {
    stub({});
    open();
    const file = new File(["%PDF"], "invoices.pdf", { type: "application/pdf" });
    await userEvent.upload(await screen.findByLabelText("Choose a CSV file"), file, { applyAccept: false });
    await userEvent.click(screen.getByRole("button", { name: "Upload file" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a CSV file. Other kinds of file can't be imported.");
    expect(called(`POST ${BASE}/invoices`)).toHaveLength(0);
  });

  it("shows the server's plain reason when it refuses the file", async () => {
    stub({ [`POST ${BASE}/invoices`]: problem(415, "UNSUPPORTED_MEDIA_TYPE", "x") });
    open();
    const file = new File(["a"], "invoices.csv", { type: "text/csv" });
    await userEvent.upload(await screen.findByLabelText("Choose a CSV file"), file);
    await userEvent.click(screen.getByRole("button", { name: "Upload file" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That type of file can't be uploaded here.");
    expect(screen.getByRole("alert")).toHaveTextContent("Reference: cid-9");
  });

  it("asks for a file when none is chosen", async () => {
    stub({});
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Upload file" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a CSV file to upload.");
  });
});

describe("Invoice import — decisions gate the commit", () => {
  it("disables Commit Invoices with the reason until the duplicate is decided, then commits the decision", async () => {
    stub({
      [`GET ${BASE}/${BATCH}`]: { status: 200, body: withDuplicate },
      [`POST ${BASE}/${BATCH}/commit`]: {
        status: 200,
        body: previewed({ status: "COMMITTED", counts: { total_rows: 3, created: 3, updated: 0, merged: 0, unchanged: 0, ignored: 0, skipped_invalid: 0 } }),
      },
    });
    open(`?batch=${BATCH}`);
    const commit = await screen.findByRole("button", { name: "Commit Invoices" });
    expect(commit).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Decide what to do with 1 row that matches an invoice.")).toBeInTheDocument();
    await userEvent.click(commit);
    expect(called(`POST ${BASE}/${BATCH}/commit`)).toHaveLength(0);

    const group = screen.getByRole("radiogroup", { name: "What to do with row 2, INV-7" });
    await userEvent.click(within(group).getByRole("radio", { name: "Keep both" }));
    expect(screen.queryByText("Decide what to do with 1 row that matches an invoice.")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Commit Invoices" }));

    expect(await screen.findByRole("heading", { name: "Import finished" })).toBeInTheDocument();
    expect(called(`POST ${BASE}/${BATCH}/commit`)[0]?.body).toEqual({ decisions: { rows: { "2": { action: "KEEP_BOTH" } } } });
    expect(called(`POST ${BASE}/${BATCH}/commit`)[0]?.headers.get("Idempotency-Key")).toBeTruthy();
    expect(screen.getByText("3 invoices created")).toBeInTheDocument();
  });

  it("makes a total conflict a decision between the stated total and the lines' sum", async () => {
    const conflictRow = {
      ...duplicateRow,
      row: 4,
      status: "CONFLICT",
      invoice_number: "INV-9",
      matches: [],
      allowed_decisions: ["IGNORE"],
      conflict: { total_minor: 100000, sum_minor: 90000 },
    };
    stub({
      [`GET ${BASE}/${BATCH}`]: {
        status: 200,
        body: previewed({ counts: { ...COUNTS, conflict: 1 }, rows: [conflictRow] }),
      },
    });
    open(`?batch=${BATCH}`);
    expect(await screen.findByRole("button", { name: "Commit Invoices" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Choose the total to keep for 1 row.")).toBeInTheDocument();
    const group = screen.getByRole("radiogroup", { name: "Which total to keep for row 4, INV-9" });
    expect(within(group).getByRole("radio", { name: /Total on the invoice: ₹1,000\.00/ })).toBeInTheDocument();
    await userEvent.click(within(group).getByRole("radio", { name: /Sum of the lines: ₹900\.00/ }));
    expect(screen.getByRole("button", { name: "Commit Invoices" })).not.toHaveAttribute("aria-disabled");
  });

  it("needs a client answer for a name that resembles an existing client", async () => {
    const match = {
      name: "northwind traders",
      display_name: "Northwind Traders",
      rows: 2,
      candidates: [{ client_id: "c1", display_name: "Northwind Trading", reason: "SIMILAR_NAME" }],
      in_file: [],
      decision_required: true,
    };
    stub({
      [`GET ${BASE}/${BATCH}`]: {
        status: 200,
        body: previewed({ counts: { ...COUNTS, client_decisions: 1 }, client_matches: [match] }),
      },
    });
    open(`?batch=${BATCH}`);
    expect(await screen.findByRole("button", { name: "Commit Invoices" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Choose which client 2 rows belong to.")).toBeInTheDocument();
    const group = screen.getByRole("radiogroup", { name: "Who is “Northwind Traders”?" });
    await userEvent.click(within(group).getByRole("radio", { name: "Same client as Northwind Trading" }));
    expect(screen.getByRole("button", { name: "Commit Invoices" })).not.toHaveAttribute("aria-disabled");
  });

  it("holds the commit back for invalid rows until skipping them is chosen", async () => {
    const invalid = {
      ...duplicateRow,
      row: 3,
      status: "INVALID",
      matches: [],
      allowed_decisions: [],
      errors: [{ field: "due_date", message: "Enter the due date as DD/MM/YYYY." }],
    };
    stub({
      [`GET ${BASE}/${BATCH}`]: {
        status: 200,
        body: previewed({ counts: { ...COUNTS, invalid: 1 }, rows: [invalid] }),
      },
    });
    open(`?batch=${BATCH}`);
    expect(await screen.findByRole("button", { name: "Commit Invoices" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Fix 1 invalid row or choose to skip them.")).toBeInTheDocument();
    expect(screen.getByText("Enter the due date as DD/MM/YYYY.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Skip the 1 invalid row" }));
    expect(screen.getByRole("button", { name: "Commit Invoices" })).not.toHaveAttribute("aria-disabled");
  });

  it("offers no commit at all when no row can be imported", async () => {
    stub({
      [`GET ${BASE}/${BATCH}`]: { status: 200, body: previewed({ counts: { ...COUNTS, total_rows: 1, new: 0, invalid: 1 } }) },
    });
    open(`?batch=${BATCH}`);
    expect(await screen.findByRole("button", { name: "Commit Invoices" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("No row in this file can be imported yet. Check the problems listed for each row.")).toBeInTheDocument();
  });
});

describe("Invoice import — failure and the error report", () => {
  it("says nothing was created when the commit fails, and keeps the decisions to try again", async () => {
    stub({
      [`GET ${BASE}/${BATCH}`]: { status: 200, body: withDuplicate },
      [`POST ${BASE}/${BATCH}/commit`]: problem(500, "INTERNAL_ERROR", "boom"),
    });
    open(`?batch=${BATCH}`);
    const group = await screen.findByRole("radiogroup", { name: "What to do with row 2, INV-7" });
    await userEvent.click(within(group).getByRole("radio", { name: "Ignore this row" }));
    await userEvent.click(screen.getByRole("button", { name: "Commit Invoices" }));
    expect(await screen.findByText(/Nothing was created/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Import finished" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("radiogroup", { name: "What to do with row 2, INV-7" })).getByRole("radio", { name: "Ignore this row" })).toBeChecked();
  });

  it("shows a recorded failure from the server as nothing created, with the reason", async () => {
    stub({
      [`GET ${BASE}/${BATCH}`]: {
        status: 200,
        body: previewed({ status: "IMPORT_FAILED", failure_reason: "Nothing was added. Something went wrong while saving this import. You can try again." }),
      },
    });
    open(`?batch=${BATCH}`);
    expect(await screen.findByText(/Nothing was added\. Something went wrong/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Commit Invoices" })).not.toHaveAttribute("aria-disabled");
  });

  it("downloads the error report as a CSV file", async () => {
    const invalid = { ...duplicateRow, row: 3, status: "INVALID", matches: [], allowed_decisions: [], errors: [{ field: "due_date", message: "Bad date." }] };
    stub({
      [`GET ${BASE}/${BATCH}`]: { status: 200, body: previewed({ counts: { ...COUNTS, invalid: 1 }, rows: [invalid] }) },
      [`GET ${BASE}/${BATCH}/error-report`]: { status: 200, text: "row,field,message\r\n3,due_date,Bad date.\r\n" },
    });
    const made: Blob[] = [];
    vi.stubGlobal("URL", { createObjectURL: (blob: Blob) => (made.push(blob), "blob:report"), revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    open(`?batch=${BATCH}`);
    await userEvent.click(await screen.findByRole("button", { name: "Download error report" }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(await made[0]?.text()).toBe("row,field,message\r\n3,due_date,Bad date.\r\n");
  });

  it("lets the person discard the import after confirming, and starts again", async () => {
    stub({
      [`GET ${BASE}/${BATCH}`]: { status: 200, body: previewed() },
      [`DELETE ${BASE}/${BATCH}`]: { status: 204 },
    });
    const page = open(`?batch=${BATCH}`);
    await userEvent.click(await screen.findByRole("button", { name: "Discard import" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Discard import" }));
    expect(await screen.findByLabelText("Choose a CSV file")).toBeInTheDocument();
    expect(page.url()).not.toContain("batch=");
  });

  it("shows a plain message when the import cannot be found", async () => {
    stub({ [`GET ${BASE}/${BATCH}`]: problem(404, "NOT_FOUND", "x") });
    open(`?batch=${BATCH}`);
    expect(await screen.findByRole("alert")).toHaveTextContent("We can't find that.");
    expect(screen.getByRole("link", { name: "Start a new import" })).toBeInTheDocument();
  });
});

describe("Invoice import — accessibility", () => {
  it("has no detectable violations on the upload, columns and review steps", async () => {
    stub({ [`GET ${BASE}/${BATCH}`]: [{ status: 200, body: batch() }] });
    const first = open();
    await screen.findByLabelText("Choose a CSV file");
    expect((await axe.run(first.view.container)).violations).toEqual([]);
    first.view.unmount();

    stub({ [`GET ${BASE}/${BATCH}`]: { status: 200, body: batch() } });
    const second = open(`?batch=${BATCH}`);
    await screen.findByRole("heading", { name: "Match your columns" });
    expect((await axe.run(second.view.container)).violations).toEqual([]);
    second.view.unmount();

    stub({ [`GET ${BASE}/${BATCH}`]: { status: 200, body: withDuplicate } });
    const third = open(`?batch=${BATCH}`);
    await screen.findByRole("heading", { name: "Review before importing" });
    expect((await axe.run(third.view.container)).violations).toEqual([]);
  });
});
