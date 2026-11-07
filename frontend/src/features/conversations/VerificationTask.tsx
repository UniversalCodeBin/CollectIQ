import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import styles from "./Conversations.module.css";

/**
 * A customer said they paid; CollectIQ cannot see that. A person checks outside CollectIQ and closes the task
 * here (E128) with a note of what they found. Closing never records a payment: only confirmed evidence does.
 */
export function VerificationTask({ taskId, open }: { taskId: string; open: boolean }) {
  const { ws = "", id = "" } = useParams();
  const client = useQueryClient();
  const [note, setNote] = useState("");
  const close = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}/verification-tasks/{task_id}/close" },
    { idempotent: true },
  );
  if (!open) return <p className={styles.muted}>Checked by a person</p>;
  return (
    <div>
      <p className={styles.muted}>Waiting for a person to check. The invoice stays unpaid until payment evidence is confirmed.</p>
      <TextField label="What did you find?" value={note} onChange={(event) => setNote(event.target.value)} />
      <Button
        variant="secondary"
        disabled={!note.trim()}
        onClick={() => {
          close.submit({ path: { ws, invoice_id: id, task_id: taskId }, body: { note: note.trim() } });
          void client.invalidateQueries({ queryKey: ["invoice", ws, id] });
        }}
      >
        Close this check
      </Button>
      <MutationFeedback mutation={close} />
    </div>
  );
}
