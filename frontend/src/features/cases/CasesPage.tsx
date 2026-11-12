// FILE GUIDE: disputes and questions (SCR-08, E077–E081). One list of open cases, a second of resolved ones. Opening a
// case pauses routine reminders for its invoice (cases/service.py `_suppress`); resolving needs an outcome, and a
// resolved case can be reopened with a reason. An AI-drafted summary is marked as such and never presented as fact.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { AiMark } from "../../components/domain/AiMark";
import { StatusChip } from "../../components/domain/StatusChip";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { SelectField, TextAreaField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { Page, PageHeader } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { Tabs } from "../../components/ui/Tabs";
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

const CASE_TYPES: Record<string, string> = {
  DISPUTE: "Dispute",
  MISSING_DOCUMENT: "Missing document",
  QUESTION: "Question",
  PROPOSAL: "Proposal from the customer",
  MATCH_REVIEW: "Payments to check",
};

const STATUSES: Record<string, string> = {
  OPEN: "Open",
  IN_REVIEW: "In review",
  AWAITING_CUSTOMER: "Waiting for the customer",
  RESOLVED: "Resolved",
};

const DISPUTE_TYPES: Record<string, string> = {
  AMOUNT: "the amount",
  DELIVERABLE: "what was delivered",
  SERVICE: "the service",
  OTHER: "something else",
};

function ResolveDialog({ workspace, caseId, onClose }: { workspace: string; caseId: string; onClose: () => void }) {
  const [outcome, setOutcome] = useState("");
  const [note, setNote] = useState("");
  const [missing, setMissing] = useState(false);
  const client = useQueryClient();
  const resolve = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/cases/{case_id}/resolve" },
    { idempotent: true },
  );

  useEffect(() => {
    if (resolve.status === "success") {
      void client.invalidateQueries({ queryKey: ["cases", workspace] });
      onClose();
    }
  }, [resolve.status, client, workspace, onClose]);

  function submit() {
    if (!outcome) return setMissing(true);
    setMissing(false);
    resolve.submit({
      path: { ws: workspace, case_id: caseId },
      body: { outcome: outcome as Outcome, ...(note.trim() ? { note: note.trim() } : {}) },
    });
  }

  return (
    <Dialog open onClose={onClose} title="Resolve case">
      <div className={styles.form}>
        <p className={styles.muted}>
          Resolving records how this ended. It does not change the invoice amount or any payment.
        </p>
        <SelectField
          label="Outcome"
          value={outcome}
          onChange={(e) => setOutcome(e.target.value)}
          error={missing ? "Choose how this was resolved." : undefined}
        >
          <option value="">Choose…</option>
          {OUTCOME_KEYS.map((key) => (
            <option key={key} value={key}>
              {OUTCOMES[key]}
            </option>
          ))}
        </SelectField>
        <TextAreaField label="Note (optional)" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
        <MutationFeedback mutation={resolve} />
        <div className={styles.actions}>
          <Button
            variant="primary"
            busy={resolve.status === "pending"}
            aria-disabled={resolve.status === "pending" || undefined}
            onClick={submit}
          >
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
  const reopen = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/cases/{case_id}/reopen" },
    { idempotent: true },
  );

  useEffect(() => {
    if (reopen.status === "success") {
      void client.invalidateQueries({ queryKey: ["cases", workspace] });
      onClose();
    }
  }, [reopen.status, client, workspace, onClose]);

  function submit() {
    if (!reason.trim()) return setMissing(true);
    setMissing(false);
    reopen.submit({ path: { ws: workspace, case_id: caseId }, body: { reason: reason.trim() } });
  }

  return (
    <Dialog open onClose={onClose} title="Reopen case">
      <div className={styles.form}>
        <p className={styles.muted}>Reopening pauses routine reminders for this invoice again.</p>
        <TextAreaField
          label="Reason"
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          error={missing ? "Say why this is being reopened." : undefined}
        />
        <MutationFeedback mutation={reopen} />
        <div className={styles.actions}>
          <Button
            variant="primary"
            busy={reopen.status === "pending"}
            aria-disabled={reopen.status === "pending" || undefined}
            onClick={submit}
          >
            Reopen case
          </Button>
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
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/cases" },
        { path: { ws }, ...(status ? { query: { status } } : {}) },
      ),
  });

  const resolvedView = status === "RESOLVED";
  const items = (list.data?.items ?? []).filter((c) => status || c.status !== "RESOLVED");

  return (
    <Page>
      <PageHeader
        title="Disputes and questions"
        description="What customers have disputed or asked about. While a case is open, routine reminders for its invoice stay paused."
      />

      <Tabs
        label="Case filter"
        items={[
          { to: `/w/${ws}/cases`, label: "Open", current: !status },
          { to: `/w/${ws}/cases?status=RESOLVED`, label: "Resolved", current: resolvedView },
        ]}
      />

      <QueryState query={list} label="cases">
        {items.length === 0 ? (
          <EmptyState
            title="Nothing to review"
            body={
              resolvedView
                ? "Resolved disputes and questions appear here."
                : "Disputes and questions from customers appear here."
            }
          />
        ) : (
          <ul aria-label="Cases" className={styles.cases}>
            {items.map((c) => {
              const resolved = c.status === "RESOLVED";
              return (
                <li key={c.id} className={styles.case} data-type={c.type} data-resolved={resolved || undefined}>
                  <div className={styles.caseHead}>
                    <p className={styles.caseTitle}>
                      <strong>{CASE_TYPES[c.type] ?? "Case"}</strong>
                      {c.type === "DISPUTE" && c.dispute_type && (
                        <span className={styles.muted}> about {DISPUTE_TYPES[c.dispute_type] ?? "something else"}</span>
                      )}
                    </p>
                    {c.type === "DISPUTE" ? (
                      <StatusChip kind="dispute" value={c.status} size="sm" />
                    ) : (
                      <span className={styles.status}>{STATUSES[c.status] ?? c.status}</span>
                    )}
                  </div>

                  <p className={styles.caseMeta}>
                    <Link to={`/w/${ws}/invoices/${c.invoice_id}/overview`} className={styles.invoiceLink}>
                      {c.invoice_number}
                    </Link>
                    <span>
                      Opened{" "}
                      <time className={styles.date} dateTime={c.opened_at}>
                        {formatDate(c.opened_at)}
                      </time>
                    </span>
                    {!resolved && <span>Reminders paused</span>}
                  </p>

                  <p className={styles.summary}>{c.summary}</p>
                  {c.summary_is_ai_derived && (
                    <p className={styles.aiNotice}>
                      <AiMark />
                      <span>AI-drafted summary. Check it against the customer's reply.</span>
                    </p>
                  )}

                  {resolved ? (
                    <>
                      <dl className={styles.outcome}>
                        <div>
                          <dt>Outcome</dt>
                          <dd>{OUTCOMES[c.resolution_outcome ?? ""] ?? "Recorded"}</dd>
                        </div>
                        {c.resolved_at && (
                          <div>
                            <dt>Resolved</dt>
                            <dd>
                              <time className={styles.date} dateTime={c.resolved_at}>
                                {formatDate(c.resolved_at)}
                              </time>
                            </dd>
                          </div>
                        )}
                        {c.resolution_note && (
                          <div>
                            <dt>Note</dt>
                            <dd>{c.resolution_note}</dd>
                          </div>
                        )}
                      </dl>
                      <div className={styles.actions}>
                        <Button variant="secondary" onClick={() => setDialog({ kind: "reopen", id: c.id })}>
                          Reopen
                        </Button>
                      </div>
                    </>
                  ) : (
                    <div className={styles.actions}>
                      <Button variant="primary" onClick={() => setDialog({ kind: "resolve", id: c.id })}>
                        Resolve
                      </Button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </QueryState>

      {dialog?.kind === "resolve" && (
        <ResolveDialog workspace={ws} caseId={dialog.id} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === "reopen" && <ReopenDialog workspace={ws} caseId={dialog.id} onClose={() => setDialog(null)} />}
    </Page>
  );
}
