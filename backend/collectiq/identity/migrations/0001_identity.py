from django.db import migrations

CREATE_TABLES = """
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email citext NOT NULL UNIQUE,
    password_hash text NOT NULL,
    status text NOT NULL DEFAULT 'UNVERIFIED' CHECK (status IN ('UNVERIFIED', 'ACTIVE', 'DISABLED')),
    email_verified_at timestamptz,
    mfa_secret_ref text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users (id),
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
CREATE INDEX user_sessions_user ON user_sessions (user_id) WHERE revoked_at IS NULL;

CREATE TABLE auth_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users (id),
    purpose text NOT NULL CHECK (purpose IN ('VERIFY_EMAIL', 'PASSWORD_RESET')),
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auth_tokens_user ON auth_tokens (user_id, purpose) WHERE used_at IS NULL;

CREATE TABLE auth_throttles (
    key text PRIMARY KEY,
    count integer NOT NULL,
    window_started_at timestamptz NOT NULL DEFAULT now(),
    locked_until timestamptz
);
"""

DROP_TABLES = "DROP TABLE auth_throttles; DROP TABLE auth_tokens; DROP TABLE user_sessions; DROP TABLE users;"

# These tables are not tenant data, so they carry no RLS. Accounts are disabled, never deleted by the app.
PRIVILEGES = """
GRANT SELECT, INSERT, UPDATE ON users, user_sessions, auth_tokens TO collectiq_app;
REVOKE DELETE ON users, user_sessions, auth_tokens FROM collectiq_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_throttles TO collectiq_app;
"""


class Migration(migrations.Migration):
    initial = True
    dependencies: list = []
    operations = [
        migrations.RunSQL(CREATE_TABLES, reverse_sql=DROP_TABLES),
        migrations.RunSQL(PRIVILEGES, reverse_sql=migrations.RunSQL.noop),
    ]
