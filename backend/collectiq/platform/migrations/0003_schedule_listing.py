"""The scheduler needs to know which workspaces exist, and the app role cannot see across tenants."""

from django.db import migrations

LISTING_FUNCTION = """
CREATE FUNCTION workspace_ids_for_schedule() RETURNS SETOF uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
  RETURN QUERY SELECT w.id FROM public.workspaces AS w ORDER BY w.id;
END
$$;
REVOKE ALL ON FUNCTION workspace_ids_for_schedule() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION workspace_ids_for_schedule() TO collectiq_app;
"""

# Names only the owner role, which is what the function runs as. The app role still sees just its workspace.
OWNER_READ_POLICY = """
CREATE POLICY workspaces_schedule_listing ON workspaces FOR SELECT TO collectiq_owner USING (true);
"""


class Migration(migrations.Migration):
    dependencies = [("platform", "0002_runtime_tables"), ("tenancy", "0001_tenancy")]

    operations = [
        migrations.RunSQL(
            OWNER_READ_POLICY, reverse_sql="DROP POLICY workspaces_schedule_listing ON workspaces;"
        ),
        migrations.RunSQL(LISTING_FUNCTION, reverse_sql="DROP FUNCTION workspace_ids_for_schedule();"),
    ]
