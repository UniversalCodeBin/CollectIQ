import styles from "./DashboardPage.module.css";

const STEPS = ["Import your invoices", "Add payment evidence", "Set your follow-up cadence", "Review the queue"];

export function DashboardPage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Dashboard</h1>
      <section aria-labelledby="getting-started" className={styles.card}>
        <h2 id="getting-started" className={styles.heading}>
          Getting started
        </h2>
        <ul className={styles.steps}>
          {STEPS.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
