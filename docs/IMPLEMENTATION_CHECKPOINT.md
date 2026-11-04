# Implementation checkpoint

Short resume note. Update it at each task boundary, and keep it short.
Sources of record:
- Plan: `/home/white/.claude/plans/pasted-content-id-ab91-collectiq-abundant-cat.md` (40 tasks; read only the current task's section)
- Ledger, with every ruling: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/progress.md` (git-ignored)

## Last verified completed task
Task 7, identity, workspaces and roles. See `git log` for the commit.

## Current task
Task 8: frontend foundation.

## Relevant files
- Brief: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/task-8-brief.md`
- `frontend/`, `docs/api/openapi.generated.yaml`, `frontend/src/lib/api-types.ts`
- `backend/collectiq/api/registry.py` holds `@endpoint`, the guard and the endpoint specs

## Changes already made
M0 and Tasks 4 to 7 are committed. Views use `@endpoint("E0xx")`, which authenticates, enforces CSRF and sets `request.ctx`. `@idempotent` goes under it.
Database tests use the `pg` fixture; `backend/tests/support.py` has `logged_in`, `owner_workspace`, `add_member`, `idem`.

## Tests actually run
See the Task 7 line in the ledger. `make check` does not run the database tests.

## Outstanding work
Tasks 8 to 40, in order. Fresh reviewer at the M3 and M4 gates and on the whole branch at the end.

## Next exact action
Run `task-start` for Task 8 and read its brief.

## Unresolved decisions
- `CollectIQ_Post_Implementation_Audit.md` (root, untracked) predates commit `a1448f4` and is stale on Task 2 and the frontend scaffold. Left untouched and uncommitted; the user decides whether to keep it.
- Open decisions OD-04, 05, 10, 11, 08, 14 still need the user; they do not block M0-M4.
