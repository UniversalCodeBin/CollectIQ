"""Tables behind idempotency, background jobs, the outbox and per-workspace data keys."""
from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE_TABLES = """
CREATE TABLE background_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  kind text NOT NULL,
  payload jsonb NOT NULL,
  dedupe_key text,
  status text NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED', 'RUNNING', 'DONE', 'DEAD_LETTER')),
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
  run_at timestamptz NOT NULL DEFAULT now(),
  lease_until timestamptz,
  lease_token uuid,
  last_error text,
  correlation_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX background_jobs_dedupe_idx ON background_jobs (workspace_id, kind, dedupe_key)
  WHERE dedupe_key IS NOT NULL;
CREATE INDEX background_jobs_claim_idx ON background_jobs (run_at, id) WHERE status IN ('QUEUED', 'RUNNING');

CREATE TABLE outbox_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL,
  correlation_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz
);
CREATE INDEX outbox_events_unpublished_idx ON outbox_events (workspace_id, created_at)
  WHERE published_at IS NULL;

CREATE TABLE idempotency_keys (
  workspace_id uuid NOT NULL,
  key uuid NOT NULL,
  request_hash bytea NOT NULL,
  response_status integer,
  response_body text,
  response_headers jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id, key)
);

CREATE TABLE workspace_keys (
  workspace_id uuid PRIMARY KEY,
  wrapped_key bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
"""

DROP_TABLES = "DROP TABLE workspace_keys, idempotency_keys, outbox_events, background_jobs;"

PRIVILEGES = """
GRANT SELECT, INSERT, UPDATE ON background_jobs, outbox_events TO collectiq_app;
REVOKE DELETE, TRUNCATE ON background_jobs, outbox_events FROM collectiq_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON idempotency_keys TO collectiq_app;
REVOKE TRUNCATE ON idempotency_keys FROM collectiq_app;
GRANT SELECT, INSERT ON workspace_keys TO collectiq_app;
REVOKE UPDATE, DELETE, TRUNCATE ON workspace_keys FROM collectiq_app;
"""

# The claim function runs as the owner, and RLS is forced on the owner too, so it needs its own way in.
# The policy names only the owner role: the app role still sees just its bound workspace.
CLAIM_POLICY = """
CREATE POLICY background_jobs_claim ON background_jobs TO collectiq_owner USING (true) WITH CHECK (true);
"""

# The only path across tenants. It returns one job's IDs, never a tenant context: the handler still runs in
# tenant_tx. Expired leases with attempts left are reclaimed; those with none left are dead-lettered first.
CLAIM_FUNCTION = """
CREATE FUNCTION claim_background_job(lease_seconds integer)
RETURNS TABLE (
  job_id uuid, workspace_id uuid, kind text, payload jsonb, attempts integer,
  max_attempts integer, lease_token uuid, correlation_id text
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
#variable_conflict use_column
BEGIN
  UPDATE public.background_jobs AS j
     SET status = 'DEAD_LETTER', lease_until = NULL, lease_token = NULL,
         last_error = 'LEASE_EXPIRED', updated_at = now()
   WHERE j.id IN (
     SELECT e.id FROM public.background_jobs AS e
      WHERE e.status = 'RUNNING' AND e.lease_until < now() AND e.attempts >= e.max_attempts
        FOR UPDATE SKIP LOCKED
   );

  RETURN QUERY
  UPDATE public.background_jobs AS j
     SET status = 'RUNNING', attempts = j.attempts + 1,
         lease_until = now() + make_interval(secs => lease_seconds),
         lease_token = gen_random_uuid(), updated_at = now()
   WHERE j.id = (
     SELECT c.id FROM public.background_jobs AS c
      WHERE (c.status = 'QUEUED' AND c.run_at <= now())
         OR (c.status = 'RUNNING' AND c.lease_until < now() AND c.attempts < c.max_attempts)
      ORDER BY c.run_at, c.id
        FOR UPDATE SKIP LOCKED
      LIMIT 1
   )
  RETURNING j.id, j.workspace_id, j.kind, j.payload, j.attempts, j.max_attempts, j.lease_token, j.correlation_id;
END
$$;
REVOKE ALL ON FUNCTION claim_background_job(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION claim_background_job(integer) TO collectiq_app;
"""


class Migration(migrations.Migration):
    dependencies = [("platform", "0001_rls_probe")]

    operations = [
        migrations.RunSQL(CREATE_TABLES, reverse_sql=DROP_TABLES),
        enable_rls("background_jobs"),
        enable_rls("outbox_events"),
        enable_rls("idempotency_keys"),
        enable_rls("workspace_keys"),
        migrations.RunSQL(PRIVILEGES, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(CLAIM_POLICY, reverse_sql="DROP POLICY background_jobs_claim ON background_jobs;"),
        migrations.RunSQL(CLAIM_FUNCTION, reverse_sql="DROP FUNCTION claim_background_job(integer);"),
    ]
