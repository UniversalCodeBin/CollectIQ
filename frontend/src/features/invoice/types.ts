export type Verdict = { action: string; allowed: boolean; reason: string | null };
type Reason = { code: string; label: string; link?: string | null };

export type InvoiceDetail = {
  version: number;
  facts: {
    id: string;
    invoice_number: string;
    client_id: string;
    client_name: string;
    status: string;
    currency: string;
    issue_date: string | null;
    due_date: string;
    gross_minor: number;
    subtotal_minor: number | null;
    tax_minor: number | null;
    payment_terms: string | null;
    po_number: string | null;
    project_ref: string | null;
    description: string | null;
    diverges_from_source: boolean;
    corrected_fields: string[];
  };
  derived: {
    payment_status: string;
    evidence_coverage: string;
    evidence_as_of: string | null;
    outstanding_minor: number;
    paid_minor: number;
    overpayment_flag: boolean;
    dispute_status: string;
    reminder_status: string;
    days_overdue: number;
  };
  ai_claims: unknown[];
  provenance: { source_system: string; file_name: string | null; source_row: number | null };
  recommended_action: { code: string; label: string } | null;
  reasons: Reason[];
  why_not: Reason[];
  allowed_actions: Verdict[];
};
