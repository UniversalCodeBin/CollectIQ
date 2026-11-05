import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ComponentType, useState } from "react";
import { Link, NavLink, useParams } from "react-router";
import { NotFoundPage } from "../../app/NotFoundPage";
import { StatusChip } from "../../components/domain/StatusChip";
import { DisabledWithReason } from "../../components/ui/DisabledWithReason";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import { formatDate, formatMinor } from "../../lib/format";
import { ActionDialog, CorrectDialog } from "./Dialogs";
import { History } from "./History";
import styles from "./InvoicePage.module.css";
import type { InvoiceDetail } from "./types";

/** Sections that exist. Later tasks add evidence, timeline, reconciliation and tasks here, never before the backend is real. */
type Section = { label: string; Screen: ComponentType<{ detail: InvoiceDetail }> };

function Overview({ detail }: { detail: InvoiceDetail }) {
  const { facts, derived } = detail;
  const money = (minor: number) => formatMinor(minor, facts.currency);
  const next = detail.recommended_action;
  return (
    <>
      <section aria-labelledby="facts-title" className={styles.card}>
        <h2 id="facts-title" className={styles.heading}>
          From the invoice
        </h2>
        <dl className={styles.facts}>
          <dt>Total</dt>
          <dd>{money(facts.gross_minor)}</dd>
          {facts.subtotal_minor !== null && (
            <>
              <dt>Subtotal</dt>
              <dd>{money(facts.subtotal_minor)}</dd>
            </>
          )}
          {facts.tax_minor !== null && (
            <>
              <dt>Tax</dt>
              <dd>{money(facts.tax_minor)}</dd>
            </>
          )}
          <dt>Issued</dt>
          <dd>{facts.issue_date ? formatDate(facts.issue_date) : "Not given"}</dd>
          <dt>Due</dt>
          <dd>{formatDate(facts.due_date)}</dd>
          <dt>Payment terms</dt>
          <dd>{facts.payment_terms ?? "Not given"}</dd>
          <dt>PO number</dt>
          <dd>{facts.po_number ?? "Not given"}</dd>
          {facts.project_ref && (
            <>
              <dt>Project</dt>
              <dd>{facts.project_ref}</dd>
            </>
          )}
          {facts.description && (
            <>
              <dt>Description</dt>
              <dd>{facts.description}</dd>
            </>
          )}
        </dl>
        {facts.diverges_from_source && (
          <p className={styles.note}>
            Some details were corrected after import{facts.corrected_fields.length > 0 ? `: ${facts.corrected_fields.map((field) => field.replace(/_/g, " ")).join(", ")}` : ""}. Your correction is kept if the file is imported again.
          </p>
        )}
      </section>

      <section aria-labelledby="derived-title" className={styles.card}>
        <h2 id="derived-title" className={styles.heading}>
          What CollectIQ worked out
        </h2>
        <p className={styles.hint}>Worked out from the invoice and the payment evidence on file. Check it against your own records.</p>
        <dl className={styles.facts}>
          <dt>Payment</dt>
          <dd>
            <StatusChip kind="payment" value={derived.payment_status} />
          </dd>
          <dt>Amount still owed</dt>
          <dd>{money(derived.outstanding_minor)}</dd>
          <dt>Recorded as paid</dt>
          <dd>{money(derived.paid_minor)}</dd>
          <dt>Evidence</dt>
          <dd>
            <StatusChip kind="evidence" value={derived.evidence_coverage} />
            {derived.evidence_as_of && <span> as of {formatDate(derived.evidence_as_of)}</span>}
          </dd>
          <dt>Timing</dt>
          <dd>{derived.days_overdue > 0 ? `${derived.days_overdue} days overdue` : "Not overdue"}</dd>
          {derived.dispute_status !== "NONE" && (
            <>
              <dt>Dispute</dt>
              <dd>
                <StatusChip kind="dispute" value={derived.dispute_status} />
              </dd>
            </>
          )}
          {derived.reminder_status !== "NONE" && derived.reminder_status !== "NOT_CONTACTED" && (
            <>
              <dt>Reminder</dt>
              <dd>
                <StatusChip kind="reminder" value={derived.reminder_status} />
              </dd>
            </>
          )}
        </dl>
        {derived.overpayment_flag && <p className={styles.note}>More has been recorded than this invoice is for. Someone should look at it.</p>}
        {detail.ai_claims.length > 0 && (
          <p className={styles.note}>CollectIQ also has {detail.ai_claims.length} unverified suggestion(s) for this invoice. They are not facts until you confirm them.</p>
        )}
      </section>

      <section aria-labelledby="source-title" className={styles.card}>
        <h2 id="source-title" className={styles.heading}>
          Where this came from
        </h2>
        <p>
          {detail.provenance.source_system === "SAMPLE"
            ? "Sample data made up for trying CollectIQ."
            : `Imported from ${detail.provenance.file_name ?? "a file"}${detail.provenance.source_row ? `, row ${detail.provenance.source_row}` : ""}.`}
        </p>
      </section>

      <section aria-labelledby="next-title" className={styles.card}>
        <h2 id="next-title" className={styles.heading}>
          What to do next
        </h2>
        {next ? <p className={styles.action}>{next.label}</p> : <p>Nothing is needed from you right now.</p>}
        {detail.reasons.length > 0 && (
          <ul className={styles.reasons}>
            {detail.reasons.map((reason) => (
              <li key={reason.code}>{reason.label}</li>
            ))}
          </ul>
        )}
        {!next &&
          detail.why_not.map((why) => (
            <p key={why.code} className={styles.hint}>
              {why.label}
            </p>
          ))}
      </section>
    </>
  );
}

