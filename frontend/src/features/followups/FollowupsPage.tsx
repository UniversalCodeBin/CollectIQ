// FILE GUIDE: follow-ups (SCR-09, E082–E090). Every reminder CollectIQ has drafted, grouped by where it stands. A draft
// waits for a person to approve it; an approved one waits for a person to send it. Nothing on this screen sends.
import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router";
import { EmptyState } from "../../components/ui/EmptyState";
import { Page, PageHeader } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { Tabs } from "../../components/ui/Tabs";
import { apiRequest } from "../../lib/api";
import { formatDate } from "../../lib/format";
import styles from "./Followups.module.css";

const GROUPS = [
  { key: "drafts", label: "Drafts awaiting approval", statuses: ["DRAFT"] },
  { key: "ready", label: "Ready to send", statuses: ["APPROVED"] },
  { key: "sent", label: "Sent history", statuses: ["MARKED_SENT"] },
  { key: "closed", label: "Closed", statuses: ["REJECTED", "CANCELLED"] },
] as const;

export function FollowupsPage() {
  const { ws = "" } = useParams();
  const [params] = useSearchParams();
  const active = GROUPS.find((g) => g.key === params.get("group")) ?? GROUPS[0];
  const list = useQuery({
    queryKey: ["reminders", ws],
    queryFn: () =>
      apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/reminders" }, { path: { ws }, query: { limit: 100 } }),
  });
  const items = list.data?.items ?? [];
  const count = (statuses: readonly string[]) => items.filter((r) => statuses.includes(r.status)).length;
  const shown = items.filter((r) => (active.statuses as readonly string[]).includes(r.status));

  return (
    <Page>
      <PageHeader
        title="Follow-ups"
        description="CollectIQ drafts the wording. A person approves each reminder and sends it; nothing goes out on its own."
      />

      <Tabs
        label="Follow-up groups"
        items={GROUPS.map((g) => ({
          to: `/w/${ws}/followups?group=${g.key}`,
          label: g.label,
          count: list.data ? count(g.statuses) : undefined,
          current: g.key === active.key,
        }))}
      />

      <QueryState query={list} label="follow-ups">
        {shown.length === 0 ? (
          <EmptyState
            title="No follow-ups here"
            body="Drafts appear when an invoice is due for a reminder and nothing is holding it."
          />
        ) : (
          <ul aria-label={active.label} className={styles.reminders}>
            {shown.map((r) => (
              <li key={r.id} className={styles.reminder}>
                <p className={styles.reminderLine}>
                  <Link to={`/w/${ws}/reminders/${r.id}`} className={styles.reminderLink}>
                    Reminder {r.sequence} for <span className={styles.number}>{r.invoice_number}</span>
                  </Link>
                  {r.sent_at ? (
                    <span className={styles.when}>
                      Marked sent{" "}
                      <time className={styles.date} dateTime={r.sent_at}>
                        {formatDate(r.sent_at)}
                      </time>
                    </span>
                  ) : (
                    r.intended_date && (
                      <span className={styles.when}>
                        Planned for{" "}
                        <time className={styles.date} dateTime={r.intended_date}>
                          {formatDate(r.intended_date)}
                        </time>
                      </span>
                    )
                  )}
                </p>
                <p className={styles.muted}>To {r.recipient}</p>
                {r.reason && <p className={styles.reason}>{r.reason}</p>}
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </Page>
  );
}
