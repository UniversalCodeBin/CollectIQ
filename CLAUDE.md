# CollectIQ — working notes

Receivables follow-up product: Django 5.2 + DRF + PostgreSQL 16 (forced row security) backend, React 19/TS SPA.

## Where things are
- Plan and status: `docs/IMPLEMENTATION_STATUS.md` (40 tasks), `docs/IMPLEMENTATION_CHECKPOINT.md` (resume point), `docs/DECISIONS_LOG.md` (rulings).
- Contracts: `CollectIQ_API_Contracts.yaml`, `CollectIQ_Requirements_Traceability.csv` (CRLF files; `make check` verifies both).
- Backend `backend/collectiq/`, layers top to bottom (import-linter enforces): api, settings_privacy, notifications, integrations, comms, conversations, cases, evidence, invoices, policy, tenancy, identity, audit, platform.

## Commands (repo root)
`make migrate`, `make test`, `make check` (12 gates), `make openapi` (regenerate after endpoint changes), `make seed`, `make e2e`.
Benchmarks: `backend/perf/` (k6).

## Rules that must not bend
- Database is `collectiq-db` on 127.0.0.1:54329. Never touch container `elitepg` or port 55432.
- Local commits only. Placeholders in `.env.example`; fixtures use `@example.test`.
- Money is integer minor units. No `MARK_PAID` or `AUTO_ALLOCATE` path, no `AUTO_SEND`. Confidence is `LOW|MEDIUM|HIGH`.
- Every customer-facing message needs human approval. An AI reading is never shown as a verified fact. A customer's statement never marks an invoice paid.
- `AI_PROVIDER=fake` is refused in production. `GEMINI_API_KEY` in the shell is not used.
- Audit wording: "append-only by database permissions, with a hash chain that detects casual edits; not tamper-resistant against a database superuser." Make no SOC 2, ISO, PCI, DPDP, GDPR, AI-accuracy or uptime claims.
- Never weaken a test. Tests use the `pg` fixture (real commits as the app role).
