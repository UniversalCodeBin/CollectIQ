# Implementation checkpoint

Short resume note. Update it at each task boundary, and keep it short.
Sources of record:
- Plan: `/home/white/.claude/plans/pasted-content-id-ab91-collectiq-abundant-cat.md` (40 tasks; read only the current task's section)
- Ledger, with every ruling: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/progress.md` (git-ignored)

## Last verified completed task
Task 6, idempotency, jobs, outbox and adapters. See `git log` for the commit.

## Current task
Task 7: identity, tenancy, authorization and the endpoint registry.

## Relevant files
- Brief: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/task-7-brief.md`
- `docs/implementation-status.md`, `docs/implementation-audit.md`
- `backend/collectiq` (all backend code lives here); `backend/collectiq/platform` holds `tenant_tx`, `@idempotent`, `enqueue`, `job_handler`, `publish`, `get_storage`, `get_cipher`

## Changes already made
M0 and Tasks 4 to 6 are committed. `tenant_tx` joins an open transaction of the same scope and refuses any other.
Database tests use the `pg` fixture in `backend/tests/conftest.py`, not `django_db`; `owner_db` gives an owner connection.

## Tests actually run
- See the Task 6 line in the ledger for the final counts. `make check` does not run the database tests.

## Outstanding work
Tasks 7 to 40, in order. Fresh reviewer at the M3 and M4 gates and on the whole branch at the end.

## Next exact action
Run `task-start` for Task 7 and read its brief. T7 must set `request.ctx`, bind the correlation id in middleware, and add a user-scoped `@idempotent` variant for E001 and E010.

## Unresolved decisions
- `CollectIQ_Post_Implementation_Audit.md` (root, untracked) predates commit `a1448f4` and is stale on Task 2 and the frontend scaffold. Left untouched and uncommitted; the user decides whether to keep it.
- Open decisions OD-04, 05, 10, 11, 08, 14 still need the user; they do not block M0-M4.
