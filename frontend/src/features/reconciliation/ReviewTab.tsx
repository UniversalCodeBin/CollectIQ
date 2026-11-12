import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { TextField } from "../../components/ui/Field";
import { EmptyState } from "../../components/ui/EmptyState";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { ProblemMessage } from "../../components/ui/ProblemMessage";
import { ApiProblem, useApiMutation } from "../../lib/api";
import { formatDate, formatMinor } from "../../lib/format";
import { minorToText, parseMinor } from "./money";
import styles from "./Reconciliation.module.css";
import type { Proposal } from "./types";

export type Group = { transaction: Proposal["transaction"]; candidates: Proposal[]; ambiguous: boolean };

/** One card per payment: a payment with several possible invoices is one decision, not several. */
export function groupProposals(items: Proposal[]): Group[] {
  const byTransaction = new Map<string, Proposal[]>();
  for (const item of items)
    byTransaction.set(item.transaction.id, [...(byTransaction.get(item.transaction.id) ?? []), item]);
  return [...byTransaction.values()].map((candidates) => ({
    transaction: candidates[0]!.transaction,
    candidates,
    ambiguous: candidates.length > 1 || candidates.some((candidate) => candidate.ambiguous),
  }));
}

const REFRESH = ["reconciliation"];

function useRefreshOnSuccess(status: string) {
  const client = useQueryClient();
  useEffect(() => {
    if (status === "success") void client.invalidateQueries({ queryKey: REFRESH });
  }, [status, client]);
}

