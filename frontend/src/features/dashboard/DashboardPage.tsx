import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { QueryState } from "../../components/ui/QueryState";
import { SampleDataBanner } from "../../components/ui/SampleDataBanner";
import { apiRequest } from "../../lib/api";
import { formatMinor } from "../../lib/format";
import styles from "./DashboardPage.module.css";

// Steps whose screen exists link to it; the rest are plain text until their task lands.
const STEPS: { label: string; to?: string }[] = [
  { label: "Import your invoices", to: "import/invoices" },
  { label: "Add payment evidence" },
  { label: "Set your follow-up cadence" },
  { label: "Review the queue", to: "receivables" },
];

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
          <section aria-labelledby="getting-started" className={styles.card}>
            <h2 id="getting-started" className={styles.heading}>
              Getting started
            </h2>
            <ul className={styles.steps}>
              {STEPS.map((step) => (
                <li key={step.label}>{step.to ? <Link to={`/w/${ws}/${step.to}`}>{step.label}</Link> : step.label}</li>
              ))}
            </ul>
          </section>
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
