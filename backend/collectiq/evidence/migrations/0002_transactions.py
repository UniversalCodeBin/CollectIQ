"""Imported statement rows (TSD M09). A row is evidence: added, voided or marked duplicate, never rewritten."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
ALTER TABLE stored_files DROP CONSTRAINT stored_files_kind_check;
ALTER TABLE stored_files ADD CONSTRAINT stored_files_kind_check
    CHECK (kind IN ('INVOICE_CSV', 'STATEMENT_CSV'));
ALTER TABLE import_batches DROP CONSTRAINT import_batches_kind_check;
ALTER TABLE import_batches ADD CONSTRAINT import_batches_kind_check
    CHECK (kind IN ('INVOICE_CSV', 'STATEMENT_CSV'));
ALTER TABLE import_batches ADD COLUMN payment_account_id uuid;
ALTER TABLE import_batches ADD FOREIGN KEY (workspace_id, payment_account_id)
    REFERENCES payment_accounts (workspace_id, id);

CREATE TABLE payment_transactions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    payment_account_id uuid NOT NULL,
    source_type text NOT NULL CHECK (source_type IN ('BANK_CSV', 'UPI_CSV', 'CASH_LOG')),
    direction text NOT NULL DEFAULT 'CREDIT' CHECK (direction IN ('CREDIT', 'DEBIT')),
    amount_minor bigint NOT NULL CHECK (amount_minor > 0),
    currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    value_date date NOT NULL,
    reference text,
    reference_candidates text[] NOT NULL DEFAULT '{}',
    payer_descriptor text,
    balance_minor bigint,
    fingerprint text NOT NULL,
    occurrence_index integer NOT NULL DEFAULT 0 CHECK (occurrence_index >= 0),
    external_id text,
    evidence_type text NOT NULL DEFAULT 'STATEMENT_ROW' CHECK (evidence_type IN ('STATEMENT_ROW')),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'VOID', 'DUPLICATE')),
    duplicate_of_transaction_id uuid,
    import_batch_id uuid,
    entered_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, payment_account_id, fingerprint, occurrence_index),
    FOREIGN KEY (workspace_id, payment_account_id) REFERENCES payment_accounts (workspace_id, id),
    FOREIGN KEY (workspace_id, import_batch_id) REFERENCES import_batches (workspace_id, id),
    FOREIGN KEY (workspace_id, duplicate_of_transaction_id) REFERENCES payment_transactions (workspace_id, id)
);
CREATE UNIQUE INDEX payment_transactions_external
    ON payment_transactions (workspace_id, source_type, external_id) WHERE external_id IS NOT NULL;
CREATE INDEX payment_transactions_account_date
    ON payment_transactions (workspace_id, payment_account_id, value_date);
CREATE INDEX payment_transactions_open ON payment_transactions (workspace_id, status, direction);
"""
DROP = """
DROP TABLE payment_transactions;
ALTER TABLE import_batches DROP COLUMN payment_account_id;
ALTER TABLE import_batches DROP CONSTRAINT import_batches_kind_check;
ALTER TABLE import_batches ADD CONSTRAINT import_batches_kind_check CHECK (kind IN ('INVOICE_CSV'));
ALTER TABLE stored_files DROP CONSTRAINT stored_files_kind_check;
ALTER TABLE stored_files ADD CONSTRAINT stored_files_kind_check CHECK (kind IN ('INVOICE_CSV'));
"""

# Never deleted. Only the status and the duplicate pointer may change; amount, date and account may not.
PRIVILEGES = """
REVOKE DELETE, UPDATE ON payment_transactions FROM collectiq_app;
GRANT UPDATE (status, duplicate_of_transaction_id) ON payment_transactions TO collectiq_app;
"""


class Migration(migrations.Migration):
    dependencies = [("evidence", "0001_accounts")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=DROP),
        enable_rls("payment_transactions"),
        migrations.RunSQL(PRIVILEGES, reverse_sql=migrations.RunSQL.noop),
    ]
