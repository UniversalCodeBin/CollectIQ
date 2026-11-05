"""Invoice lifecycle states, derived state per invoice, and the PRD's name for a failed import."""

from django.db import migrations
from django.db.migrations import RunSQL

from collectiq.platform.rls import enable_rls

INVOICE_STATUS = """
ALTER TABLE invoices DROP CONSTRAINT invoices_status_check;
ALTER TABLE invoices ADD CONSTRAINT invoices_status_check
    CHECK (status IN ('PENDING_REVIEW', 'ACTIVE', 'CANCELLED', 'WRITTEN_OFF', 'ARCHIVED'));
ALTER TABLE invoices ADD COLUMN assignee_id uuid;
CREATE INDEX invoices_assignee ON invoices (workspace_id, assignee_id) WHERE assignee_id IS NOT NULL;
"""
INVOICE_STATUS_REVERSE = """
DROP INDEX invoices_assignee;
ALTER TABLE invoices DROP COLUMN assignee_id;
ALTER TABLE invoices DROP CONSTRAINT invoices_status_check;
ALTER TABLE invoices ADD CONSTRAINT invoices_status_check CHECK (status IN ('ACTIVE', 'VOID'));
"""

CREATE_STATE = """
CREATE TABLE invoice_state (
    invoice_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    payment_status text NOT NULL DEFAULT 'OUTSTANDING' CHECK (payment_status IN
        ('OUTSTANDING', 'PARTIALLY_PAID', 'PAID_VERIFIED', 'AWAITING_VERIFICATION', 'UNCERTAIN')),
    evidence_coverage text NOT NULL DEFAULT 'MISSING' CHECK (evidence_coverage IN
        ('SUPPORTED', 'STALE', 'MISSING')),
    coverage_as_of timestamptz,
    paid_minor bigint NOT NULL DEFAULT 0 CHECK (paid_minor >= 0),
    outstanding_minor bigint NOT NULL CHECK (outstanding_minor >= 0),
    overpayment_flag boolean NOT NULL DEFAULT false,
    dispute_status text NOT NULL DEFAULT 'NONE' CHECK (dispute_status IN
        ('NONE', 'OPEN', 'IN_REVIEW', 'AWAITING_CUSTOMER', 'RESOLVED')),
    reminder_status text NOT NULL DEFAULT 'NOT_CONTACTED' CHECK (reminder_status IN
        ('NOT_CONTACTED', 'DRAFT_READY', 'SCHEDULED', 'SNOOZED', 'WAITING_FOR_CUSTOMER',
         'NEEDS_REVIEW', 'SUPPRESSED', 'RESOLVED')),
    snooze_until date,
    next_evaluation_at timestamptz,
    open_task_count integer NOT NULL DEFAULT 0 CHECK (open_task_count >= 0),
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, invoice_id) REFERENCES invoices (workspace_id, id)
);
CREATE INDEX invoice_state_reminder ON invoice_state (workspace_id, reminder_status, next_evaluation_at);
CREATE INDEX invoice_state_payment ON invoice_state (workspace_id, payment_status);
"""
DROP_STATE = "DROP TABLE invoice_state;"

PRIVILEGES = "REVOKE DELETE ON invoice_state FROM collectiq_app;"

# Forced row security hides every row from a migration, which has no workspace, so it is lifted for
# the length of each data step. A migration runs in one transaction, so nothing else sees the gap.
BACKFILL = """
ALTER TABLE invoices NO FORCE ROW LEVEL SECURITY;
ALTER TABLE invoice_state NO FORCE ROW LEVEL SECURITY;
INSERT INTO invoice_state (workspace_id, invoice_id, outstanding_minor)
SELECT workspace_id, id, gross_minor FROM invoices;
ALTER TABLE invoice_state FORCE ROW LEVEL SECURITY;
ALTER TABLE invoices FORCE ROW LEVEL SECURITY;
"""

RENAME_FAILED = """
ALTER TABLE import_batches NO FORCE ROW LEVEL SECURITY;
ALTER TABLE import_batches DROP CONSTRAINT import_batches_status_check;
UPDATE import_batches SET status = 'IMPORT_FAILED' WHERE status = 'FAILED';
ALTER TABLE import_batches ADD CONSTRAINT import_batches_status_check
    CHECK (status IN ('PREVIEW', 'COMMITTED', 'IMPORT_FAILED', 'DISCARDED'));
ALTER TABLE import_batches FORCE ROW LEVEL SECURITY;
"""
RENAME_FAILED_REVERSE = """
ALTER TABLE import_batches NO FORCE ROW LEVEL SECURITY;
ALTER TABLE import_batches DROP CONSTRAINT import_batches_status_check;
UPDATE import_batches SET status = 'FAILED' WHERE status = 'IMPORT_FAILED';
ALTER TABLE import_batches ADD CONSTRAINT import_batches_status_check
    CHECK (status IN ('PREVIEW', 'COMMITTED', 'FAILED', 'DISCARDED'));
ALTER TABLE import_batches FORCE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [("invoices", "0002_invoice_import")]

    operations = [
        RunSQL(INVOICE_STATUS, reverse_sql=INVOICE_STATUS_REVERSE),
        RunSQL(CREATE_STATE, reverse_sql=DROP_STATE),
        enable_rls("invoice_state"),
        RunSQL(PRIVILEGES, reverse_sql=RunSQL.noop),
        RunSQL(BACKFILL, reverse_sql=RunSQL.noop),
        RunSQL(RENAME_FAILED, reverse_sql=RENAME_FAILED_REVERSE),
    ]
