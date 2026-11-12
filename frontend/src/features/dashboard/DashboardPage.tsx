// FILE GUIDE: the workspace overview (SCR-02). Every figure comes from the dashboard, queue and cases endpoints;
// nothing here is estimated in the browser. Money stays in integer minor units until formatMinor renders it.
import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { ArrowRight, Check } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { AgingBar } from "../../components/domain/AgingBar";
import { AiMark } from "../../components/domain/AiMark";
import { StatusChip } from "../../components/domain/StatusChip";
import { Button } from "../../components/ui/Button";
import { MetricStrip, MetricTile } from "../../components/ui/MetricTile";
import { Ledger, Page, PageHeader, Section } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { SampleDataBanner } from "../../components/ui/SampleDataBanner";
import { apiRequest } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { formatDate, formatMinor } from "../../lib/format";
import { bucketLabel, tileLabel } from "../../lib/receivableLabels";
import styles from "./DashboardPage.module.css";

const STEPS: { key: string; label: string; detail: string; to: string }[] = [
  {
    key: "invoices",
    label: "Import your invoices",
    detail: "Upload a CSV exported from your accounting system.",
    to: "import/invoices",
  },
  {
    key: "evidence",
    label: "Add payment evidence",
    detail: "Record the bank accounts customers pay into.",
    to: "accounts",
  },
  {
    key: "cadence",
    label: "Set your follow-up cadence",
    detail: "Choose how often a reminder may be drafted.",
    to: "settings/automation",
  },
  {
    key: "queue",
    label: "Review the queue",
    detail: "See which invoices need a decision and why.",
    to: "receivables",
  },
];

const storeKey = (ws: string) => `collectiq.onboarding.${ws}`;

function readSkips(ws: string): string[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(storeKey(ws)) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === "string") : [];
  } catch {
    return [];
  }
}

function writeSkips(ws: string, value: string[]) {
  try {
    window.localStorage.setItem(storeKey(ws), JSON.stringify(value));
  } catch {
    // Private windows can refuse storage. The checklist still works for this visit.
  }
}

function GettingStarted({ ws }: { ws: string }) {
  const [skipped, setSkipped] = useState(() => readSkips(ws));
  const hidden = skipped.includes("*");

  function remember(next: string[]) {
    setSkipped(next);
    writeSkips(ws, next);
  }

  if (hidden) {
    return (
      <Section
        title="No invoices yet"
        description="Import invoices to see what customers owe you."
        actions={
          <Button variant="quiet" onClick={() => remember(skipped.filter((key) => key !== "*"))}>
            Show getting started
          </Button>
        }
      >
        <Ledger>
          <ul className={styles.plainLinks}>
            <li>
              <Link to={`/w/${ws}/import/invoices`}>Import your invoices</Link>
            </li>
            <li>
              <Link to={`/w/${ws}/receivables`}>Review the queue</Link>
            </li>
          </ul>
        </Ledger>
      </Section>
    );
  }

  return (
    <Section
      title="Getting started"
      description="Four steps before your first follow-up. Each one can be done later."
      actions={
        <Button variant="quiet" onClick={() => remember([...skipped, "*"])}>
          Hide this checklist
        </Button>
      }
    >
      <Ledger flush>
        <ol className={styles.steps}>
          {STEPS.map((step, index) => {
            const isSkipped = skipped.includes(step.key);
            return (
              <li key={step.key} className={styles.step} data-skipped={isSkipped || undefined}>
                <span className={styles.stepNumber} aria-hidden="true">
                  {index + 1}
                </span>
                <div className={styles.stepText}>
                  <Link to={`/w/${ws}/${step.to}`} className={styles.stepLink}>
                    {step.label}
                  </Link>
                  <span className={styles.stepDetail}>{step.detail}</span>
                </div>
                {isSkipped ? (
                  <span className={styles.skipped}>Skipped</span>
                ) : (
                  <Button
                    variant="quiet"
                    size="sm"
                    aria-label={`Skip ${step.label}`}
                    onClick={() => remember([...skipped, step.key])}
                  >
                    Skip
                  </Button>
                )}
              </li>
            );
          })}
        </ol>
      </Ledger>
    </Section>
  );
}

const plural = (count: number) => `${count} ${count === 1 ? "invoice" : "invoices"}`;

function listLink(ws: string, filter: Record<string, string>) {
  return `/w/${ws}/receivables?${new URLSearchParams({ view: "all", ...filter }).toString()}`;
}

