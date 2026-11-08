# Product readiness report

Date: 2026-11-08. Branch `build/m0-m8`. Local commits only; nothing pushed.

## 1. Executive summary
The planned build is complete except Task 32 (live AI features, deferred under OD-05). The backend, SPA, contracts,
runbooks and operational scripts are in place and pass the gates below. Nothing here has run against a real Gmail
account, a real PayPal merchant, a real AI model, a real SMTP relay or production-grade hardware.
**Pilot-ready: conditionally**, for a supervised pilot with file/memory mail backends and manual reminders approved
by a person, once the operator completes the steps in section 10. **Production-ready: no.**

## 2. Final git commit and repo state
See the last commit on `build/m0-m8` (`git log -1`). `CollectIQ_Post_Implementation_Audit.md` is untracked and untouched.

## 3. Features implemented (this cycle)
PayPal connect E129 (merchant-check port, no live checker), Gmail monitoring E096 (honest refusal), verification-task
close E128, commitments and snooze screens (FL-08, FL-09), commitments refetch fix, encrypted backup and restore
drill, `audit_anchor`, `check_deploy_env.py`, break-glass and incident runbooks, `docs/operations.md`, load runner.

## 4. Tests and exact results
- `make test` (full backend, real Postgres, app role): first run 1348 passed, 2 failed (E096 audit-completeness
  allowlist; a forbidden-claim wording in a new runbook). Both fixed; the re-run result is recorded in section 4a.
- `make e2e`: 30 passed (3.6 min).
- `make check`: 13 of 13 gates passed after fixing a secret-scanner false positive and ruff line lengths.
- Vitest runs inside `make check` and passed.
### 4a. Final `make test` re-run
1350 passed, 0 failed (11 min 50 s); Vitest in the same target: 262 passed in 22 files.

## 5. Security verification
Verified by tests: forced RLS, app role without owner rights, append-only audit with hash chain, injection corpus
against the fake provider, secret scrubbing in logs, TS-023 audit completeness, production refuses fake AI and
placeholder keys. Not done: independent penetration test, screen-reader audit, image scan (no scanner installed),
live-model injection testing. Audit wording: append-only by database permissions, with a hash chain that detects
casual edits; not tamper-resistant against a database superuser. The off-host anchor makes rewrites detectable only
if the operator stores anchors elsewhere.

## 6. Financial-integrity verification
Integer minor units, no MARK_PAID/AUTO_ALLOCATE/AUTO_SEND path, only evidence writes payments and allocations,
customer statements never mark paid, PayPal events stay EVIDENCE_ONLY. Covered by the allocation, matching and
`check` gates ("Only evidence may write payment transactions… KEPT", contracts 4 kept).

## 7. Agent architecture status
See `docs/agent-platform.md`. Bounded, tenant-isolated, read-only tools, proposal-only effects; no real provider.

## 8. Performance measurements
`docs/pilot/performance.md`: one workstation, gunicorn 4 workers, ~5,000 invoices. At 5 users: ~39.5 req/s, 0 errors,
dashboard p50/p95/p99 149/218/246 ms. At 20 users: ~39.4 req/s, dashboard p95 691 ms. Not a capacity guarantee.

## 9. Deployment and recovery verification
Encrypted backup and restore drill run for real on 2026-11-08 (row counts matched, 5 s, 1.8 MB). Env check script
tested. Not done: a deployment on a separate host, a multi-day scheduler soak, restore timing at scale.

## 10. Remaining external dependencies
Google OAuth client and test mailbox (Gmail send, token refresh); PayPal merchant API credentials and a real
merchant check; AI provider and key (OD-05); SMTP relay; TLS proxy and hosting; ClamAV daemon; image scanner;
off-host store for backups and audit anchors; error-reporting choice.

## 11. Open decisions needing authorization
OD-04, OD-05, OD-08, OD-10, OD-11, OD-14 (briefs in `docs/pilot/open-decisions.md`) and SEC-22 legal review of
data-protection applicability. These are business, provider-terms or legal choices.

## 12. Known limitations
Only CASE_OPENED and REMINDER_DRAFT_READY notification kinds exist (FR-146). No real email by default. No key
rotation. Gmail monitoring and PayPal match candidates not built. Single-machine performance only.

## 13. Pilot-readiness assessment
Conditional yes: supervised pilot, human-approved messages, evidence imported by file. Needs section 10 items for
hosting, backups off-host and audit anchors stored elsewhere, then a first-week scheduler check.

## 14. Production-readiness assessment
No. Missing: real integrations, live AI evaluation, penetration test, image scan, error reporting, capacity test on
target hardware, legal review.

## Requirement classification
- Implemented and verified: core receivables, evidence, matching, cases, conversations, reminders (human-approved),
  audit, RLS, FL-08/09 screens (Vitest and e2e); E128, E129 (as a port), backup drill. FL-03/10/12/13/14/16 were re-run on 2026-11-08: Vitest 262/262 and Playwright 30/30 on the live local backend. `frontend/e2e/fl-live.spec.ts` drives only the live-capable slices (FL-03 invoice correction with a reason, FL-12 no payment shown without evidence, FL-10 cases screen, FL-13/16 Gmail never shown connected). The AI-dependent starts (a reply classified as a dispute, a reading to correct in FL-14), the PDF extraction review in FL-03, Gmail reconnect (FL-13, OD-11) and disconnect of a real connection (FL-16) are not driven live; they stay covered by stubbed Vitest only.
- Implemented but not fully verified: SMTP adapter, ClamAV adapter, Gmail send (no real mailbox), nightly scheduler soak.
- Not implemented: Gmail monitoring and token refresh, PayPal events as match candidates, key rotation, error reporting.
- Blocked by external dependency: Gmail/PayPal live use, live AI, image scan.
- Requires owner authorization: OD-04/05/08/10/11/14, SEC-22.
