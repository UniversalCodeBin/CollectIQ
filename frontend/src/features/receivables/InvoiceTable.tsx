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
};

/** Rows from the queue also say why each one is here and what to do about it. */
export type QueueRow = InvoiceRow & {
  reasons: { code: string; label: string }[];
  why_not: { code: string; label: string }[];
  recommended_action: { code: string; label: string } | null;
};

const HIDDEN_DISPUTE = new Set(["NONE"]);
const HIDDEN_REMINDER = new Set(["NONE", "NOT_CONTACTED"]);

export function isQueueRow(row: InvoiceRow | QueueRow): row is QueueRow {
  return "reasons" in row;
}

function Status({ row }: { row: InvoiceRow }) {
  return (
    <span className={styles.chips}>
      <StatusChip kind="payment" value={row.payment_status} size="sm" />
      {row.status !== "ACTIVE" && <StatusChip kind="invoice" value={row.status} size="sm" />}
      {!HIDDEN_DISPUTE.has(row.dispute_status) && <StatusChip kind="dispute" value={row.dispute_status} size="sm" />}
      {!HIDDEN_REMINDER.has(row.reminder_status) && <StatusChip kind="reminder" value={row.reminder_status} size="sm" />}
    </span>
  );
}

export function InvoiceTable({ workspace, caption, rows, queue }: { workspace: string; caption: string; rows: Array<InvoiceRow | QueueRow>; queue: boolean }) {
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
          render: (row) => <Link to={`/w/${workspace}/invoices/${row.id}/overview`}>{row.invoice_number}</Link>,
        },
        { key: "client_name", header: "Client", render: (row) => <Link to={`/w/${workspace}/clients/${row.client_id}`}>{row.client_name}</Link> },
        {
          key: "due_date",
          header: "Due",
          render: (row) => (
            <>
              {formatDate(row.due_date)}
              {row.days_overdue > 0 && <span className={styles.late}> · {row.days_overdue} days overdue</span>}
            </>
          ),
        },
        { key: "outstanding_minor", header: "Outstanding", numeric: true, render: (row) => formatMinor(row.outstanding_minor, row.currency) },
        { key: "status", header: "Status", render: (row) => <Status row={row} /> },
        ...(queue
          ? [
              {
                key: "next",
                header: "Why it's here",
                render: (row: InvoiceRow | QueueRow) =>
                  isQueueRow(row) ? (
                    <div className={styles.next}>
                      {row.reasons.map((reason) => (
                        <p key={reason.code}>{reason.label}</p>
                      ))}
                      {row.recommended_action ? (
                        <p className={styles.action}>{row.recommended_action.label}</p>
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
