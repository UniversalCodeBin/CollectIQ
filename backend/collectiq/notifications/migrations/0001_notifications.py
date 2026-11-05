"""In-app notifications: who should look at what. They carry ids and codes only, never customer text."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    user_id uuid NOT NULL REFERENCES users (id),
    type text NOT NULL CHECK (type IN ('CASE_OPENED', 'REMINDER_DRAFT_READY')),
    subject_ref jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    read_at timestamptz,
    UNIQUE (workspace_id, id),
    UNIQUE (user_id, type, subject_ref)
);
CREATE INDEX notifications_user ON notifications (user_id, read_at, created_at DESC);
"""

DROP = "DROP TABLE notifications;"


class Migration(migrations.Migration):
    initial = True
    dependencies = [("tenancy", "0001_tenancy")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=DROP),
        enable_rls("notifications"),
    ]
