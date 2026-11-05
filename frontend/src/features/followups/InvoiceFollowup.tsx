import { Link, useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import styles from "./Followups.module.css";
import { plainReasons } from "./reasons";

/** A reminder is only ever prepared when a person asks. Nothing here sends anything. */
export function InvoiceFollowup({ detail }: { detail: { facts: { id: string } } }) {
  const { ws = "" } = useParams();
  const evaluate = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}/reminders/evaluate" }, { idempotent: true });
  const result = evaluate.status === "success" ? evaluate.data : undefined;
  const why = result && !result.reminder ? plainReasons(result.reasons) : [];
  return (
    <section aria-labelledby="followup-title" className={styles.card}>
      <h2 id="followup-title" className={styles.heading}>
        Follow-up
      </h2>
      <p className={styles.muted}>Prepare a reminder for you to review. You approve it and send it yourself; CollectIQ sends nothing.</p>
      <div className={styles.actions}>
        <Button onClick={() => evaluate.submit({ path: { ws, invoice_id: detail.facts.id } })}>Prepare a reminder</Button>
      </div>
      <MutationFeedback mutation={evaluate} />
      {result?.reminder && <Link to={`/w/${ws}/reminders/${result.reminder.id}`}>Review the draft</Link>}
      {result && !result.reminder && (
        <div role="status">
          <p>No draft was made.</p>
          {why.length > 0 && <ul>{why.map((line) => <li key={line}>{line}</li>)}</ul>}
        </div>
      )}
    </section>
  );
}
