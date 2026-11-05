"""Gmail and PayPal adapter storage: OAuth state, sealed credentials and webhook evidence."""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
ALTER TABLE integration_connections ADD COLUMN external_account text;

CREATE TABLE oauth_states (
    state_hash text PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    user_id uuid NOT NULL,
    provider text NOT NULL CHECK (provider IN ('GMAIL')),
    verifier_sealed bytea NOT NULL,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE oauth_credential_refs (
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    provider text NOT NULL CHECK (provider IN ('GMAIL')),
    sealed bytea NOT NULL,
    scopes text[] NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, provider)
);

CREATE TABLE webhook_events (
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    provider text NOT NULL CHECK (provider IN ('PAYPAL')),
    event_id text NOT NULL,
    event_type text NOT NULL,
    status text NOT NULL CHECK (status IN ('EVIDENCE_ONLY')),
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, provider, event_id)
);

REVOKE ALL ON oauth_states, oauth_credential_refs, webhook_events FROM collectiq_app;
GRANT SELECT, INSERT ON oauth_states TO collectiq_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON oauth_credential_refs TO collectiq_app;
GRANT SELECT, INSERT ON webhook_events TO collectiq_app;

-- The callback and the webhook arrive without a workspace in the URL. These two functions are the only
-- cross-tenant reads, and each returns just what its caller needs.
CREATE FUNCTION consume_oauth_state(p_hash text, p_user uuid)
RETURNS TABLE (workspace_id uuid, verifier_sealed bytea)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
#variable_conflict use_column
BEGIN
  RETURN QUERY
  UPDATE public.oauth_states AS s SET used_at = now()
   WHERE s.state_hash = p_hash AND s.user_id = p_user AND s.used_at IS NULL AND s.expires_at > now()
  RETURNING s.workspace_id, s.verifier_sealed;
END $$;
REVOKE ALL ON FUNCTION consume_oauth_state(text, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION consume_oauth_state(text, uuid) TO collectiq_app;

CREATE FUNCTION paypal_workspace_for(p_merchant text) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT c.workspace_id FROM public.integration_connections c
   WHERE c.provider = 'PAYPAL' AND c.state = 'CONNECTED_VERIFIED' AND c.external_account = p_merchant
   LIMIT 1
$$;
CREATE POLICY oauth_states_definer ON oauth_states TO collectiq_owner USING (true) WITH CHECK (true);
CREATE POLICY integration_connections_definer ON integration_connections FOR SELECT TO collectiq_owner USING (true);
REVOKE ALL ON FUNCTION paypal_workspace_for(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION paypal_workspace_for(text) TO collectiq_app;
"""

REVERSE = """
DROP POLICY integration_connections_definer ON integration_connections;
DROP POLICY oauth_states_definer ON oauth_states;
DROP FUNCTION paypal_workspace_for(text);
DROP FUNCTION consume_oauth_state(text, uuid);
DROP TABLE webhook_events, oauth_credential_refs, oauth_states;
ALTER TABLE integration_connections DROP COLUMN external_account;
"""


class Migration(migrations.Migration):
    dependencies = [("integrations", "0001_connections"), ("comms", "0002_send_states")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=REVERSE),
        enable_rls("oauth_states"),
        enable_rls("oauth_credential_refs"),
        enable_rls("webhook_events"),
    ]
