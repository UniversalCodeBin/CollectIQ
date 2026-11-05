import { useInfiniteQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import { InvoiceTable } from "./InvoiceTable";
import styles from "./Receivables.module.css";

const FILTERS = ["tile", "aging", "currency", "q", "client_id"] as const;
const PAGE = 50;

export function ReceivablesPage() {
  const { ws = "" } = useParams();
  const [params] = useSearchParams();
  const all = params.get("view") === "all";
  const filters = Object.fromEntries(FILTERS.flatMap((name) => (params.get(name) ? [[name, params.get(name) as string]] : [])));
  const list = useInfiniteQuery({
    queryKey: ["receivables", ws, all ? "all" : "queue", filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => {
      const query = { ...filters, limit: String(PAGE), ...(pageParam ? { cursor: pageParam } : {}) };
      return all
        ? apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/invoices" }, { path: { ws }, query })
        : apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/queue" }, { path: { ws }, query });
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const rows = list.data?.pages.flatMap((page) => page.items) ?? [];
  const withFilters = (extra: Record<string, string>) => `?${new URLSearchParams({ ...extra, ...filters }).toString()}`;

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Receivables</h1>
      <nav aria-label="Receivables views" className={styles.views}>
        <Link to={withFilters({})} aria-current={all ? undefined : "page"}>
          Needs attention
        </Link>
        <Link to={withFilters({ view: "all" })} aria-current={all ? "page" : undefined}>
          All invoices
        </Link>
      </nav>
      <QueryState query={list} label="invoices">
        {rows.length === 0 ? (
          <EmptyState
            title={all ? "No invoices match" : "Nothing needs your attention"}
            body={all ? "Try removing a filter, or import more invoices." : "Invoices that need a follow-up, a check or a decision show up here."}
            action={all ? undefined : <Link to={withFilters({ view: "all" })}>See all invoices</Link>}
          />
        ) : (
          <>
            <InvoiceTable workspace={ws} caption={all ? "All invoices" : "Invoices that need attention"} rows={rows as never} queue={!all} />
            {list.hasNextPage && (
              <div>
                <Button variant="secondary" onClick={() => void list.fetchNextPage()} aria-disabled={list.isFetchingNextPage || undefined}>
                  Load more
                </Button>
              </div>
            )}
          </>
        )}
      </QueryState>
    </div>
  );
}
