# Readiness baseline (2026-11-07, commit 4c26f51)

Rerun from a clean working tree, sequentially, against `collectiq-db`:

| Check | Result |
|---|---|
| `make test` backend | 1,278 passed (11 min) |
| `make test` Vitest | 240 passed, 22 files |
| `make e2e` Playwright | 29 passed (2.8 min) |
| `make check` | 13 of 13 gates |

This reconciles the acceptance report: its test counts hold (1,277 then, 1,278 now after the claims test fix).

## Blockers for a supervised pilot

| # | Blocker | Severity | Owner |
|---|---|---|---|
| 1 | No email delivery (file/memory only): invitations, resets and reminders cannot reach anyone | Critical | I build SMTP backend; owner supplies credentials |
| 2 | No upload malware scanning (OD-14) | Critical for any upload | I build ClamAV adapter; owner approves |
| 3 | No hosting/staging target (OD-04) | Critical | Owner |
| 4 | Data-protection review not done (SEC-22, OD-08) | Critical for real people's data | Owner and counsel |
| 5 | Per-client and per-invoice pause missing | High | I build |
| 6 | Snoozes do not end on their date; notification retention not enforced | High | I build |
| 7 | UI gaps: send/connect/confirm-unknown buttons, SUBMITTED labels, pending interpretations | High | Built (E124 and screens); real-Gmail send unverified |
| 8 | AI provider not chosen (OD-05); Task 32, summaries, wording drafts | Medium (AI is off by default) | Owner |
| 9 | No independent pen test, screen-reader audit, image scan | Medium | External |
| 10 | Backup encryption, off-database audit anchor, break-glass, restore timing at scale | Medium | Partly me, partly hosting |
