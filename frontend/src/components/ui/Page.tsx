import { ChevronLeft } from "lucide-react";
import { useId, type ReactNode } from "react";
import { Link } from "react-router";
import styles from "./Page.module.css";

/** The frame every workspace screen sits in: one column on the paper background, capped so lines stay readable. */
export function Page({ width = "default", children }: { width?: "default" | "narrow"; children: ReactNode }) {
  return (
    <div className={styles.page} data-width={width}>
      {children}
    </div>
  );
}

type HeaderProps = {
  title: ReactNode;
  /** One plain sentence saying what the screen is for. */
  description?: ReactNode;
  back?: { to: string; label: string };
  /** Chips or a date that qualify the title, shown under it. */
  meta?: ReactNode;
  /** At most one primary action; anything else is secondary or quiet. */
  actions?: ReactNode;
};

/** The only h1 on a screen. */
export function PageHeader({ title, description, back, meta, actions }: HeaderProps) {
  return (
    <header className={styles.header}>
      {back && (
        <Link className={styles.back} to={back.to}>
          <ChevronLeft size={16} aria-hidden="true" />
          {back.label}
        </Link>
      )}
      <div className={styles.headerRow}>
        <div className={styles.headerText}>
          <h1 className={styles.title}>{title}</h1>
          {description && <p className={styles.description}>{description}</p>}
          {meta && <div className={styles.meta}>{meta}</div>}
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>
    </header>
  );
}

type SectionProps = {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  /** Sits beside the title: a count or a status chip. */
  aside?: ReactNode;
  children: ReactNode;
  /** h2 by default; h3 inside another section or the evidence rail. */
  level?: 2 | 3;
  id?: string;
};

/** A titled region separated from its neighbours by space and a hairline, not by a box. */
export function Section({ title, description, actions, aside, children, level = 2, id }: SectionProps) {
  const generated = useId();
  const headingId = id ?? generated;
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <section aria-labelledby={headingId} className={styles.section} data-level={level}>
      <div className={styles.sectionHead}>
        <div className={styles.sectionText}>
          <div className={styles.sectionTitleRow}>
            <Heading id={headingId} className={styles.sectionTitle}>
              {title}
            </Heading>
            {aside}
          </div>
          {description && <p className={styles.description}>{description}</p>}
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>
      {children}
    </section>
  );
}

/** The principal data block of a screen: a white sheet under a ruled ink line, like the head of a ledger page. */
export function Ledger({ children, flush = false }: { children: ReactNode; flush?: boolean }) {
  return (
    <div className={styles.ledger} data-flush={flush || undefined}>
      {children}
    </div>
  );
}

/** Filters and view controls that sit above a ledger. */
export function Toolbar({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div className={styles.toolbar} role={label ? "group" : undefined} aria-label={label}>
      {children}
    </div>
  );
}

/** Record on the left, its evidence and reasoning in the margin on the right; the margin drops below on narrow screens. */
export function Split({ children, rail }: { children: ReactNode; rail: ReactNode }) {
  return (
    <div className={styles.split}>
      <div className={styles.splitMain}>{children}</div>
      <div className={styles.splitRail}>{rail}</div>
    </div>
  );
}
