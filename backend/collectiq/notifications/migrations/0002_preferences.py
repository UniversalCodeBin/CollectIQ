"""Per-person choice of which in-app notifications to receive. Absent row means on."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE notification_preferences (
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    user_id uuid NOT NULL REFERENCES users (id),
    type text NOT NULL CHECK (type IN ('CASE_OPENED', 'REMINDER_DRAFT_READY')),
    in_app boolean NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, user_id, type)
);
"""


class Migration(migrations.Migration):
    dependencies = [("notifications", "0001_notifications")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql="DROP TABLE notification_preferences;"),
        enable_rls("notification_preferences"),
    ]
