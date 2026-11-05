import { useMutation } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import type { paths } from "./api-types";

type Method = "get" | "post" | "put" | "patch" | "delete";

export type ApiOp = {
  [P in keyof paths]: {
    [M in Method]: paths[P][M] extends undefined | never ? never : { path: P; method: M };
  }[Method];
}[keyof paths];

type Operation<O extends ApiOp> = O extends { path: infer P extends keyof paths; method: infer M extends Method }
  ? paths[P][M]
  : never;

type Parameters_<T> = T extends { parameters: infer P } ? P : object;
type PathField<T> = Parameters_<T> extends { path: infer V } ? { path: V } : { path?: undefined };
type QueryField<T> = Parameters_<T> extends { query?: infer V } ? { query?: V } : { query?: undefined };
type BodyField<T> = T extends { requestBody: { content: { "application/json": infer B } } }
  ? { body: B }
  : T extends { requestBody?: { content: { "application/json": infer B } } }
    ? { body?: B }
    : T extends { requestBody?: { content: { "multipart/form-data": unknown } } }
      ? { body?: FormData }
      : { body?: undefined };

export type RequestOf<O extends ApiOp> = PathField<Operation<O>> & QueryField<Operation<O>> & BodyField<Operation<O>>;

type Responses<T> = T extends { responses: infer R } ? R : never;
type Json<T> = T extends { content: { "application/json": infer B } } ? B : undefined;
export type ResponseOf<O extends ApiOp> = Json<
  Responses<Operation<O>>[Extract<keyof Responses<Operation<O>>, 200 | 201 | 202 | 204>]
>;

export type FieldError = { field: string | null; message: string };

type ProblemInit = {
  status: number;
  code: string;
  detail: string;
  correlationId: string | null;
  errors?: FieldError[];
};

/** A definite refusal from the server, or code "NETWORK" (status 0) when no answer arrived. */
export class ApiProblem extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string;
  readonly correlationId: string | null;
  readonly errors: FieldError[];

  constructor({ status, code, detail, correlationId, errors = [] }: ProblemInit) {
    super(`${code} (${status})`);
    this.name = "ApiProblem";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.correlationId = correlationId;
    this.errors = errors;
  }
}

const FIXED_MESSAGES: Record<string, string> = {
  NETWORK: "We couldn't reach CollectIQ. Check your connection and try again.",
  NOT_FOUND: "We can't find that. It may have been removed, or you may not have access to it.",
  AI_DISABLED: "AI reading is turned off for this workspace. An Owner can turn it on in Settings, or use CSV import or manual entry.",
  AI_NOT_CONFIGURED: "AI is not configured on this server. Use CSV import or manual entry.",
  CONFLICT_VERSION: "This record changed since you opened it. Reload to see the latest version, then try again.",
  IDEMPOTENCY_MISMATCH: "This action was already started with different details. Reload and start again.",
  PAYLOAD_TOO_LARGE: "That file is too large to upload.",
  UNSUPPORTED_MEDIA_TYPE: "That type of file can't be uploaded here.",
  RATE_LIMITED: "Too many attempts. Wait a little, then try again.",
  INTEGRATION_UNAVAILABLE: "A connected service isn't responding. Your work is safe; try again later.",
  AI_UNAVAILABLE: "AI help isn't available right now. You can carry on without it.",
  INTERNAL_ERROR: "Something went wrong on our side. Your work is safe; try again shortly.",
};

const DETAIL_FALLBACKS: Record<string, string> = {
  AUTH_REQUIRED: "Sign in to continue.",
  FORBIDDEN: "You don't have permission to do this.",
  VALIDATION_FAILED: "Some details need fixing.",
  STATE_TRANSITION_INVALID: "This can't be done in the record's current state.",
  DUPLICATE_RESOURCE: "This already exists.",
  POLICY_BLOCKED: "A safety rule is blocking this action.",
  IMPORT_VALIDATION_FAILED: "The file has rows that need fixing.",
};

const GENERIC_MESSAGE = "This couldn't be completed. Try again, or contact support with the reference below.";
const UNFIT_FOR_USERS = /%|\bG-?\d{1,2}\b|\bgate\b/i;

