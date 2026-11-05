import { type FormEvent, useEffect, useRef, useState } from "react";
import { Button } from "../../components/ui/Button";
import { SelectField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import styles from "./ImportPage.module.css";
import type { ImportBatch } from "./types";

const REQUIRED = [
  ["invoice_number", "Invoice number"],
  ["client_name", "Client name"],
  ["due_date", "Due date"],
  ["currency", "Currency"],
  ["total", "Total"],
] as const;
const OPTIONAL = [
  ["issue_date", "Issue date"],
  ["subtotal", "Subtotal"],
  ["tax", "Tax"],
  ["payment_terms", "Payment terms"],
  ["payment_reference", "Payment reference"],
  ["client_email", "Client email"],
  ["po_number", "PO number"],
  ["project_ref", "Project reference"],
  ["description", "Description"],
  ["external_id", "External ID"],
] as const;

type Props = { workspace: string; batch: ImportBatch; onMapped: (batch: ImportBatch) => void };

export function MappingStep({ workspace, batch, onMapped }: Props) {
  const save = useApiMutation({ method: "put", path: "/api/v1/workspaces/{ws}/imports/{import_id}/mapping" }, { idempotent: false });
  const [mapping, setMapping] = useState<Record<string, string>>(() => ({ ...batch.suggested_mapping, ...batch.mapping }));
  const [dateFormat, setDateFormat] = useState(batch.date_format ?? batch.date_format_options[0] ?? "");
  const [missing, setMissing] = useState<string[]>([]);
  const handed = useRef<unknown>(null);
  const saved = save.status === "success" ? save.data : undefined;

  useEffect(() => {
    if (saved && handed.current !== saved) {
      handed.current = saved;
      onMapped(saved);
    }
  }, [saved, onMapped]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const absent = REQUIRED.filter(([target]) => !mapping[target]).map(([target]) => target);
    setMissing(absent);
    if (absent.length) return;
    const chosen = Object.fromEntries(Object.entries(mapping).filter(([, header]) => header));
    save.submit({ path: { ws: workspace, import_id: batch.id }, body: { mapping: chosen, date_format: dateFormat || null } });
  }

  function field([target, label]: readonly [string, string], required: boolean) {
    return (
      <SelectField
        key={target}
        label={label}
        value={mapping[target] ?? ""}
        error={missing.includes(target) ? `Choose the column that holds the ${label.toLowerCase()}.` : undefined}
        onChange={(event) => setMapping((current) => ({ ...current, [target]: event.target.value }))}
      >
        <option value="">{required ? "Choose a column" : "Not in my file"}</option>
        {batch.headers.map((header) => (
          <option key={header} value={header}>
            {header}
          </option>
        ))}
      </SelectField>
    );
  }

  return (
    <form onSubmit={submit} className={styles.card} noValidate>
      <h2 className={styles.heading}>Match your columns</h2>
      <p className={styles.lead}>
        <span>{batch.file_name}</span> has {batch.counts.total_rows ?? 0} rows. Tell us which column holds each detail.
      </p>
      <div className={styles.grid}>
        {REQUIRED.map((entry) => field(entry, true))}
        <SelectField label="Date format" value={dateFormat} onChange={(event) => setDateFormat(event.target.value)}>
          {batch.date_format_options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </SelectField>
      </div>
      <details className={styles.more}>
        <summary>Other details you can bring in</summary>
        <div className={styles.grid}>{OPTIONAL.map((entry) => field(entry, false))}</div>
      </details>
      <MutationFeedback mutation={save} />
      <div>
        <Button variant="primary" type="submit" aria-disabled={save.status === "pending" || undefined}>
          Continue to preview
        </Button>
      </div>
    </form>
  );
}
