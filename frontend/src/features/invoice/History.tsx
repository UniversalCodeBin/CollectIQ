import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { EmptyState } from "../../components/ui/EmptyState";
import { Section } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import { formatDate, formatMinor } from "../../lib/format";
import styles from "./InvoicePage.module.css";
import type { InvoiceDetail } from "./types";

const EVIDENCE: Record<string, string> = {
  BANK_STATEMENT: "Bank statement row",
  USER_CONFIRMATION: "Entered by a person",
};

/** FR-056: every payment applied to this invoice and every reversal, oldest first. Nothing here is edited in place. */
export function History({ detail }: { detail: InvoiceDetail }) {
  const { ws = "" } = useParams();
  const id = detail.facts.id;
  const history = useQuery({
    queryKey: ["invoice", ws, id, "payments"],
    queryFn: () =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}/payments" },
        { path: { ws, invoice_id: id } },
      ),
  });
  return (
    <Section
      title="Payment history"
      description="Payments a person confirmed against this invoice, and any reversal. Entries are never edited; a mistake is undone by a reversal."
    >
      <QueryState query={history} label="payment history">
        {history.data &&
          (history.data.items.length === 0 ? (
            <EmptyState
              title="No payments applied yet"
              body="When a person confirms a payment against this invoice, it appears here, and so does any later reversal."
            />
          ) : (
            <ol aria-label="Payment history" className={styles.history}>
              {history.data.items.map((row) => {
                const reversal = row.kind === "REVERSAL";
                return (
                  <li key={row.id} className={styles.historyRow} data-reversal={reversal || undefined}>
                    <p className={styles.historyLine}>
                      <strong className={styles.historyKind}>{reversal ? "Reversed" : "Applied"}</strong>
                      <span className={styles.mono}>{formatMinor(Math.abs(row.amount_minor), row.currency)}</span>
                      <span className={styles.historyMeta}>on {formatDate(row.created_at)}</span>
                    </p>
                    <p className={styles.historyMeta}>
                      Payment of {formatDate(row.value_date)}
                      {row.payer_descriptor ? ` from ${row.payer_descriptor}` : ""}.{" "}
                      {EVIDENCE[row.evidence_type] ?? row.evidence_type}.
                      {row.overpayment_confirmed ? " Overpayment confirmed by a person." : ""}
                    </p>
                    {row.note && <p className={styles.historyMeta}>Reason: {row.note}</p>}
                  </li>
                );
              })}
            </ol>
          ))}
      </QueryState>
    </Section>
  );
}
