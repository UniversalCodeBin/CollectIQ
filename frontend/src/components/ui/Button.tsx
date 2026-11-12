import type { ButtonHTMLAttributes, Ref } from "react";
import { Link, type LinkProps } from "react-router";
import styles from "./Button.module.css";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "quiet";
  size?: "sm" | "md" | "lg";
  /** Stretch to the width of the container (auth forms, mobile action bars). */
  block?: boolean;
  /** Shows a small working indicator; the caller still disables the button while a request is pending. */
  busy?: boolean;
  ref?: Ref<HTMLButtonElement>;
};

export function Button({
  variant = "secondary",
  size = "md",
  block = false,
  busy = false,
  className,
  type = "button",
  children,
  ...props
}: Props) {
  return (
    <button
      type={type}
      data-variant={variant}
      data-size={size}
      data-block={block || undefined}
      data-busy={busy || undefined}
      aria-busy={busy || undefined}
      className={`${styles.button} ${className ?? ""}`}
      {...props}
    >
      {busy && <span className={styles.spinner} aria-hidden="true" />}
      {children}
    </button>
  );
}

type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> & {
  /** Required: the accessible name, also shown as the native tooltip. */
  label: string;
  ref?: Ref<HTMLButtonElement>;
};

/** A square, icon-only button. The label is the accessible name; nothing is icon-only without one. */
export function IconButton({ label, className, type = "button", title, ...props }: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={title ?? label}
      className={`${styles.icon} ${className ?? ""}`}
      {...props}
    />
  );
}

type ButtonLinkProps = LinkProps & {
  variant?: "primary" | "secondary" | "quiet";
  size?: "sm" | "md" | "lg";
  block?: boolean;
};

/** A link that moves to another screen but sits among buttons, so it borrows their look. It never performs an action. */
export function ButtonLink({ variant = "secondary", size = "md", block = false, className, ...props }: ButtonLinkProps) {
  return (
    <Link
      data-variant={variant}
      data-size={size}
      data-block={block || undefined}
      className={`${styles.button} ${styles.link} ${className ?? ""}`}
      {...props}
    />
  );
}
