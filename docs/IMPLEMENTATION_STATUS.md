# Implementation status

The running record of what is built. The [audit](implementation-audit.md) explains why; the plan and its ledger hold the detail. Updated at each task boundary.

## Resume point

- **Branch:** `build/m0-m8`. Local commits only, with no remote.
- **Done:** dashboard (SCR-02), receivables queue and all-invoices list (SCR-03), invoice details with correct, cancel and archive (SCR-04), read-only client profile (SCR-14).
- **Done:** payment accounts, statement coverage and attestations (API only).
- **Done:** statement import (E053, API only): generic CSV parser, credit-only default, fingerprint dedupe, coverage confirmation.
- **Done:** Task 18, explainable match suggestions (E055, E056).
- **Done:** Task 19, confirmed allocations, reversal, manual payment, void and duplicate (E049-E052, E057-E061, API only).
- **Done:** Task 20, Reconciliation and Payment Accounts screens (SCR-06, SCR-15): review, confirmed, unmatched, allocate, manual payment with proof, statement upload with explicit date format, invoice Payment history (E117-E119).
- **Done:** Task 23, messages, timeline, claims, commitments and snooze (E062-E066, E071-E075, API only): encrypted pasted/eml/txt replies, person-confirmed association, payment claims open a verification task without touching balance, opt-out suppression, dispute cases from replies, commitments and approval-gated snooze with undo.
- **Done:** Task 22, disputes and blockers (E076-E082): dispute and blocker cases, reminders suppressed on open, human-only resolution, 24-hour cooling-off and approved resume.
- **Done (earlier):** Task 21, policy engine (E016-E020, E092, E101): pure gates G1-G15, single-use authorization, immutable policy versions, pause and resume, approvals, header pause control and SCR-10 settings.
- **Done:** Task 24, reminders and manual handoff (E083-E089, API only): template drafts with a deterministic fact block, content linter, gates re-run at approval and mark-sent, approval never sends, mark-sent records a hand-off, payments and cases cancel pending drafts.
- **Done:** Task 31, AI settings and flagged PDF extraction (E038-E041, E109-E110): per-workspace opt-ins default off plus a kill switch (Owner only, audited), PDF text extraction with content checks, extraction held as an unverified draft until a person edits and confirms, ungrounded values dropped, reply interpretation now gated on its opt-in, review page and AI settings page with an "AI not configured" notice. Summaries/wording drafts beyond this are not built.
- **Done:** Task 30, reply interpretation and deterministic date resolver (E067-E070): the gateway task `conversations.interpret` reads a stored reply, evidence must appear in the message, PAYMENT_CLAIM and DISPUTE auto-apply only at MEDIUM or HIGH as the AI actor, promise dates are resolved by code (ambiguous dates flagged, never guessed), no snooze without a passed real-data eval (AIR-12), person accept, dismiss and correct, injection corpus and synthetic evals.
- **Earlier:** Task 29, AI gateway (`ai/gateway.py`): allowlist, minimise, redact (email, phone, account become stable tokens), pseudonymise client names, cap, one JSON repair then fail-safe, bounded retries, rate limit, kill switch, explicit `AI_NOT_CONFIGURED`. The provider request has no tools field. `fake` is refused in production. 22 unit tests.
- **Earlier:** Task 28, Review Inbox UI and onboarding (SCR-17, SCR-01): inbox grouped by item type with each item linking to where it is resolved, notifications with mark-as-read, five more main-nav links (Receivables, Conversations, Disputes & Blockers, Follow-ups, Review Inbox), and a skippable, hideable getting-started checklist that remembers skips. Playwright covers onboarding and a draft that leaves the inbox once resolved.
- **Earlier:** Task 25, notifications and review inbox (E106-E108, API only): per-user notifications carrying ids and codes only, deduped; the inbox is derived read-only from cases, reminder drafts, match proposals, payment-claim tasks and approvals; leads see only assigned cases.
- **Next:** Task 31, summaries, wording, settings and flagged PDF extraction (E038-E041, E109-E110).

## T1 spike outcome

The toolchain runs on this host: Python 3.12 with uv, Node with npm, and PostgreSQL 16 in Podman.

- The database runs in container `collectiq-db` on `127.0.0.1:54329`. Container `elitepg` and port 55432 belong to something else and stay untouched.
- The application role `collectiq_app` is neither a superuser nor `BYPASSRLS`, and T4 proves forced RLS applies to it.
- The owner role has `CREATEDB`, which the test database needs.
- `make env` generates a local `.env`. `.env.example` holds placeholders only.

## Tasks

