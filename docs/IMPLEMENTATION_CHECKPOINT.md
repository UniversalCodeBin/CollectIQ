# Implementation checkpoint

Short resume note. Update it at each task boundary, and keep it short.
Sources of record:
- Plan: `/home/white/.claude/plans/pasted-content-id-ab91-collectiq-abundant-cat.md` (40 tasks; read only the current task's section)
- Ledger, with every ruling: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/progress.md` (git-ignored)

## Last verified completed task
- **Task 13** is complete; the commit and ledger line follow this checkpoint. Evidence: 151 vitest (19 new), Playwright 4 of 4 including a real import, make check 12 of 12.

## Current task
- **Task 14: invoice list, queue, detail and dashboard screens** (SCR-02, 03, 04, 14). Next free endpoint is E117.

## Relevant files
- Frontend T13: frontend/src/features/import/{ImportPage,UploadStep,MappingStep,ReviewStep,DoneStep,ChoiceGroup}.tsx, decisions.ts, types.ts; lib/api.ts (FormData, apiText); lib/format.ts (formatMinor); e2e/import.spec.ts; tests/web/import.test.tsx.

## Changes already made
- SCR-05 import flow is live and reachable from the dashboard's Getting started list. Backend unchanged.

## Tests actually run
- vitest 151 passed; Playwright 4 passed; make check 12/12. One auth test flaked once under a cold full run and passed on every rerun (ledgered).

## Outstanding work
- SCR-05 not yet compared against the Stitch screen.png (T38/T39 visual check). No Add menu in the shell yet. FR-007 provenance shows on the detail screen in T14.

## Next exact action
- Start Task 14 with task-start, tests first.

## Unresolved decisions
- `CollectIQ_Post_Implementation_Audit.md` (root, untracked) predates commit `a1448f4` and is stale on Task 2 and the frontend scaffold. Left untouched and uncommitted; the user decides whether to keep it.
- Open decisions OD-04, 05, 10, 11, 08, 14 still need the user; they do not block M0-M4.
