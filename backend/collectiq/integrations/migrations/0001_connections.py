"""One row per workspace and provider. CONNECTED_VERIFIED needs a verification time the database enforces."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE integration_connections (
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    provider text NOT NULL CHECK (provider IN ('GMAIL', 'PAYPAL')),
    state text NOT NULL CHECK (state IN (
        'NEEDS_CONFIGURATION', 'SANDBOX_ONLY', 'CONNECTED_VERIFIED', 'NEEDS_REAUTH', 'DEGRADED', 'DISCONNECTED'
    )),
    verified_at timestamptz,
    last_error text,
    updated_by uuid,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, provider),
    CHECK (state <> 'CONNECTED_VERIFIED' OR verified_at IS NOT NULL)
);
"""


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0001_tenancy")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql="DROP TABLE integration_connections;"),
        enable_rls("integration_connections"),
    ]
