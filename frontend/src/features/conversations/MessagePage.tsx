// FILE GUIDE: one customer reply (SCR-07, E064). Three layers stay visibly apart: what the customer said, what a
// person recorded about it, and what the ledger verifies. A reply is a statement; it never changes a payment record.
import { useQuery } from "@tanstack/react-query";
import { CircleHelp } from "lucide-react";
import { type ReactNode, useId } from "react";
import { Link, useParams } from "react-router";
import { Page, PageHeader } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import { formatDate } from "../../lib/format";
import styles from "./Conversations.module.css";
import { labelText } from "./labels";

const SOURCE: Record<string, string> = {
  PASTE: "Pasted by a person",
  EML: "From an uploaded email file",
  TXT: "From an uploaded text file",
};

function Layer({
  layer,
  title,
  note,
  children,
}: {
  layer: "said" | "recorded" | "verified";
  title: string;
  note: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={styles.layer} data-layer={layer}>
      <h2 id={id} className={styles.layerTitle}>
        {title}
      </h2>
      <p className={styles.layerNote}>{note}</p>
      {children}
    </section>
  );
}

export function MessagePage() {
  const { ws = "", id = "" } = useParams();
  const found = useQuery({
    queryKey: ["messages", ws, id],
    queryFn: () =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/messages/{message_id}" },
        { path: { ws, message_id: id } },
      ),
  });
  const message = found.data;
  const claim = message?.associations.some((a) => a.labels.includes("PAYMENT_CLAIM")) ?? false;

  return (
    <Page>
      <QueryState query={found} label="the reply">
        {message && (
          <>
            <PageHeader
              back={{ to: `/w/${ws}/conversations`, label: "Conversations" }}
              title={message.subject ?? "Customer reply"}
              meta={
                <p className={styles.meta}>
                  {message.sender && <span>From {message.sender}</span>}
                  <time className={styles.date} dateTime={message.received_at}>
                    Received {formatDate(message.received_at)}
                  </time>
                  <span>{SOURCE[message.source] ?? message.source}</span>
                </p>
              }
            />

            <div className={styles.layers}>
              <Layer
                layer="said"
                title="What the customer said"
                note="The customer's own words, shown as written. Nothing here has been checked against a record."
              >
                <pre className={styles.statement}>{message.body}</pre>
              </Layer>

              <Layer
                layer="recorded"
                title="What a person recorded"
                note="The invoices this reply is about and what it says, as a person on your team recorded them."
              >
                {message.associations.length === 0 ? (
                  <p className={styles.muted}>This reply is not linked to an invoice yet.</p>
                ) : (
                  <ul className={styles.links} aria-label="Linked invoices">
                    {message.associations.map((a) => (
                      <li key={a.invoice_id} className={styles.linkRow}>
                        <Link to={`/w/${ws}/invoices/${a.invoice_id}/overview`} className={styles.invoiceLink}>
                          {a.invoice_number}
                        </Link>
                        {a.labels.length > 0 && (
                          <span className={styles.tags}>
                            {a.labels.map((label) => (
                              <span key={label} className={styles.tag}>
                                {labelText(label)}
                              </span>
                            ))}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Layer>

              <Layer
                layer="verified"
                title="What is verified"
                note="What the ledger shows. Only confirmed evidence changes it."
              >
                {claim && (
                  <div role="status" className={styles.claim}>
                    <CircleHelp size={18} aria-hidden="true" className={styles.claimIcon} />
                    <p className={styles.claimText}>
                      <strong>Payment not verified</strong>
                      <span>
                        The customer says this is paid. The invoice stays unpaid until someone checks the bank evidence,
                        and routine reminders are paused meanwhile.
                      </span>
                    </p>
                  </div>
                )}
                <p className={styles.plain}>
                  A reply does not change any payment record. Only a confirmed payment in Reconciliation marks money
                  received.
                </p>
              </Layer>
            </div>
          </>
        )}
      </QueryState>
    </Page>
  );
}
