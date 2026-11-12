// FILE GUIDE: one invoice (SCR-04). The overview keeps three layers apart: what the invoice says (recorded facts),
// what CollectIQ worked out from those facts and the confirmed payments (calculated), and anything an AI model read
// (unverified, on the AI brief tab). Corrections, cancelling and archiving go through dialogs that need a reason, and
// the server decides which of them are allowed. Nothing on this screen marks an invoice paid.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Flag, Hourglass, CirclePause } from "lucide-react";
import { type ComponentType, useState } from "react";
import { Link, useParams } from "react-router";
import { NotFoundPage } from "../../app/NotFoundPage";
import { AiMark } from "../../components/domain/AiMark";
import { StatusChip } from "../../components/domain/StatusChip";
import { DisabledWithReason } from "../../components/ui/DisabledWithReason";
import { MetricStrip, MetricTile } from "../../components/ui/MetricTile";
import { Page, PageHeader, Section, Split } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { Tabs } from "../../components/ui/Tabs";
import { apiRequest } from "../../lib/api";
import { formatDate, formatMinor } from "../../lib/format";
import { InvoiceBrief } from "../ai/InvoiceBrief";
import { InvoiceTimeline } from "../conversations/Timeline";
import { InvoiceFollowup } from "../followups/InvoiceFollowup";
import { ActionDialog, CorrectDialog } from "./Dialogs";
import { History } from "./History";
import styles from "./InvoicePage.module.css";
import type { InvoiceDetail } from "./types";

type Screen = { label: string; Screen: ComponentType<{ detail: InvoiceDetail }> };

/** Reminder states in which the server holds routine reminders back (a dispute, a payment claim or a snooze). */
const HELD = new Set(["SUPPRESSED", "SNOOZED"]);

function Fact({ term, children, mono }: { term: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className={styles.fact}>
      <dt>{term}</dt>
      <dd className={mono ? styles.mono : undefined}>{children}</dd>
    </div>
  );
}