export function plainProblem(problem: ApiProblem): { message: string; fields: FieldError[]; correlationId: string | null } {
  const fallback = DETAIL_FALLBACKS[problem.code];
  const fixed = FIXED_MESSAGES[problem.code];
  let message = fixed ?? fallback ?? GENERIC_MESSAGE;
  if (fallback && !fixed && problem.detail && !UNFIT_FOR_USERS.test(problem.detail)) message = problem.detail;
  const fields = problem.errors.filter((error) => !UNFIT_FOR_USERS.test(error.message));
  return { message, fields, correlationId: problem.correlationId };
}

function cookie(name: string): string | null {
  const prefix = `${name}=`;
  const match = document.cookie.split("; ").find((part) => part.startsWith(prefix));
  return match ? decodeURIComponent(match.slice(prefix.length)) : null;
}

function buildUrl(template: string, path: object | undefined, query: object | undefined): string {
  const values = (path ?? {}) as Record<string, string>;
  const url = template.replace(/\{(\w+)\}/g, (_, name: string) => encodeURIComponent(values[name] ?? ""));
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null) search.set(name, String(value));
  }
  const suffix = search.toString();
  return suffix ? `${url}?${suffix}` : url;
}

async function problemFrom(response: Response): Promise<ApiProblem> {
  const parsed: unknown = await response.json().catch(() => null);
  const body = (parsed && typeof parsed === "object" ? parsed : {}) as Record<string, unknown>;
  const text = (value: unknown) => (typeof value === "string" ? value : "");
  return new ApiProblem({
    status: response.status,
    code: text(body.code) || "UNKNOWN",
    detail: text(body.detail),
    correlationId: text(body.correlation_id) || response.headers.get("X-Correlation-ID"),
    errors: Array.isArray(body.errors) ? (body.errors as FieldError[]) : [],
  });
}

type Transport = { idempotencyKey?: string; ifMatch?: number; signal?: AbortSignal };

async function send(op: ApiOp, request: object, transport: Transport, accept: string): Promise<Response> {
  const { path, query, body } = request as { path?: object; query?: object; body?: unknown };
  const headers = new Headers({ Accept: accept });
  // A file upload sets its own multipart boundary, so no content type is given for it.
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isForm) headers.set("Content-Type", "application/json");
  if (op.method !== "get") {
    const csrf = cookie("collectiq_csrf");
    if (csrf) headers.set("X-CSRFToken", csrf);
  }
  if (transport.idempotencyKey) headers.set("Idempotency-Key", transport.idempotencyKey);
  if (transport.ifMatch !== undefined) headers.set("If-Match", `"${transport.ifMatch}"`);

  let response: Response;
  try {
    response = await fetch(buildUrl(op.path, path, query), {
      method: op.method.toUpperCase(),
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      signal: transport.signal,
    });
  } catch (cause) {
    if (transport.signal?.aborted) throw cause;
    throw new ApiProblem({ status: 0, code: "NETWORK", detail: "", correlationId: null });
  }
  if (!response.ok) throw await problemFrom(response);
  return response;
}

export async function apiRequest<O extends ApiOp>(
  op: O,
  request: RequestOf<O>,
  transport: Transport = {},
): Promise<ResponseOf<O>> {
  const response = await send(op, request, transport, "application/json, application/problem+json");
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as ResponseOf<O>;
}

/** For an answer that is a file, such as a CSV report, rather than JSON. */
export async function apiText<O extends ApiOp>(op: O, request: RequestOf<O>, transport: Transport = {}): Promise<string> {
  const response = await send(op, request, transport, "text/csv, application/problem+json");
  return response.text();
}

function fingerprint(text: string): string {
  let hash = 0xcbf29ce484222325n;
  for (let index = 0; index < text.length; index += 1) {
    hash = BigInt.asUintN(64, (hash ^ BigInt(text.charCodeAt(index))) * 0x100000001b3n);
  }
  return hash.toString(16);
}

function readKey(id: string): string | null {
  try {
    return window.sessionStorage.getItem(id);
  } catch {
    return null;
  }
}

function writeKey(id: string, key: string): void {
  try {
    window.sessionStorage.setItem(id, key);
  } catch {
    // The key still lives in memory for this page; only a reload loses it.
  }
}

