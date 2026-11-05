# Implementation status

The running record of what is built. The [audit](implementation-audit.md) explains why; the plan and its ledger hold the detail. Updated at each task boundary.

## Resume point

- **Branch:** `build/m0-m8`. Local commits only, with no remote.
- **Done:** dashboard (SCR-02), receivables queue and all-invoices list (SCR-03), invoice details with correct, cancel and archive (SCR-04), read-only client profile (SCR-14).
- **Done:** payment accounts, statement coverage and attestations (API only).
- **Next:** Task 16, statement import.

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

## Open items carried forward

- 13 moderate npm audit findings to revisit at T39.
- Old idempotency rows and finished jobs are not purged yet; only a key's own expired row is removed. Revisit at T37 or T40.
- `workspace_keys` is select and insert only for the app role, so crypto-shredding in the deletion task needs a privileged path.
- The CI file exists but has never run (plan A10).
- Endpoint gaps in the audit are added as `proposed-new` by T7, T25 and T31, then listed in the final report for approval.
- `X-Forwarded-For` is not trusted yet, and stale `auth_throttles` rows are not purged. Revisit at T40.
- T14: proposed-new endpoint to add a client alias (SCR-14 'add alias'), plus contact rules (FR-149).
- T17/T19: updating gross_minor on an invoice with allocations must be handled once allocations exist
- T13: COMMIT allowed_actions reflects no decisions; the UI works out readiness from local decisions
- Next free endpoint id is E117
FR-025 filter controls and FR-026 sort and Reset to exception order have no UI yet; FR-023 supporting-evidence links wait for T15+.
