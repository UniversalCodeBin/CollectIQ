import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { fieldError, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { ProblemMessage } from "../../components/ui/ProblemMessage";
import { ApiProblem, apiRequest, useApiMutation } from "../../lib/api";
import { formatDate, formatMinor } from "../../lib/format";
import styles from "./Reconciliation.module.css";
import type { Payment } from "./types";

function ReverseDialog({ workspace, allocationId, onClose }: { workspace: string; allocationId: string; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const [local, setLocal] = useState<ApiProblem | null>(null);
  const client = useQueryClient();
  const reverse = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/allocations/{allocation_id}/reverse" }, { idempotent: true });
  useEffect(() => {
    if (reverse.status === "success") {
      void client.invalidateQueries({ queryKey: ["reconciliation"] });
      onClose();
    }
  }, [reverse.status, client, onClose]);
  function submit() {
    if (!reason.trim()) {
      return setLocal(new ApiProblem({ status: 400, code: "VALIDATION_FAILED", detail: "", correlationId: null, errors: [{ field: "reason", message: "Say why this allocation is being reversed." }] }));
    }
    setLocal(null);
    reverse.submit({ path: { ws: workspace, allocation_id: allocationId }, body: { reason: reason.trim() } });
  }
  return (
    <Dialog open onClose={onClose} title="Reverse allocation">
      <div className={styles.form}>
        <p className={styles.muted}>The allocation stays in the history; a reversal is recorded beside it and the invoice balance is restored.</p>
        <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} error={fieldError(local, "reason")} />
        {local && <ProblemMessage problem={local} />}
        <MutationFeedback mutation={reverse} />
        <div className={styles.actions}>
          <Button variant="danger" aria-disabled={reverse.status === "pending" || undefined} onClick={submit}>
            Reverse allocation
          </Button>
          <Button data-cancel onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function Details({ workspace, payment }: { workspace: string; payment: Payment }) {
  const [reversing, setReversing] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: ["reconciliation", workspace, "payment", payment.id],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/payments/{payment_id}" }, { path: { ws: workspace, payment_id: payment.id } }),
  });
  if (detail.isPending) return <p role="status">Loading history…</p>;
  if (detail.isError) return <p role="alert">The history could not be loaded.</p>;
  const reversed = new Set(detail.data.allocations.flatMap((a) => (a.reverses_allocation_id ? [a.reverses_allocation_id] : [])));
  return (
    <>
      <ul className={styles.history} aria-label="Allocation history">
        {detail.data.allocations.map((a) => (
          <li key={a.id} className={a.kind === "REVERSAL" ? styles.reversal : undefined}>
            <span>{a.kind === "REVERSAL" ? "Reversal" : "Allocated"}</span> <strong>{a.invoice_number ?? a.invoice_id}</strong>{" "}
            {formatMinor(Math.abs(a.amount_minor), payment.currency)} · {formatDate(a.created_at)}
            {a.note ? ` · ${a.note}` : ""}
            {a.kind === "ALLOCATION" && !reversed.has(a.id) && (
              <>
                {" "}
                <Button variant="quiet" onClick={() => setReversing(a.id)}>
                  Reverse allocation
                </Button>
              </>
            )}
          </li>
        ))}
      </ul>
      {detail.data.attachment && <p className={styles.muted}>Proof attached: {detail.data.attachment.file_name}</p>}
      {reversing && <ReverseDialog workspace={workspace} allocationId={reversing} onClose={() => setReversing(null)} />}
    </>
  );
}

export function ConfirmedTab({ workspace, items }: { workspace: string; items: Payment[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (items.length === 0) return <EmptyState title="No confirmed payments yet" body="Payments you confirm against an invoice appear here with their history." />;
  return (
    <ul className={styles.list}>
      {items.map((p) => (
        <li key={p.id} className={styles.card}>
          <div className={styles.row}>
            <div>
              <p className={styles.amount}>{formatMinor(p.amount_minor, p.currency)}</p>
              <p className={styles.muted}>
                {p.payer_descriptor ?? "Unknown payer"} · {formatDate(p.value_date)}
                {p.lower_assurance ? " · entered by hand" : ""}
              </p>
            </div>
            <Button aria-expanded={open === p.id} onClick={() => setOpen(open === p.id ? null : p.id)}>
              Details
            </Button>
          </div>
          {open === p.id && <Details workspace={workspace} payment={p} />}
        </li>
      ))}
    </ul>
  );
}
