# Implementation checkpoint

Short resume note. Update it at each task boundary, and keep it short.
Sources of record:
- Plan: `/home/white/.claude/plans/pasted-content-id-ab91-collectiq-abundant-cat.md` (40 tasks; read only the current task's section)
- Ledger, with every ruling: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/progress.md` (git-ignored)

## Last verified completed task
- **Task 23** (messages, claims, commitments, snooze; E062-E066, E071-E075) is complete; the commit follows this checkpoint. Evidence: see the Task 23 commit message.

## Current task
- **Task 24: Reminders and manual handoff (E083-E089).** Owed: subscribers on `CaseOpened` to cancel drafts and snoozes; end active snoozes when their date passes; a path to close `verification_tasks` and decrement `open_task_count` (T25/T30); the E065 timeline has no cursor paging (T37). From T22: E085 should expose `cases.service.request_resume`; MATCH_REVIEW case type needs a migration (invoice_id is NOT NULL). Still owed from T19: AllocationConfirmed/Reversed subscribers (FR-057); nightly evidence.integrity_check (T37/T40). Next free endpoint is E120.

## Relevant files
- Frontend T14: frontend/src/features/{dashboard,receivables,invoice,client}/*, components/ui/QueryState.tsx, lib/format.ts (formatDate), lib/statusMap.ts; e2e/receivables.spec.ts; tests/web/receivables.test.tsx. Backend: invoices/read_models.py (null issue_date).

## Changes already made
- SCR-02, 03, 04 and 14 are live. Correct, cancel and archive work from the invoice page. Backend fix: invoice detail with no issue date.

## Tests actually run
- vitest 186 passed; Playwright 9 passed; make check 12/12.

## Outstanding work
- SCR-02/03/04/14 not yet compared against the Stitch screen.png (T38/T39). No filter or sort controls (FR-025/026). Client edit UI deferred. Invoice tabs for evidence, timeline, reconciliation and tasks arrive with their tasks.

## Next exact action
- Start Task 23 with tests first. Candidate loading in service_matching is O(transactions x open invoices) in Python and `_history` is N+1; benchmark both in T37.

## Unresolved decisions
- `CollectIQ_Post_Implementation_Audit.md` (root, untracked) predates commit `a1448f4` and is stale on Task 2 and the frontend scaffold. Left untouched and uncommitted; the user decides whether to keep it.
- Open decisions OD-04, 05, 10, 11, 08, 14 still need the user; they do not block M0-M4.
