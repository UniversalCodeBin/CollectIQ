import type { ReactNode } from "react";
import styles from "./EmptyState.module.css";

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className={styles.empty}>
      <h2 className={styles.title}>{title}</h2>
      {body && <p>{body}</p>}
      {action}
    </div>
  );
}
