import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router";
import { SESSION_KEY } from "../../app/SessionGate";
import { Button } from "../../components/ui/Button";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import { AuthPage, authStyles } from "./AuthPage";

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
        <p className={authStyles.note}>Open the full link from the invitation email, or ask for a new invitation.</p>
      </AuthPage>
    );
  }
  return (
    <AuthPage title="Join this workspace">
      <p className={authStyles.note}>You've been invited to work in a CollectIQ workspace.</p>
      <MutationFeedback mutation={accept} />
      <Button
        variant="primary"
        disabled={accept.status === "pending"}
        onClick={() => accept.submit({ body: { token } })}
      >
        Accept invitation
      </Button>
      <Link to="/signup">Create an account first</Link>
    </AuthPage>
  );
}
