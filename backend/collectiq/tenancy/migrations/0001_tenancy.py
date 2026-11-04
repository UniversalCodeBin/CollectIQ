from django.db import migrations

from collectiq.platform.rls import WORKSPACE_PREDICATE, enable_rls

USER_PREDICATE = "NULLIF(current_setting('app.user_id', true), '')::uuid"

CREATE_TABLES = """
CREATE TABLE workspaces (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    country text NOT NULL,
    timezone text NOT NULL,
    default_currency text NOT NULL,
    business_hours jsonb NOT NULL DEFAULT '{}',
    active_policy_id uuid,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DELETION_REQUESTED', 'DELETED')),
    deletion_requested_at timestamptz,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE workspace_memberships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    user_id uuid NOT NULL REFERENCES users (id),
    role text NOT NULL CHECK (role IN ('OWNER', 'FINANCE_ADMIN', 'PROJECT_LEAD')),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'REMOVED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, user_id)
);
CREATE INDEX workspace_memberships_user ON workspace_memberships (user_id) WHERE status = 'ACTIVE';

CREATE TABLE workspace_policies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    version integer NOT NULL,
    settings jsonb NOT NULL,
    changed_by uuid REFERENCES users (id),
    effective_from timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, version),
    UNIQUE (workspace_id, id)
);

ALTER TABLE workspaces ADD CONSTRAINT workspaces_active_policy_fk
    FOREIGN KEY (id, active_policy_id) REFERENCES workspace_policies (workspace_id, id);

CREATE TABLE workspace_invitations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    email citext NOT NULL,
    role text NOT NULL CHECK (role IN ('OWNER', 'FINANCE_ADMIN', 'PROJECT_LEAD')),
    token_hash text UNIQUE,
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    revoked_at timestamptz,
    invited_by uuid NOT NULL REFERENCES users (id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX workspace_invitations_one_pending ON workspace_invitations (workspace_id, email)
    WHERE accepted_at IS NULL AND revoked_at IS NULL;
"""

DROP_TABLES = """
DROP TABLE workspace_invitations;
ALTER TABLE workspaces DROP CONSTRAINT workspaces_active_policy_fk;
DROP TABLE workspace_policies;
DROP TABLE workspace_memberships;
DROP TABLE workspaces;
"""

# A workspace is its own tenant row, so the shared helper's workspace_id predicate does not fit it.
WORKSPACES_RLS = f"""
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspaces FORCE ROW LEVEL SECURITY;
CREATE POLICY workspaces_tenant_isolation ON workspaces
    USING (id = {WORKSPACE_PREDICATE.split(" = ", 1)[1]})
    WITH CHECK (id = {WORKSPACE_PREDICATE.split(" = ", 1)[1]});
"""

# OR'ed with tenant isolation: before a workspace is chosen, a user can read their own memberships and those
# workspaces. Services still filter by workspace_id, because of the same OR.
MEMBER_VISIBILITY = f"""
CREATE POLICY workspace_memberships_own ON workspace_memberships FOR SELECT
    USING (user_id = {USER_PREDICATE});
CREATE POLICY workspaces_member_read ON workspaces FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM workspace_memberships m
        WHERE m.workspace_id = workspaces.id AND m.status = 'ACTIVE' AND m.user_id = {USER_PREDICATE}
    ));
"""

DROP_MEMBER_VISIBILITY = """
DROP POLICY workspaces_member_read ON workspaces;
DROP POLICY workspace_memberships_own ON workspace_memberships;
"""

# Removal is a status change and policies are versioned rows; the app can do neither by deleting.
PRIVILEGES = """
REVOKE DELETE ON workspaces, workspace_memberships, workspace_invitations FROM collectiq_app;
REVOKE UPDATE, DELETE ON workspace_policies FROM collectiq_app;
"""


class Migration(migrations.Migration):
    initial = True
    dependencies = [("identity", "0001_identity")]
    operations = [
        migrations.RunSQL(CREATE_TABLES, reverse_sql=DROP_TABLES),
        migrations.RunSQL(
            WORKSPACES_RLS,
            reverse_sql="DROP POLICY workspaces_tenant_isolation ON workspaces;"
            " ALTER TABLE workspaces NO FORCE ROW LEVEL SECURITY;"
            " ALTER TABLE workspaces DISABLE ROW LEVEL SECURITY;",
        ),
        enable_rls("workspace_memberships"),
        enable_rls("workspace_policies"),
        enable_rls("workspace_invitations"),
        migrations.RunSQL(MEMBER_VISIBILITY, reverse_sql=DROP_MEMBER_VISIBILITY),
        migrations.RunSQL(PRIVILEGES, reverse_sql=migrations.RunSQL.noop),
    ]
