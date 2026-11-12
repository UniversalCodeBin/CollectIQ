import type { ReactNode } from "react";
import styles from "./KeyValue.module.css";

/** A list of named facts. Terms and values stay direct children of the list, so each value is its term's next sibling. */
export function KeyValue({ children, layout = "rows" }: { children: ReactNode; layout?: "rows" | "stacked" }) {
  return (
    <dl className={styles.list} data-layout={layout}>
      {children}
    </dl>
  );
}

export function Pair({ term, children }: { term: ReactNode; children: ReactNode }) {
  return (
    <>
      <dt className={styles.term}>{term}</dt>
      <dd className={styles.value}>{children}</dd>
    </>
  );
}
