import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { Section } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import styles from "./Settings.module.css";

type Workspace = { name?: string; legal_name?: string | null; sender_name?: string | null; version: number };

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
  const pending = save.status === "pending";
  useEffect(() => {
    if (save.status === "success") void client.invalidateQueries({ queryKey: ["workspace", ws] });
  }, [save.status, client, ws]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    save.submit({
      path: { ws },
      body: { legal_name: legal.trim() || null, sender_name: sender.trim() || null },
      version: workspace?.version,
    });
  }

  const fallback = workspace?.name ? `Leave empty to use ${workspace.name}.` : "Leave empty to use the workspace name.";

  return (
    <Section
      title="Your business"
      description="How reminders are signed. Every reminder is still reviewed by a person before it is sent."
    >
      <QueryState query={found} label="your business details">
        <form className={styles.form} onSubmit={submit} noValidate>
          <TextField
            label="Sender name"
            hint={`The name a reminder is signed with. ${fallback}`}
            value={sender}
            onChange={(event) => setSender(event.target.value)}
          />
          <TextField
            label="Legal name"
            hint="Shown beneath the sender name when it differs. Leave empty to leave it out."
            value={legal}
            onChange={(event) => setLegal(event.target.value)}
          />
          <MutationFeedback mutation={save} />
          {save.status === "success" && (
            <p role="status" className={styles.done}>
              Saved. New reminder drafts use these names.
            </p>
          )}
          <div className={styles.actions}>
            <Button variant="primary" type="submit" busy={pending} aria-disabled={pending || undefined}>
              Save
            </Button>
          </div>
        </form>
      </QueryState>
    </Section>
  );
}
