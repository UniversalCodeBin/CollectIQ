from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE reconciliation_matches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    transaction_id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'PROPOSED'
        CHECK (status IN ('PROPOSED', 'CONFIRMED', 'REJECTED', 'SUPERSEDED')),
    band text NOT NULL CHECK (band IN ('HIGH', 'MEDIUM', 'LOW')),
    score integer NOT NULL CHECK (score >= 0),
    ambiguous boolean NOT NULL DEFAULT false,
    factors jsonb NOT NULL,
    matcher_version text NOT NULL,
    inputs_hash text NOT NULL,
    decided_by uuid,
    decided_at timestamptz,
    decision_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, transaction_id) REFERENCES payment_transactions (workspace_id, id),
    FOREIGN KEY (workspace_id, invoice_id) REFERENCES invoices (workspace_id, id)
);
CREATE UNIQUE INDEX reconciliation_matches_one_proposal
    ON reconciliation_matches (workspace_id, transaction_id, invoice_id) WHERE status = 'PROPOSED';
CREATE INDEX reconciliation_matches_invoice ON reconciliation_matches (workspace_id, invoice_id, status);
CREATE INDEX reconciliation_matches_transaction ON reconciliation_matches (workspace_id, transaction_id, status);
CREATE INDEX reconciliation_matches_rejected
    ON reconciliation_matches (workspace_id, transaction_id, invoice_id, inputs_hash) WHERE status = 'REJECTED';
"""
DROP = "DROP TABLE reconciliation_matches;"

# A decision history is kept: rows are never deleted, and only the decision columns change.
PRIVILEGES = """
REVOKE DELETE, UPDATE ON reconciliation_matches FROM collectiq_app;
GRANT UPDATE (status, decided_by, decided_at, decision_reason) ON reconciliation_matches TO collectiq_app;
"""


class Migration(migrations.Migration):
    dependencies = [("evidence", "0002_transactions"), ("invoices", "0003_invoice_state")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=DROP),
        enable_rls("reconciliation_matches"),
        migrations.RunSQL(PRIVILEGES, reverse_sql=migrations.RunSQL.noop),
    ]
