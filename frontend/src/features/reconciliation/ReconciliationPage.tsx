// FILE GUIDE: payment reconciliation (SCR-06). Three views of the same evidence: suggestions waiting for a person,
// payments already applied (with their reversible history) and money not yet applied to any invoice. Nothing here
// allocates on its own; every allocation is a confirmed server call.
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { Page, PageHeader } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { Tabs } from "../../components/ui/Tabs";
import { apiRequest } from "../../lib/api";
import { ConfirmedTab } from "./ConfirmedTab";
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
    queryFn: () =>
      apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/reconciliation/proposals" }, { path, query }),
  });

  const payments = useQuery({
    queryKey: ["reconciliation", ws, "payments"],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/payments" }, { path, query }),
  });

  const unmatched = useQuery({
    queryKey: ["reconciliation", ws, "unmatched"],
    queryFn: () =>
      apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/transactions/unmatched" }, { path, query }),
  });

  const active = (TABS as readonly string[]).includes(tab) ? tab : "review";
  const confirmed = (payments.data?.items ?? []).filter((p) => p.status === "ACTIVE" && p.allocated_minor > 0);

  const counts = {
    review: proposals.data ? groupProposals(proposals.data.items as unknown as Proposal[]).length : 0,
    confirmed: confirmed.length,
    unmatched: unmatched.data?.items.length ?? 0,
  };

  const labels = {
    review: "Match review",
    confirmed: "Confirmed Payments",
    unmatched: "Unmatched",
  } as const;

  const current = { review: proposals, confirmed: payments, unmatched }[active as (typeof TABS)[number]];

  return (
    <Page>
      <PageHeader
        title="Payment Reconciliation"
        description="Match bank payments to invoices. A suggestion changes nothing until you confirm it, and every allocation can be reversed with a reason."
      />

      <Tabs
        label="Reconciliation views"
        items={TABS.map((name) => ({
          to: `/w/${ws}/reconciliation/${name}`,
          label: labels[name],
          count: counts[name],
          current: active === name,
        }))}
      />

      <QueryState query={current} label="payments">
        {active === "review" && (
          <ReviewTab workspace={ws} items={(proposals.data?.items ?? []) as unknown as Proposal[]} />
        )}
        {active === "confirmed" && <ConfirmedTab workspace={ws} items={confirmed} />}
        {active === "unmatched" && <UnmatchedTab workspace={ws} items={unmatched.data?.items ?? []} />}
      </QueryState>
    </Page>
  );
}
