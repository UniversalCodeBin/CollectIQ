import styles from "./BrandMark.module.css";

/** Two slanted ledger bars: the product mark. Decorative; the wordmark beside it carries the name. */
export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false" className={styles.mark}>
      <rect x="2" y="2" width="28" height="28" rx="7" className={styles.tile} />
      <path d="M10.5 23 L15 9 h3.5 L14 23 Z" className={styles.bar} />
      <path d="M17 23 L21.5 9 H25 L20.5 23 Z" className={styles.accent} />
    </svg>
  );
}

/** The mark and the two-line wordmark used in the app bar and on the sign-in screens. */
export function BrandLockup({ tone = "default" }: { tone?: "default" | "inverse" }) {
  return (
    <span className={styles.lockup} data-tone={tone}>
      <BrandMark />
      <span className={styles.words}>
        <span className={styles.name}>CollectIQ</span>
        <span className={styles.tag}>Receivables OS</span>
      </span>
    </span>
  );
}
