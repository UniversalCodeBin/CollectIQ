# Implementation checkpoint

Short resume note. Update it at each task boundary, and keep it short.
Sources of record:
- Plan: `/home/white/.claude/plans/pasted-content-id-ab91-collectiq-abundant-cat.md` (40 tasks; read only the current task's section)
- Ledger: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/progress.md` (git-ignored)

## Last verified completed task
- **Task 29** (AI gateway) complete; commit follows. Evidence: 22 gateway unit tests, make check 12/12. Task 28 is `ea3028c`.

## Current task
- **Task 30: reply interpretation and date resolver** (E066-E070): `ai/date_resolver.py`, `conversations/service_interpretation.py`, evals, injection corpus. Gateway API: `Gateway(provider, AIConfig).run(task_id, payload, scope)`; register tasks with `ai.registry.register(TaskSpec(...))`. Next free endpoint E120.

## Owed carry-forwards
- Per-client and per-invoice pause; end snoozes when their date passes (`end_due_snoozes`); E085 should expose `cases.service.request_resume`; MATCH_REVIEW case type migration (invoice_id NOT NULL); AllocationConfirmed/Reversed FR-057 case opening; close `verification_tasks` and decrement `open_task_count`; nightly `evidence.integrity_check` (T37/T40); N+1 `_history`, candidate loading and E065 cursor paging (T37); 90-day notification retention; notification preferences (FR-146).

## Unresolved decisions
- `CollectIQ_Post_Implementation_Audit.md` (root, untracked) left untouched and uncommitted.
- Open decisions OD-04, 05, 08, 10, 11, 14 need the user; they do not block current work.
