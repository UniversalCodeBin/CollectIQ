import { QueryClient } from "@tanstack/react-query";
import { ApiProblem } from "./api";

const MAX_RETRIES = 2;

/** A refusal gives the same answer the next time, and waiting on it only delays showing it. */
export function shouldRetry(failures: number, error: unknown): boolean {
  if (failures >= MAX_RETRIES) return false;
  if (!(error instanceof ApiProblem)) return true;
  return error.status === 0 || error.status === 429 || error.status >= 500;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: shouldRetry }, mutations: { retry: false } } });
}
