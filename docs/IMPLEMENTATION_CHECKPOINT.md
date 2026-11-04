# Implementation checkpoint

Short resume note. Update it at each task boundary, and keep it short.
Sources of record:
- Plan: `/home/white/.claude/plans/pasted-content-id-ab91-collectiq-abundant-cat.md` (40 tasks; read only the current task's section)
- Ledger, with every ruling: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/progress.md` (git-ignored)

## Last verified completed task
Task 5, audit write path. See `git log` for the commit.

## Current task
Task 6: idempotency, jobs, outbox, logging, storage and crypto.

## Relevant files
- Brief: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/task-6-brief.md`
- `docs/implementation-status.md`, `docs/implementation-audit.md`
- `backend/collectiq` (all backend code lives here)

## Changes already made
M0, T4 and T5 are committed: scaffold, quality gate, audit, traceability, `tenant_tx`, `user_tx`, `enable_rls`, `Money`, `ProblemError`, `audit.record`.
Database tests use the `pg` fixture in `backend/tests/conftest.py`, not `django_db`; `owner_db` gives an owner connection.

## Tests actually run
- `make check`: 12 of 12 steps passed.
- `make test`: 104 pytest and 6 vitest passing against `collectiq_test` as `collectiq_app`. `make check` does not run the database tests.

## Outstanding work
Tasks 6 to 40, in order. Fresh reviewer at the M3 and M4 gates and on the whole branch at the end.

## Next exact action
Run `task-start` for Task 6 and read its brief.

## Unresolved decisions
- `CollectIQ_Post_Implementation_Audit.md` (root, untracked) predates commit `a1448f4` and is stale on Task 2 and the frontend scaffold. Left untouched and uncommitted; the user decides whether to keep it.
- Open decisions OD-04, 05, 10, 11, 08, 14 still need the user; they do not block M0-M4.
