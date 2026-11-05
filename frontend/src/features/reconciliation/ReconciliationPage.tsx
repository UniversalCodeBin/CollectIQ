import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import { ConfirmedTab } from "./ConfirmedTab";
import styles from "./Reconciliation.module.css";
import { groupProposals, ReviewTab } from "./ReviewTab";
import type { Proposal } from "./types";
import { UnmatchedTab } from "./UnmatchedTab";

const TABS = ["review", "confirmed", "unmatched"] as const;

export function ReconciliationPage() {
  const { ws = "", tab = "review" } = useParams();
  const path = { ws };
  const query = { limit: 100 };
  const proposals = useQuery({
    queryKey: ["reconciliation", ws, "proposals"],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/reconciliation/proposals" }, { path, query }),
  });
  const payments = useQuery({
    queryKey: ["reconciliation", ws, "payments"],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/payments" }, { path, query }),
  });
  const unmatched = useQuery({
    queryKey: ["reconciliation", ws, "unmatched"],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/transactions/unmatched" }, { path, query }),
  });
  const active = (TABS as readonly string[]).includes(tab) ? tab : "review";
  const confirmed = (payments.data?.items ?? []).filter((p) => p.status === "ACTIVE" && p.allocated_minor > 0);
  const counts = {
    review: proposals.data ? groupProposals(proposals.data.items as unknown as Proposal[]).length : 0,
    confirmed: confirmed.length,
    unmatched: unmatched.data?.items.length ?? 0,
  };
  const labels = { review: "Match review", confirmed: "Confirmed Payments", unmatched: "Unmatched" } as const;
  const current = { review: proposals, confirmed: payments, unmatched }[active as (typeof TABS)[number]];

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Payment Reconciliation</h1>
      <nav aria-label="Reconciliation views" className={styles.tabs}>
        {TABS.map((name) => (
          <Link key={name} to={`../reconciliation/${name}`} relative="path" aria-current={active === name ? "page" : undefined}>
            {labels[name]} <span className={styles.count}>{counts[name]}</span>
          </Link>
        ))}
      </nav>
      <QueryState query={current} label="payments">
        {active === "review" && <ReviewTab workspace={ws} items={(proposals.data?.items ?? []) as unknown as Proposal[]} />}
        {active === "confirmed" && <ConfirmedTab workspace={ws} items={confirmed} />}
        {active === "unmatched" && <UnmatchedTab workspace={ws} items={unmatched.data?.items ?? []} />}
      </QueryState>
    </div>
  );
}
