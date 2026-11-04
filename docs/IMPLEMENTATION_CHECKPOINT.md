# Implementation checkpoint

Short resume note. Update it at each task boundary, and keep it short.
Sources of record:
- Plan: `/home/white/.claude/plans/pasted-content-id-ab91-collectiq-abundant-cat.md` (40 tasks; read only the current task's section)
- Ledger, with every ruling: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/progress.md` (git-ignored)

## Last verified completed task
Task 11 invoice CSV import

## Current task
Task 12 read models

## Relevant files
backend/collectiq/invoices/service_import.py, invoices/domain/*, api/import_views.py

## Changes already made
Import committed

## Tests actually run
571 pytest, 132 vitest, make check 12/12, fault injection 9/9

## Outstanding work
Tasks 12-40

## Next exact action
task-start 12

## Unresolved decisions
- `CollectIQ_Post_Implementation_Audit.md` (root, untracked) predates commit `a1448f4` and is stale on Task 2 and the frontend scaffold. Left untouched and uncommitted; the user decides whether to keep it.
- Open decisions OD-04, 05, 10, 11, 08, 14 still need the user; they do not block M0-M4.
