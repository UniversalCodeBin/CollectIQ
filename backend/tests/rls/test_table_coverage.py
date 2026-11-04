"""Every table is either tenant-scoped under forced RLS, or named here with its reason."""
import psycopg

# Global by design (SAD 370): a user can belong to many workspaces, and these exist before any workspace does.
NON_TENANT_TABLES = {
    "users",
    "user_sessions",
    "auth_tokens",
    "auth_throttles",
    "django_migrations",
    "django_content_type",
}


def _tables(owner_db: psycopg.Connection) -> dict[str, tuple[bool, bool, int]]:
    rows = owner_db.execute(
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
               (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
        """
    ).fetchall()
    return {name: (enabled, forced, policies) for name, enabled, forced, policies in rows}


def test_every_tenant_table_has_forced_rls(pg, owner_db: psycopg.Connection) -> None:
    tables = _tables(owner_db)
    unprotected = {
        name: state
        for name, state in tables.items()
        if name not in NON_TENANT_TABLES and not (state[0] and state[1] and state[2] > 0)
    }
    assert unprotected == {}


def test_allowlist_names_real_tables_without_a_tenant_column(pg, owner_db: psycopg.Connection) -> None:
    assert NON_TENANT_TABLES - set(_tables(owner_db)) == set()
    tenant_columns = owner_db.execute(
        "SELECT table_name FROM information_schema.columns"
        " WHERE table_schema = 'public' AND column_name = 'workspace_id' AND table_name = ANY(%s)",
        [sorted(NON_TENANT_TABLES)],
    ).fetchall()
    assert tenant_columns == []
