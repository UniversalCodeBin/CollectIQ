#!/bin/sh
# Creates the database and its two roles. Idempotent: safe to run on every `make db-up`.
#   collectiq_owner  owns schema objects, runs migrations. Not a superuser.
#   collectiq_app    runtime role. Cannot bypass row-level security, own objects or create databases.
# Expects OWNER_PASSWORD and APP_PASSWORD in the environment.
set -eu
: "${OWNER_PASSWORD:?OWNER_PASSWORD is required}"
: "${APP_PASSWORD:?APP_PASSWORD is required}"

psql -v ON_ERROR_STOP=1 -U postgres -q -d postgres \
  -v owner_pw="$OWNER_PASSWORD" -v app_pw="$APP_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE collectiq_owner LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'collectiq_owner') \gexec
SELECT 'CREATE ROLE collectiq_app LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'collectiq_app') \gexec
ALTER ROLE collectiq_owner NOSUPERUSER CREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'owner_pw';
ALTER ROLE collectiq_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'app_pw';
SELECT 'CREATE DATABASE collectiq OWNER collectiq_owner' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'collectiq') \gexec
SQL

psql -v ON_ERROR_STOP=1 -U postgres -q -d collectiq <<'SQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO collectiq_owner;
GRANT USAGE ON SCHEMA public TO collectiq_app;
ALTER DEFAULT PRIVILEGES FOR ROLE collectiq_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO collectiq_app;
ALTER DEFAULT PRIVILEGES FOR ROLE collectiq_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO collectiq_app;
SQL