function forgetKey(id: string): void {
  try {
    window.sessionStorage.removeItem(id);
  } catch {
    // Nothing was stored.
  }
}

export type MutationStatus = "idle" | "pending" | "success" | "problem" | "unknown";

type MutationOptions = {
  idempotent?: boolean;
  ifMatch?: boolean;
  /** The body holds a secret, so the key stays in memory: its name in storage is derived from the body. */
  secretBody?: boolean;
};
type Attempt<O extends ApiOp> = RequestOf<O> & { version?: number };
type Sent<O extends ApiOp> = { attempt: Attempt<O>; key?: string; storageId: string };

function isOutcomeUnknown(problem: ApiProblem): boolean {
  return problem.status === 0 || problem.status >= 500;
}

/** These refuse the retry itself, so they say nothing about whether the first attempt landed. */
function saysNothingAboutEarlierAttempt(problem: ApiProblem): boolean {
  return isOutcomeUnknown(problem) || [401, 403, 429].includes(problem.status);
}

/**
 * Sends a change. A key is created on the first attempt and kept until the server gives a definite
 * answer, so a retry can only ever return the original result. While the outcome is unknown the only
 * way forward is checkStatus(), which resends the same key and body; a new submission is refused.
 */
export function useApiMutation<O extends ApiOp>(op: O, options: MutationOptions = {}) {
  const { idempotent = false, ifMatch = false, secretBody = false } = options;
  const [status, setStatus] = useState<MutationStatus>("idle");
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [data, setData] = useState<ResponseOf<O> | undefined>(undefined);
  const [checking, setChecking] = useState(false);
  const busy = useRef(false);
  const inDoubt = useRef<Sent<O> | null>(null);
  const canCheck = idempotent || ifMatch;

  const mutation = useMutation<ResponseOf<O>, unknown, Sent<O>>({
    mutationFn: ({ attempt, key }) => {
      const { version, ...request } = attempt;
      return apiRequest(op, request as unknown as RequestOf<O>, { idempotencyKey: key, ifMatch: ifMatch ? version : undefined });
    },
  });
  const { mutateAsync } = mutation;

  const send = useCallback(
    async (sent: Sent<O>, recheck: boolean) => {
      busy.current = true;
      try {
        const result = await mutateAsync(sent);
        forgetKey(sent.storageId);
        inDoubt.current = null;
        setData(result);
        setProblem(null);
        setStatus("success");
      } catch (error) {
        const failure =
          error instanceof ApiProblem
            ? error
            : new ApiProblem({ status: 0, code: "NETWORK", detail: "", correlationId: null });
        setProblem(failure);
        const stillUnknown = recheck ? saysNothingAboutEarlierAttempt(failure) : isOutcomeUnknown(failure);
        if (canCheck && stillUnknown) {
          inDoubt.current = sent;
          setStatus("unknown");
        } else {
          forgetKey(sent.storageId);
          inDoubt.current = null;
          setStatus("problem");
        }
      } finally {
        busy.current = false;
        setChecking(false);
      }
    },
    [canCheck, mutateAsync],
  );

  const submit = useCallback(
    (attempt: Attempt<O>) => {
      if (ifMatch && attempt.version === undefined) throw new Error(`${op.path} needs a version for If-Match`);
      if (busy.current || inDoubt.current) return;
      const { path, query, body } = attempt as { path?: object; query?: object; body?: unknown };
      const signature = JSON.stringify({ path, query, body });
      const storageId = `collectiq.idempotency.${op.method}.${op.path}.${fingerprint(signature)}`;
      let key: string | undefined;
      if (idempotent) {
        key = secretBody ? crypto.randomUUID() : (readKey(storageId) ?? crypto.randomUUID());
        if (!secretBody) writeKey(storageId, key);
      }
      setStatus("pending");
      setProblem(null);
      void send({ attempt, key, storageId }, false);
    },
    [idempotent, ifMatch, secretBody, op.method, op.path, send],
  );

  const checkStatus = useCallback(() => {
    const sent = inDoubt.current;
    if (busy.current || !sent) return;
    setChecking(true);
    void send(sent, true);
  }, [send]);

  return { status, data, problem, checking, submit, checkStatus };
}
