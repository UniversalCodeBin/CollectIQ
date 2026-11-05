import { Link, useParams } from "react-router";
import styles from "./DashboardPage.module.css";

// Steps whose screen exists link to it; the rest are plain text until their task lands.
const STEPS: { label: string; to?: string }[] = [
  { label: "Import your invoices", to: "import/invoices" },
  { label: "Add payment evidence" },
  { label: "Set your follow-up cadence" },
  { label: "Review the queue" },
];

export function DashboardPage() {
  const { ws = "" } = useParams();
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Dashboard</h1>
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
    </div>
  );
}
