import { Outlet, useParams } from "react-router";
import { NotFoundPage } from "./NotFoundPage";
import { SessionGate } from "./SessionGate";
import { Shell } from "./Shell";

export function WorkspaceLayout() {
  const { ws } = useParams();
  return (
    <SessionGate>
      {(session) => {
        const workspace = session.workspaces.find((candidate) => candidate.id === ws);
        if (!workspace) return <NotFoundPage />;
        return (
          <Shell workspaceId={workspace.id} workspaceName={workspace.name}>
            <Outlet />
          </Shell>
        );
      }}
    </SessionGate>
  );
}
