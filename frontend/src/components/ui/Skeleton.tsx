import styles from "./Skeleton.module.css";

/** Placeholder rows shown while a list loads. Decorative: the loading message beside it is what gets announced. */
export function Skeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className={styles.skeleton} aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className={styles.row}>
          <span className={styles.bar} data-width="wide" />
          <span className={styles.bar} data-width="mid" />
          <span className={styles.bar} data-width="short" />
        </div>
      ))}
    </div>
  );
}
