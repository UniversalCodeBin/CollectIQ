# Implementation checkpoint

Short resume note. Update it at each task boundary, and keep it short.
Sources of record:
- Plan: `/home/white/.claude/plans/pasted-content-id-ab91-collectiq-abundant-cat.md` (40 tasks; read only the current task's section)
- Ledger: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/progress.md` (git-ignored)

## Last verified completed task
- **Task 36** (Settings, export, deletion, payload inspector) complete; commit follows. Task 35 is `0eb3aa5`. Task 32 deferred (OD-05).

## Current task
- **Task 37** (audit completeness, critical negatives, runbooks). Next free endpoint E120. Owed: nightly scheduling of `audit.verify_chain`, `evidence.integrity_check`, `privacy.retention`; why-view link from audit rows; legal name and sender display name.

## Owed carry-forwards
- Per-client and per-invoice pause; end snoozes when their date passes (`end_due_snoozes`); E085 should expose `cases.service.request_resume`; MATCH_REVIEW case type migration (invoice_id NOT NULL); AllocationConfirmed/Reversed FR-057 case opening; close `verification_tasks` and decrement `open_task_count`; nightly `evidence.integrity_check` (T37/T40); N+1 `_history`, candidate loading and E065 cursor paging (T37); 90-day notification retention; notification preferences (FR-146).

## Unresolved decisions
- `CollectIQ_Post_Implementation_Audit.md` (root, untracked) left untouched and uncommitted.
- Open decisions OD-04, 05, 08, 10, 11, 14 need the user; they do not block current work.
