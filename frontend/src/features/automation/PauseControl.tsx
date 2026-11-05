import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Button } from "../../components/ui/Button";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { apiRequest, useApiMutation } from "../../lib/api";
import styles from "./Automation.module.css";

/** The emergency stop. Shown in every screen so pausing never needs a search. Hidden for people who may not see the policy. */
export function PauseControl({ workspace }: { workspace: string }) {
  const client = useQueryClient();
  const policy = useQuery({
    queryKey: ["policy", workspace],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/policy" }, { path: { ws: workspace } }),
    retry: false,
  });
  const pause = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/automation/pause" });
  const resume = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/automation/resume" });
  const done = pause.status === "success" || resume.status === "success";

  useEffect(() => {
    if (done) void client.invalidateQueries({ queryKey: ["policy", workspace] });
  }, [done, client, workspace]);

  if (!policy.data) return null;
  const paused = pause.status === "success" ? true : resume.status === "success" ? false : policy.data.automation_paused;
  return (
    <div className={styles.banner} role={paused ? "status" : undefined} data-paused={paused || undefined}>
      <p className={styles.muted}>
        {paused
          ? "Automation is paused. No reminder or follow-up will be prepared until you resume."
          : "Automation is on. Nothing is sent without a person approving it."}
      </p>
      {paused ? (
        <Button onClick={() => resume.submit({ path: { ws: workspace } })}>Resume automation</Button>
      ) : (
        <Button onClick={() => pause.submit({ path: { ws: workspace }, body: {} })}>Pause automation</Button>
      )}
      <MutationFeedback mutation={pause} />
      <MutationFeedback mutation={resume} />
    </div>
  );
}
