import { useQueryClient } from "@tanstack/react-query";
import { Link2Off } from "lucide-react";
import { useEffect } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router";
import { SESSION_KEY } from "../../app/SessionGate";
import { Button } from "../../components/ui/Button";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import { AuthPage, AuthSwitch, authStyles } from "./AuthPage";

export function AcceptInvitationPage() {
  const [params] = useSearchParams();
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const accept = useApiMutation({ method: "post", path: "/api/v1/invitations/accept" });
  const token = params.get("token");
  const joined = accept.status === "success" ? accept.data?.workspace_id : undefined;

  useEffect(() => {
    if (!joined) return;
    client.removeQueries({ queryKey: SESSION_KEY });
    void navigate(`/w/${joined}/dashboard`, { replace: true });
  }, [joined, client, navigate]);

  if (accept.status === "problem" && accept.problem?.status === 401) {
    return <Navigate to={`/login?next=${encodeURIComponent(`${pathname}${search}`)}`} replace />;
  }
  if (!token) {
    return (
      <AuthPage title="This link is incomplete">
        <div className={authStyles.outcome}>
          <Link2Off size={20} aria-hidden="true" />
          <p>Open the full link from the invitation email, or ask the person who invited you to send a new one.</p>
        </div>
      </AuthPage>
    );
  }
  return (
    <AuthPage title="Join this workspace" lead="You've been invited to work in a CollectIQ workspace.">
      <MutationFeedback mutation={accept} />
      <Button
        variant="primary"
        size="lg"
        block
        busy={accept.status === "pending"}
        disabled={accept.status === "pending"}
        onClick={() => accept.submit({ body: { token } })}
      >
        Accept invitation
      </Button>
      <AuthSwitch>
        No account yet? <Link to="/signup">Create an account first</Link>
      </AuthSwitch>
    </AuthPage>
  );
}
