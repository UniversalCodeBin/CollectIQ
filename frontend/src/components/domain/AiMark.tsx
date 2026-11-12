import { Sparkles } from "lucide-react";
import styles from "./AiMark.module.css";

/**
 * Marks text that CollectIQ's AI wrote or read, so it is never mistaken for a recorded fact.
 * The words carry the meaning; the violet only supports them.
 */
export function AiMark({ label = "AI suggestion, not verified" }: { label?: string }) {
  return (
    <span className={styles.mark}>
      <Sparkles size={12} aria-hidden="true" className={styles.icon} />
      {label}
    </span>
  );
}