function Overview({ detail }: { detail: InvoiceDetail }) {
  const { ws = "" } = useParams();
  const { facts, derived } = detail;
  const money = (minor: number) => formatMinor(minor, facts.currency);
  const next = detail.recommended_action;
  const reminderShown = derived.reminder_status !== "NONE" && derived.reminder_status !== "NOT_CONTACTED";

  return (
    <>
      <MetricStrip label="Balance" terms>
        <MetricTile label="Invoiced" value={money(facts.gross_minor)} detail="From the invoice" />
        <MetricTile label="Recorded as paid" value={money(derived.paid_minor)} detail="Payments a person confirmed" />
        <MetricTile
          label="Amount still owed"
          value={money(derived.outstanding_minor)}
          detail={`Due ${formatDate(facts.due_date)}`}
        />
      </MetricStrip>

      <Split
        rail={
          <>
            <Section
              title="What CollectIQ worked out"
              description="Calculated from the invoice and the payments confirmed against it. Check it against your own books."
            >
              <dl className={styles.facts}>
                <Fact term="Payment">
                  <StatusChip kind="payment" value={derived.payment_status} />
                </Fact>
                <Fact term="Evidence">
                  <span className={styles.inline}>
                    <StatusChip kind="evidence" value={derived.evidence_coverage} />
                    {derived.evidence_as_of && <span>as of {formatDate(derived.evidence_as_of)}</span>}
                  </span>
                </Fact>
                <Fact term="Timing">
                  {derived.days_overdue > 0 ? `${derived.days_overdue} days overdue` : "Not overdue"}
                </Fact>
                {derived.dispute_status !== "NONE" && (
                  <Fact term="Dispute">
                    <StatusChip kind="dispute" value={derived.dispute_status} />
                  </Fact>
                )}
                {reminderShown && (
                  <Fact term="Reminders">
                    <StatusChip kind="reminder" value={derived.reminder_status} />
                  </Fact>
                )}
              </dl>
              {derived.overpayment_flag && (
                <p className={styles.warning}>
                  More has been recorded against this invoice than it is for. Someone should look at it.
                </p>
              )}
            </Section>

            <Section title="What to do next">
              {next ? (
                <p className={styles.nextAction}>{next.label}</p>
              ) : (
                <p className={styles.plain}>Nothing is needed from you right now.</p>
              )}
              {detail.reasons.length > 0 && (
                <ul className={styles.reasons} aria-label="Why">
                  {detail.reasons.map((reason) => (
                    <li key={reason.code}>{reason.label}</li>
                  ))}
                </ul>
              )}
              {!next &&
                detail.why_not.map((why) => (
                  <p key={why.code} className={styles.muted}>
                    {why.label}
                  </p>
                ))}
            </Section>

            <Section title="AI readings" aside={<AiMark label="Unverified" />}>
              {detail.ai_claims.length > 0 ? (
                <p className={styles.plain}>
                  {detail.ai_claims.length === 1
                    ? "There is 1 AI suggestion for this invoice."
                    : `There are ${detail.ai_claims.length} AI suggestions for this invoice.`}{" "}
                  None of them is a fact until a person confirms it.
                </p>
              ) : (
                <p className={styles.plain}>
                  None on file. You can ask for an AI brief; it is shown on its own tab, labelled as unverified, and
                  changes nothing.
                </p>
              )}
              <Link to={`/w/${ws}/invoices/${facts.id}/brief`} className={styles.textLink}>
                Open the AI brief
              </Link>
            </Section>
          </>
        }
      >
        <Section
          title="From the invoice"
          description="As recorded in your accounting system, plus any correction made here."
        >
          <dl className={styles.facts}>
            <Fact term="Total" mono>
              {money(facts.gross_minor)}
            </Fact>
            {facts.subtotal_minor !== null && (
              <Fact term="Subtotal" mono>
                {money(facts.subtotal_minor)}
              </Fact>
            )}
            {facts.tax_minor !== null && (
              <Fact term="Tax" mono>
                {money(facts.tax_minor)}
              </Fact>
            )}
            <Fact term="Issued">{facts.issue_date ? formatDate(facts.issue_date) : "Not given"}</Fact>
            <Fact term="Due">{formatDate(facts.due_date)}</Fact>
            <Fact term="Payment terms">{facts.payment_terms ?? "Not given"}</Fact>
            <Fact term="PO number" mono={facts.po_number !== null}>
              {facts.po_number ?? "Not given"}
            </Fact>
            {facts.project_ref && <Fact term="Project">{facts.project_ref}</Fact>}
            {facts.description && <Fact term="Description">{facts.description}</Fact>}
          </dl>
          {facts.diverges_from_source && (
            <p className={styles.note}>
              Some details were corrected after import
              {facts.corrected_fields.length > 0
                ? `: ${facts.corrected_fields.map((field) => field.replace(/_/g, " ")).join(", ")}`
                : ""}
              . Your correction is kept if the file is imported again.
            </p>
          )}
        </Section>

        <Section title="Where this came from">
          <p className={styles.plain}>
            {detail.provenance.source_system === "SAMPLE"
              ? "Sample data made up for trying CollectIQ."
              : `Imported from ${detail.provenance.file_name ?? "a file"}${
                  detail.provenance.source_row ? `, row ${detail.provenance.source_row}` : ""
                }.`}
          </p>
        </Section>
      </Split>
    </>
  );
}

const SCREENS: Record<string, Screen> = {
  overview: { label: "Overview", Screen: Overview },
  history: { label: "Payment history", Screen: History },
  timeline: { label: "Conversation", Screen: InvoiceTimeline },
  followups: { label: "Follow-up", Screen: InvoiceFollowup },
  brief: { label: "AI brief", Screen: InvoiceBrief },
};

