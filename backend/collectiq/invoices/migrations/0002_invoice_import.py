from django.db import migrations
from django.db.migrations import RunSQL

from collectiq.platform.rls import enable_rls

CREATE_TABLES = """
CREATE TABLE stored_files (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    kind text NOT NULL CHECK (kind IN ('INVOICE_CSV')),
    storage_key text NOT NULL,
    file_name text NOT NULL CHECK (char_length(file_name) BETWEEN 1 AND 255),
    content_sha256 bytea NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    scan_status text NOT NULL DEFAULT 'NOT_SCANNED'
        CHECK (scan_status IN ('NOT_SCANNED', 'CLEAN', 'QUARANTINED')),
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, storage_key)
);

CREATE TABLE import_batches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    kind text NOT NULL CHECK (kind IN ('INVOICE_CSV')),
    file_id uuid NOT NULL,
    source_system text NOT NULL DEFAULT 'CSV',
    mapping jsonb,
    date_format text,
    status text NOT NULL DEFAULT 'PREVIEW'
        CHECK (status IN ('PREVIEW', 'COMMITTED', 'FAILED', 'DISCARDED')),
    counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    failure_reason text,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, file_id) REFERENCES stored_files (workspace_id, id)
);
CREATE INDEX import_batches_recent ON import_batches (workspace_id, created_at);

CREATE TABLE import_mappings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    kind text NOT NULL,
    mapping jsonb NOT NULL,
    date_format text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, kind)
);

CREATE TABLE invoices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    client_id uuid NOT NULL,
    source_system text NOT NULL DEFAULT 'CSV',
    external_id text,
    invoice_number text NOT NULL CHECK (char_length(invoice_number) BETWEEN 1 AND 128),
    normalized_number text NOT NULL,
    issue_date date,
    due_date date NOT NULL,
    currency char(3) NOT NULL,
    gross_minor bigint NOT NULL CHECK (gross_minor >= 0),
    subtotal_minor bigint CHECK (subtotal_minor >= 0),
    tax_minor bigint CHECK (tax_minor >= 0),
    payment_terms text,
    payment_references text[] NOT NULL DEFAULT '{}',
    po_number text,
    project_ref text,
    description text,
    line_items jsonb NOT NULL DEFAULT '[]'::jsonb,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'VOID')),
    possible_duplicate_of uuid,
    import_batch_id uuid,
    source_row integer,
    raw_row_ciphertext bytea,
    field_provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    diverges_from_source boolean NOT NULL DEFAULT false,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, client_id) REFERENCES clients (workspace_id, id),
    FOREIGN KEY (workspace_id, import_batch_id) REFERENCES import_batches (workspace_id, id),
    FOREIGN KEY (workspace_id, possible_duplicate_of) REFERENCES invoices (workspace_id, id)
);
CREATE UNIQUE INDEX invoices_source_identity ON invoices (workspace_id, source_system, external_id)
    WHERE external_id IS NOT NULL;
CREATE INDEX invoices_client_number ON invoices (workspace_id, client_id, normalized_number);
CREATE INDEX invoices_due ON invoices (workspace_id, due_date);
"""

DROP_TABLES = "DROP TABLE invoices, import_mappings, import_batches, stored_files;"

PRIVILEGES = "REVOKE DELETE ON invoices, import_batches, stored_files FROM collectiq_app;"


class Migration(migrations.Migration):
    dependencies = [("invoices", "0001_clients")]

    operations = [
        RunSQL(CREATE_TABLES, reverse_sql=DROP_TABLES),
        enable_rls("stored_files"),
        enable_rls("import_batches"),
        enable_rls("import_mappings"),
        enable_rls("invoices"),
        RunSQL(PRIVILEGES, reverse_sql=RunSQL.noop),
    ]
