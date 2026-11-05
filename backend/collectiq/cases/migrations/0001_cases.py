"""Disputes and blockers (SAD cases), with the notes people add. Only a person can resolve one."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE cases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    invoice_id uuid NOT NULL,
    type text NOT NULL CHECK (type IN ('DISPUTE', 'MISSING_DOCUMENT', 'QUESTION', 'PROPOSAL')),
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'IN_REVIEW', 'AWAITING_CUSTOMER', 'RESOLVED')),
    dispute_type text CHECK (dispute_type IN ('AMOUNT', 'DELIVERABLE', 'SERVICE', 'OTHER')),
    summary text NOT NULL CHECK (length(summary) BETWEEN 1 AND 2000),
    source_message_id uuid,
    assignee_id uuid REFERENCES users (id),
    opened_by_kind text NOT NULL CHECK (opened_by_kind IN ('USER', 'SYSTEM', 'AI')),
    opened_by uuid REFERENCES users (id),
    opened_at timestamptz NOT NULL DEFAULT now(),
    resolution_outcome text CHECK (resolution_outcome IN
        ('NO_CHANGE', 'INVOICE_CORRECTED', 'ADJUSTMENT_AGREED', 'WITHDRAWN_BY_CUSTOMER', 'OTHER')),
    resolution_note text,
    resolved_by uuid REFERENCES users (id),
    resolved_at timestamptz,
    reopen_count integer NOT NULL DEFAULT 0 CHECK (reopen_count >= 0),
    version integer NOT NULL DEFAULT 1,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, invoice_id) REFERENCES invoices (workspace_id, id),
    -- INV (BR-60): a case is resolved by a person who is recorded, with an outcome. Nothing else resolves one.
    CHECK ((status = 'RESOLVED') = (resolved_by IS NOT NULL AND resolved_at IS NOT NULL
                                    AND resolution_outcome IS NOT NULL)),
    CHECK (type = 'DISPUTE' OR dispute_type IS NULL)
);
-- One open dispute per invoice (SAD): a second one is a duplicate, not a new record.
CREATE UNIQUE INDEX cases_one_open_dispute ON cases (invoice_id)
    WHERE type = 'DISPUTE' AND status <> 'RESOLVED';
CREATE INDEX cases_queue ON cases (workspace_id, status, assignee_id);
CREATE INDEX cases_invoice ON cases (workspace_id, invoice_id);

CREATE TABLE case_notes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    case_id uuid NOT NULL,
    author_id uuid NOT NULL REFERENCES users (id),
    kind text NOT NULL CHECK (kind IN ('NOTE', 'STATUS', 'ASSIGNMENT', 'RESOLUTION', 'REOPEN')),
    body text NOT NULL CHECK (length(body) BETWEEN 1 AND 2000),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, case_id) REFERENCES cases (workspace_id, id)
);
CREATE INDEX case_notes_case ON case_notes (workspace_id, case_id, created_at);

REVOKE DELETE, TRUNCATE ON cases FROM collectiq_app;
REVOKE UPDATE, DELETE, TRUNCATE ON case_notes FROM collectiq_app;
"""

DROP = """
DROP TABLE case_notes;
DROP TABLE cases;
"""


class Migration(migrations.Migration):
    initial = True
    dependencies = [("invoices", "0003_invoice_state"), ("tenancy", "0001_tenancy")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=DROP),
        enable_rls("cases"),
        enable_rls("case_notes"),
    ]