/** One line saying why routine follow-up is held, built only from states the server reported. */
function HoldNotice({ derived }: { derived: InvoiceDetail["derived"] }) {
  const held = HELD.has(derived.reminder_status);
  const disputed = derived.dispute_status !== "NONE" && derived.dispute_status !== "RESOLVED";
  const claimed = derived.payment_status === "AWAITING_VERIFICATION";
  const uncertain = derived.payment_status === "UNCERTAIN";
  if (!held && !disputed && !claimed && !uncertain) return null;

  const Icon = disputed ? Flag : claimed || uncertain ? Hourglass : CirclePause;
  const title = disputed
    ? "A dispute is open on this invoice."
    : claimed
      ? "The customer says this has been paid."
      : uncertain
        ? "A payment may have arrived but could not be confirmed."
        : "Routine reminders are paused for this invoice.";
  const body = [
    claimed || uncertain ? "It stays unpaid until someone checks the bank evidence." : null,
    held && (disputed || claimed || uncertain) ? "Routine reminders are paused meanwhile." : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={styles.hold}
      role="status"
      data-tone={disputed ? "disputed" : claimed || uncertain ? "awaiting" : "paused"}
    >
      <Icon size={18} aria-hidden="true" className={styles.holdIcon} />
      <p className={styles.holdText}>
        <strong>{title}</strong>
        {body && <> {body}</>}
      </p>
    </div>
  );
}

export function InvoicePage() {
  const { ws = "", id = "", tab = "" } = useParams();
  const screen = SCREENS[tab];
  const client = useQueryClient();
  const [dialog, setDialog] = useState<"correct" | "cancel" | "archive" | null>(null);
  const key = ["invoice", ws, id];

  const found = useQuery({
    queryKey: key,
    enabled: Boolean(screen),
    queryFn: () =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}" },
        { path: { ws, invoice_id: id } },
      ),
  });

  if (!screen) return <NotFoundPage />;

  const detail = found.data as InvoiceDetail | undefined;
  const refresh = () => {
    setDialog(null);
    void client.invalidateQueries({ queryKey: key });
    void client.invalidateQueries({ queryKey: ["receivables", ws] });
    void client.invalidateQueries({ queryKey: ["dashboard", ws] });
  };
  const verdict = (name: string) =>
    detail?.allowed_actions.find((entry) => entry.action === name) ?? { allowed: false, reason: null };

  return (
    <Page>
      <QueryState query={found} label="the invoice">
        {detail && (
          <>
            <PageHeader
              back={{ to: `/w/${ws}/receivables`, label: "Receivables" }}
              title={
                <>
                  Invoice <span className={styles.number}>{detail.facts.invoice_number}</span>
                </>
              }
              meta={
                <>
                  <Link to={`/w/${ws}/clients/${detail.facts.client_id}`} className={styles.clientLink}>
                    {detail.facts.client_name}
                  </Link>
                  <StatusChip kind="invoice" value={detail.facts.status} />
                </>
              }
              actions={
                <>
                  <DisabledWithReason
                    action={verdict("CORRECT")}
                    label="Correct details"
                    variant="secondary"
                    onClick={() => setDialog("correct")}
                  />
                  <DisabledWithReason
                    action={verdict("CANCEL")}
                    label="Cancel invoice"
                    variant="danger"
                    onClick={() => setDialog("cancel")}
                  />
                  <DisabledWithReason
                    action={verdict("ARCHIVE")}
                    label="Archive invoice"
                    variant="secondary"
                    onClick={() => setDialog("archive")}
                  />
                </>
              }
            />

            <HoldNotice derived={detail.derived} />

            <Tabs
              label="Invoice sections"
              items={Object.entries(SCREENS).map(([name, entry]) => ({
                to: `/w/${ws}/invoices/${id}/${name}`,
                label: entry.label,
              }))}
            />

            <screen.Screen detail={detail} />

            <CorrectDialog
              open={dialog === "correct"}
              onClose={() => setDialog(null)}
              workspace={ws}
              detail={detail}
              onDone={refresh}
            />
            <ActionDialog
              kind="cancel"
              open={dialog === "cancel"}
              onClose={() => setDialog(null)}
              workspace={ws}
              invoiceId={id}
              onDone={refresh}
            />
            <ActionDialog
              kind="archive"
              open={dialog === "archive"}
              onClose={() => setDialog(null)}
              workspace={ws}
              invoiceId={id}
              onDone={refresh}
            />
          </>
        )}
      </QueryState>
    </Page>
  );
}
