# CollectIQ — Implementation Roadmap (M0–M8)

Dependency-aware sequence for Claude Code and the engineering team. Durations are deliberately omitted (no velocity data); SAD MS-1…8 week ranges are indicative only. **Current state: nothing implemented; no repository supplied.** Module IDs M01–M20 refer to TSD §6; endpoint IDs E001–E112 to `CollectIQ_API_Contracts.yaml`.

**Global rules for every milestone.** Merge only with: tests for changed behaviour; OpenAPI diff clean; audit event asserted for state changes; RLS coverage test green; no float money; no secrets/PII in fixtures. A milestone is complete only when its **completion gate** passes in CI.

---
## M0 — Repository and specification audit
**Deliverables:** repo scaffold (§5 structure), CI skeleton (lint, types, tests, import-boundary linter, secret scan, OpenAPI diff), `docs/`; confirm source gaps (DESIGN.md, Stitch, SCR-16/17); per-requirement traceability refinement (OD-22); collect bank/PayPal sample files (OD-10).
**Depends on:** approvals OD-03, OD-12 (can proceed provisionally).
**Acceptance:** empty skeleton passes CI; import-boundary rule demonstrably fails on a seeded violation; traceability CSV has requirement-level (not range-level) mapping for P0.
**Tests:** CI meta-tests. **Risks:** stack rejected → rework scaffold only.
**Completion gate:** approvals recorded; CI green.

## M1 — Foundation: auth, tenancy, roles, platform, design system
**Deliverables:** M01 auth/session (E001–E009), M02 workspace + RLS, M03 roles, platform (jobs, outbox, idempotency, problem+json, logging scrubbers, crypto/storage abstractions), audit core (M18 write path), frontend shell + design tokens + routing + typed client.
**Depends on:** M0. **Acceptance:** cross-tenant access returns 404 in every test; authz matrix generated from the registry passes; idempotency replay works; jobs survive worker kill (lease expiry).
**Tests:** RLS suite (TS-024), authz matrix, CSRF/enumeration, job chaos. **Risks:** RLS misconfiguration (mitigate: CI table-coverage test, non-owner app role).
**Gate:** TS-024 + authz matrix green; no tenant table without forced RLS.

## M2 — Data model, invoice import, ledger
**Deliverables:** schema for clients/contacts/invoices/invoice_state/import_batches/stored_files/extraction_results; M05 CSV import (E033–E037) with explicit date format, validation report, duplicate handling; M06 list/queue read model (E042, E047, E048 baseline); M07 invoice detail, client profile, suppression; PDF extraction **only if** OD-19/OD-05/OD-14 resolved (flagged OFF otherwise).
**Depends on:** M1. **Acceptance:** FR-001…FR-018 CSV path; re-import creates no duplicates; every queue row has a reason.
**Tests:** TS-002, TS-003 (if PDF), fixtures for BOM/locale dates, NFR-01 baseline measurement. **Risks:** locale/date ambiguity; large files.
**Gate:** TS-002 green; load baseline recorded.

## M3 — Statement ingestion and reconciliation
**Deliverables:** M08 accounts/coverage/attestations (E029–E032, E054); M09 statement import (E053); M10 matcher, proposals, confirm/reject, manual payment, allocation/reversal/void, duplicate marking (E049–E061); `derive()` and `invoice_state` maintenance; evidence-coverage derivation (AC-1).
**Depends on:** M2, OD-10, OD-16. **Acceptance:** invariants F-1…F-9; ambiguous matches never auto-confirmed; coverage gaps block `SUPPORTED`.
**Tests:** property tests, concurrency (N parallel confirms), TS-004, 011, 012, 013, 031, 032, 033. **Risks:** derivation corner cases (OD-13); matcher weights (OD-09).
**Gate:** all F-invariant tests + TS above green; DB negative tests as app role pass.

