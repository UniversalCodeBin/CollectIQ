# Implementation checkpoint

Short resume note. Update it at each task boundary, and keep it short.
Sources of record:
- Plan: `/home/white/.claude/plans/pasted-content-id-ab91-collectiq-abundant-cat.md` (40 tasks; read only the current task's section)
- Ledger, with every ruling: `.superpowers/sdd/pasted-content-id-ab91-collectiq-abundant-cat/progress.md` (git-ignored)

## Last verified completed task
- **Task 12** is complete; the commit and ledger line follow this checkpoint. Evidence: 681 pytest, 132 vitest, make check 12 of 12, fault injection 11 of 11 killed, k6 at 5,000 invoices within NFR-01.

## Current task
- **Task 13: invoice import UI** (SCR-05 upload, mapping, preview, decisions, error report).

## Relevant files
- Backend T12: api/invoice_views.py, invoices/{read_models,service_invoice,state}.py, invoices/domain/queue.py, migration 0003, management/commands/seed_sample.py.
- Benchmark: backend/perf/{setup_read_models.py,read_models.js}.

## Changes already made
- E042-E048 implemented and contract-tested; invoice_state table with row security; import now writes states and IMPORT_FAILED.

## Tests actually run
- pytest 681 passed; vitest 132; make check 12/12; mutate.py 11/11 killed; k6 5 VUs 30 s at 5,000 invoices: list p95 931 ms, queue 1.07 s, dashboard 1.07 s, detail 426 ms, 0 failures.

## Outstanding work
- Frontend for E042-E048 arrives with T13/T14. Benchmark ran on the development server only (T39 re-measures). Port 8000 is held by an unrelated process; the benchmark used 8765.

## Next exact action
- Start Task 13 with task-start, tests first.

## Unresolved decisions
- `CollectIQ_Post_Implementation_Audit.md` (root, untracked) predates commit `a1448f4` and is stale on Task 2 and the frontend scaffold. Left untouched and uncommitted; the user decides whether to keep it.
- Open decisions OD-04, 05, 10, 11, 08, 14 still need the user; they do not block M0-M4.
