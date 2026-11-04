"""Migration helper that puts a tenant table under forced row-level security."""
import re

from django.db import migrations

# NULLIF is essential: after SET LOCAL ends the setting reverts to '', and a bare cast would raise.
WORKSPACE_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_TABLE = re.compile(r"[a-z_][a-z0-9_]*")


def enable_rls(table: str) -> migrations.RunSQL:
    if not _TABLE.fullmatch(table):
        raise ValueError(f"unsafe table name: {table!r}")
    policy = f"{table}_tenant_isolation"
    return migrations.RunSQL(
        sql=f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {policy} ON {table}
          USING ({WORKSPACE_PREDICATE})
          WITH CHECK ({WORKSPACE_PREDICATE});
        """,
        reverse_sql=f"""
        DROP POLICY {policy} ON {table};
        ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
        """,
    )
