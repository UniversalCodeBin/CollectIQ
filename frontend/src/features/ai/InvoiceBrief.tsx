import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import styles from "../followups/Followups.module.css";

const STEP_LABEL: Record<string, string> = {
  SEND_REMINDER: "Prepare a reminder",
  WAIT: "Wait",
  REVIEW_REPLY: "Review the customer's reply",
  REVIEW_DISPUTE: "Review the dispute",
  CHECK_PAYMENT_EVIDENCE: "Check the payment evidence",
  NONE: "Nothing needed",
};

/** Plain wording for each refused-draft code; the draft itself is never shown when it was refused. */
const REJECTED = "The suggested wording broke a rule for customer messages, so it was dropped.";

/**
 * AI brief for one invoice. The brief is a reading by a model: shown apart from the verified
 * figures and labelled so. Nothing here sends, pays or changes anything.
 */
export function InvoiceBrief({ detail }: { detail: { facts: { id: string } } }) {
  const { ws = "" } = useParams();
  const brief = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}/ai/brief" });
  const out = brief.status === "success" ? brief.data : undefined;
  const text = out?.brief as { summary?: string; next_step?: string; draft_wording?: string | null } | null | undefined;
  const asked = Boolean(out) && out?.status !== "NOT_ENABLED";
  return (
    <section aria-labelledby="brief-title" className={styles.card}>
      <h2 id="brief-title" className={styles.heading}>
        AI brief
      </h2>
      <p className={styles.muted}>
        A short reading of this invoice by an AI model. It is not a verified fact and it changes nothing. Sending anything stays with you.
      </p>
      <div className={styles.actions}>
        <Button onClick={() => brief.submit({ path: { ws, invoice_id: detail.facts.id } })}>Generate AI brief</Button>
      </div>
      <MutationFeedback mutation={brief} />
      {out?.status === "NOT_ENABLED" && (
        <p role="status">AI invoice briefs are switched off for this workspace. An owner can turn them on in AI settings.</p>
      )}
      {asked && !text && (
        <p role="status">No brief could be made right now. The invoice details on the other tabs are unaffected.</p>
      )}
      {text && (
        <div aria-label="AI-generated brief">
          <p className={styles.statusLine}>AI-generated, unverified</p>
          <p>{text.summary}</p>
          {text.next_step && <p>Suggested next step: {STEP_LABEL[text.next_step] ?? "Nothing needed"}</p>}
          {text.draft_wording && (
            <>
              <p className={styles.muted}>Draft wording (not sent; use Prepare a reminder to review and send it yourself)</p>
              <pre className={styles.statement}>{text.draft_wording}</pre>
            </>
          )}
        </div>
      )}
      {(out?.wording_rejected?.length ?? 0) > 0 && <p role="status">{REJECTED}</p>}
      {(out?.suggestions.length ?? 0) > 0 && (
        <p role="status">The AI suggests pausing reminders for this invoice. This is only a suggestion; nothing has been paused. You can pause reminders from the Follow-up tab.</p>
      )}
    </section>
  );
}