| Task | Result | Commit |
| --- | --- | --- |
| T1 Toolchain spike | Done | `5cd78f1` |
| T2 Scaffold and quality gate | Done; `make check` passing | `a1448f4` |
| T3 Audit and traceability | Done; `make check` passing | `1facbae` |
| T4 Tenant-scoped database layer | Done; `tests/rls` passing against Postgres as the app role | `5e96de0` |
| T5 Audit write path | Done; `tests/integration` passing against Postgres as the app role | `6744ad5` |
| T6 Idempotency, jobs, outbox and adapters | Done; `tests/integration` passing against Postgres as the app role | `ae8a8ec` |
| T7 Identity, workspaces and roles | Done; full suite passing against Postgres as the app role; 11 injected security faults all caught | `2697f90` |
| T8 Frontend foundation | 78 vitest, build, `make check` 12 of 12, fault injection all killed | `508c302` |
| T9 Auth screens, onboarding start, E2E harness | `make e2e` 3 passed, vitest 132 passed, build ok, `make check` 12 of 12, fault injection 0 survivors | `66e6e3e` |
| T10 Clients, contacts, suppression | E021-E028 live; 23 client tests, 13 fault injections killed, make test 434 + 132 passed, make check 12/12 | `fc7d7f8` |
| T11 Invoice CSV import | import tests green, 571 pytest + 132 vitest, make check 12 of 12, fault injection 9 of 9, 1,000-row preview and 10,000-row commit both well inside budget (10,000 rows 5.1 s) | `2335b50` |
| T12 Queue and dashboard read models | 681 pytest + 132 vitest, make check 12 of 12, fault injection 11 of 11 killed, k6 at 5,000 invoices within NFR-01 (list p95 931 ms, queue 1.07 s, dashboard 1.07 s) | `dad3c16` |
| T13 Invoice import and review UI | 19 new vitest (151 total), 1 new Playwright flow (4 of 4), make check 12 of 12; backend unchanged | `69b2d56` |
| T14 Dashboard, receivables, invoice details and client profile | 35 new vitest (186 total), 5 new Playwright tests on the real API incl. widths 320/768/1024/1440 (9 total), 1 new backend regression test, make check 12 of 12 | See `git log` |
| T15 Accounts, coverage and attestations | 26 unit tests (99% branch on evidence domain, gate ≥95%), 17 integration tests incl. TS-032 sequence, tenant isolation, append-only rows; make check 12 of 12 | See `git log` |
| T16 Statement import (E053) | 15 parser unit tests, 20 integration tests (TS-031 overlap, F-6 re-import, credit-only default, locale/BOM, coverage, row immutability), make check 12 of 12 | `feat(evidence): statement import` |
| T17 derive() and state maintenance | 20 property/table tests (every precedence branch, TS-011/012, INV-01, Hypothesis), 4 integration tests (recompute/version, outbox follow, seeded-drift detection and audited repair), make check 12 of 12 | `feat(evidence): payment state derivation` |
| T19 Confirmed allocations and reversals | 874 pytest in total, of which the two new allocation files cover triggers, TS-011/012, F-8 races, the database backstop and a Hypothesis state-equals-derive property; `evidence.domain` 96% combined statement and branch on the full run, gate ≥95%, before one further matcher test; make check 12 of 12 | `feat(evidence): confirmed allocations and reversals` |
| T20 Reconciliation and Payment Accounts screens | E117, E118, E119 added; 5 new Playwright tests on the real API (14 total), 3 new vitest, 2 new backend tests; 884 pytest, 199 vitest, make check 12 of 12 | `feat(web): reconciliation e2e, invoice history, allocate unmatched` |
| T32 Live AI provider adapter | Deferred: no provider chosen (OD-05); fake provider is dev/test only | n/a |
| T33 Integration registry and lifecycle (E093) | 9 integration tests (no connected state without verification, DB CHECK, Owner-only, audited, tenant isolation), 1 vitest; 1212 pytest + 234 vitest, make check 12 of 12 | this commit |
| T34 Gmail send-only and PayPal webhook adapters (E090, E091, E094, E095, E097, E098) | 23 provider tests on fake transports (scopes, PKCE state, sealed tokens, no auto retry on unknown, evidence-only webhooks), flags off by default; not verified against Gmail or PayPal | this commit |
| T35 Audit History (E099, E100) | 6 backend tests (tenant-scoped search, paging, CSV formula neutralisation, audited export, seeded chain break detected by `audit.verify_chain`), 1 vitest; append-only wording with the superuser limit | this commit |
| T36 Settings and payload inspector (E102-E105) | 9 backend tests (export scope and secret exclusion, Owner-only, typed-confirmation deletion with zero-row scan, audit retained, payload inspector with tokens only, retention), 1 interpretation test, 4 vitest; members, export/deletion and payload tabs | this commit |

## Open items carried forward

- 13 moderate npm audit findings to revisit at T39.
- Old idempotency rows and finished jobs are not purged yet; only a key's own expired row is removed. Revisit at T37 or T40.
- `workspace_keys` is select and insert only for the app role, so crypto-shredding in the deletion task needs a privileged path.
- The CI file exists but has never run (plan A10).
- Endpoint gaps in the audit are added as `proposed-new` by T7, T25 and T31, then listed in the final report for approval.
- `X-Forwarded-For` is not trusted yet, and stale `auth_throttles` rows are not purged. Revisit at T40.
- T14: proposed-new endpoint to add a client alias (SCR-14 'add alias'), plus contact rules (FR-149).
- T19 handled gross changes on an invoice with allocations: a total lowered below what is paid derives UNCERTAIN with a flag (test_lowered_total_below_paid_becomes_uncertain_not_paid). A guard on the correction path remains an option.
- T13: COMMIT allowed_actions reflects no decisions; the UI works out readiness from local decisions
- Next free endpoint id is E117
FR-025 filter controls and FR-026 sort and Reset to exception order have no UI yet; FR-023 supporting-evidence links wait for T15+.
