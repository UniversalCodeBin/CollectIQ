# Sourced by serve.sh and by support.ts helpers. Loads ./.env, then points both database URLs at a database of
# the e2e run's own, so a `make dev` worker running at the same time cannot take the run's jobs (or its email).
set -a
. ./.env
set +a
E2E_MAINTENANCE_DATABASE_URL="$MIGRATION_DATABASE_URL"
DATABASE_URL="${DATABASE_URL%/*}/collectiq_e2e"
MIGRATION_DATABASE_URL="${MIGRATION_DATABASE_URL%/*}/collectiq_e2e"
export E2E_MAINTENANCE_DATABASE_URL DATABASE_URL MIGRATION_DATABASE_URL
