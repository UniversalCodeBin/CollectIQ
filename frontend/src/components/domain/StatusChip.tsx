import { type StatusKind, statusOf } from "../../lib/statusMap";
import styles from "./StatusChip.module.css";

type Props = {
  kind: StatusKind;
  value: string;
  qualifier?: string;
  detail?: string;
  size?: "sm" | "md";
};

/** Icon, words and shape carry the meaning, so nothing depends on colour alone. */
export function StatusChip({ kind, value, qualifier, detail, size = "md" }: Props) {
  const { label, icon: Icon, tone, shape } = statusOf(kind, value);
  return (
    <span className={styles.chip} data-shape={shape} data-tone={tone} data-size={size}>
      <Icon size={size === "sm" ? 12 : 16} aria-hidden="true" className={styles.icon} />
      <span>
        {label}
        {qualifier && <span> · {qualifier}</span>}
        {detail && <span className={styles.detail}> {detail}</span>}
      </span>
    </span>
  );
}
