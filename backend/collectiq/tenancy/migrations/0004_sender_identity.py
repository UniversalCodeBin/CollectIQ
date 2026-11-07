"""Who a reminder is from: the business's legal name and the name its messages are signed with (FR-122)."""

from django.db import migrations

UP = """
ALTER TABLE workspaces
    ADD COLUMN legal_name text CHECK (legal_name IS NULL OR length(legal_name) BETWEEN 1 AND 200),
    ADD COLUMN sender_name text CHECK (sender_name IS NULL OR length(sender_name) BETWEEN 1 AND 100);
"""
DOWN = "ALTER TABLE workspaces DROP COLUMN legal_name, DROP COLUMN sender_name;"


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0003_ai_brief_flag")]
    operations = [migrations.RunSQL(UP, reverse_sql=DOWN)]
