import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import { formatDate } from "../../lib/format";
import styles from "./Conversations.module.css";
import { labelText } from "./labels";

/** Three layers, kept apart: what the customer said, what a person recorded about it, and what the ledger verifies. */
export function MessagePage() {
  const { ws = "", id = "" } = useParams();
  const found = useQuery({
    queryKey: ["messages", ws, id],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/messages/{message_id}" }, { path: { ws, message_id: id } }),
  });
  const message = found.data;
  const claim = message?.associations.some((a) => a.labels.includes("PAYMENT_CLAIM")) ?? false;
  return (
    <div className={styles.page}>
      <QueryState query={found} label="the reply">
        {message && (
          <>
            <h1 className={styles.title}>{message.subject ?? "Customer reply"}</h1>
            <p className={styles.muted}>
              {message.sender ? `From ${message.sender} · ` : ""}
              {formatDate(message.received_at)}
            </p>
            <section aria-labelledby="said-title" className={styles.card}>
              <h2 id="said-title" className={styles.heading}>
                What the customer said
              </h2>
              <p className={styles.muted}>Customer statement. Shown as written; not checked against any record.</p>
              <pre className={styles.statement}>{message.body}</pre>
            </section>
            <section aria-labelledby="recorded-title" className={styles.card}>
              <h2 id="recorded-title" className={styles.heading}>
                What a person recorded
              </h2>
              {message.associations.length === 0 ? (
                <p className={styles.muted}>This reply is not linked to an invoice yet.</p>
              ) : (
                <ul className={styles.list}>
                  {message.associations.map((a) => (
                    <li key={a.invoice_id}>
                      <Link to={`/w/${ws}/invoices/${a.invoice_id}/overview`}>{a.invoice_number}</Link>{" "}
                      {a.labels.map((label) => (
                        <span key={label} className={styles.tag}>
                          {labelText(label)}
                        </span>
                      ))}
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section aria-labelledby="verified-title" className={styles.card}>
              <h2 id="verified-title" className={styles.heading}>
                What is verified
              </h2>
              {claim && <p role="status">Payment not verified</p>}
              <p className={styles.muted}>
                A reply does not change any payment record. Only a confirmed payment in Reconciliation marks money received.
              </p>
            </section>
          </>
        )}
      </QueryState>
    </div>
  );
}
