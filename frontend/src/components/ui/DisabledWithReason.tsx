import { useId } from "react";
import { Button } from "./Button";
import styles from "./DisabledWithReason.module.css";

export type AllowedAction = { allowed: boolean; reason: string | null };

type Props = {
  action: AllowedAction;
  label: string;
  onClick: () => void;
  variant?: "primary" | "secondary" | "danger";
};

/** Renders the server's allowed_actions verdict. A refused action stays focusable and says why. */
export function DisabledWithReason({ action, label, onClick, variant = "primary" }: Props) {
  const id = useId();
  if (action.allowed) {
    return (
      <Button variant={variant} onClick={onClick}>
        {label}
      </Button>
    );
  }
  return (
    <span className={styles.wrap}>
      <Button variant={variant} aria-disabled="true" aria-describedby={id}>
        {label}
      </Button>
      <span id={id} className={styles.reason}>
        {action.reason ?? "This isn't available right now."}
      </span>
    </span>
  );
}
