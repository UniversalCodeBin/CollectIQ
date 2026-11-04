# Implementation status

The running record of what is built. The [audit](implementation-audit.md) explains why; the plan and its ledger hold the detail. Updated at each task boundary.

## Resume point

- **Branch:** `build/m0-m8`. Local commits only, with no remote.
- **Done:** T1–T8 (M0 scaffold, tenancy, audit, platform, identity; web foundation).
- **Next:** T9 auth screens and first E2E.

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
| T8 Frontend foundation | 78 vitest, build, `make check` 12 of 12, fault injection all killed | See `git log` |

## Open items carried forward

- 13 moderate npm audit findings to revisit at T39.
- Old idempotency rows and finished jobs are not purged yet; only a key's own expired row is removed. Revisit at T37 or T40.
- `workspace_keys` is select and insert only for the app role, so crypto-shredding in the deletion task needs a privileged path.
- The CI file exists but has never run (plan A10).
- Endpoint gaps in the audit are added as `proposed-new` by T7, T25 and T31, then listed in the final report for approval.
- `X-Forwarded-For` is not trusted yet, and stale `auth_throttles` rows are not purged. Revisit at T40.