const SECTIONS: Record<string, Section> = {
  overview: { label: "Overview", Screen: Overview },
  history: { label: "Payment history", Screen: History },
};

export function InvoicePage() {
  const { ws = "", id = "", tab = "" } = useParams();
  const section = SECTIONS[tab];
  const client = useQueryClient();
  const [dialog, setDialog] = useState<"correct" | "cancel" | "archive" | null>(null);
  const key = ["invoice", ws, id];
  const found = useQuery({
    queryKey: key,
    enabled: Boolean(section),
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}" }, { path: { ws, invoice_id: id } }),
  });
  if (!section) return <NotFoundPage />;

  const detail = found.data as InvoiceDetail | undefined;
  const refresh = () => {
    setDialog(null);
    void client.invalidateQueries({ queryKey: key });
    void client.invalidateQueries({ queryKey: ["receivables", ws] });
    void client.invalidateQueries({ queryKey: ["dashboard", ws] });
  };
  const verdict = (name: string) => detail?.allowed_actions.find((entry) => entry.action === name) ?? { allowed: false, reason: null };

  return (
    <div className={styles.page}>
      <QueryState query={found} label="the invoice">
        {detail && (
          <>
            <header className={styles.header}>
              <h1 className={styles.title}>Invoice {detail.facts.invoice_number}</h1>
              <p className={styles.sub}>
                <Link to={`/w/${ws}/clients/${detail.facts.client_id}`}>{detail.facts.client_name}</Link>
                <StatusChip kind="invoice" value={detail.facts.status} />
              </p>
              <div className={styles.actions}>
                <DisabledWithReason action={verdict("CORRECT")} label="Correct details" variant="secondary" onClick={() => setDialog("correct")} />
                <DisabledWithReason action={verdict("CANCEL")} label="Cancel invoice" variant="danger" onClick={() => setDialog("cancel")} />
                <DisabledWithReason action={verdict("ARCHIVE")} label="Archive invoice" variant="secondary" onClick={() => setDialog("archive")} />
              </div>
            </header>
            <nav aria-label="Invoice sections" className={styles.tabs}>
              {Object.entries(SECTIONS).map(([name, entry]) => (
                <NavLink key={name} to={`/w/${ws}/invoices/${id}/${name}`}>
                  {entry.label}
                </NavLink>
              ))}
            </nav>
            <section.Screen detail={detail} />
            <CorrectDialog open={dialog === "correct"} onClose={() => setDialog(null)} workspace={ws} detail={detail} onDone={refresh} />
            <ActionDialog kind="cancel" open={dialog === "cancel"} onClose={() => setDialog(null)} workspace={ws} invoiceId={id} onDone={refresh} />
            <ActionDialog kind="archive" open={dialog === "archive"} onClose={() => setDialog(null)} workspace={ws} invoiceId={id} onDone={refresh} />
          </>
        )}
      </QueryState>
    </div>
  );
}
