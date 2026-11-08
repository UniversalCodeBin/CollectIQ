#!/usr/bin/env bash
# Encrypted database backup and a restore drill into a scratch database. Never touches the live database.
# Usage: BACKUP_PASSPHRASE_FILE=path DB_CONTAINER=collectiq-db scripts/backup_encrypted.sh backup|drill FILE
set -euo pipefail
: "${DB_CONTAINER:?set DB_CONTAINER}" "${BACKUP_PASSPHRASE_FILE:?set BACKUP_PASSPHRASE_FILE}"
DB_NAME="${DB_NAME:-collectiq}"
pg() { podman exec -i "$DB_CONTAINER" "$@"; }
gpg_args=(--batch --yes --pinentry-mode loopback --passphrase-file "$BACKUP_PASSPHRASE_FILE")

case "${1:-}" in
backup)
  out="${2:?output file, e.g. collectiq-$(date +%F).dump.gpg}"
  pg pg_dump -U postgres -Fc "$DB_NAME" | gpg "${gpg_args[@]}" --symmetric --cipher-algo AES256 -o "$out"
  sha256sum "$out" > "$out.sha256"
  echo "wrote $out ($(stat -c %s "$out") bytes)"
  ;;
drill)
  src="${2:?encrypted backup file}"
  scratch="${DB_NAME}_drill_$$"
  start=$(date +%s)
  sha256sum -c "$src.sha256"
  pg psql -U postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $scratch OWNER collectiq_owner" >/dev/null
  trap 'pg psql -U postgres -c "DROP DATABASE IF EXISTS $scratch" >/dev/null' EXIT
  gpg "${gpg_args[@]}" --decrypt "$src" | pg pg_restore -U postgres --no-owner --role=collectiq_owner -d "$scratch"
  for t in users workspaces clients invoices audit_events; do
    a=$(pg psql -U postgres -Atc "SELECT count(*) FROM $t" "$DB_NAME")
    b=$(pg psql -U postgres -Atc "SELECT count(*) FROM $t" "$scratch")
    printf '%-14s source=%s restored=%s %s\n' "$t" "$a" "$b" "$([ "$a" = "$b" ] && echo ok || echo DIFFERS)"
  done
  echo "drill finished in $(( $(date +%s) - start )) s (scratch database dropped)"
  ;;
*) echo "usage: $0 backup|drill FILE" >&2; exit 2 ;;
esac
