"""A real table under forced RLS, so tests/rls proves the mechanism on what production runs."""
from django.db import migrations

from collectiq.platform.rls import enable_rls


class Migration(migrations.Migration):
    initial = True
    dependencies: list[tuple[str, str]] = []
    operations = [
        migrations.RunSQL(
            sql="""
            CREATE TABLE rls_probe (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              workspace_id uuid NOT NULL
            );
            """,
            reverse_sql="DROP TABLE rls_probe;",
        ),
        enable_rls("rls_probe"),
    ]
