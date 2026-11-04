import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { Button } from "../components/ui/Button";
import { ProblemMessage } from "../components/ui/ProblemMessage";
import { ApiProblem, apiRequest, type ResponseOf } from "../lib/api";

export const SESSION_OP = { method: "get", path: "/api/v1/auth/session" } as const;
export const SESSION_KEY = ["session"];

export type Session = ResponseOf<typeof SESSION_OP>;

/** Waits for the session. A signed-out visitor goes to sign in and comes back to where they were heading. */
export function SessionGate({ children }: { children: (session: Session) => ReactNode }) {
  const { pathname, search } = useLocation();
  const session = useQuery({
    queryKey: SESSION_KEY,
    queryFn: ({ signal }) => apiRequest(SESSION_OP, {}, { signal }),
  });

  if (session.isPending) return <p role="status">Loading…</p>;
  if (session.error) {
    if (session.error instanceof ApiProblem && session.error.status === 401) {
      const next = pathname === "/" ? "" : `?next=${encodeURIComponent(`${pathname}${search}`)}`;
      return <Navigate to={`/login${next}`} replace />;
    }
    const problem =
      session.error instanceof ApiProblem
        ? session.error
        : new ApiProblem({ status: 0, code: "NETWORK", detail: "", correlationId: null });
    return (
      <div>
        <ProblemMessage problem={problem} />
        <Button onClick={() => void session.refetch()}>Try again</Button>
      </div>
    );
  }
  return children(session.data);
}
