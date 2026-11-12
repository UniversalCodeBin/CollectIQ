import { ChartColumn, Layers, ShieldCheck, Sparkles } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";
import { BrandLockup } from "../../components/ui/BrandMark";
import { OfflineBanner } from "../../components/ui/OfflineBanner";
import styles from "./AuthPage.module.css";

export { styles as authStyles };

/* Each line describes something the product does today; none of it is a promise about outcomes. */
const BENEFITS = [
  {
    icon: ChartColumn,
    text: "See what is outstanding, overdue and in dispute",
    tone: "primary",
  },
  {
    icon: Layers,
    text: "Match payments to invoices, confirming each one yourself",
    tone: "primary",
  },
  {
    icon: Sparkles,
    text: "Draft follow-ups with AI; nothing goes out until you approve it",
    tone: "ai",
  },
  {
    icon: ShieldCheck,
    text: "Keep a history of who did what, and when",
    tone: "primary",
  },
] as const;

/**
 * The frame for screens outside a workspace: a short description of the product beside the form
 * on wide screens, the form alone on narrow ones. Focus lands on the heading when it changes.
 */
export function AuthPage({ title, lead, children }: { title: string; lead?: ReactNode; children: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [title]);
  return (
    <div className={styles.page}>
      <OfflineBanner />
      <main className={styles.frame}>
        <div className={styles.intro}>
          <p className={styles.pitch}>Receivables Operations Copilot</p>
          <p className={styles.pitchLead}>
            Turn invoices, payments and customer replies into a clear list of what to follow up next. It works alongside
            your accounting system and does not replace it.
          </p>
          <ul className={styles.benefits}>
            {BENEFITS.map(({ icon: Icon, text, tone }) => (
              <li key={text}>
                <span className={styles.benefitIcon} data-tone={tone}>
                  <Icon size={18} aria-hidden="true" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>
        <div className={styles.card}>
          <div className={styles.head}>
            <BrandLockup />
            <h1 ref={heading} tabIndex={-1} className={styles.title}>
              {title}
            </h1>
            {lead ? <p className={styles.lead}>{lead}</p> : null}
          </div>
          {children}
        </div>
      </main>
      <svg
        className={styles.waves}
        viewBox="0 0 1440 220"
        preserveAspectRatio="none"
        aria-hidden="true"
        focusable="false"
      >
        <path className={styles.waveBack} d="M0 120 C 240 40 420 60 640 110 S 1080 190 1440 80 V220 H0 Z" />
        <path className={styles.waveMid} d="M0 160 C 260 100 480 120 720 160 S 1160 210 1440 140 V220 H0 Z" />
        <path className={styles.waveFront} d="M0 196 C 300 160 560 170 820 196 S 1240 220 1440 190 V220 H0 Z" />
      </svg>
    </div>
  );
}

/** A divider row under the form: one question, one link. */
export function AuthSwitch({ children }: { children: ReactNode }) {
  return <p className={styles.switch}>{children}</p>;
}
