# Implementation status

The running record of what is built. The [audit](implementation-audit.md) explains why; the plan and its ledger hold the detail. Updated at each task boundary.

## Resume point

- **Branch:** `build/m0-m8`. Local commits only, with no remote.
- **Done:** M0 (Tasks 1 to 3), Task 4.
- **Next:** Task 5, audit write path.

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
| T4 Tenant-scoped database layer | Done; `tests/rls` passing against Postgres as the app role | See `git log` |

## Open items carried forward

- 13 moderate npm audit findings to revisit at T39.
- The CI file exists but has never run (plan A10).
- Endpoint gaps in the audit are added as `proposed-new` by T7, T25 and T31, then listed in the final report for approval.