function SplitDialog({
  proposal,
  onClose,
  onApply,
  pending,
}: {
  proposal: Proposal;
  onClose: () => void;
  onApply: (minor: number) => void;
  pending: boolean;
}) {
  const limit = Math.min(proposal.transaction.amount_minor, proposal.invoice.outstanding_minor);
  const [text, setText] = useState(minorToText(limit));
  const [refusal, setRefusal] = useState<ApiProblem | null>(null);
  const minor = parseMinor(text);
  const currency = proposal.transaction.currency;

  function apply() {
    if (minor === null || minor > limit) {
      return setRefusal(
        new ApiProblem({
          status: 400,
          code: "VALIDATION_FAILED",
          detail: "",
          correlationId: null,
          errors: [{ field: "amount", message: `Enter an amount between 0.01 and ${formatMinor(limit, currency)}.` }],
        }),
      );
    }
    setRefusal(null);
    onApply(minor);
  }

  return (
    <Dialog open onClose={onClose} title={`Apply part of this payment to ${proposal.invoice.invoice_number}`}>
      <div className={styles.form}>
        <p className={styles.muted}>
          Payment {formatMinor(proposal.transaction.amount_minor, currency)}; invoice balance{" "}
          {formatMinor(proposal.invoice.outstanding_minor, currency)}.
        </p>
        <TextField
          label={`Amount to apply (${currency})`}
          inputMode="decimal"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        {minor !== null && minor <= limit && (
          <p role="status" className={styles.note}>
            Invoice balance after this: {formatMinor(proposal.invoice.outstanding_minor - minor, currency)}. Left on the
            payment: {formatMinor(proposal.transaction.amount_minor - minor, currency)}.
          </p>
        )}
        {refusal && <ProblemMessage problem={refusal} />}
        <div className={styles.actions}>
          <Button variant="primary" aria-disabled={pending || undefined} onClick={apply}>
            Apply allocation
          </Button>
          <Button variant="secondary" data-cancel onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function Suggestion({ workspace, group }: { workspace: string; group: Group }) {
  const [chosen, setChosen] = useState<string | null>(group.ambiguous ? null : group.candidates[0]!.id);
  const [splitting, setSplitting] = useState(false);
  const [needChoice, setNeedChoice] = useState(false);
  const confirm = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/reconciliation/proposals/{proposal_id}/confirm" },
    { idempotent: true },
  );
  const reject = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/reconciliation/proposals/{proposal_id}/reject" },
    { idempotent: true },
  );
  useRefreshOnSuccess(confirm.status);
  useRefreshOnSuccess(reject.status);
  useEffect(() => {
    if (confirm.status === "success") setSplitting(false);
  }, [confirm.status]);

  const selected = group.candidates.find((candidate) => candidate.id === chosen) ?? null;
  const currency = group.transaction.currency;
  const busy = confirm.status === "pending" || reject.status === "pending";

  function apply(proposal: Proposal, minor: number) {
    confirm.submit({
      path: { ws: workspace, proposal_id: proposal.id },
      body: { allocations: [{ invoice_id: proposal.invoice.id, amount_minor: minor }] } as never,
    });
  }
  const full = (proposal: Proposal) => Math.min(proposal.transaction.amount_minor, proposal.invoice.outstanding_minor);

  return (
    <li className={styles.card} data-suggested>
      <div className={styles.cardHead}>
        <div className={styles.money}>
          <span className={styles.caption}>Payment received</span>
          <p className={styles.amount}>{formatMinor(group.transaction.amount_minor, currency)}</p>
          <p className={styles.meta}>
            <span>{group.transaction.payer_descriptor ?? "Unknown payer"}</span>
            <span>{formatDate(group.transaction.value_date)}</span>
            {group.transaction.reference && <span className={styles.ref}>{group.transaction.reference}</span>}
          </p>
        </div>
        <p className={styles.pending}>Suggested match. Nothing is applied until you confirm.</p>
      </div>
      {group.ambiguous && (
        <p className={styles.note}>More than one invoice could match this payment. Choose the one it belongs to.</p>
      )}
      <fieldset className={styles.candidates}>
        <legend className="visually-hidden">Possible invoices</legend>
        {group.candidates.map((candidate) => (
          <div
            key={candidate.id}
            className={styles.candidate}
            data-chosen={(group.ambiguous && chosen === candidate.id) || undefined}
          >
            <div className={styles.candidateHead}>
              {group.ambiguous ? (
                <label className={styles.choice}>
                  <input
                    type="radio"
                    name={`choice-${group.transaction.id}`}
                    checked={chosen === candidate.id}
                    onChange={() => {
                      setChosen(candidate.id);
                      setNeedChoice(false);
                    }}
                  />
                  <span className={styles.invoiceNumber}>{candidate.invoice.invoice_number}</span>
                  <span className="visually-hidden"> Select this candidate</span>
                </label>
              ) : (
                <strong className={styles.invoiceNumber}>{candidate.invoice.invoice_number}</strong>
              )}
              <span className={styles.label} data-strength={candidate.label}>
                {candidate.label}
              </span>
            </div>
            <p className={styles.meta}>
              <span>{candidate.invoice.client_name}</span>
              <span>Due {formatDate(candidate.invoice.due_date)}</span>
              <span>
                Balance{" "}
                <span className={styles.figure}>{formatMinor(candidate.invoice.outstanding_minor, currency)}</span>
              </span>
            </p>
            <ul className={styles.reasons} aria-label="Why it was suggested">
              {candidate.reasons.map((reason) => (
                <li key={reason.code}>{reason.text}</li>
              ))}
            </ul>
          </div>
        ))}
      </fieldset>
      {needChoice && (
        <p role="alert" className={styles.error}>
          Select the invoice this payment belongs to first.
        </p>
      )}
      <div className={styles.actions}>
        <Button
          variant="primary"
          aria-disabled={busy || !selected || undefined}
          onClick={() => {
            if (!selected) return setNeedChoice(true);
            if (!busy) apply(selected, full(selected));
          }}
        >
          Confirm Match & Apply Allocation
        </Button>
        <Button
          variant="secondary"
          aria-disabled={busy || !selected || undefined}
          onClick={() => (selected ? setSplitting(true) : setNeedChoice(true))}
        >
          Split / Partial Allocation...
        </Button>
        <Button
          variant="quiet"
          aria-disabled={busy || !selected || undefined}
          onClick={() => {
            if (!selected) return setNeedChoice(true);
            reject.submit({ path: { ws: workspace, proposal_id: selected.id }, body: {} });
          }}
        >
          Not a Match
        </Button>
      </div>
      <MutationFeedback mutation={confirm} />
      <MutationFeedback mutation={reject} />
      {splitting && selected && (
        <SplitDialog
          proposal={selected}
          pending={busy}
          onClose={() => setSplitting(false)}
          onApply={(minor) => apply(selected, minor)}
        />
      )}
    </li>
  );
}

export function ReviewTab({ workspace, items }: { workspace: string; items: Proposal[] }) {
  const groups = groupProposals(items);
  if (groups.length === 0) {
    return (
      <EmptyState
        title="Nothing to review"
        body="When a payment looks like it belongs to an invoice, the suggestion appears here for you to confirm."
      />
    );
  }
  return (
    <ul className={styles.list}>
      {groups.map((group) => (
        <Suggestion key={group.transaction.id} workspace={workspace} group={group} />
      ))}
    </ul>
  );
}
