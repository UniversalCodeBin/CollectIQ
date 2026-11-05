"""Customer replies a person pasted in, what they were taken to mean, promises, and snoozes.

The body is encrypted. A label is a person's reading of a message; it never marks anything paid.
"""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    source text NOT NULL CHECK (source IN ('PASTE', 'EML', 'TXT')),
    sender text CHECK (char_length(sender) <= 320),
    subject text CHECK (char_length(subject) <= 500),
    received_at timestamptz NOT NULL,
    body_enc bytea NOT NULL,
    body_sha256 text NOT NULL,
    uploaded_by uuid NOT NULL REFERENCES users (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id)
);
CREATE INDEX messages_workspace_created ON messages (workspace_id, created_at DESC);

CREATE TABLE message_invoices (
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    message_id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    labels text[] NOT NULL DEFAULT '{}',
    associated_by uuid NOT NULL REFERENCES users (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (message_id, invoice_id),
    FOREIGN KEY (workspace_id, message_id) REFERENCES messages (workspace_id, id),
    FOREIGN KEY (workspace_id, invoice_id) REFERENCES invoices (workspace_id, id)
);
CREATE INDEX message_invoices_invoice ON message_invoices (workspace_id, invoice_id);

CREATE TABLE commitments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    invoice_id uuid NOT NULL,
    source_message_id uuid,
    strength text NOT NULL CHECK (strength IN ('EXPLICIT', 'TENTATIVE')),
    promised_date date,
    window_start date,
    window_end date,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'WITHDRAWN', 'BROKEN')),
    note text CHECK (char_length(note) <= 1000),
    created_by uuid NOT NULL REFERENCES users (id),
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, invoice_id) REFERENCES invoices (workspace_id, id),
    CONSTRAINT has_a_date CHECK (promised_date IS NOT NULL OR window_end IS NOT NULL OR strength = 'TENTATIVE'),
    CONSTRAINT window_ordered CHECK (window_start IS NULL OR window_end IS NULL OR window_start <= window_end),
    UNIQUE (workspace_id, id)
);
CREATE INDEX commitments_invoice ON commitments (workspace_id, invoice_id);

CREATE TABLE verification_tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    invoice_id uuid NOT NULL,
    message_id uuid NOT NULL,
    kind text NOT NULL CHECK (kind IN ('PAYMENT_CLAIM')),
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
    closed_by uuid REFERENCES users (id),
    closed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, invoice_id) REFERENCES invoices (workspace_id, id),
    FOREIGN KEY (workspace_id, message_id) REFERENCES messages (workspace_id, id),
    UNIQUE (message_id, invoice_id, kind)
);

CREATE TABLE snoozes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    invoice_id uuid NOT NULL,
    commitment_id uuid,
    until date NOT NULL,
    status text NOT NULL DEFAULT 'PROPOSED'
        CHECK (status IN ('PROPOSED', 'ACTIVE', 'UNDONE', 'ENDED', 'DISCARDED')),
    prior_reminder_status text,
    approval_id uuid NOT NULL UNIQUE,
    proposed_by uuid NOT NULL REFERENCES users (id),
    approved_by uuid REFERENCES users (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    activated_at timestamptz,
    ended_at timestamptz,
    CONSTRAINT active_has_approver CHECK (status <> 'ACTIVE' OR (approved_by IS NOT NULL
        AND prior_reminder_status IS NOT NULL)),
    FOREIGN KEY (workspace_id, invoice_id) REFERENCES invoices (workspace_id, id)
);
CREATE UNIQUE INDEX snoozes_one_active ON snoozes (invoice_id) WHERE status = 'ACTIVE';
"""

DROP = """
DROP TABLE snoozes;
DROP TABLE verification_tasks;
DROP TABLE commitments;
DROP TABLE message_invoices;
DROP TABLE messages;
"""


class Migration(migrations.Migration):
    initial = True
    dependencies = [("invoices", "0003_invoice_state"), ("tenancy", "0001_tenancy"), ("cases", "0001_cases")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=DROP),
        enable_rls("messages"),
        enable_rls("message_invoices"),
        enable_rls("commitments"),
        enable_rls("verification_tasks"),
        enable_rls("snoozes"),
    ]
