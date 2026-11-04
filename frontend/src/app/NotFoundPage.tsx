import styles from "./NotFoundPage.module.css";

/** The one answer for an unknown path, a foreign workspace and a record the caller can't see. */
export function NotFoundPage() {
  return (
    <div data-page="not-found" className={styles.page}>
      <h1 className={styles.title}>We can't find that page</h1>
      <p>It may have moved, or you may not have access to it. Check the address, or ask your workspace owner.</p>
    </div>
  );
}
