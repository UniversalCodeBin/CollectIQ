// FILE GUIDE: review inbox (SCR-17). Everything waiting on a person's decision, grouped in the order to work through it,
// each item linking to the screen where it is resolved. Notifications sit below; marking one read changes nothing else.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { Page, PageHeader, Section } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { formatDate } from "../../lib/format";
import styles from "./Inbox.module.css";

type Item = components["schemas"]["InboxItemOut"];
type Note = components["schemas"]["NotificationOut"];

/** Headings in the order a person should work through them: people waiting first, then money, then routine. */
const GROUPS: { kind: Item["kind"]; title: string; description: string }[] = [
  {
    kind: "CASE",
    title: "Cases",
    description: "Disputes and questions from customers. Reminders for these invoices are paused.",
  },
  {
    kind: "PAYMENT_CLAIM",
    title: "Payment claims",
    description:
      "A customer says they paid. Their word alone never marks an invoice paid; check it against payment evidence.",
  },
  { kind: "MATCH_PROPOSAL", title: "Payment matches", description: "Bank entries that may belong to an invoice." },
  { kind: "REMINDER_DRAFT", title: "Reminder drafts", description: "Drafts waiting for someone to approve or reject." },
  { kind: "APPROVAL", title: "Approvals", description: "Requests waiting for someone to approve or reject." },
];

function Count({ n }: { n: number }) {
  return <span className={styles.count}>{n}</span>;
}

function When({ at }: { at: string }) {
  return (
    <time className={styles.date} dateTime={at}>
      {formatDate(at)}
    </time>
  );
}

function NoteRow({ ws, note }: { ws: string; note: Note }) {
  const client = useQueryClient();
  const read = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/notifications/{notification_id}/read" });
  const done = read.status === "success" || note.read_at !== null;

  useEffect(() => {
    if (read.status === "success") void client.invalidateQueries({ queryKey: ["notifications", ws] });
  }, [read.status, client, ws]);

  return (
    <li className={styles.row} data-unread={!done || undefined}>
      <div className={styles.rowMain}>
        <Link to={`/w/${ws}/${note.target_route}`} className={styles.actionLink}>
          {note.action}
        </Link>
        <p className={styles.rowMeta}>
          {!done && <span className={styles.unread}>Unread</span>}
          <When at={note.created_at} />
        </p>
      </div>
      {!done && (
        <Button
          variant="quiet"
          size="sm"
          busy={read.status === "pending"}
          aria-disabled={read.status === "pending" || undefined}
          onClick={() => read.status !== "pending" && read.submit({ path: { ws, notification_id: note.id } })}
        >
          Mark as read
        </Button>
      )}
      <div className={styles.feedback}>
        <MutationFeedback mutation={read} />
      </div>
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
  const noteItems = notes.data?.items ?? [];

  return (
    <Page>
      <PageHeader
        title="Review Inbox"
        description="Everything waiting on a decision from your team, in the order to work through it. Each item opens where it is resolved."
        meta={
          inbox.data && items.length > 0 ? (
            <p className={styles.summary}>{items.length === 1 ? "1 item waiting" : `${items.length} items waiting`}</p>
          ) : undefined
        }
      />

      <QueryState query={inbox} label="your review inbox">
        {inbox.data && items.length === 0 && (
          <EmptyState
            title="Nothing needs your review"
            body="Cases, payment claims, matches, drafts and approvals appear here when they need a person."
          />
        )}
        {GROUPS.map(({ kind, title, description }) => {
          const rows = items.filter((item) => item.kind === kind);
          if (!rows.length) return null;
          return (
            <Section
              key={kind}
              id={`g-${kind}`}
              title={title}
              description={description}
              aside={<Count n={rows.length} />}
            >
              <ul className={styles.list}>
                {rows.map((item) => (
                  <li key={`${kind}-${Object.values(item.subject_ref).join("-")}`} className={styles.row}>
                    <div className={styles.rowMain}>
                      <Link to={`/w/${ws}/${item.target_route}`} className={styles.actionLink}>
                        {item.action}
                      </Link>
                      <p className={styles.rowMeta}>
                        Waiting since <When at={item.created_at} />
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            </Section>
          );
        })}
      </QueryState>

      <QueryState query={notes} label="your notifications">
        {noteItems.length > 0 && (
          <Section
            id="notes-title"
            title="Notifications"
            description="A record of what happened. Marking one read changes nothing else."
          >
            <ul className={styles.list}>
              {noteItems.map((note) => (
                <NoteRow key={note.id} ws={ws} note={note} />
              ))}
            </ul>
          </Section>
        )}
      </QueryState>
    </Page>
  );
}
