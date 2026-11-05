# Implementation checkpoint

Short resume note. Update it at each task boundary, and keep it short.
Sources of record:
- Plan: `/home/white/.claude/plans/pasted-content-id-ab91-collectiq-abundant-cat.md` (40 tasks; read only the current task's section)
- Ledger, with every ruling: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/progress.md` (git-ignored)

## Last verified completed task
- **Task 16** is complete; the commit follows this checkpoint. Evidence: 15 parser unit tests, 20 integration tests, make check 12 of 12.

## Current task
- **Task 19: allocation, reversal, manual payment, void, duplicate (E049-E052, E057-E061).** Task 18 is done (matcher m1-2026-11, reconciliation_matches, E055/E056, TransactionsImported subscriber). T19 must replace the `service_state._allocation_amounts` seam, implement E057 confirm and E058 reject over `service_matching.reject`, exclude allocated transactions from E055, and add allocation operations to the state-equals-derive property. Nightly scheduling of evidence.integrity_check is still to wire (T37/T40). Next free endpoint is E117.

## Relevant files
- Frontend T14: frontend/src/features/{dashboard,receivables,invoice,client}/*, components/ui/QueryState.tsx, lib/format.ts (formatDate), lib/statusMap.ts; e2e/receivables.spec.ts; tests/web/receivables.test.tsx. Backend: invoices/read_models.py (null issue_date).

## Changes already made
- SCR-02, 03, 04 and 14 are live. Correct, cancel and archive work from the invoice page. Backend fix: invoice detail with no issue date.

## Tests actually run
- vitest 186 passed; Playwright 9 passed; make check 12/12.

## Outstanding work
- SCR-02/03/04/14 not yet compared against the Stitch screen.png (T38/T39). No filter or sort controls (FR-025/026). Client edit UI deferred. Invoice tabs for evidence, timeline, reconciliation and tasks arrive with their tasks.

## Next exact action
- Start Task 19 with tests first. Candidate loading in service_matching is O(transactions x open invoices) in Python; benchmark in T37.

## Unresolved decisions
- ~20 committed backend files (audit, identity, platform, settings, tenancy, two api views) are reformatted but uncommitted from a mistaken `ruff format`; reverting was refused by the permission check. Run `git checkout --` on them; do not commit them.
- `CollectIQ_Post_Implementation_Audit.md` (root, untracked) predates commit `a1448f4` and is stale on Task 2 and the frontend scaffold. Left untouched and uncommitted; the user decides whether to keep it.
- Open decisions OD-04, 05, 10, 11, 08, 14 still need the user; they do not block M0-M4.
- Task 19 needs Opus 5.5 High (ledger triggers, deferred constraints, concurrency races: financial integrity). Resume: switch model, then say "continue Task 19". Switch back to Sonnet 5.5 Medium after Task 19 is committed.
