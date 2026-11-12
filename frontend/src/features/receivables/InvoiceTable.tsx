import { ArrowRight } from "lucide-react";
import { Link } from "react-router";
import { StatusChip } from "../../components/domain/StatusChip";
import { DataTable } from "../../components/ui/DataTable";
import { formatDate, formatMinor } from "../../lib/format";
import styles from "./Receivables.module.css";

export type InvoiceRow = {
  id: string;
  invoice_number: string;
  client_id: string;
  client_name: string;
  currency: string;
  status: string;
  due_date: string;
  outstanding_minor: number;
  payment_status: string;
  dispute_status: string;
  reminder_status: string;
  days_overdue: number;
  evidence_coverage?: string;
};

export type QueueRow = InvoiceRow & {
  tier?: number;
  reasons: { code: string; label: string }[];
  why_not: { code: string; label: string }[];
  recommended_action: {
    code: string;
    label: string;
    can_act?: boolean;
    performed_by?: string;
    reason?: string | null;
  } | null;
};

const HIDDEN_DISPUTE = new Set(["NONE"]);
const HIDDEN_REMINDER = new Set(["NONE", "NOT_CONTACTED"]);

export function isQueueRow(row: InvoiceRow | QueueRow): row is QueueRow {
  return "reasons" in row;
}

function Status({ row }: { row: InvoiceRow }) {
  return (
    <div className={styles.chips}>
      <StatusChip kind="payment" value={row.payment_status} size="sm" />
      {row.status !== "ACTIVE" && <StatusChip kind="invoice" value={row.status} size="sm" />}
      {!HIDDEN_DISPUTE.has(row.dispute_status) && <StatusChip kind="dispute" value={row.dispute_status} size="sm" />}
      {!HIDDEN_REMINDER.has(row.reminder_status) && (
        <StatusChip kind="reminder" value={row.reminder_status} size="sm" />
      )}
      {row.evidence_coverage && <StatusChip kind="evidence" value={row.evidence_coverage} size="sm" />}
    </div>
  );
}

export function InvoiceTable({
  workspace,
  caption,
  rows,
  queue,
  showClient = true,
}: {
  workspace: string;
  caption: string;
  rows: Array<InvoiceRow | QueueRow>;
  queue: boolean;
  /** Off on a client's own page, where every row would repeat the page title. */
  showClient?: boolean;
}) {
  return (
    <DataTable
      caption={caption}
      rows={rows}
      rowKey={(row) => row.id}
      columns={[
        {
          key: "invoice_number",
          header: "Invoice",
          rowHeader: true,
          render: (row) => (
            <div className={styles.invoiceCell}>
              <Link to={`/w/${workspace}/invoices/${row.id}/overview`} className={styles.invoiceLink}>
                {row.invoice_number}
              </Link>
            </div>
          ),
        },
        ...(showClient
          ? [
              {
                key: "client_name",
                header: "Client",
                render: (row: InvoiceRow | QueueRow) => (
                  <Link to={`/w/${workspace}/clients/${row.client_id}`} className={styles.clientLink}>
                    {row.client_name}
                  </Link>
                ),
              },
            ]
          : []),
        {
          key: "due_date",
          header: "Due",
          render: (row) => (
            <div className={styles.dueCell}>
              <span className={styles.dueDateText}>{formatDate(row.due_date)}</span>
              {row.days_overdue > 0 && <span className={styles.late}>{row.days_overdue} days overdue</span>}
            </div>
          ),
        },
        {
          key: "outstanding_minor",
          header: "Outstanding",
          numeric: true,
          render: (row) => (
            <span className={styles.amountValue}>{formatMinor(row.outstanding_minor, row.currency)}</span>
          ),
        },
        {
          key: "status",
          header: "Status",
          render: (row) => <Status row={row} />,
        },
        ...(queue
          ? [
              {
                key: "next",
                header: "Why it's here",
                wide: true,
                render: (row: InvoiceRow | QueueRow) =>
                  isQueueRow(row) ? (
                    <div className={styles.next}>
                      {row.reasons.length > 0 && (
                        <div className={styles.reasonGroup}>
                          {row.reasons.map((reason) => (
                            <span key={reason.code} className={styles.reasonBadge}>
                              {reason.label}
                            </span>
                          ))}
                        </div>
                      )}
                      {row.recommended_action ? (
                        <div className={styles.actionBlock}>
                          <Link to={`/w/${workspace}/invoices/${row.id}/overview`} className={styles.actionBtn}>
                            <span>{row.recommended_action.label}</span>
                            <span className="visually-hidden"> for {row.invoice_number}</span>
                            <ArrowRight size={13} aria-hidden="true" />
                          </Link>
                        </div>
                      ) : (
                        row.why_not.map((why) => (
                          <p key={why.code} className={styles.quiet}>
                            {why.label}
                          </p>
                        ))
                      )}
                    </div>
                  ) : null,
              },
            ]
          : []),
      ]}
    />
  );
}
