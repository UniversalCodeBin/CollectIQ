"""Provider submission states. SUBMITTED means handed to the mail provider, never that it was delivered."""

from django.db import migrations

UP = """
ALTER TABLE reminders DROP CONSTRAINT reminders_status_check;
ALTER TABLE reminders ADD CONSTRAINT reminders_status_check CHECK (status IN (
    'DRAFT', 'APPROVED', 'SUBMITTING', 'SUBMITTED', 'SUBMISSION_UNKNOWN', 'MARKED_SENT', 'REJECTED', 'CANCELLED'));
ALTER TABLE reminders DROP CONSTRAINT approved_has_approver;
ALTER TABLE reminders ADD CONSTRAINT approved_has_approver CHECK (
    status NOT IN ('APPROVED', 'SUBMITTING', 'SUBMITTED', 'SUBMISSION_UNKNOWN', 'MARKED_SENT')
    OR approved_by IS NOT NULL);
ALTER TABLE reminders ADD COLUMN provider_message_id text;
ALTER TABLE reminders ADD COLUMN submitted_at timestamptz;
ALTER TABLE reminders ADD COLUMN send_error text;
DROP INDEX reminders_one_live_key;
CREATE UNIQUE INDEX reminders_one_live_key ON reminders (workspace_id, idempotency_key)
    WHERE status IN ('DRAFT', 'APPROVED', 'SUBMITTING', 'SUBMITTED', 'SUBMISSION_UNKNOWN', 'MARKED_SENT');
"""

DOWN = """
DROP INDEX reminders_one_live_key;
CREATE UNIQUE INDEX reminders_one_live_key ON reminders (workspace_id, idempotency_key)
    WHERE status IN ('DRAFT', 'APPROVED', 'MARKED_SENT');
ALTER TABLE reminders DROP COLUMN send_error, DROP COLUMN submitted_at, DROP COLUMN provider_message_id;
ALTER TABLE reminders DROP CONSTRAINT approved_has_approver;
ALTER TABLE reminders ADD CONSTRAINT approved_has_approver CHECK (
    status NOT IN ('APPROVED', 'MARKED_SENT') OR approved_by IS NOT NULL);
ALTER TABLE reminders DROP CONSTRAINT reminders_status_check;
ALTER TABLE reminders ADD CONSTRAINT reminders_status_check CHECK (status IN (
    'DRAFT', 'APPROVED', 'MARKED_SENT', 'REJECTED', 'CANCELLED'));
"""


class Migration(migrations.Migration):
    dependencies = [("comms", "0001_reminders")]
    operations = [migrations.RunSQL(UP, reverse_sql=DOWN)]
