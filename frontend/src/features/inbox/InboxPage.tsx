import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { formatDate } from "../../lib/format";
import styles from "./Inbox.module.css";

type Item = components["schemas"]["InboxItemOut"];
type Note = components["schemas"]["NotificationOut"];

/** Headings in the order a person should work through them: people waiting first, then money, then routine. */
const GROUPS: { kind: Item["kind"]; title: string }[] = [
  { kind: "CASE", title: "Cases" },
  { kind: "PAYMENT_CLAIM", title: "Payment claims" },
  { kind: "MATCH_PROPOSAL", title: "Payment matches" },
  { kind: "REMINDER_DRAFT", title: "Reminder drafts" },
  { kind: "APPROVAL", title: "Approvals" },
];

function NoteRow({ ws, note }: { ws: string; note: Note }) {
  const client = useQueryClient();
  const read = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/notifications/{notification_id}/read" });
  const done = read.status === "success" || note.read_at !== null;
  return (
    <li className={styles.row}>
      <Link to={`/w/${ws}/${note.target_route}`}>{note.action}</Link>
      <span className={styles.muted}>{formatDate(note.created_at)}</span>
      {!done && (
        <Button
          variant="quiet"
          onClick={() => {
            read.submit({ path: { ws, notification_id: note.id } });
            void client.invalidateQueries({ queryKey: ["notifications", ws] });
          }}
        >
          Mark as read
        </Button>
      )}
      <MutationFeedback mutation={read} />
    </li>
  );
}

export function InboxPage() {
  const { ws = "" } = useParams();
  const inbox = useQuery({
    queryKey: ["review-inbox", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/review-inbox" }, { path: { ws } }),
  });
  const notes = useQuery({
    queryKey: ["notifications", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/notifications" }, { path: { ws } }),
  });
  const items = inbox.data?.items ?? [];

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Review Inbox</h1>
      <p className={styles.muted}>Everything waiting for a person. Resolving an item where it lives removes it from here.</p>
      <QueryState query={inbox} label="your review inbox">
        {inbox.data && items.length === 0 && <EmptyState title="Nothing needs your review" />}
        {GROUPS.map(({ kind, title }) => {
          const rows = items.filter((item) => item.kind === kind);
          if (!rows.length) return null;
          return (
            <section key={kind} aria-labelledby={`g-${kind}`} className={styles.card}>
              <h2 id={`g-${kind}`} className={styles.heading}>
                {title} <span className={styles.count}>{rows.length}</span>
              </h2>
              <ul className={styles.list}>
                {rows.map((item) => (
                  <li key={`${kind}-${Object.values(item.subject_ref).join("-")}`} className={styles.row}>
                    <Link to={`/w/${ws}/${item.target_route}`}>{item.action}</Link>
                    <span className={styles.muted}>{formatDate(item.created_at)}</span>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </QueryState>
      <QueryState query={notes} label="your notifications">
        {notes.data && notes.data.items.length > 0 && (
          <section aria-labelledby="notes-title" className={styles.card}>
            <h2 id="notes-title" className={styles.heading}>
              Notifications
            </h2>
            <ul className={styles.list}>
              {notes.data.items.map((note) => (
                <NoteRow key={note.id} ws={ws} note={note} />
              ))}
            </ul>
          </section>
        )}
      </QueryState>
    </div>
  );
}
