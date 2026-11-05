import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useParams } from "react-router";
import { EmptyState } from "../../components/ui/EmptyState";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import { formatDate } from "../../lib/format";
import styles from "./Conversations.module.css";
import { labelText } from "./labels";

export type TimelineEvent = { type: string; id: string; at: string; title: string; [key: string]: unknown };
type Renderer = (event: TimelineEvent) => ReactNode;
const text = (value: unknown) => (typeof value === "string" ? value : "");

/** One renderer per event type the server sends. A type nobody has taught the screen still shows its title. */
export const TIMELINE_RENDERERS: Record<string, Renderer> = {
  MESSAGE: (e) => (
    <>
      <p className={styles.muted}>Customer statement{text(e.sender) ? ` from ${text(e.sender)}` : ""} · not verified</p>
      {text(e.excerpt) && <p className={styles.statement}>{text(e.excerpt)}</p>}
      <p>
        {(Array.isArray(e.labels) ? (e.labels as string[]) : []).map((label) => (
          <span key={label} className={styles.tag}>
            {labelText(label)}
          </span>
        ))}
      </p>
    </>
  ),
  COMMITMENT: (e) => (
    <p className={styles.muted}>
      {e.strength === "EXPLICIT" ? "Firm promise" : "Possible timing"}
      {text(e.date) ? ` for ${formatDate(text(e.date))}` : ""} · {text(e.status).toLowerCase()}
    </p>
  ),
  CASE: (e) => (
    <p className={styles.muted}>
      {e.case_type === "DISPUTE" ? "Dispute" : "Question or request"} · {text(e.status).toLowerCase().replace("_", " ")}
    </p>
  ),
  SNOOZE: (e) => (
    <p className={styles.muted}>
      Until {text(e.until) ? formatDate(text(e.until)) : "a set date"} · {text(e.status).toLowerCase()}
    </p>
  ),
  VERIFICATION_TASK: (e) => <p className={styles.muted}>{e.status === "OPEN" ? "Waiting for a person to check" : "Checked by a person"}</p>,
};

export function InvoiceTimeline({ detail }: { detail: { facts: { id: string } } }) {
  const { ws = "" } = useParams();
  const id = detail.facts.id;
  const found = useQuery({
    queryKey: ["invoice", ws, id, "timeline"],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}/messages" }, { path: { ws, invoice_id: id } }),
  });
  const items = (found.data?.items ?? []) as TimelineEvent[];
  return (
    <section aria-labelledby="timeline-title" className={styles.card}>
      <h2 id="timeline-title" className={styles.heading}>
        Conversation
      </h2>
      <QueryState query={found} label="the conversation">
        {items.length === 0 ? (
          <EmptyState title="Nothing said or decided yet" body="Customer replies, promises, disputes and pauses for this invoice appear here." />
        ) : (
          <ol aria-label="Conversation timeline" className={styles.list}>
            {items.map((event) => (
              <li key={`${event.type}-${event.id}`}>
                <p className={styles.row}>
                  <strong>{event.title}</strong>
                  <span className={styles.muted}>{formatDate(event.at)}</span>
                </p>
                {TIMELINE_RENDERERS[event.type]?.(event)}
              </li>
            ))}
          </ol>
        )}
      </QueryState>
    </section>
  );
}
