import { describe, expect, it } from "vitest";
import { ApiProblem } from "../../src/lib/api";
import { createQueryClient, shouldRetry } from "../../src/lib/queryClient";

const problem = (status: number) =>
  new ApiProblem({ status, code: "X", detail: "", correlationId: null });

describe("which failed reads are tried again", () => {
  it("does not repeat a refusal, so a signed-out visitor is redirected at once", () => {
    for (const status of [400, 401, 403, 404, 409, 422]) expect(shouldRetry(0, problem(status))).toBe(false);
  });

  it("repeats a lost connection or server failure a limited number of times", () => {
    for (const status of [0, 500, 503]) {
      expect(shouldRetry(0, problem(status))).toBe(true);
      expect(shouldRetry(1, problem(status))).toBe(true);
      expect(shouldRetry(2, problem(status))).toBe(false);
    }
  });

  it("repeats a rate limit like a server failure", () => {
    expect(shouldRetry(0, problem(429))).toBe(true);
  });

  it("is what the application's client uses, and mutations never repeat", () => {
    const defaults = createQueryClient().getDefaultOptions();
    expect(defaults.queries?.retry).toBe(shouldRetry);
    expect(defaults.mutations?.retry).toBe(false);
  });
});
