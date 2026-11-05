"""PDF extractions: what a model read from an invoice PDF, held for a person to check before any invoice exists."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
ALTER TABLE stored_files DROP CONSTRAINT stored_files_kind_check;
ALTER TABLE stored_files ADD CONSTRAINT stored_files_kind_check
    CHECK (kind IN ('INVOICE_CSV', 'STATEMENT_CSV', 'PAYMENT_ATTACHMENT', 'INVOICE_PDF'));
CREATE TABLE invoice_extractions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    file_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'READY' CHECK (status IN
        ('READY', 'NEEDS_MANUAL_REVIEW', 'CONFIRMED', 'DISCARDED')),
    derived_by text NOT NULL DEFAULT 'AI' CHECK (derived_by = 'AI'),
    ai_fields jsonb NOT NULL DEFAULT '{}',
    fields jsonb NOT NULL DEFAULT '{}',
    dropped_fields text[] NOT NULL DEFAULT '{}',
    failure_code text,
    processing_record_id uuid,
    invoice_id uuid,
    version integer NOT NULL DEFAULT 1,
    created_by uuid REFERENCES users (id),
    confirmed_by uuid REFERENCES users (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, file_id) REFERENCES stored_files (workspace_id, id),
    FOREIGN KEY (workspace_id, invoice_id) REFERENCES invoices (workspace_id, id),
    CONSTRAINT confirmed_by_a_person CHECK (status <> 'CONFIRMED' OR confirmed_by IS NOT NULL),
    UNIQUE (workspace_id, id)
);
"""


class Migration(migrations.Migration):
    dependencies = [("invoices", "0003_invoice_state"), ("evidence", "0005_payment_attachment")]
    operations = [
        migrations.RunSQL(
            CREATE,
            reverse_sql=(
                "DROP TABLE invoice_extractions; DELETE FROM stored_files WHERE kind = 'INVOICE_PDF';"
                " ALTER TABLE stored_files DROP CONSTRAINT stored_files_kind_check;"
                " ALTER TABLE stored_files ADD CONSTRAINT stored_files_kind_check"
                " CHECK (kind IN ('INVOICE_CSV', 'STATEMENT_CSV', 'PAYMENT_ATTACHMENT'));"
            ),
        ),
        enable_rls("invoice_extractions"),
    ]
