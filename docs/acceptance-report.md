# Acceptance report

Evidence-based status at the end of the 40-task build, branch `build/m0-m8`. Every row says what was
actually run. Nothing here is a certification, a compliance claim, an accuracy figure or an uptime promise.

## Summary

Tasks 1-31 and 33-40 are built and committed; Task 32 is deferred (OD-05). The product covers import,
receivables queue, invoice detail, evidence and reconciliation, conversations, policy gates, reminders with human
approval, Gmail/PayPal integration paths, AI settings and flagged PDF extraction, audit history, settings, export
and deletion. It has not been run with real customers, a real mail provider, a live AI model or production
hardware. Several features listed under "Not built" below are still owed.

## What was verified

| Area | Evidence | Limits |
|---|---|---|
| Backend tests | `make test`: 1,274 backend tests passed on a real PostgreSQL 16 with forced row security, as the app role | Developer machine; one database |
| Frontend tests | Vitest suite (240 tests). Two were timing-sensitive under load and were made robust without weaker assertions | jsdom, not a real browser |
| Browser journeys | Playwright: critical journeys, 5 viewport widths, recovery cases, axe on 15 screens (0 violations) | Empty-state axe only; no screen-reader audit |
| Quality gates | `make check`: 13 gates (lint, types, layering, OpenAPI and traceability consistency, claims, secrets) | |
| API fuzzing | Schemathesis, 116 operations, 6,657 cases, no 5xx | Unauthenticated; 36 operations answered only 401/403 |
| Dependencies | `npm audit` production 0; 10 moderate findings in dev tooling only; `pip-audit` none | Point in time |
| Container | Image built, runs as non-root, refuses fake AI and `change-me` secrets in production, serves HSTS and security headers behind `X-Forwarded-Proto: https` | No image vulnerability scan |
| Nightly jobs | `schedule_nightly` queues `audit.verify_chain`, `evidence.integrity_check`, `privacy.retention` once per day per workspace (dedupe key is the date); 4 tests | Scheduler in the example compose file was not run for 24 h |
| Recovery drill | `pg_dump -Fc` of a seeded database restored into a scratch database: row counts matched and the audit chain verified intact on the copy | One small dataset, one machine; no timing at scale, no offsite copy, no lost-key case |
| Load | k6, 5,000 invoices, 5 virtual users, dev server: list p95 669 ms, queue 657 ms, dashboard 694 ms, detail 336 ms, 0% failed, all thresholds met | Not production hardware; not gunicorn |

## Invariants and where they are enforced

- Money is integer minor units; balances derive from human-confirmed allocations. No `MARK_PAID`, `AUTO_ALLOCATE` or
  `AUTO_SEND` path exists.
- A customer's statement never marks an invoice paid; an AI reading is stored as a reading and shown as unverified.
- Every customer-facing message needs human approval; gates G1-G15 are re-run at approval and at send.
- Tenant isolation: forced RLS on every tenant table, coverage test, cross-tenant requests answer 404.
- Audit history is append-only by database permissions, with a hash chain that detects casual edits;
  it is not tamper-resistant against a database superuser.
- `AI_PROVIDER=fake` is refused in production; the AI layer has no database handle.

## Not built or not verified

Owed features: per-client and per-invoice pause; ending snoozes when their date passes; MATCH_REVIEW case type and
allocation-driven case opening; closing verification tasks; N+1 history loading and cursor paging on E065; 90-day
notification retention and notification preferences; navigation link to PDF import and a screen for pending
interpretations; PDF size/page limit and OCR; AI summaries and wording drafts; legal name and sender display name;
UI buttons for connecting, sending and confirming an unknown send; PayPal connect endpoint; token refresh; Gmail
monitoring; webhook events as match candidates; frontend labels for SUBMITTED and SUBMISSION_UNKNOWN; a link from
audit rows to the why-view; UI for FL-03, 08, 09, 10, 12, 13, 14, 16.

Not done: real email delivery (file and memory backends only), independent penetration test, screen-reader audit,
live-AI evaluation, image scanning, break-glass process, off-database audit anchor, backup encryption and key
rotation, load test on target hardware, restore timing at scale.

Open decisions needing the owner: OD-04, 05, 08, 10, 11, 14 (see `docs/DECISIONS_LOG.md`). Legal review of
data-protection applicability (SEC-22) has not happened.

## Readiness

| Question | Answer |
|---|---|
| Implemented | Core receivables, evidence, policy, reminders (manual send path), audit, settings, deployment example |
| Tested | Locally, as listed above |
| Configured for production | Example only; secrets, TLS proxy, SPA host CSP and backups are the operator's |
| Ready for real customers | No. Email delivery, restore at scale, hardware load, security review by a third party and the owed features come first |
| Ready for a supervised pilot with synthetic or consented data | Plausible after the operator completes the deployment steps and the open decisions are answered |
