"""Declared receiving accounts, the date ranges looked at, and attestations (TSD M08)."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE payment_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    kind text NOT NULL CHECK (kind IN ('BANK', 'PAYPAL', 'UPI', 'CASH')),
    label text NOT NULL CHECK (char_length(label) BETWEEN 1 AND 100),
    currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE')),
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id)
);
CREATE UNIQUE INDEX payment_accounts_label ON payment_accounts (workspace_id, lower(label));
CREATE INDEX payment_accounts_status ON payment_accounts (workspace_id, status);

CREATE TABLE account_coverages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    payment_account_id uuid NOT NULL,
    covers_from date NOT NULL,
    covers_to date NOT NULL,
    import_batch_id uuid,
    confirmed_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT coverage_range_ordered CHECK (covers_to >= covers_from),
    FOREIGN KEY (workspace_id, payment_account_id) REFERENCES payment_accounts (workspace_id, id),
    FOREIGN KEY (workspace_id, import_batch_id) REFERENCES import_batches (workspace_id, id)
);
CREATE INDEX account_coverages_account ON account_coverages (workspace_id, payment_account_id, covers_to);

CREATE TABLE evidence_attestations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    scope text NOT NULL CHECK (scope IN ('ACCOUNT', 'INVOICE')),
    payment_account_id uuid,
    invoice_id uuid,
    as_of timestamptz NOT NULL,
    note text CHECK (char_length(note) <= 1000),
    attested_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT attestation_scope_matches CHECK (
        (scope = 'ACCOUNT' AND payment_account_id IS NOT NULL AND invoice_id IS NULL)
        OR (scope = 'INVOICE' AND invoice_id IS NOT NULL AND payment_account_id IS NULL)
    ),
    FOREIGN KEY (workspace_id, payment_account_id) REFERENCES payment_accounts (workspace_id, id),
    FOREIGN KEY (workspace_id, invoice_id) REFERENCES invoices (workspace_id, id)
);
CREATE INDEX evidence_attestations_account ON evidence_attestations (workspace_id, payment_account_id, as_of);
CREATE INDEX evidence_attestations_invoice ON evidence_attestations (workspace_id, invoice_id, as_of);
"""
DROP = "DROP TABLE evidence_attestations; DROP TABLE account_coverages; DROP TABLE payment_accounts;"

# What was looked at, and who said so, is a record: it is added to and never rewritten or removed.
PRIVILEGES = """
REVOKE UPDATE, DELETE ON account_coverages, evidence_attestations FROM collectiq_app;
REVOKE DELETE ON payment_accounts FROM collectiq_app;
"""


class Migration(migrations.Migration):
    initial = True
    dependencies = [("tenancy", "0001_tenancy"), ("invoices", "0003_invoice_state")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=DROP),
        enable_rls("payment_accounts"),
        enable_rls("account_coverages"),
        enable_rls("evidence_attestations"),
        migrations.RunSQL(PRIVILEGES, reverse_sql=migrations.RunSQL.noop),
    ]
