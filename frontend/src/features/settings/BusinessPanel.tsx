import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import styles from "../automation/Automation.module.css";

type Workspace = { legal_name?: string | null; sender_name?: string | null; version: number };

/** Who reminders are from (E012). Both names are optional: empty falls back to the workspace name. */
export function BusinessPanel() {
  const { ws = "" } = useParams();
  const client = useQueryClient();
  const found = useQuery({
    queryKey: ["workspace", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}" }, { path: { ws } }),
  });
  const workspace = found.data as Workspace | undefined;
  const [legal, setLegal] = useState("");
  const [sender, setSender] = useState("");
  useEffect(() => {
    setLegal(workspace?.legal_name ?? "");
    setSender(workspace?.sender_name ?? "");
  }, [workspace?.legal_name, workspace?.sender_name]);
  const save = useApiMutation({ method: "patch", path: "/api/v1/workspaces/{ws}" }, { ifMatch: true });
  useEffect(() => {
    if (save.status === "success") void client.invalidateQueries({ queryKey: ["workspace", ws] });
  }, [save.status, client, ws]);
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Your business</h1>
      <p className={styles.muted}>
        Reminders are signed with the sender name, and the legal name goes beneath it. Leave a field empty to use
        the workspace name. Every reminder is still reviewed by a person before it is sent.
      </p>
      <QueryState query={found} label="your business details">
        <TextField label="Legal name" value={legal} onChange={(event) => setLegal(event.target.value)} />
        <TextField label="Sender name" value={sender} onChange={(event) => setSender(event.target.value)} />
        <MutationFeedback mutation={save} />
        <Button
          variant="primary"
          onClick={() =>
            save.submit({
              path: { ws },
              body: { legal_name: legal.trim() || null, sender_name: sender.trim() || null },
              version: workspace?.version,
            })
          }
        >
          Save
        </Button>
      </QueryState>
    </div>
  );
}
