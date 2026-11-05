"""Per-workspace AI opt-ins. Both default to off: nothing leaves the application until an Owner turns it on."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE workspace_ai_settings (
    workspace_id uuid PRIMARY KEY REFERENCES workspaces (id),
    pdf_extraction_enabled boolean NOT NULL DEFAULT false,
    reply_interpretation_enabled boolean NOT NULL DEFAULT false,
    kill_switch boolean NOT NULL DEFAULT false,
    updated_by uuid REFERENCES users (id),
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0001_tenancy")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql="DROP TABLE workspace_ai_settings;"),
        enable_rls("workspace_ai_settings"),
    ]
