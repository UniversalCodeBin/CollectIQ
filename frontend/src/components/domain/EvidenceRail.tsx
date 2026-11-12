import { useId, type ReactNode } from "react";
import styles from "./EvidenceRail.module.css";

/**
 * The margin beside a record: what the record rests on and why the system is treating it the way it is.
 * It sits to the right on wide screens and below the record on narrow ones.
 */
export function EvidenceRail({ title = "Evidence & reasoning", children }: { title?: string; children: ReactNode }) {
  const headingId = useId();
  return (
    <aside className={styles.rail} aria-labelledby={headingId} id="evidence">
      <h2 id={headingId} className={styles.title}>
        {title}
      </h2>
      {children}
    </aside>
  );
}

export function RailBlock({ title, aside, children }: { title: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className={styles.block}>
      <div className={styles.blockHead}>
        <h3 className={styles.blockTitle}>{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}
