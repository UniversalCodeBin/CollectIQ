import { Check, Circle } from "lucide-react";
import { authStyles } from "./AuthPage";

/* Mirrors the server's rules (identity/passwords.py): 12–128 characters, not the email address.
   The server stays the authority; these checks only save a round trip. */
export const PASSWORD_MIN = 12;
export const PASSWORD_MAX = 128;

const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export type FieldErrors = Partial<Record<string, string>>;

export function checkEmail(value: string): string | undefined {
  if (!value.trim()) return "Enter your email address.";
  if (!EMAIL_SHAPE.test(value.trim())) return "Enter an email address in the format name@example.com.";
  return undefined;
}

export function checkNewPassword(value: string, email?: string): string | undefined {
  if (!value) return "Enter a password.";
  if (value.length < PASSWORD_MIN) return `Use at least ${PASSWORD_MIN} characters.`;
  if (value.length > PASSWORD_MAX) return `Use no more than ${PASSWORD_MAX} characters.`;
  if (email && value.trim().toLowerCase() === email.trim().toLowerCase())
    return "Use a password that is different from your email address.";
  return undefined;
}

/** For setErrors: drops one field's message once the person edits that field. */
export function clearError(name: string) {
  return (errors: FieldErrors): FieldErrors => (errors[name] ? { ...errors, [name]: undefined } : errors);
}

/** Puts focus on the first field with a problem so a keyboard or screen reader user lands on it. */
export function focusFirstError(form: HTMLFormElement, errors: FieldErrors) {
  const first = Object.keys(errors).find((name) => errors[name]);
  if (first) form.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
}

/** The password rules, ticked off as the person types. Text carries the state, not colour alone. */
export function PasswordRules({ password, email }: { password: string; email?: string }) {
  const rules = [
    {
      text: `At least ${PASSWORD_MIN} characters`,
      met: password.length >= PASSWORD_MIN,
    },
    {
      text: `No more than ${PASSWORD_MAX} characters`,
      met: password.length > 0 && password.length <= PASSWORD_MAX,
    },
    ...(email !== undefined
      ? [
          {
            text: "Different from your email address",
            met: password.length > 0 && password.trim().toLowerCase() !== email.trim().toLowerCase(),
          },
        ]
      : []),
  ];
  return (
    <ul className={authStyles.rules} aria-label="Password rules">
      {rules.map((rule) => (
        <li key={rule.text} data-met={rule.met ? "" : undefined}>
          {rule.met ? <Check size={14} aria-hidden="true" /> : <Circle size={14} aria-hidden="true" />}
          {rule.text}
          <span className="visually-hidden">{rule.met ? " (met)" : " (not yet met)"}</span>
        </li>
      ))}
    </ul>
  );
}
