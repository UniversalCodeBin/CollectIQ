# CollectIQ

A receivables operations assistant. It records invoice and payment evidence, keeps balances derived
from human-confirmed allocations, and pauses follow-ups when anything is uncertain. It does not replace
an accounting system, and it never marks an invoice paid on its own.

Status and limitations: [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md).

## Prerequisites

Podman, [uv](https://docs.astral.sh/uv/), Node 24, make.

## Run it locally

```bash
make db-up     # creates .env with random local secrets, starts Postgres on 127.0.0.1:54329
make migrate
make seed      # optional, synthetic sample data, labelled as sample in the UI
make dev       # API :8000, worker, web :5173
```

## Deploy

An example layout is in [deploy/compose.prod.example.yaml](deploy/compose.prod.example.yaml): Postgres, a one-off
`migrate` step (owner role), the API under gunicorn, the job worker, and a scheduler that queues the nightly audit-chain
check, evidence integrity check and retention (`manage.py schedule_nightly`). Build the image with
`podman build -t collectiq-backend:local backend`.

- Secrets live in an env file outside the repository. `.env.example` holds placeholders only.
- Production refuses `AI_PROVIDER=fake` and any `change-me` secret.
- TLS ends at a reverse proxy that sets `X-Forwarded-Proto: https`. The API redirects plain http and sets HSTS.
- The proxy serves `frontend/dist` and must set its own Content-Security-Policy; the API sets one for JSON only.
- Email defaults to file or memory, so no message reaches a real mailbox. An SMTP backend (`EMAIL_BACKEND_KIND=smtp`, `SMTP_*` variables) exists but has never been exercised against a real server; until credentials are supplied, invitations and resets are not delivered.
- Uploads are recorded as not scanned unless `SCANNER_KIND=clamav` is set; the ClamAV adapter has only been tested against a fake server.
- Backup and restore: [docs/runbooks/backup-restore.md](docs/runbooks/backup-restore.md).
- What was and was not verified: [docs/acceptance-report.md](docs/acceptance-report.md).
