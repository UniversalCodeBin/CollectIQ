import { type FormEvent, useState } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { ProblemMessage } from "../../components/ui/ProblemMessage";
import { ApiProblem, useApiMutation } from "../../lib/api";
import styles from "../automation/Automation.module.css";

const LABELS: Record<string, string> = {
  invoice_number: "Invoice number",
  client_name: "Client",
  issue_date: "Issue date (YYYY-MM-DD)",
  due_date: "Due date (YYYY-MM-DD)",
  currency: "Currency",
  total: "Total",
};

/** Flagged PDF extraction (E038-E041): upload, review the AI's reading as unverified, then confirm. */
export function PdfExtractionPage() {
  const { ws = "" } = useParams();
  const upload = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/invoices/pdf" }, { idempotent: true, secretBody: true });
  const edit = useApiMutation({ method: "patch", path: "/api/v1/workspaces/{ws}/extractions/{extraction_id}" }, { ifMatch: true });
  const confirm = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/extractions/{extraction_id}/confirm" }, { idempotent: true });
  const [file, setFile] = useState<File | null>(null);
  const [local, setLocal] = useState<ApiProblem | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});

  const current = edit.status === "success" ? edit.data : upload.status === "success" ? upload.data : undefined;
  const extraction = current;
  const done = confirm.status === "success" ? confirm.data : undefined;

  function send(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      return setLocal(new ApiProblem({ status: 400, code: "VALIDATION_FAILED", detail: "Choose a PDF file to upload.", correlationId: null, errors: [] }));
    }
    setLocal(null);
    const body = new FormData();
    body.set("file", file);
    upload.submit({ path: { ws }, body });
  }

  if (done) {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>Invoice created</h1>
        <p className={styles.muted}>You confirmed the details, so the invoice now exists. It was not marked paid and nothing was sent.</p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Invoice from PDF</h1>
      {!extraction && (
        <form className={styles.card} onSubmit={send} noValidate>
          <p className={styles.muted}>
            AI reads the PDF text and suggests the details. Nothing is added until you review and confirm. If AI is off or unavailable, use CSV import or add the invoice by hand.
          </p>
          <TextField label="Choose a PDF file" type="file" accept=".pdf,application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          {local && <ProblemMessage problem={local} />}
          <MutationFeedback mutation={upload} />
          <div className={styles.actions}>
            <Button variant="primary" type="submit" aria-disabled={upload.status === "pending" || undefined}>
              Read PDF
            </Button>
          </div>
        </form>
      )}
      {extraction && (
        <div className={styles.card}>
          <p role="status">
            {extraction.status === "NEEDS_MANUAL_REVIEW"
              ? "We could not read this PDF automatically. Fill in the details below, or use CSV import."
              : "AI suggested these details. They are unverified until you confirm them."}
          </p>
          {extraction.dropped_fields.length > 0 && (
            <p className={styles.muted}>Left blank because the document does not support them: {extraction.dropped_fields.map((f) => LABELS[f] ?? f).join(", ")}.</p>
          )}
          {Object.keys(LABELS).map((name) => (
            <TextField
              key={name}
              label={LABELS[name] ?? name}
              value={values[name] ?? extraction.fields[name] ?? ""}
              onChange={(e) => setValues({ ...values, [name]: e.target.value })}
            />
          ))}
          <MutationFeedback mutation={edit} />
          <MutationFeedback mutation={confirm} />
          <div className={styles.actions}>
            <Button
              onClick={() => edit.submit({ path: { ws, extraction_id: extraction.id }, body: { fields: values }, version: extraction.version })}
              aria-disabled={Object.keys(values).length === 0 || undefined}
            >
              Save corrections
            </Button>
            <Button
              variant="primary"
              onClick={() => confirm.submit({ path: { ws, extraction_id: extraction.id }, body: { decisions: { create_client: true } } })}
              aria-disabled={Object.keys(values).length > 0 || confirm.status === "pending" || undefined}
            >
              Confirm and create invoice
            </Button>
          </div>
          {Object.keys(values).length > 0 && <p className={styles.muted}>Save your corrections before confirming.</p>}
        </div>
      )}
    </div>
  );
}
