import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { fieldError, SelectField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { ProblemMessage } from "../../components/ui/ProblemMessage";
import { ApiProblem, apiRequest, useApiMutation } from "../../lib/api";
import { formatDate, formatMinor } from "../../lib/format";
import { minorToText, parseMinor } from "./money";
import styles from "./Reconciliation.module.css";
import type { Unmatched } from "./types";

const METHODS = [
  ["BANK_TRANSFER", "Bank transfer"],
  ["UPI", "UPI"],
  ["CASH", "Cash"],
  ["PAYPAL_MANUAL", "PayPal"],
  ["OTHER", "Other"],
] as const;

const refuse = (field: string, message: string) =>
  new ApiProblem({ status: 400, code: "VALIDATION_FAILED", detail: "", correlationId: null, errors: [{ field, message }] });

function PaymentDialog({ workspace, onClose }: { workspace: string; onClose: () => void }) {
  const client = useQueryClient();
  const [method, setMethod] = useState("BANK_TRANSFER");
  const [currency, setCurrency] = useState("INR");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState("");
  const [reference, setReference] = useState("");
  const [payer, setPayer] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [local, setLocal] = useState<ApiProblem | null>(null);
  const [attachProblem, setAttachProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const minor = parseMinor(amount);
    if (minor === null) return setLocal(refuse("amount", "Enter the amount received, such as 1500.50."));
    if (!date) return setLocal(refuse("value_date", "Enter the date the money was received."));
    setLocal(null);
    setBusy(true);
    try {
      const made = await apiRequest(
        { method: "post", path: "/api/v1/workspaces/{ws}/payments" },
        {
          path: { ws: workspace },
          body: {
            method: method as never,
            amount: { amount_minor: minor, currency: currency as never },
            value_date: date,
            ...(reference ? { reference } : {}),
            ...(payer ? { payer } : {}),
          },
        },
        { idempotencyKey: crypto.randomUUID() },
      );
      if (file) {
        const body = new FormData();
        body.set("file", file);
        try {
          await apiRequest({ method: "post", path: "/api/v1/workspaces/{ws}/payments/{payment_id}/attachment" }, { path: { ws: workspace, payment_id: made.payment.id }, body } as never, {
            idempotencyKey: crypto.randomUUID(),
          });
        } catch {
          setAttachProblem("The payment was saved, but the proof could not be attached. Open the payment to try again.");
          void client.invalidateQueries({ queryKey: ["reconciliation"] });
          return;
        }
      }
      void client.invalidateQueries({ queryKey: ["reconciliation"] });
      onClose();
    } catch (error) {
      setLocal(error instanceof ApiProblem ? error : new ApiProblem({ status: 0, code: "NETWORK", detail: "", correlationId: null }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title="Record a payment">
      <form className={styles.form} onSubmit={(e) => void submit(e)} noValidate>
        <p className={styles.muted}>A payment you enter by hand is marked as lower assurance than a bank statement row.</p>
        <SelectField label="Method" value={method} onChange={(e) => setMethod(e.target.value)}>
          {METHODS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </SelectField>
        <SelectField label="Currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
          {["INR", "USD", "EUR", "GBP"].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </SelectField>
        <TextField label="Amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} error={fieldError(local, "amount")} />
        <TextField label="Date received" type="date" value={date} onChange={(e) => setDate(e.target.value)} error={fieldError(local, "value_date")} />
        <TextField label="Reference (optional)" value={reference} onChange={(e) => setReference(e.target.value)} />
        <TextField label="Paid by (optional)" value={payer} onChange={(e) => setPayer(e.target.value)} />
        <TextField
          label="Proof of payment (optional)"
          type="file"
          accept="image/png,image/jpeg,application/pdf"
          hint="PNG, JPEG or PDF, up to 5 MB."
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        {local && <ProblemMessage problem={local} />}
        {attachProblem && <p role="alert">{attachProblem}</p>}
        <div className={styles.actions}>
          <Button variant="primary" type="submit" aria-disabled={busy || undefined}>
            Save payment
          </Button>
          <Button data-cancel onClick={onClose}>
            {attachProblem ? "Close" : "Cancel"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}


function AllocateDialog({ workspace, item, onClose }: { workspace: string; item: Unmatched; onClose: () => void }) {
  const client = useQueryClient();
  const invoices = useQuery({
    queryKey: ["reconciliation", workspace, "open-invoices"],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/invoices" }, { path: { ws: workspace }, query: { limit: "100" } }),
  });
  const allocate = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/allocations" }, { idempotent: true });
  const open = (invoices.data?.items ?? []).filter((i) => i.currency === item.currency && i.outstanding_minor > 0);
  const [invoiceId, setInvoiceId] = useState("");
  const [amount, setAmount] = useState(minorToText(item.remaining_minor));
  const [local, setLocal] = useState<ApiProblem | null>(null);
  const invoice = open.find((i) => i.id === invoiceId);

  useEffect(() => {
    if (allocate.status === "success") {
      void client.invalidateQueries({ queryKey: ["reconciliation"] });
      onClose();
    }
  }, [allocate.status, client, onClose]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const minor = parseMinor(amount);
    if (!invoice) return setLocal(refuse("invoice_id", "Choose the invoice this payment belongs to."));
    if (minor === null) return setLocal(refuse("amount", "Enter the amount to apply, such as 1500.50."));
    if (minor > item.remaining_minor) return setLocal(refuse("amount", "That is more than is left on this payment."));
    if (minor > invoice.outstanding_minor) return setLocal(refuse("amount", "That is more than the invoice still owes."));
    setLocal(null);
    allocate.submit({
      path: { ws: workspace },
      body: { transaction_id: item.id, allocations: [{ invoice_id: invoice.id, amount_minor: minor }] } as never,
    });
  }

  return (
    <Dialog open onClose={onClose} title="Apply payment to an invoice">
      <form className={styles.form} onSubmit={submit} noValidate>
        <p className={styles.muted}>
          {formatMinor(item.remaining_minor, item.currency)} is unapplied. Nothing changes until you press Apply payment.
        </p>
        <SelectField label="Invoice" value={invoiceId} onChange={(e) => setInvoiceId(e.target.value)} error={fieldError(local, "invoice_id")}>
          <option value="">Choose an invoice</option>
          {open.map((i) => (
            <option key={i.id} value={i.id}>
              {`${i.invoice_number} · ${i.client_name} · ${formatMinor(i.outstanding_minor, i.currency)}`}
            </option>
          ))}
        </SelectField>
        <TextField label="Amount to apply" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} error={fieldError(local, "amount")} />
        {local && !fieldError(local, "amount") && !fieldError(local, "invoice_id") && <ProblemMessage problem={local} />}
        <MutationFeedback mutation={allocate} />
        <div className={styles.actions}>
          <Button variant="primary" type="submit" aria-disabled={allocate.status === "pending" || undefined}>
            Apply payment
          </Button>
          <Button data-cancel onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function UnmatchedTab({ workspace, items }: { workspace: string; items: Unmatched[] }) {
  const [recording, setRecording] = useState(false);
  const [applying, setApplying] = useState<Unmatched | null>(null);
  return (
    <>
      <div className={styles.toolbar}>
        <Button variant="primary" onClick={() => setRecording(true)}>
          Record a payment
        </Button>
      </div>
      {items.length === 0 ? (
        <EmptyState title="Every payment is matched" body="Payments with money not yet applied to an invoice show up here." />
      ) : (
        <ul className={styles.list}>
          {items.map((t) => (
            <li key={t.id} className={styles.card}>
              <div className={styles.row}>
                <p className={styles.amount}>{formatMinor(t.remaining_minor, t.currency)} unapplied</p>
                <p className={styles.muted}>
                  {t.payer_descriptor ?? "Unknown payer"} · {formatDate(t.value_date)}
                  {t.account_label ? ` · ${t.account_label}` : ""}
                </p>
                <Button onClick={() => setApplying(t)}>Apply to an invoice</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {applying && <AllocateDialog workspace={workspace} item={applying} onClose={() => setApplying(null)} />}
      {recording && <PaymentDialog workspace={workspace} onClose={() => setRecording(false)} />}
    </>
  );
}
