"""Privacy tables: export requests, the redacted AI payload as sent (kept apart from the processing record), and the final deletion record.

`deletion_records.workspace_id` has no foreign key on purpose: the record outlives the workspace's data.
The deletion procedure runs as the table owner (SECURITY DEFINER). It deletes only rows of the workspace
it is given, scans for leftovers and raises (rolling everything back) if any remain.
"""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE ai_payloads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    processing_id uuid NOT NULL,
    redacted_input jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, processing_id) REFERENCES ai_processing_records (workspace_id, id),
    UNIQUE (workspace_id, processing_id)
);

CREATE TABLE export_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    requested_by uuid,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'READY', 'FAILED')),
    storage_key text,
    size_bytes bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    expires_at timestamptz NOT NULL
);

CREATE TABLE deletion_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    requested_by uuid,
    tables_cleared integer NOT NULL,
    rows_deleted bigint NOT NULL,
    rows_remaining bigint NOT NULL CHECK (rows_remaining = 0),
    completed_at timestamptz NOT NULL DEFAULT now()
);

REVOKE UPDATE, DELETE, TRUNCATE ON deletion_records FROM collectiq_app;
REVOKE INSERT ON deletion_records FROM collectiq_app;
"""

# Tables the procedure leaves alone: the append-only audit history, the final record and the workspace row.
FUNCTION = """
CREATE FUNCTION privacy_delete_workspace(ws uuid, actor uuid) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    t text;
    removed bigint := 0;
    pass_removed bigint;
    n bigint;
    cleared integer := 0;
    remaining bigint := 0;
    tables text[];
BEGIN
    PERFORM set_config('app.workspace_id', ws::text, true);
    SELECT array_agg(c.table_name::text ORDER BY c.table_name) INTO tables
    FROM information_schema.columns c
    JOIN information_schema.tables x
      ON x.table_schema = c.table_schema AND x.table_name = c.table_name AND x.table_type = 'BASE TABLE'
    WHERE c.table_schema = 'public' AND c.column_name = 'workspace_id'
      AND c.table_name NOT IN ('audit_events', 'deletion_records', 'workspaces');
    UPDATE public.workspaces SET name = '[deleted]', business_hours = '{}', active_policy_id = NULL,
        status = 'DELETED', updated_at = now() WHERE id = ws;
    ALTER TABLE public.payment_allocations DISABLE TRIGGER payment_allocations_append_only;
    FOR pass IN 1..12 LOOP
        pass_removed := 0;
        FOREACH t IN ARRAY tables LOOP
            BEGIN
                EXECUTE format('DELETE FROM public.%I WHERE workspace_id = $1', t) USING ws;
                GET DIAGNOSTICS n = ROW_COUNT;
                pass_removed := pass_removed + n;
            EXCEPTION WHEN foreign_key_violation THEN
                NULL;
            END;
        END LOOP;
        removed := removed + pass_removed;
        EXIT WHEN pass_removed = 0 AND pass > 1;
    END LOOP;
    ALTER TABLE public.payment_allocations ENABLE TRIGGER payment_allocations_append_only;
    FOREACH t IN ARRAY tables LOOP
        EXECUTE format('SELECT count(*) FROM public.%I WHERE workspace_id = $1', t) INTO n USING ws;
        remaining := remaining + n;
        cleared := cleared + 1;
    END LOOP;
    IF remaining > 0 THEN
        RAISE EXCEPTION 'workspace deletion left % rows behind', remaining;
    END IF;
    INSERT INTO public.deletion_records (workspace_id, requested_by, tables_cleared, rows_deleted, rows_remaining)
    VALUES (ws, actor, cleared, removed, remaining);
    RETURN removed;
END $$;
REVOKE ALL ON FUNCTION privacy_delete_workspace(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION privacy_delete_workspace(uuid, uuid) TO collectiq_app;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0001_tenancy"),
        ("conversations", "0002_interpretations"),
        ("evidence", "0005_payment_attachment"),
        ("audit", "0001_audit_events"),
    ]
    operations = [
        migrations.RunSQL(
            CREATE,
            reverse_sql="DROP TABLE deletion_records; DROP TABLE export_requests; DROP TABLE ai_payloads;",
        ),
        enable_rls("ai_payloads"),
        enable_rls("export_requests"),
        enable_rls("deletion_records"),
        migrations.RunSQL(FUNCTION, reverse_sql="DROP FUNCTION privacy_delete_workspace(uuid, uuid);"),
    ]
