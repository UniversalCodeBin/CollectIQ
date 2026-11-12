import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { Section } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import { formatDate } from "../../lib/format";
import styles from "./Settings.module.css";

/** The AI tasks the server records today. An unknown id is shown as recorded rather than guessed at. */
const TASKS: Record<string, string> = {
  "conversations.interpret": "Reading a customer reply",
  "invoices.extract_pdf": "Reading an invoice PDF",
  "agent.invoice_brief": "Invoice brief",
};

/** Statuses from ai/gateway.py and ai/agents.py. An unknown one is shown as recorded. */
const STATUS: Record<string, string> = {
  OK: "Answered and passed checks",
  COMPLETED: "Answered and passed checks",
  AWAITING_APPROVAL: "Answered; a suggestion waits for a person",
  PROVIDER_ERROR: "The provider did not answer",
  INVALID_OUTPUT: "The answer failed checks and was not used",
  BUDGET_EXCEEDED: "Stopped at the usage limit",
  DISABLED: "Not run: this AI option is off",
  AI_NOT_CONFIGURED: "Not run: AI is not configured",
};
const statusText = (status: string) => STATUS[status] ?? status;

/** What was sent to AI (E105), with personal details already replaced by tokens. Viewing it is audited. */
export function PayloadsPanel() {
  const { ws = "" } = useParams();
  const payloads = useQuery({
    queryKey: ["ai-payloads", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/ai/payloads" }, { path: { ws } }),
  });
  const items = payloads.data?.items ?? [];

  return (
    <Section
      title="What was sent to AI"
      description={`${payloads.data?.note ?? "Shown as sent, with personal details replaced by tokens."} Opening this page is recorded in the audit history.`}
    >
      <QueryState query={payloads} label="what was sent to AI">
        {payloads.data && items.length === 0 ? (
          <p className={styles.muted}>
            Nothing has been sent to an AI provider. When AI assistance is on and reads a document or reply, the text it
            was given appears here.
          </p>
        ) : (
          <ul className={styles.list} aria-label="Requests sent to AI">
            {items.map((item) => (
              <li key={item.id} className={styles.row}>
                <div className={styles.payloadHead}>
                  <h3 className={styles.payloadTitle}>{TASKS[item.task_id] ?? item.task_id}</h3>
                  <time className={styles.date} dateTime={item.created_at}>
                    {formatDate(item.created_at)}
                  </time>
                </div>
                <dl className={styles.facts}>
                  <dt>Result</dt>
                  <dd>{statusText(item.status)}</dd>
                  <dt>Provider</dt>
                  <dd>{item.provider ?? "No provider"}</dd>
                  <dt>Input hash</dt>
                  <dd className={styles.mono}>{item.input_sha256 ?? "None"}</dd>
                </dl>
                {item.dropped_fields.length > 0 && (
                  <p className={styles.muted}>Fields not sent: {item.dropped_fields.join(", ")}</p>
                )}
                <pre className={styles.pre} tabIndex={0} aria-label="Text sent">
                  {item.payload ? JSON.stringify(item.payload, null, 2) : "Cleared by the retention window."}
                </pre>
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </Section>
  );
}
