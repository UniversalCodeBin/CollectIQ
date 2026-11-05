import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { QueryState } from "../../components/ui/QueryState";
import { SampleDataBanner } from "../../components/ui/SampleDataBanner";
import { apiRequest } from "../../lib/api";
import { formatMinor } from "../../lib/format";
import styles from "./DashboardPage.module.css";

// Every step can be skipped; nothing here blocks the rest of the product.
const STEPS: { key: string; label: string; to: string }[] = [
  { key: "invoices", label: "Import your invoices", to: "import/invoices" },
  { key: "evidence", label: "Add payment evidence", to: "accounts" },
  { key: "cadence", label: "Set your follow-up cadence", to: "settings/automation" },
  { key: "queue", label: "Review the queue", to: "receivables" },
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

function GettingStarted({ ws }: { ws: string }) {
  const [skipped, setSkipped] = useState(() => readSkips(ws));
  const hidden = skipped.includes("*");
  function remember(next: string[]) {
    setSkipped(next);
    window.localStorage.setItem(storeKey(ws), JSON.stringify(next));
  }
  if (hidden) {
    return (
      <section aria-labelledby="no-invoices" className={styles.card}>
        <h2 id="no-invoices" className={styles.heading}>
          No invoices yet
        </h2>
        <ul className={styles.steps}>
          <li>
            <Link to={`/w/${ws}/import/invoices`}>Import your invoices</Link>
          </li>
          <li>
            <Link to={`/w/${ws}/receivables`}>Review the queue</Link>
          </li>
        </ul>
        <Button variant="quiet" onClick={() => remember(skipped.filter((key) => key !== "*"))}>
          Show getting started
        </Button>
      </section>
    );
  }
  return (
    <section aria-labelledby="getting-started" className={styles.card}>
      <h2 id="getting-started" className={styles.heading}>
        Getting started
      </h2>
      <ul className={styles.steps}>
        {STEPS.map((step) => {
          const isSkipped = skipped.includes(step.key);
          return (
            <li key={step.key}>
              <Link to={`/w/${ws}/${step.to}`}>{step.label}</Link>
              {isSkipped ? (
                <span> Skipped</span>
              ) : (
                <Button variant="quiet" aria-label={`Skip ${step.label}`} onClick={() => remember([...skipped, step.key])}>
                  Skip
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      <Button variant="quiet" onClick={() => remember([...skipped, "*"])}>
        Hide this checklist
      </Button>
    </section>
  );
}

const TILE_LABELS: Record<string, string> = {
  outstanding: "Outstanding",
  overdue: "Overdue",
  due_soon: "Due soon",
  partially_paid: "Partly paid",
  needs_verification: "Needs checking",
  disputed: "In dispute",
  snoozed: "Paused",
};
const BUCKET_LABELS: Record<string, string> = { not_due: "Not due yet" };

const tileLabel = (key: string) => TILE_LABELS[key] ?? key.replace(/_/g, " ");
const bucketLabel = (key: string) => BUCKET_LABELS[key] ?? (/^\d/.test(key) ? `${key} days` : key.replace(/_/g, " "));
const plural = (count: number) => `${count} ${count === 1 ? "invoice" : "invoices"}`;

/** The list address for a server-given filter, so the list shows what the number counted. */
function listLink(ws: string, filter: Record<string, string>) {
  return `/w/${ws}/receivables?${new URLSearchParams({ view: "all", ...filter }).toString()}`;
}

export function DashboardPage() {
  const { ws = "" } = useParams();
  const dashboard = useQuery({
    queryKey: ["dashboard", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/dashboard" }, { path: { ws } }),
  });
  const data = dashboard.data;
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Dashboard</h1>
      <QueryState query={dashboard} label="your dashboard">
        {data?.has_sample_data && <SampleDataBanner />}
        {data && data.currencies.length === 0 ? (
          <GettingStarted ws={ws} />
        ) : (
          data?.currencies.map((block) => (
            <section key={block.currency} aria-labelledby={`cur-${block.currency}`} className={styles.card}>
              <h2 id={`cur-${block.currency}`} className={styles.heading}>
                {block.currency}
              </h2>
              <ul className={styles.tiles}>
                {block.tiles.map((tile) => (
                  <li key={tile.key}>
                    <Link className={styles.tile} to={listLink(ws, tile.filter as Record<string, string>)}>
                      <span className={styles.tileName}>{tileLabel(tile.key)}</span>
                      <span className={styles.amount}>{formatMinor(tile.amount_minor, block.currency)}</span>
                      <span className={styles.count}>{plural(tile.count)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
              <h3 className={styles.subheading}>How late</h3>
              <ul className={styles.tiles}>
                {block.aging.map((bucket) => (
                  <li key={bucket.bucket}>
                    <Link className={styles.tile} to={listLink(ws, bucket.filter as Record<string, string>)}>
                      <span className={styles.tileName}>{bucketLabel(bucket.bucket)}</span>
                      <span className={styles.amount}>{formatMinor(bucket.amount_minor, block.currency)}</span>
                      <span className={styles.count}>{plural(bucket.count)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </QueryState>
    </div>
  );
}
