# Backup and restore

What is backed up: the PostgreSQL database (all business data, the audit chain, background jobs) and the
`/data` volume (uploaded files, which are encrypted with per-workspace keys). Neither is useful without
`COLLECTIQ_MASTER_KEY`, which must be kept separately and safely. Losing the key makes stored files and
tokens unreadable.

## Encrypted backup and drill (scripted)

`scripts/backup_encrypted.sh` encrypts the dump with GnuPG (AES-256, passphrase from a file you keep apart
from the backup and from `COLLECTIQ_MASTER_KEY`), writes a SHA-256 beside it, and can restore into a scratch
database and compare row counts. It never touches the live database.

```bash
export DB_CONTAINER=<db-container> BACKUP_PASSPHRASE_FILE=/secure/path/passphrase
scripts/backup_encrypted.sh backup collectiq-$(date +%F).dump.gpg
scripts/backup_encrypted.sh drill  collectiq-YYYY-MM-DD.dump.gpg
```

Drill run on 2026-11-08 against the local development database (402 users, 10,863 invoices, 3,683 audit
events): backup 1.8 MB, restore and comparison 5 s, every compared table matched. That is one small dataset
on one machine, not a statement about production sizes. Offsite copy and passphrase custody are the owner's
(OD-04); the script does not copy the file anywhere.

## Back up (manual, unencrypted)

```bash
podman exec <db-container> pg_dump -U postgres -Fc collectiq > collectiq-$(date +%F).dump
podman run --rm -v collectiq_data:/data:ro -v "$PWD":/out docker.io/library/python:3.12-slim \
  tar -C /data -czf /out/collectiq-data-$(date +%F).tgz .
```

Keep dumps off the machine that holds the database, and protect them as you would the database.

## Restore into a scratch database (the drill)

```bash
podman exec <db-container> psql -U postgres -c "CREATE DATABASE collectiq_restore OWNER collectiq_owner"
podman exec -i <db-container> pg_restore -U postgres --no-owner --role=collectiq_owner \
  -d collectiq_restore < collectiq-YYYY-MM-DD.dump
```

Then check, before trusting the copy:

1. Row counts match the source for `users`, `workspaces`, `clients`, `invoices`, `audit_events`.
2. Point an API image at the restored database (change the database name in both URLs) and run the audit
   chain check as the app role: `history.verify_chain` for a workspace must report `intact: true`.
3. Sign in and open the workspace.

To replace production, stop the API and worker, restore into an empty database, point the services at it, and
start them. Run `schedule_nightly` once afterwards so the integrity checks run on the restored data.

## What the drill proved, and what it did not

Recorded in `docs/acceptance-report.md`. A drill on one small dataset on one machine shows the procedure
works; it says nothing about restore time at scale, offsite storage, or a lost master key.
