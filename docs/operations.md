# Operations guide (pilot)

What exists, how to run it, and what is not provided. Read with `deploy/compose.prod.example.yaml`.

## Environment checks (staging and production)
`python scripts/check_deploy_env.py /secure/collectiq.env --production` lists placeholders, short keys, an
app role that equals the owner role, `AI_PROVIDER=fake`, flags that need credentials, non-https origins and
an unscanned upload path. It exits 1 on any finding. The application also refuses to start in production
with placeholder keys, `AI_PROVIDER=fake`, or SMTP selected without a host.

## Pilot deployment
1. Build: `podman build -t collectiq-backend:local backend`; build the SPA (`npm run build` in `frontend`).
2. Create the env file outside the repository; run the check above until clean.
3. `podman compose -f deploy/compose.prod.example.yaml --env-file /secure/collectiq.env up -d`.
4. Put a TLS reverse proxy in front (sets `X-Forwarded-Proto: https`, serves the SPA, sets its CSP).
5. Run migrations with the owner URL (`python manage.py migrate`), check `health/ready`.
6. Schedule `python manage.py schedule_nightly` daily (cron or systemd timer) and keep `run_worker` running.
7. Take a first encrypted backup and run the drill on it (below) **before** inviting users.

## Backup, restore, audit anchor
- `scripts/backup_encrypted.sh backup FILE` / `drill FILE` (see [backup and restore](runbooks/backup-restore.md)).
  The passphrase file is held outside the host that stores backups. A lost passphrase means unreadable backups.
- `python manage.py audit_anchor > anchors/<date>.jsonl` after the nightly run; copy the file to storage the
  database operator cannot rewrite. `--check FILE` later proves chain heads still match. Without off-host
  storage of these files the anchor adds nothing.
- Break-glass: [procedure](runbooks/break-glass.md). Incidents: [response](runbooks/incident-response.md).

## Monitoring and error reporting
Provided: JSON logs with secrets scrubbed, `health/live` and `health/ready`, nightly audit-chain and evidence
integrity jobs (a failure is a job in `FAILED` state, visible in `background_jobs`), the audit history.
Not provided: a metrics server, alerting, or an error-reporting service (no Sentry or similar is wired).
For the pilot: ship container logs to the host's log store, poll `health/ready` from an external uptime check,
and alert on `background_jobs` rows in `FAILED` state. Choosing a hosted error tracker sends data to a third
party and needs the operator's decision (OD-14); none is enabled.

## Secrets
Secrets live in the env file or the host's secret store; `.env.example` holds placeholders only. Stored
integration credentials are sealed with `COLLECTIQ_MASTER_KEY`. Rotating that key needs a re-seal, which is
not automated (see [token compromise](runbooks/token-compromise.md)). A managed secret store is an operator choice.

## Image scanning
No scanner (trivy, grype) is installed in this environment, so no image scan has been run and none is claimed.
Run `trivy image localhost/collectiq-backend:local` in CI or on the build host and record the result; upload
scanning uses ClamAV when `SCANNER_KIND=clamav` and a daemon is reachable (`CLAMAV_HOST`, `CLAMAV_PORT`).

## Nightly scheduler soak
`backend/tests/integration/test_scheduler.py` covers one-per-day dedupe and drain on a clean database. A
multi-day soak on a deployed host has not been run; the pilot's first week is that soak: confirm each morning
that four jobs per workspace reached `DONE` for the previous day.

## Measured performance
[docs/pilot/performance.md](pilot/performance.md): single-machine read-path numbers, not a capacity guarantee.