## M4 — Policy engine, disputes, conversation workflows
**Deliverables:** M15 `evaluate()`, G1–G15, `policy_decisions`, approvals, pause/resume, policy versions (E016–E020, E074/E075, E092, E101); M13 cases (E076–E082); M11 message capture/timeline (E062–E066, E063 if approved); commitments (E071–E073); reminder drafts template-only + linter + approve/mark-sent (E083–E089).
**Depends on:** M3, OD-06, OD-07, OD-17, OD-20. **Acceptance:** no consequential action without `AuthorizedAction`; gates re-run under lock; disputed invoice never receives a reminder; no AUTO_SEND exists.
**Tests:** gate matrix, TOCTOU concurrency, mutation testing of policy package, TS-001, 006, 009, 010, 021, 027, 034, 035. **Risks:** policy bypass paths (mitigate: static check on executors).
**Gate:** TS-001/006/009/010/021 green; static check for `AuthorizedAction` usage green.

## M5 — AI interpretation and human-approved follow-ups
**Deliverables:** M12 gateway (allowlist, redaction, pseudonymisation, kill switch), prompt/schema registry, T2 interpretation, evidence-span check, deterministic date resolver, injection flag, review/accept/dismiss/correct (E066–E070) with reversal of derived actions; T3/T4 explanations; optional T5/T6 drafting; AI settings (E109/E110); payload recording.
**Depends on:** M4, OD-05, OD-09. **Acceptance:** model has no tools/DB access; invalid outputs rejected; injection cannot trigger action; correction reverses derived actions; auto-snooze unavailable until AIR-12 report passes for exact prompt+model config.
**Tests:** offline evaluation, recorded-response replay, schema fuzz, injection corpus, TS-005, 007, 008, 015, 020, 029, 030. **Risks:** provider terms; unsafe auto-snooze (zero tolerance).
**Gate:** TS-015/020/030 green; AIR-12 report (≥150 labelled replies, 0 unsafe) required only for enabling auto-snooze.

## M6 — Integrations management and review inbox
**Deliverables:** M16 integration shell (E093), Gmail send-only OAuth + send protocol with `SUBMISSION_UNKNOWN` (E090/E091/E094/E095/E097) **[P1, gated]**, monitoring consent + polling of tracked threads (E096) **[P1, gated by OD-11]**, PayPal sandbox webhook (E098) **[P1]**; M17 notifications and review inbox (E106–E108).
**Depends on:** M4 (policy), OD-11, OD-04 (secrets/KMS). **Acceptance:** send-only grant contains no read scope; out-of-scope mail never fetched; invalid webhook signature changes nothing; revoked token pauses dependent automation.
**Tests:** provider sandbox contract tests, TS-016, 018, 019, 025, 026, 014 (webhook dedupe). **Risks:** OAuth verification/assessment delay → P0 unaffected.
**Gate:** TS-016/018/025/026 green; P0 release not blocked by M6.

## M7 — Audit history, workspace settings, hardening
**Deliverables:** M18 search/export UI/API (E099–E101), M19 settings/export/deletion/payload inspector (E102–E105), hash-chain verification job, retention jobs, runbooks (wrong-send suspicion, token compromise, bad-allocation fix), security review fixes.
**Depends on:** M5, M6 (partly). **Acceptance:** exactly one audit event per consequential change; export/deletion honoured incl. key shredding (if approved); inspector shows redacted payloads as sent.
**Tests:** TS-022, 023, 028; backup/restore drill; chaos tests. **Risks:** retention/legal unresolved (OD-08).
**Gate:** TS-023 harness covers every mutating endpoint.

## M8 — End-to-end validation, deployment readiness, documentation
**Deliverables:** E2E for FL-01…FL-16, accessibility (WCAG 2.2 AA), performance vs §20, penetration-style review, staging deployment, pilot readiness checklist, final doc updates.
**Depends on:** M6/M7 (P0 scope), OD-04, OD-05, OD-08, OD-14 for pilot. **Acceptance:** all release-blocking tests green; no open Sev-1/2; claims audit passes (no unsupported compliance/immutability/accuracy statements).
**Gate:** TSD §24 checklist fully ticked.

---
## Dependency overview
M0 → M1 → M2 → M3 → M4 → M5 → M7 → M8; M4 → M6 → M8. P1 items (Gmail, PayPal, monitoring, MFA, project lead) may slip without blocking P0 release.
