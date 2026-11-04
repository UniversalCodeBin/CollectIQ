import { type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, useId } from "react";
import type { ApiProblem } from "../../lib/api";
import { plainProblem } from "../../lib/api";
import styles from "./Field.module.css";

type Common = { label: string; hint?: string; error?: string | undefined };

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

function Parts({ common, ids, children }: { common: Common; ids: ReturnType<typeof useDescribedField>; children: ReactNode }) {
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

export function TextField({ label, hint, error, ...input }: Common & InputHTMLAttributes<HTMLInputElement>) {
  const common = { label, hint, error };
  const ids = useDescribedField(common);
  return (
    <Parts common={common} ids={ids}>
      <input {...input} {...ids.control} />
    </Parts>
  );
}

export function SelectField({ label, hint, error, children, ...select }: Common & SelectHTMLAttributes<HTMLSelectElement>) {
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

/** The server's message for one field, so it can sit beside that field as well as in the summary. */
export function fieldError(problem: ApiProblem | null, field: string): string | undefined {
  return problem ? plainProblem(problem).fields.find((error) => error.field === field)?.message : undefined;
}
