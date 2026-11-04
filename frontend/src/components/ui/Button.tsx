import type { ButtonHTMLAttributes, Ref } from "react";
import styles from "./Button.module.css";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "quiet";
  ref?: Ref<HTMLButtonElement>;
};

export function Button({ variant = "secondary", className, type = "button", ...props }: Props) {
  return <button type={type} data-variant={variant} className={`${styles.button} ${className ?? ""}`} {...props} />;
}
