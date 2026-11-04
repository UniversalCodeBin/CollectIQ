import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet, useParams } from "react-router";
import { Button } from "../components/ui/Button";
import { ProblemMessage } from "../components/ui/ProblemMessage";
import { ApiProblem, apiRequest } from "../lib/api";
import { NotFoundPage } from "./NotFoundPage";
import { Shell } from "./Shell";

export const SESSION_OP = { method: "get", path: "/api/v1/auth/session" } as const;

export function WorkspaceLayout() {
  const { ws } = useParams();
  const session = useQuery({
    queryKey: ["session"],
    queryFn: ({ signal }) => apiRequest(SESSION_OP, {}, { signal }),
  });

  if (session.isPending) return <p role="status">Loading…</p>;
  if (session.error) {
    if (session.error instanceof ApiProblem && session.error.status === 401) return <Navigate to="/login" replace />;
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
  const workspace = session.data.workspaces.find((candidate) => candidate.id === ws);
  if (!workspace) return <NotFoundPage />;
  return (
    <Shell workspaceId={workspace.id} workspaceName={workspace.name}>
      <Outlet />
    </Shell>
  );
}
