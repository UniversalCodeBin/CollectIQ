"""One proof file on a manual payment (FR-032). The file is a stored_files row; this table only links it."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
ALTER TABLE stored_files DROP CONSTRAINT stored_files_kind_check;
ALTER TABLE stored_files ADD CONSTRAINT stored_files_kind_check
    CHECK (kind IN ('INVOICE_CSV', 'STATEMENT_CSV', 'PAYMENT_ATTACHMENT'));
CREATE TABLE payment_attachments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    transaction_id uuid NOT NULL,
    file_id uuid NOT NULL,
    content_type text NOT NULL CHECK (content_type IN ('image/png', 'image/jpeg', 'application/pdf')),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, transaction_id),
    FOREIGN KEY (workspace_id, transaction_id) REFERENCES payment_transactions (workspace_id, id),
    FOREIGN KEY (workspace_id, file_id) REFERENCES stored_files (workspace_id, id)
);
"""
DROP = """
DROP TABLE payment_attachments;
DELETE FROM stored_files WHERE kind = 'PAYMENT_ATTACHMENT';
ALTER TABLE stored_files DROP CONSTRAINT stored_files_kind_check;
ALTER TABLE stored_files ADD CONSTRAINT stored_files_kind_check
    CHECK (kind IN ('INVOICE_CSV', 'STATEMENT_CSV'));
"""
PRIVILEGES = "REVOKE UPDATE, DELETE, TRUNCATE ON payment_attachments FROM collectiq_app;"


class Migration(migrations.Migration):
    dependencies = [("evidence", "0004_ledger_triggers")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=DROP),
        enable_rls("payment_attachments"),
        migrations.RunSQL(PRIVILEGES, reverse_sql=migrations.RunSQL.noop),
    ]
