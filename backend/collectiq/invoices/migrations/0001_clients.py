from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE_TABLES = """
CREATE TABLE clients (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 200),
    normalized_name text NOT NULL,
    sensitivity text NOT NULL DEFAULT 'STANDARD' CHECK (sensitivity IN ('STANDARD', 'LONG_TERM', 'SENSITIVE')),
    tone text NOT NULL DEFAULT 'NEUTRAL' CHECK (tone IN ('NEUTRAL', 'FRIENDLY', 'FORMAL')),
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id)
);
CREATE INDEX clients_workspace_normalized_name ON clients (workspace_id, normalized_name);

CREATE TABLE client_contacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    client_id uuid NOT NULL,
    email citext NOT NULL CHECK (char_length(email::text) <= 254),
    name text CHECK (char_length(name) <= 200),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUPPRESSED')),
    suppression_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, client_id) REFERENCES clients (workspace_id, id),
    UNIQUE (workspace_id, client_id, email),
    UNIQUE (workspace_id, id),
    CONSTRAINT suppression_has_reason CHECK ((status = 'SUPPRESSED') = (suppression_reason IS NOT NULL))
);
CREATE INDEX client_contacts_workspace_email ON client_contacts (workspace_id, email);

CREATE TABLE client_aliases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    client_id uuid NOT NULL,
    text text NOT NULL CHECK (char_length(text) BETWEEN 1 AND 200),
    normalized_text text NOT NULL,
    kind text NOT NULL DEFAULT 'NAME' CHECK (kind IN ('NAME', 'REFERENCE')),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, client_id) REFERENCES clients (workspace_id, id),
    UNIQUE (workspace_id, client_id, kind, normalized_text)
);
CREATE INDEX client_aliases_workspace_normalized ON client_aliases (workspace_id, normalized_text);
"""

DROP_TABLES = "DROP TABLE client_aliases; DROP TABLE client_contacts; DROP TABLE clients;"

# Clients are corrected, never erased here: unpaid invoices will point at them.
PRIVILEGES = """
REVOKE DELETE ON clients, client_contacts FROM collectiq_app;
"""


class Migration(migrations.Migration):
    initial = True
    dependencies = [("tenancy", "0001_tenancy")]
    operations = [
        migrations.RunSQL(CREATE_TABLES, reverse_sql=DROP_TABLES),
        enable_rls("clients"),
        enable_rls("client_contacts"),
        enable_rls("client_aliases"),
        migrations.RunSQL(PRIVILEGES, reverse_sql=migrations.RunSQL.noop),
    ]
