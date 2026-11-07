"""Per-client and per-invoice reminder pauses. A resumed pause stays as history; it is never deleted."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE reminder_pauses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    scope text NOT NULL CHECK (scope IN ('CLIENT', 'INVOICE')),
    client_id uuid,
    invoice_id uuid,
    reason text CHECK (char_length(reason) <= 500),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'RESUMED')),
    paused_by uuid NOT NULL REFERENCES users (id),
    paused_at timestamptz NOT NULL DEFAULT now(),
    resumed_by uuid REFERENCES users (id),
    resumed_at timestamptz,
    CONSTRAINT pause_has_one_target CHECK (
        (scope = 'CLIENT' AND client_id IS NOT NULL AND invoice_id IS NULL)
        OR (scope = 'INVOICE' AND invoice_id IS NOT NULL AND client_id IS NULL)),
    CONSTRAINT resumed_has_resumer CHECK (status = 'ACTIVE' OR (resumed_by IS NOT NULL AND resumed_at IS NOT NULL)),
    FOREIGN KEY (workspace_id, client_id) REFERENCES clients (workspace_id, id),
    FOREIGN KEY (workspace_id, invoice_id) REFERENCES invoices (workspace_id, id)
);
CREATE UNIQUE INDEX reminder_pauses_one_client ON reminder_pauses (client_id) WHERE status = 'ACTIVE';
CREATE UNIQUE INDEX reminder_pauses_one_invoice ON reminder_pauses (invoice_id) WHERE status = 'ACTIVE';
CREATE INDEX reminder_pauses_workspace ON reminder_pauses (workspace_id, paused_at DESC);
"""


class Migration(migrations.Migration):
    dependencies = [("comms", "0002_send_states"), ("invoices", "0003_invoice_state")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql="DROP TABLE reminder_pauses;"),
        enable_rls("reminder_pauses"),
    ]
