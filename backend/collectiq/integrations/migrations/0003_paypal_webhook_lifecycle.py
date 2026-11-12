"""Extend webhook_events with lifecycle processing statuses and execution metadata."""

from django.db import migrations

CREATE = """
ALTER TABLE webhook_events DROP CONSTRAINT webhook_events_status_check;
ALTER TABLE webhook_events ADD CONSTRAINT webhook_events_status_check
    CHECK (status IN (
        'RECEIVED', 'VERIFIED', 'PROCESSING', 'PROCESSED',
        'RETRYABLE_FAILURE', 'PERMANENT_FAILURE', 'REJECTED', 'EVIDENCE_ONLY'
    ));
ALTER TABLE webhook_events ADD COLUMN processed_at timestamptz;
ALTER TABLE webhook_events ADD COLUMN error_message text;
GRANT UPDATE ON webhook_events TO collectiq_app;
"""

REVERSE = """
REVOKE UPDATE ON webhook_events FROM collectiq_app;
ALTER TABLE webhook_events DROP COLUMN error_message;
ALTER TABLE webhook_events DROP COLUMN processed_at;
ALTER TABLE webhook_events DROP CONSTRAINT webhook_events_status_check;
ALTER TABLE webhook_events ADD CONSTRAINT webhook_events_status_check
    CHECK (status IN ('EVIDENCE_ONLY'));
"""


class Migration(migrations.Migration):
    dependencies = [("integrations", "0002_adapters")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=REVERSE),
    ]
