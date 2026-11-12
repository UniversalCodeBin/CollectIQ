import { CircleAlert, Info, PauseCircle, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import styles from "./Callout.module.css";

const ICONS = { info: Info, paused: PauseCircle, error: CircleAlert, safe: ShieldCheck } as const;

type Props = {
  /** info: context. paused: something is on hold and why. error: something needs fixing. safe: a protection that is in force. */
  tone?: keyof typeof ICONS;
  title?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  /** "status" announces changes politely; leave unset for content that is there from the start. */
  role?: "status" | "alert";
};

/** A notice inside the page. The icon and the words carry the meaning; the tint only supports them. */
export function Callout({ tone = "info", title, children, actions, role }: Props) {
  const Icon = ICONS[tone];
  return (
    <div className={styles.callout} data-tone={tone} role={role}>
      <Icon size={18} aria-hidden="true" className={styles.icon} />
      <div className={styles.text}>
        {title && <p className={styles.title}>{title}</p>}
        {children && <div className={styles.body}>{children}</div>}
      </div>
      {actions && <div className={styles.actions}>{actions}</div>}
    </div>
  );
}
