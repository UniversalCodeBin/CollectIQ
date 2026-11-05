import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { SelectField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import { formatDate } from "../../lib/format";
import styles from "./Cases.module.css";

const OUTCOMES: Record<string, string> = {
  NO_CHANGE: "No change to the invoice",
  INVOICE_CORRECTED: "Invoice corrected",
  ADJUSTMENT_AGREED: "Adjustment agreed",
  WITHDRAWN_BY_CUSTOMER: "Withdrawn by the customer",
  OTHER: "Other",
};
const OUTCOME_KEYS = Object.keys(OUTCOMES) as Array<keyof typeof OUTCOMES>;
type Outcome = "NO_CHANGE" | "INVOICE_CORRECTED" | "ADJUSTMENT_AGREED" | "WITHDRAWN_BY_CUSTOMER" | "OTHER";

function ResolveDialog({ workspace, caseId, onClose }: { workspace: string; caseId: string; onClose: () => void }) {
  const [outcome, setOutcome] = useState("");
  const [note, setNote] = useState("");
  const [missing, setMissing] = useState(false);
  const client = useQueryClient();
  const resolve = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/cases/{case_id}/resolve" }, { idempotent: true });
  useEffect(() => {
    if (resolve.status === "success") {
      void client.invalidateQueries({ queryKey: ["cases", workspace] });
      onClose();
    }
  }, [resolve.status, client, workspace, onClose]);
  function submit() {
    if (!outcome) return setMissing(true);
    setMissing(false);
    resolve.submit({ path: { ws: workspace, case_id: caseId }, body: { outcome: outcome as Outcome, ...(note.trim() ? { note: note.trim() } : {}) } });
  }
  return (
    <Dialog open onClose={onClose} title="Resolve case">
      <div className={styles.form}>
        <SelectField label="Outcome" value={outcome} onChange={(e) => setOutcome(e.target.value)} error={missing ? "Choose how this was resolved." : undefined}>
          <option value="">Choose…</option>
          {OUTCOME_KEYS.map((key) => (
            <option key={key} value={key}>
              {OUTCOMES[key]}
            </option>
          ))}
        </SelectField>
        <TextField label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        <MutationFeedback mutation={resolve} />
        <div className={styles.actions}>
          <Button aria-disabled={resolve.status === "pending" || undefined} onClick={submit}>
            Resolve case
          </Button>
          <Button data-cancel onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function ReopenDialog({ workspace, caseId, onClose }: { workspace: string; caseId: string; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const [missing, setMissing] = useState(false);
  const client = useQueryClient();
  const reopen = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/cases/{case_id}/reopen" }, { idempotent: true });
  useEffect(() => {
    if (reopen.status === "success") {
      void client.invalidateQueries({ queryKey: ["cases", workspace] });
      onClose();
    }
  }, [reopen.status, client, workspace, onClose]);
  function submit() {
    if (!reason.trim()) return setMissing(true);
    reopen.submit({ path: { ws: workspace, case_id: caseId }, body: { reason: reason.trim() } });
  }
  return (
    <Dialog open onClose={onClose} title="Reopen case">
      <div className={styles.form}>
        <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} error={missing ? "Say why this is being reopened." : undefined} />
        <MutationFeedback mutation={reopen} />
        <div className={styles.actions}>
          <Button onClick={submit}>Reopen case</Button>
          <Button data-cancel onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

export function CasesPage() {
  const { ws = "" } = useParams();
  const [params] = useSearchParams();
  const status = params.get("status") ?? "";
  const [dialog, setDialog] = useState<{ kind: "resolve" | "reopen"; id: string } | null>(null);
  const list = useQuery({
    queryKey: ["cases", ws, status],
    queryFn: () =>
      apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/cases" }, { path: { ws }, ...(status ? { query: { status } } : {}) }),
  });
  const items = (list.data?.items ?? []).filter((c) => status || c.status !== "RESOLVED");
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Disputes and questions</h1>
      <nav aria-label="Case filter" className={styles.actions}>
        <Link to={`/w/${ws}/cases`}>Open</Link>
        <Link to={`/w/${ws}/cases?status=RESOLVED`}>Resolved</Link>
      </nav>
      <QueryState query={list} label="cases">
        {items.length === 0 ? (
          <EmptyState title="Nothing to review" body="Disputes and questions from customers appear here." />
        ) : (
          <ul aria-label="Cases" className={styles.list}>
            {items.map((c) => (
              <li key={c.id} className={styles.card}>
                <p className={styles.row}>
                  <strong>{c.type === "DISPUTE" ? "Dispute" : "Question or request"}</strong>
                  <span className={styles.muted}>
                    {c.status.toLowerCase().replace("_", " ")} · opened {formatDate(c.opened_at)}
                  </span>
                </p>
                <p>
                  <Link to={`/w/${ws}/invoices/${c.invoice_id}/overview`}>{c.invoice_number}</Link>
                </p>
                <p>{c.summary}</p>
                {c.summary_is_ai_derived && <p className={styles.muted}>AI-drafted summary. Check it against the customer's reply.</p>}
                {c.status === "RESOLVED" ? (
                  <>
                    <p className={styles.muted}>Outcome: {OUTCOMES[c.resolution_outcome ?? ""] ?? "Recorded"}</p>
                    <div className={styles.actions}>
                      <Button variant="secondary" onClick={() => setDialog({ kind: "reopen", id: c.id })}>
                        Reopen
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className={styles.actions}>
                    <Button onClick={() => setDialog({ kind: "resolve", id: c.id })}>Resolve</Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </QueryState>
      {dialog?.kind === "resolve" && <ResolveDialog workspace={ws} caseId={dialog.id} onClose={() => setDialog(null)} />}
      {dialog?.kind === "reopen" && <ReopenDialog workspace={ws} caseId={dialog.id} onClose={() => setDialog(null)} />}
    </div>
  );
}
