"""Reminder drafts a person approves and then sends by hand. Nothing here is ever sent by the system."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE reminders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    invoice_id uuid NOT NULL,
    contact_id uuid NOT NULL,
    sequence integer NOT NULL CHECK (sequence >= 1),
    intended_date date NOT NULL,
    status text NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'APPROVED', 'MARKED_SENT', 'REJECTED', 'CANCELLED')),
    subject text NOT NULL CHECK (char_length(subject) BETWEEN 1 AND 300),
    body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 5000),
    fact_block jsonb NOT NULL,
    fact_hash text NOT NULL,
    idempotency_key text NOT NULL,
    state_version integer NOT NULL,
    approved_by uuid REFERENCES users (id),
    approved_at timestamptz,
    sent_at timestamptz,
    method text CHECK (method IN ('EMAIL', 'WHATSAPP', 'PHONE', 'OTHER')),
    marked_by uuid REFERENCES users (id),
    marked_at timestamptz,
    rejected_by uuid REFERENCES users (id),
    reason text CHECK (char_length(reason) <= 1000),
    created_by uuid NOT NULL REFERENCES users (id),
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, invoice_id) REFERENCES invoices (workspace_id, id),
    FOREIGN KEY (workspace_id, contact_id) REFERENCES client_contacts (workspace_id, id),
    CONSTRAINT approved_has_approver CHECK (status NOT IN ('APPROVED', 'MARKED_SENT') OR approved_by IS NOT NULL),
    CONSTRAINT sent_has_record CHECK (status <> 'MARKED_SENT' OR (sent_at IS NOT NULL AND method IS NOT NULL
        AND marked_by IS NOT NULL)),
    UNIQUE (workspace_id, id)
);
CREATE INDEX reminders_invoice ON reminders (workspace_id, invoice_id, created_at DESC);
CREATE INDEX reminders_workspace_created ON reminders (workspace_id, created_at DESC);
-- TS-014: one live record per invoice, step and intended date, however often the evaluation is retried.
CREATE UNIQUE INDEX reminders_one_live_key ON reminders (workspace_id, idempotency_key)
    WHERE status IN ('DRAFT', 'APPROVED', 'MARKED_SENT');
"""

DROP = "DROP TABLE reminders;"


class Migration(migrations.Migration):
    initial = True
    dependencies = [("invoices", "0003_invoice_state"), ("tenancy", "0001_tenancy")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=DROP),
        enable_rls("reminders"),
    ]
