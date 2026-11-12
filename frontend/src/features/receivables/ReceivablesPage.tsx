// FILE GUIDE: the receivables list (SCR-03). "Needs attention" is the server's queue, already ordered and with its
// reasons; "All invoices" is the plain invoice list. Filters live in the address so dashboard links and the back
// button land on the same view. Nothing is counted or ranked in the browser.
import { useInfiniteQuery } from "@tanstack/react-query";
import { FileUp, Search, X } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { Button, ButtonLink } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { TextField } from "../../components/ui/Field";
import { Ledger, Page, PageHeader, Toolbar } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { Tabs } from "../../components/ui/Tabs";
import { apiRequest } from "../../lib/api";
import { bucketLabel, tileLabel } from "../../lib/receivableLabels";
import { InvoiceTable } from "./InvoiceTable";
import styles from "./Receivables.module.css";

const FILTERS = ["tile", "aging", "currency", "q", "client_id"] as const;
const PAGE = 50;

function filterLabel(name: string, value: string) {
  switch (name) {
    case "tile":
      return tileLabel(value);
    case "aging":
      return bucketLabel(value);
    case "currency":
      return `Currency ${value}`;
    case "q":
      return `Matching “${value}”`;
    case "client_id":
      return "One customer";
    default:
      return value;
  }
}

export function ReceivablesPage() {
  const { ws = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const all = params.get("view") === "all";
  const [searchInput, setSearchInput] = useState(params.get("q") ?? "");

  const filters = Object.fromEntries(
    FILTERS.flatMap((name) => (params.get(name) ? [[name, params.get(name) as string]] : [])),
  );
  const active = Object.entries(filters);

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

  function without(name: string) {
    const next = new URLSearchParams(params);
    next.delete(name);
    return `?${next.toString()}`;
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    const next = new URLSearchParams(params);
    const query = searchInput.trim();
    if (query) next.set("q", query);
    else next.delete("q");
    navigate(`?${next.toString()}`);
  }

  return (
    <Page>
      <PageHeader
        title="Receivables"
        description={
          all
            ? "Every invoice in this workspace, whatever its state."
            : "Invoices that need a decision, a check or a follow-up, in the order to deal with them."
        }
        actions={
          <ButtonLink to={`/w/${ws}/import/invoices`}>
            <FileUp size={16} aria-hidden="true" />
            Import invoices
          </ButtonLink>
        }
      />

      <Tabs
        label="Receivables views"
        items={[
          { to: withFilters({}), label: "Needs attention", current: !all },
          { to: withFilters({ view: "all" }), label: "All invoices", current: all },
        ]}
      />

      <Toolbar>
        <form className={styles.search} onSubmit={submitSearch} role="search" aria-label="Invoices">
          <TextField
            label="Search invoices"
            type="search"
            icon={Search}
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Invoice number, customer or reference"
          />
          <Button type="submit" variant="secondary">
            Search
          </Button>
        </form>
      </Toolbar>

      {active.length > 0 && (
        <div className={styles.filters} role="group" aria-label="Filters in use">
          <span className={styles.filtersLabel}>Showing</span>
          <ul className={styles.filterList}>
            {active.map(([name, value]) => (
              <li key={name}>
                <Link
                  to={without(name)}
                  className={styles.filterChip}
                  onClick={() => name === "q" && setSearchInput("")}
                >
                  {filterLabel(name, value)}
                  <X size={14} aria-hidden="true" />
                  <span className="visually-hidden"> (remove this filter)</span>
                </Link>
              </li>
            ))}
          </ul>
          {active.length > 1 && (
            <Link to={all ? "?view=all" : "?"} className={styles.clearAll} onClick={() => setSearchInput("")}>
              Clear filters
            </Link>
          )}
        </div>
      )}

      <QueryState query={list} label="invoices">
        {rows.length === 0 ? (
          <EmptyState
            title={all ? "No invoices match" : "Nothing needs your attention"}
            body={
              all
                ? "Try removing a filter, or import more invoices."
                : "Invoices that need a follow-up, a check or a decision show up here."
            }
            action={all ? undefined : <Link to={withFilters({ view: "all" })}>See all invoices</Link>}
          />
        ) : (
          <Ledger flush>
            <InvoiceTable
              workspace={ws}
              caption={all ? "All invoices" : "Invoices that need attention"}
              rows={rows as never}
              queue={!all}
            />
            {list.hasNextPage && (
              <div className={styles.loadMore}>
                <Button
                  variant="secondary"
                  onClick={() => void list.fetchNextPage()}
                  busy={list.isFetchingNextPage}
                  aria-disabled={list.isFetchingNextPage || undefined}
                >
                  Load more
                </Button>
              </div>
            )}
          </Ledger>
        )}
      </QueryState>
    </Page>
  );
}
