"""A third AI opt-in, for the invoice brief agent. Off by default, like the others."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0002_ai_settings")]
    operations = [
        migrations.RunSQL(
            "ALTER TABLE workspace_ai_settings ADD COLUMN invoice_brief_enabled boolean NOT NULL DEFAULT false;",
            reverse_sql="ALTER TABLE workspace_ai_settings DROP COLUMN invoice_brief_enabled;",
        )
    ]
