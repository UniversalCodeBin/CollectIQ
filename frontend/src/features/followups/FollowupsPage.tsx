import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router";
import { EmptyState } from "../../components/ui/EmptyState";
import { QueryState } from "../../components/ui/QueryState";
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
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/reminders" }, { path: { ws }, query: { limit: 100 } }),
  });
  const items = list.data?.items ?? [];
  const count = (statuses: readonly string[]) => items.filter((r) => statuses.includes(r.status)).length;
  const shown = items.filter((r) => (active.statuses as readonly string[]).includes(r.status));
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Follow-ups</h1>
      <p className={styles.muted}>CollectIQ prepares the wording. A person approves it and sends it outside CollectIQ.</p>
      <nav aria-label="Follow-up groups" className={styles.actions}>
        {GROUPS.map((g) => (
          <Link key={g.key} to={`/w/${ws}/followups?group=${g.key}`} aria-current={g.key === active.key ? "page" : undefined}>
            {g.label} {count(g.statuses)}
          </Link>
        ))}
      </nav>
      <QueryState query={list} label="follow-ups">
        {shown.length === 0 ? (
          <EmptyState title="No follow-ups here" body="Drafts appear when an invoice is due for a reminder and nothing is holding it." />
        ) : (
          <ul aria-label={active.label} className={styles.list}>
            {shown.map((r) => (
              <li key={r.id} className={styles.card}>
                <p className={styles.row}>
                  <Link to={`/w/${ws}/reminders/${r.id}`}>
                    {r.invoice_number} · reminder {r.sequence}
                  </Link>
                  <span className={styles.muted}>{r.sent_at ? `Marked sent ${formatDate(r.sent_at)}` : `Planned ${formatDate(r.intended_date)}`}</span>
                </p>
                <p className={styles.muted}>To {r.recipient}</p>
                {r.reason && <p className={styles.muted}>{r.reason}</p>}
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </div>
  );
}
