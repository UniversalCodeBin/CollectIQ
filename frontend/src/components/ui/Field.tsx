import { Eye, EyeOff, type LucideIcon } from "lucide-react";
import {
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useId,
  useState,
} from "react";
import type { ApiProblem } from "../../lib/api";
import { plainProblem } from "../../lib/api";
import styles from "./Field.module.css";

type Common = { label: string; hint?: ReactNode; error?: string | undefined };

function useDescribedField({ hint, error }: Common) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return {
    id,
    hintId,
    errorId,
    control: {
      id,
      className: styles.control,
      "aria-invalid": error ? (true as const) : undefined,
      "aria-describedby": [hintId, errorId].filter(Boolean).join(" ") || undefined,
    },
  };
}

function Parts({
  common,
  ids,
  children,
}: {
  common: Common;
  ids: ReturnType<typeof useDescribedField>;
  children: ReactNode;
}) {
  return (
    <div className={styles.field}>
      <label htmlFor={ids.id} className={styles.label}>
        {common.label}
      </label>
      {children}
      {common.hint && (
        <span id={ids.hintId} className={styles.hint}>
          {common.hint}
        </span>
      )}
      {common.error && (
        <span id={ids.errorId} className={styles.error}>
          {common.error}
        </span>
      )}
    </div>
  );
}

type TextProps = Common & InputHTMLAttributes<HTMLInputElement> & { icon?: LucideIcon };

export function TextField({ label, hint, error, icon: Icon, ...input }: TextProps) {
  const common = { label, hint, error };
  const ids = useDescribedField(common);
  return (
    <Parts common={common} ids={ids}>
      {Icon ? (
        <span className={styles.adorned}>
          <Icon size={18} aria-hidden="true" className={styles.lead} />
          <input {...input} {...ids.control} data-lead="" />
        </span>
      ) : (
        <input {...input} {...ids.control} />
      )}
    </Parts>
  );
}

/** A password input with a show/hide toggle. The value never leaves component state. */
export function PasswordField({ label, hint, error, icon: Icon, ...input }: Omit<TextProps, "type">) {
  const [visible, setVisible] = useState(false);
  const common = { label, hint, error };
  const ids = useDescribedField(common);
  return (
    <Parts common={common} ids={ids}>
      <span className={styles.adorned}>
        {Icon && <Icon size={18} aria-hidden="true" className={styles.lead} />}
        <input
          {...input}
          {...ids.control}
          type={visible ? "text" : "password"}
          data-lead={Icon ? "" : undefined}
          data-trail=""
          spellCheck={false}
          autoCapitalize="off"
        />
        <button
          type="button"
          className={styles.reveal}
          /* A toggle keeps one name; aria-pressed carries the state (changing both double-announces). */
          aria-label={`Show ${label.toLowerCase()}`}
          aria-pressed={visible}
          aria-controls={ids.id}
          onClick={() => setVisible((shown) => !shown)}
        >
          {visible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
        </button>
      </span>
    </Parts>
  );
}

export function SelectField({
  label,
  hint,
  error,
  children,
  ...select
}: Common & SelectHTMLAttributes<HTMLSelectElement>) {
  const common = { label, hint, error };
  const ids = useDescribedField(common);
  return (
    <Parts common={common} ids={ids}>
      <select {...select} {...ids.control}>
        {children}
      </select>
    </Parts>
  );
}

/** A multi-line text field with the same label, hint and error wiring as TextField. */
export function TextAreaField({
  label,
  hint,
  error,
  rows = 5,
  ...area
}: Common & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const common = { label, hint, error };
  const ids = useDescribedField(common);
  return (
    <Parts common={common} ids={ids}>
      <textarea rows={rows} {...area} {...ids.control} data-multiline="" />
    </Parts>
  );
}

/** A checkbox whose label is the click target; a hint or error is announced with it. */
export function Checkbox({
  label,
  hint,
  error,
  ...input
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label: ReactNode; hint?: ReactNode; error?: string }) {
  const id = useId();
  const described = [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className={styles.check}>
      <input {...input} id={id} type="checkbox" aria-invalid={error ? true : undefined} aria-describedby={described} />
      <label htmlFor={id}>{label}</label>
      {hint && (
        <span id={`${id}-hint`} className={styles.hint}>
          {hint}
        </span>
      )}
      {error && (
        <span id={`${id}-error`} className={styles.error}>
          {error}
        </span>
      )}
    </div>
  );
}

/** The server's message for one field, so it can sit beside that field as well as in the summary. */
export function fieldError(problem: ApiProblem | null, field: string): string | undefined {
  return problem ? plainProblem(problem).fields.find((error) => error.field === field)?.message : undefined;
}
