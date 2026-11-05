"""Policy decisions (single use) and approval requests (decided once). Policy versions live in workspace_policies."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE policy_decisions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    action_type text NOT NULL,
    subject text NOT NULL,
    actor_kind text NOT NULL,
    actor_user_id uuid,
    outcome text NOT NULL CHECK (outcome IN
        ('ALLOW_AUTOMATIC', 'REQUIRE_APPROVAL', 'DENY', 'DEFER', 'PAUSE_FOR_REVIEW', 'CANCEL')),
    gate_results jsonb NOT NULL,
    reasons text[] NOT NULL,
    rules_version text NOT NULL,
    policy_version integer NOT NULL,
    state_version integer NOT NULL,
    inputs_hash text NOT NULL,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id)
);
CREATE INDEX policy_decisions_subject ON policy_decisions (workspace_id, subject, created_at DESC);

CREATE TABLE approval_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    decision_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    requested_at timestamptz NOT NULL DEFAULT now(),
    decided_by uuid REFERENCES users (id),
    decided_at timestamptz,
    note text,
    UNIQUE (decision_id),
    FOREIGN KEY (workspace_id, decision_id) REFERENCES policy_decisions (workspace_id, id),
    CHECK ((status = 'PENDING') = (decided_by IS NULL AND decided_at IS NULL))
);
CREATE INDEX approval_requests_pending ON approval_requests (workspace_id, requested_at) WHERE status = 'PENDING';

-- A decision is a record: it can be consumed once and never changed, moved back, or deleted.
CREATE FUNCTION policy_decisions_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'policy decisions cannot be deleted';
    END IF;
    IF OLD.consumed_at IS NOT NULL OR NEW.consumed_at IS NULL THEN
        RAISE EXCEPTION 'a policy decision can be consumed once and not changed afterwards';
    END IF;
    IF (to_jsonb(NEW) - 'consumed_at') IS DISTINCT FROM (to_jsonb(OLD) - 'consumed_at') THEN
        RAISE EXCEPTION 'only consumed_at of a policy decision may change';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER policy_decisions_guard BEFORE UPDATE OR DELETE ON policy_decisions
    FOR EACH ROW EXECUTE FUNCTION policy_decisions_guard();

-- An approval is decided once: PENDING to APPROVED or REJECTED, never reopened or deleted.
CREATE FUNCTION approval_requests_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'approval requests cannot be deleted';
    END IF;
    IF OLD.status <> 'PENDING' OR NEW.status = 'PENDING' THEN
        RAISE EXCEPTION 'an approval request is decided once';
    END IF;
    IF (to_jsonb(NEW) - 'status' - 'decided_by' - 'decided_at' - 'note')
        IS DISTINCT FROM (to_jsonb(OLD) - 'status' - 'decided_by' - 'decided_at' - 'note') THEN
        RAISE EXCEPTION 'only the decision of an approval request may change';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER approval_requests_guard BEFORE UPDATE OR DELETE ON approval_requests
    FOR EACH ROW EXECUTE FUNCTION approval_requests_guard();

REVOKE UPDATE, DELETE, TRUNCATE ON policy_decisions, approval_requests FROM collectiq_app;
GRANT SELECT, INSERT ON policy_decisions, approval_requests TO collectiq_app;
GRANT UPDATE (consumed_at) ON policy_decisions TO collectiq_app;
GRANT UPDATE (status, decided_by, decided_at, note) ON approval_requests TO collectiq_app;
"""

DROP = """
DROP TABLE approval_requests;
DROP TABLE policy_decisions;
DROP FUNCTION approval_requests_guard();
DROP FUNCTION policy_decisions_guard();
"""


class Migration(migrations.Migration):
    initial = True
    dependencies = [("tenancy", "0001_tenancy")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=DROP),
        enable_rls("policy_decisions"),
        enable_rls("approval_requests"),
    ]
