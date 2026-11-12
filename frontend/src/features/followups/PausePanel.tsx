import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { apiRequest, useApiMutation } from "../../lib/api";
import { formatDate } from "../../lib/format";
import styles from "./Followups.module.css";

type Pause = {
  id: string;
  scope: string;
  reason: string | null;
  status: string;
  paused_at: string;
  resumed_at: string | null;
};

/**
 * Pause or resume reminders for one client or one invoice, with the history of earlier pauses.
 * A pause is a person's decision; the server enforces it on drafting, approval and hand-off.
 */
export function PausePanel({ scope, targetId }: { scope: "CLIENT" | "INVOICE"; targetId: string }) {
  const { ws = "" } = useParams();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const key = ["pauses", ws, scope, targetId];
  const query = scope === "CLIENT" ? { client_id: targetId, history: true } : { invoice_id: targetId, history: true };
  const found = useQuery({
    queryKey: key,
    queryFn: () =>
      apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/reminder-pauses" }, { path: { ws }, query }),
  });
  const pause = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/reminder-pauses" },
    { idempotent: true },
  );
  const resume = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/reminder-pauses/{pause_id}/resume" },
    { idempotent: true },
  );
  const items = (found.data?.items ?? []) as Pause[];
  const active = items.find((entry) => entry.status === "ACTIVE");
  const ended = items.filter((entry) => entry.status !== "ACTIVE");
  const noun = scope === "CLIENT" ? "this client" : "this invoice";
  const changed = pause.status === "success" || resume.status === "success";
  useEffect(() => {
    if (!changed) return;
    setReason("");
    void queryClient.invalidateQueries({ queryKey: key });
    // refresh once per finished change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [changed, pause.data, resume.data]);

  return (
    <section aria-labelledby={`pause-${scope}`} className={styles.card}>
      <h2 id={`pause-${scope}`} className={styles.heading}>
        Pause reminders
      </h2>
      {active ? (
        <>
          <p role="status">
            Reminders are paused for {active.scope === "CLIENT" ? "this client" : "this invoice"} since{" "}
            {formatDate(active.paused_at)}
            {active.reason ? `: ${active.reason}` : ""}. No reminder can be approved or recorded as sent until you
            resume.
          </p>
          <Button onClick={() => resume.submit({ path: { ws, pause_id: active.id } })}>Resume reminders</Button>
          <MutationFeedback mutation={resume} />
        </>
      ) : (
        <>
          <p className={styles.muted}>
            Stop reminders for {noun} until you resume them. Nothing is sent or changed besides that.
          </p>
          <TextField
            label="Reason (optional)"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            maxLength={500}
          />
          <Button
            onClick={() =>
              pause.submit({
                path: { ws },
                body: { scope, target_id: targetId, ...(reason.trim() ? { reason: reason.trim() } : {}) },
              })
            }
          >
            Pause reminders
          </Button>
          <MutationFeedback mutation={pause} />
        </>
      )}
      {ended.length > 0 && (
        <>
          <h3 className={styles.muted}>Earlier pauses</h3>
          <ul>
            {ended.map((entry) => (
              <li key={entry.id}>
                {entry.scope === "CLIENT" ? "Client" : "Invoice"}: {formatDate(entry.paused_at)} to{" "}
                {entry.resumed_at ? formatDate(entry.resumed_at) : "now"}
                {entry.reason ? ` (${entry.reason})` : ""}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
