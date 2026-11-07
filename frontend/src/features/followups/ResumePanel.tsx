import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import styles from "./Followups.module.css";
import { plainReasons } from "./reasons";

/**
 * After a dispute is resolved, reminders stay off until a person brings them back: ask the policy engine
 * (E127), approve (E092), then resume (E082). Nothing is drafted or sent by resuming.
 */
export function ResumePanel({ invoiceId, onChanged }: { invoiceId: string; onChanged: () => void }) {
  const { ws = "" } = useParams();
  const client = useQueryClient();
  const [approved, setApproved] = useState(false);
  const ask = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}/followups/resume-request" }, { idempotent: true });
  const decide = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/approvals/{approval_id}/decide" }, { idempotent: true });
  const resume = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}/followups/resume" }, { idempotent: true });
  const answer = ask.status === "success" ? ask.data : undefined;
  const approvalId = answer?.approval_id ?? null;
  const resumed = resume.status === "success";
  const ready = approved || decide.status === "success";

  function finish() {
    void client.invalidateQueries({ queryKey: ["invoice", ws, invoiceId] });
    onChanged();
  }

  return (
    <section aria-labelledby="resume-title" className={styles.card}>
      <h2 id="resume-title" className={styles.heading}>
        Bring reminders back
      </h2>
      <p className={styles.muted}>The dispute on this invoice is resolved. Reminders stay off until you choose to bring them back. This sends nothing.</p>
      {!resumed && (
        <div className={styles.actions}>
          <Button onClick={() => ask.submit({ path: { ws, invoice_id: invoiceId } })}>Check whether reminders can resume</Button>
        </div>
      )}
      <MutationFeedback mutation={ask} />
      {answer && !approvalId && (
        <div role="status">
          <p>Not yet.</p>
          <ul>{plainReasons(answer.reasons).map((line) => <li key={line}>{line}</li>)}</ul>
        </div>
      )}
      {approvalId && !ready && !resumed && (
        <div className={styles.actions}>
          <Button
            onClick={() =>
              decide.submit({ path: { ws, approval_id: approvalId }, body: { decision: "APPROVED" } })
            }
          >
            Approve bringing reminders back
          </Button>
        </div>
      )}
      <MutationFeedback mutation={decide} />
      {approvalId && ready && !resumed && (
        <div className={styles.actions}>
          <Button
            onClick={() => {
              setApproved(true);
              resume.submit({ path: { ws, invoice_id: invoiceId }, body: { approval_id: approvalId } });
            }}
          >
            Resume after resolution
          </Button>
        </div>
      )}
      <MutationFeedback mutation={resume} />
      {resumed && (
        <p role="status">
          Reminders are back on for this invoice. <Button variant="secondary" onClick={finish}>Done</Button>
        </p>
      )}
    </section>
  );
}