export function DashboardPage() {
  const { ws = "" } = useParams();

  const dashboard = useQuery({
    queryKey: ["dashboard", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/dashboard" }, { path: { ws } }),
  });

  const queue = useQuery({
    queryKey: ["queue", ws, "dashboard-preview"],
    queryFn: () =>
      apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/queue" }, { path: { ws }, query: { limit: "5" } }),
    enabled: Boolean(ws),
  });

  const cases = useQuery({
    queryKey: ["cases", ws, "dashboard-preview"],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/cases" }, { path: { ws } }),
    enabled: Boolean(ws),
  });

  const data = dashboard.data;
  const empty = data !== undefined && data.currencies.length === 0;

  return (
    <Page>
      <PageHeader
        title="Dashboard"
        description="What customers owe you, how late it is, and what needs a decision next."
        meta={data?.as_of_date && <span>Figures as of {formatDate(data.as_of_date)}</span>}
      />

      <QueryState query={dashboard} label="your dashboard">
        {data?.has_sample_data && <SampleDataBanner />}

        {empty ? (
          <GettingStarted ws={ws} />
        ) : (
          data?.currencies.map((block) => (
            <Section
              key={block.currency}
              id={`cur-${block.currency}`}
              title={block.currency}
              description={`Invoices raised in ${block.currency}. Each currency is totalled on its own.`}
            >
              <MetricStrip label={`${block.currency} totals`}>
                {block.tiles.map((tile) => (
                  <MetricTile
                    key={tile.key}
                    label={tileLabel(tile.key)}
                    value={<span className={styles.money}>{formatMinor(tile.amount_minor, block.currency)}</span>}
                    detail={plural(tile.count)}
                    to={listLink(ws, tile.filter)}
                  />
                ))}
              </MetricStrip>
              {block.aging.length > 0 && (
                <Section level={3} title={`${block.currency} by days past due`} description="What is still owed, grouped by how late it is.">
                  <Ledger>
                    <AgingBar
                      currency={block.currency}
                      caption={`${block.currency} outstanding by days past due`}
                      parts={block.aging.map((bucket) => ({
                        key: bucket.bucket,
                        label: bucketLabel(bucket.bucket),
                        amountMinor: bucket.amount_minor,
                        count: bucket.count,
                        to: listLink(ws, bucket.filter),
                      }))}
                    />
                  </Ledger>
                </Section>
              )}
            </Section>
          ))
        )}

        {!empty && (
          <div className={styles.columns}>
            <NextActions ws={ws} query={queue} />
            <OpenCases ws={ws} query={cases} />
          </div>
        )}
      </QueryState>
    </Page>
  );
}

type ListQuery<T> = UseQueryResult<{ items: T[] }>;
type QueueQuery = ListQuery<components["schemas"]["QueueItemOut"]>;
type CasesQuery = ListQuery<components["schemas"]["CaseOut"]>;

function NextActions({ ws, query }: { ws: string; query: QueueQuery }) {
  const items = (query.data?.items ?? []).slice(0, 5);
  return (
    <Section
      title="Next actions"
      description="The invoices that need a decision first, with the reason."
      actions={
        <Link to={`/w/${ws}/receivables`} className={styles.more}>
          Open the queue
          <ArrowRight size={14} aria-hidden="true" />
        </Link>
      }
    >
      <Ledger flush>
        <QueryState query={query} label="the queue">
          {items.length > 0 ? (
            <ul className={styles.rows} aria-label="Next actions">
              {items.map((item) => (
                <li key={item.id} className={styles.row}>
                  <div className={styles.rowMain}>
                    <div className={styles.rowTitle}>
                      <span className={styles.client}>{item.client_name}</span>
                      <span className={styles.invoiceNumber}>{item.invoice_number}</span>
                    </div>
                    <p className={styles.reason}>{item.reasons[0]?.label ?? "Review this invoice"}</p>
                    <p className={styles.rowMeta}>
                      <span className={styles.money}>{formatMinor(item.outstanding_minor, item.currency)}</span>{" "}
                      outstanding
                      {item.days_overdue > 0 && `, ${item.days_overdue} days overdue`}
                    </p>
                  </div>
                  <Link to={`/w/${ws}/invoices/${item.id}/overview`} className={styles.rowAction}>
                    {item.recommended_action?.label ?? "Open invoice"}
                    <span className="visually-hidden"> for {item.invoice_number}</span>
                    <ArrowRight size={14} aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.clear}>
              <Check size={16} aria-hidden="true" />
              Nothing needs a decision right now.
            </p>
          )}
        </QueryState>
      </Ledger>
    </Section>
  );
}

function OpenCases({ ws, query }: { ws: string; query: CasesQuery }) {
  const open = (query.data?.items ?? []).filter((item) => item.status !== "RESOLVED");
  return (
    <Section
      title="Disputes and questions"
      description="Routine reminders stay paused on an invoice while its case is open."
      aside={query.data && <span className={styles.count}>{open.length} open</span>}
      actions={
        <Link to={`/w/${ws}/cases`} className={styles.more}>
          See all cases
          <ArrowRight size={14} aria-hidden="true" />
        </Link>
      }
    >
      <Ledger flush>
        <QueryState query={query} label="cases">
          {open.length > 0 ? (
            <ul className={styles.rows} aria-label="Open cases">
              {open.slice(0, 4).map((item) => (
                <li key={item.id} className={styles.row}>
                  <div className={styles.rowMain}>
                    <div className={styles.rowTitle}>
                      {item.type === "DISPUTE" ? (
                        <StatusChip kind="dispute" value={item.status} size="sm" />
                      ) : (
                        <span className={styles.client}>Question or request</span>
                      )}
                      <Link to={`/w/${ws}/invoices/${item.invoice_id}/overview`} className={styles.invoiceLink}>
                        {item.invoice_number}
                      </Link>
                    </div>
                    {item.summary && <p className={styles.reason}>{item.summary}</p>}
                    <p className={styles.rowMeta}>
                      {item.summary_is_ai_derived && <AiMark label="AI-written summary, not verified" />}
                      <span>Opened {formatDate(item.opened_at)}</span>
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.clear}>
              <Check size={16} aria-hidden="true" />
              No open disputes or questions.
            </p>
          )}
        </QueryState>
      </Ledger>
    </Section>
  );
}
