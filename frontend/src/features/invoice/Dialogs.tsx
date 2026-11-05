import { useEffect, useRef, useState } from "react";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import styles from "./InvoicePage.module.css";
import type { InvoiceDetail } from "./types";

type Common = { open: boolean; onClose: () => void; workspace: string; onDone: () => void };

const COPY = {
  cancel: {
    title: "Cancel this invoice?",
    lead: "A cancelled invoice stops appearing in the queue and no reminders are prepared for it. Its history stays.",
    confirm: "Cancel this invoice",
    keep: "Keep invoice",
    needReason: "Say why before cancelling, so the history makes sense later.",
  },
  archive: {
    title: "Archive this invoice?",
    lead: "An archived invoice is hidden from your working lists. Its history stays.",
    confirm: "Archive this invoice",
    keep: "Keep invoice",
    needReason: "Say why before archiving, so the history makes sense later.",
  },
} as const;

/** Runs a mutation once and hands control back when it succeeds. */
function useOnSuccess(status: string, done: () => void) {
  const handled = useRef(false);
  useEffect(() => {
    if (status === "success" && !handled.current) {
      handled.current = true;
      done();
    }
    if (status !== "success") handled.current = false;
  }, [status, done]);
}

export function ActionDialog({ kind, invoiceId, ...common }: Common & { kind: "cancel" | "archive"; invoiceId: string }) {
  const copy = COPY[kind];
  const [reason, setReason] = useState("");
  const [missing, setMissing] = useState(false);
  const mutation = useApiMutation(
    kind === "cancel"
      ? { method: "post", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}/cancel" }
      : { method: "post", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}/archive" },
    { idempotent: true },
  );
  useOnSuccess(mutation.status, common.onDone);

  function confirm() {
    if (!reason.trim()) return setMissing(true);
    setMissing(false);
    mutation.submit({ path: { ws: common.workspace, invoice_id: invoiceId }, body: { reason: reason.trim() } });
  }
  return (
    <Dialog open={common.open} onClose={common.onClose} title={copy.title} destructive>
      <p>{copy.lead}</p>
      <TextField label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} error={missing ? copy.needReason : undefined} />
      <MutationFeedback mutation={mutation} />
      <div className={styles.dialogActions}>
        <Button variant="secondary" data-cancel onClick={common.onClose}>
          {copy.keep}
        </Button>
        <Button variant="danger" onClick={confirm}>
          {copy.confirm}
        </Button>
      </div>
    </Dialog>
  );
}

type Draft = { invoice_number: string; due_date: string; issue_date: string; payment_terms: string; po_number: string; project_ref: string; description: string };
const FIELDS: { key: keyof Draft; label: string; type?: string }[] = [
  { key: "invoice_number", label: "Invoice number" },
  { key: "issue_date", label: "Issue date", type: "date" },
  { key: "due_date", label: "Due date", type: "date" },
  { key: "payment_terms", label: "Payment terms" },
  { key: "po_number", label: "PO number" },
  { key: "project_ref", label: "Project" },
  { key: "description", label: "Description" },
];
const draftOf = (facts: InvoiceDetail["facts"]): Draft => ({
  invoice_number: facts.invoice_number,
  due_date: facts.due_date,
  issue_date: facts.issue_date ?? "",
  payment_terms: facts.payment_terms ?? "",
  po_number: facts.po_number ?? "",
  project_ref: facts.project_ref ?? "",
  description: facts.description ?? "",
});

export function CorrectDialog({ detail, ...common }: Common & { detail: InvoiceDetail }) {
  const start = draftOf(detail.facts);
  const [draft, setDraft] = useState<Draft>(start);
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const mutation = useApiMutation({ method: "patch", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}" }, { ifMatch: true });
  useOnSuccess(mutation.status, common.onDone);

  function save() {
    const changed = Object.fromEntries(FIELDS.filter(({ key }) => draft[key] !== start[key]).map(({ key }) => [key, draft[key]]));
    if (Object.keys(changed).length === 0) return setProblem("Change at least one detail first.");
    if (!reason.trim()) return setProblem("Say why you are correcting it, so the history makes sense later.");
    setProblem(null);
    mutation.submit({ path: { ws: common.workspace, invoice_id: detail.facts.id }, body: { ...changed, reason: reason.trim() }, version: detail.version });
  }
  return (
    <Dialog open={common.open} onClose={common.onClose} title="Correct invoice details">
      <p>Your correction is kept even if the same invoice is imported again.</p>
      {FIELDS.map(({ key, label, type }) => (
        <TextField key={key} label={label} type={type} value={draft[key]} onChange={(event) => setDraft((now) => ({ ...now, [key]: event.target.value }))} />
      ))}
      <TextField label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
      {problem && <p role="alert">{problem}</p>}
      <MutationFeedback mutation={mutation} />
      <div className={styles.dialogActions}>
        <Button variant="secondary" data-cancel onClick={common.onClose}>
          Close
        </Button>
        <Button variant="primary" onClick={save}>
          Save correction
        </Button>
      </div>
    </Dialog>
  );
}
