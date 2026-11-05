import type { ReactNode } from "react";
import { ApiProblem } from "../../lib/api";
import { Button } from "./Button";
import { ProblemMessage } from "./ProblemMessage";

type Query = { isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown };

/** The loading and failed states every data screen shares. Children render only once data is there. */
export function QueryState({ query, label, children }: { query: Query; label: string; children: ReactNode }) {
  if (query.isPending) return <p role="status">Loading {label}…</p>;
  if (query.isError) {
    const problem = query.error instanceof ApiProblem ? query.error : new ApiProblem({ status: 0, code: "NETWORK", detail: "", correlationId: null });
    return (
      <div>
        <ProblemMessage problem={problem} />
        <Button variant="secondary" onClick={() => void query.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  return <>{children}</>;
}
