import { Button, ButtonLink } from "../../components/ui/Button";
import styles from "./ImportPage.module.css";
import type { ImportBatch } from "./types";

const LINES: [string, string, string][] = [
  ["created", "invoice created", "invoices created"],
  ["updated", "invoice updated", "invoices updated"],
  ["merged", "invoice merged", "invoices merged"],
  ["unchanged", "invoice already up to date", "invoices already up to date"],
  ["ignored", "row ignored", "rows ignored"],
  ["skipped_invalid", "invalid row skipped", "invalid rows skipped"],
];

export function DoneStep({
  batch,
  workspace,
  onAnother,
}: {
  batch: ImportBatch;
  workspace: string;
  onAnother: () => void;
}) {
  return (
    <section className={styles.card} aria-labelledby="done-title">
      <h2 id="done-title" className={styles.heading}>
        Import finished
      </h2>
      <ul className={styles.counts}>
        {LINES.map(([key, one, many]) => {
          const count = batch.counts[key] ?? 0;
          return count > 0 ? <li key={key}>{`${count} ${count === 1 ? one : many}`}</li> : null;
        })}
      </ul>
      <div className={styles.actions}>
        <ButtonLink to={`/w/${workspace}/receivables`} variant="primary">
          See your receivables
        </ButtonLink>
        <ButtonLink to={`/w/${workspace}/dashboard`}>Go to the dashboard</ButtonLink>
        <Button variant="quiet" onClick={onAnother}>
          Import another file
        </Button>
      </div>
    </section>
  );
}
