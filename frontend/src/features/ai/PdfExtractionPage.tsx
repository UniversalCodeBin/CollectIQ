import { type FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { AiMark } from "../../components/domain/AiMark";
import { Button } from "../../components/ui/Button";
import { Callout } from "../../components/ui/Callout";
import { TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { Page, PageHeader, Section } from "../../components/ui/Page";
import { ProblemMessage } from "../../components/ui/ProblemMessage";
import { ApiProblem, useApiMutation } from "../../lib/api";
import styles from "../settings/Settings.module.css";

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
  const upload = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/invoices/pdf" },
    { idempotent: true, secretBody: true },
  );
  const edit = useApiMutation(
    { method: "patch", path: "/api/v1/workspaces/{ws}/extractions/{extraction_id}" },
    { ifMatch: true },
  );
  const confirm = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/extractions/{extraction_id}/confirm" },
    { idempotent: true },
  );
  const [file, setFile] = useState<File | null>(null);
  const [local, setLocal] = useState<ApiProblem | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});

  const extraction = edit.status === "success" ? edit.data : upload.status === "success" ? upload.data : undefined;
  const done = confirm.status === "success" ? confirm.data : undefined;
  const unsaved = Object.keys(values).length > 0;
  const busy = edit.status === "pending" || confirm.status === "pending";

  // Once the server has the corrections, the fields show its copy; nothing is left unsaved.
  useEffect(() => {
    if (edit.status === "success") setValues({});
  }, [edit.status, edit.data]);

  function send(event: FormEvent) {
    event.preventDefault();
    if (upload.status === "pending") return;
    if (!file) {
      return setLocal(
        new ApiProblem({
          status: 400,
          code: "VALIDATION_FAILED",
          detail: "Choose a PDF file to upload.",
          correlationId: null,
          errors: [],
        }),
      );
    }
    setLocal(null);
    const body = new FormData();
    body.set("file", file);
    upload.submit({ path: { ws }, body });
  }

  function saveCorrections() {
    if (!extraction || !unsaved || busy) return;
    edit.submit({ path: { ws, extraction_id: extraction.id }, body: { fields: values }, version: extraction.version });
  }

  function confirmInvoice() {
    if (!extraction || unsaved || busy) return;
    confirm.submit({ path: { ws, extraction_id: extraction.id }, body: { decisions: { create_client: true } } });
  }

  const back = { to: `/w/${ws}/import/invoices`, label: "Import" };

  if (done) {
    return (
      <Page width="narrow">
        <PageHeader
          back={back}
          title="Invoice created"
          description="You confirmed the details, so the invoice now exists. It was not marked paid and nothing was sent."
        />
        {done.invoice_id && (
          <div className={styles.actions}>
            <Link to={`/w/${ws}/invoices/${done.invoice_id}/overview`}>Open the invoice</Link>
          </div>
        )}
      </Page>
    );
  }

  return (
    <Page width="narrow">
      <PageHeader
        back={back}
        title="Invoice from PDF"
        description="AI reads the PDF text and suggests the details. Nothing is added until you review and confirm. If AI is off or unavailable, use CSV import or add the invoice by hand."
      />
      {!extraction && (
        <Section title="Upload a PDF">
          <form className={styles.form} onSubmit={send} noValidate>
            <TextField
              label="Choose a PDF file"
              type="file"
              accept=".pdf,application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {local && <ProblemMessage problem={local} />}
            <MutationFeedback mutation={upload} />
            <div className={styles.actions}>
              <Button
                variant="primary"
                type="submit"
                busy={upload.status === "pending"}
                aria-disabled={upload.status === "pending" || undefined}
              >
                Read PDF
              </Button>
            </div>
          </form>
        </Section>
      )}
      {extraction && (
        <Section title="Check the details" aside={extraction.ai_derived ? <AiMark label="Read by AI" /> : undefined}>
          <Callout tone={extraction.status === "NEEDS_MANUAL_REVIEW" ? "info" : "paused"} role="status">
            {extraction.status === "NEEDS_MANUAL_REVIEW"
              ? "We could not read this PDF automatically. Fill in the details below, or use CSV import."
              : "AI suggested these details. They are unverified until you confirm them."}
          </Callout>
          {extraction.dropped_fields.length > 0 && (
            <p className={styles.muted}>
              Left blank because the document does not support them:{" "}
              {extraction.dropped_fields.map((f) => LABELS[f] ?? f).join(", ")}.
            </p>
          )}
          <div className={styles.form}>
            {Object.keys(LABELS).map((name) => {
              const shown = values[name] ?? extraction.fields[name] ?? "";
              // Marked only while the field still holds what the AI read; a person's correction is not an AI reading.
              const fromAi =
                values[name] === undefined &&
                extraction.ai_fields[name] === extraction.fields[name] &&
                name in extraction.ai_fields;
              return (
                <TextField
                  key={name}
                  label={LABELS[name] ?? name}
                  value={shown}
                  hint={fromAi ? <AiMark /> : undefined}
                  onChange={(e) => setValues({ ...values, [name]: e.target.value })}
                />
              );
            })}
            <MutationFeedback mutation={edit} />
            <MutationFeedback mutation={confirm} />
            {edit.status === "success" && !unsaved && (
              <p role="status" className={styles.done}>
                Corrections saved. Confirm when the details are right.
              </p>
            )}
            {unsaved && <p className={styles.muted}>Save your corrections before confirming.</p>}
            <div className={styles.actions}>
              <Button
                busy={edit.status === "pending"}
                aria-disabled={!unsaved || busy || undefined}
                onClick={saveCorrections}
              >
                Save corrections
              </Button>
              <Button
                variant="primary"
                busy={confirm.status === "pending"}
                aria-disabled={unsaved || busy || undefined}
                onClick={confirmInvoice}
              >
                Confirm and create invoice
              </Button>
            </div>
          </div>
        </Section>
      )}
    </Page>
  );
}
