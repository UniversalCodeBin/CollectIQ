"""audit_events per TSD section 9: append-only by privilege and trigger, with a per-workspace hash chain.

This detects casual edits. It is not tamper-resistant against a database superuser.
"""
import django.contrib.postgres.fields
from django.db import migrations, models

from collectiq.platform.rls import enable_rls

CREATE_TABLE = """
CREATE TABLE audit_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_type text NOT NULL,
  actor_id uuid,
  action text NOT NULL,
  object_type text NOT NULL,
  object_id text NOT NULL,
  before_masked jsonb,
  after_masked jsonb,
  reason_codes text[],
  evidence_refs jsonb,
  policy_decision_id uuid,
  correlation_id text NOT NULL,
  prev_hash bytea,
  hash bytea NOT NULL
);
CREATE INDEX audit_events_workspace_id_id_idx ON audit_events (workspace_id, id DESC);
"""

PRIVILEGES = """
GRANT SELECT, INSERT ON audit_events TO collectiq_app;
GRANT USAGE ON SEQUENCE audit_events_id_seq TO collectiq_app;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM collectiq_app;
"""

# The epoch keeps the hash independent of the session's TimeZone, and jsonb text has a canonical key order.
HASH_FUNCTION = """
CREATE FUNCTION audit_event_hash(e audit_events) RETURNS bytea
LANGUAGE sql STABLE AS $$
  SELECT sha256(coalesce(e.prev_hash, ''::bytea) || convert_to(jsonb_build_array(
    e.id, e.workspace_id, extract(epoch FROM e.occurred_at), e.actor_type, e.actor_id,
    e.action, e.object_type, e.object_id, e.before_masked, e.after_masked,
    e.reason_codes, e.evidence_refs, e.policy_decision_id, e.correlation_id
  )::text, 'UTF8'))
$$;
"""

# The identity default is drawn before this trigger waits for the lock, so a writer can queue behind one
# holding a higher id, and "highest id" would then fork the chain. Drawing the id again under the lock makes
# id order equal chain order. This relies on READ COMMITTED, where each statement here sees the last commit.
CHAIN_TRIGGER = """
CREATE FUNCTION audit_events_chain() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('audit_events'), hashtext(NEW.workspace_id::text));
  NEW.id := nextval(pg_get_serial_sequence('audit_events', 'id'));
  NEW.prev_hash := (
    SELECT e.hash FROM audit_events e WHERE e.workspace_id = NEW.workspace_id ORDER BY e.id DESC LIMIT 1
  );
  NEW.hash := audit_event_hash(NEW);
  RETURN NEW;
END
$$;
CREATE TRIGGER audit_events_chain BEFORE INSERT ON audit_events
  FOR EACH ROW EXECUTE FUNCTION audit_events_chain();
"""

# TRUNCATE is left to privileges: the owner needs it for test cleanup and the later deletion procedure.
APPEND_ONLY_TRIGGER = """
CREATE FUNCTION audit_events_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only: % is not allowed', TG_OP;
END
$$;
CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION audit_events_append_only();
"""


class Migration(migrations.Migration):
    initial = True
    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.RunSQL(CREATE_TABLE, reverse_sql="DROP TABLE audit_events;"),
        enable_rls("audit_events"),
        migrations.RunSQL(PRIVILEGES, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(HASH_FUNCTION, reverse_sql="DROP FUNCTION audit_event_hash(audit_events);"),
        migrations.RunSQL(
            CHAIN_TRIGGER,
            reverse_sql="DROP TRIGGER audit_events_chain ON audit_events; DROP FUNCTION audit_events_chain();",
        ),
        migrations.RunSQL(
            APPEND_ONLY_TRIGGER,
            reverse_sql=(
                "DROP TRIGGER audit_events_append_only ON audit_events;"
                " DROP FUNCTION audit_events_append_only();"
            ),
        ),
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigIntegerField(primary_key=True, serialize=False)),
                ("workspace_id", models.UUIDField()),
                ("occurred_at", models.DateTimeField()),
                ("actor_type", models.TextField()),
                ("actor_id", models.UUIDField(null=True)),
                ("action", models.TextField()),
                ("object_type", models.TextField()),
                ("object_id", models.TextField()),
                ("before_masked", models.JSONField(null=True)),
                ("after_masked", models.JSONField(null=True)),
                (
                    "reason_codes",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.TextField(), null=True, size=None
                    ),
                ),
                ("evidence_refs", models.JSONField(null=True)),
                ("policy_decision_id", models.UUIDField(null=True)),
                ("correlation_id", models.TextField()),
                ("prev_hash", models.BinaryField(null=True)),
                ("hash", models.BinaryField()),
            ],
            options={"db_table": "audit_events", "managed": False},
        ),
    ]
