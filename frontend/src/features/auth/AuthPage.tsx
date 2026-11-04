import { type ReactNode, useEffect, useRef } from "react";
import { OfflineBanner } from "../../components/ui/OfflineBanner";
import styles from "./AuthPage.module.css";

export { styles as authStyles };

/** The single-column frame for screens outside a workspace. Focus lands on the heading when it changes. */
export function AuthPage({ title, children }: { title: string; children: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [title]);
  return (
    <main className={styles.page}>
      <span className={styles.brand}>CollectIQ</span>
      <OfflineBanner />
      <div className={styles.card}>
        <h1 ref={heading} tabIndex={-1} className={styles.title}>
          {title}
        </h1>
        {children}
      </div>
    </main>
  );
}
