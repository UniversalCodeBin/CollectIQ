# Implementation checkpoint

Short resume note. Update it at each task boundary, and keep it short.
Sources of record:
- Plan: `/home/white/.claude/plans/pasted-content-id-ab91-collectiq-abundant-cat.md` (40 tasks; read only the current task's section)
- Ledger, with every ruling: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/progress.md` (git-ignored)

## Last verified completed task
- **Task 14** is complete; the commit and ledger line follow this checkpoint. Evidence: 186 vitest (35 new), Playwright 9 of 9 (5 new, real API, four widths), make check 12 of 12.

## Current task
- **Task 15: accounts and coverage.** Next free endpoint is E117.

## Relevant files
- Frontend T14: frontend/src/features/{dashboard,receivables,invoice,client}/*, components/ui/QueryState.tsx, lib/format.ts (formatDate), lib/statusMap.ts; e2e/receivables.spec.ts; tests/web/receivables.test.tsx. Backend: invoices/read_models.py (null issue_date).

## Changes already made
- SCR-02, 03, 04 and 14 are live. Correct, cancel and archive work from the invoice page. Backend fix: invoice detail with no issue date.

## Tests actually run
- vitest 186 passed; Playwright 9 passed; make check 12/12.

## Outstanding work
- SCR-02/03/04/14 not yet compared against the Stitch screen.png (T38/T39). No filter or sort controls (FR-025/026). Client edit UI deferred. Invoice tabs for evidence, timeline, reconciliation and tasks arrive with their tasks.

## Next exact action
- Start Task 15 with task-start, tests first.

## Unresolved decisions
- `CollectIQ_Post_Implementation_Audit.md` (root, untracked) predates commit `a1448f4` and is stale on Task 2 and the frontend scaffold. Left untouched and uncommitted; the user decides whether to keep it.
- Open decisions OD-04, 05, 10, 11, 08, 14 still need the user; they do not block M0-M4.
