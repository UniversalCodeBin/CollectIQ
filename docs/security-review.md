# Security review and threat register mapping (Task 39)

Scope: the threat register T-01 to T-20 in `CollectIQ_SAD_v0.1.md`. "Tested" means an automated test in this
repository exercises the control. "Not built" and "Owed" are stated as such; nothing here is a certification
or a penetration test. No person has audited the screens with a screen reader.

| ID | Threat | Control in the code | Evidence | Status |
|---|---|---|---|---|
| T-01 | Credential stuffing | Argon2id, lockout with Retry-After, IP rate limit, session limits | `test_identity.py`: lockout, lock window, IP rate limit, idle and absolute session limits | Tested. Breached-password check and MFA not built (P1) |
| T-02 | Privilege escalation | Central `authorize()`, permission table | `contract/test_authz_matrix.py`, `unit/test_authorize.py`, `meta/test_authorized_action_static.py` | Tested |
| T-03 | Cross-tenant leakage | Forced row security, composite FKs, 404 for foreign ids, context-less jobs see nothing | `rls/test_context.py`, `rls/test_table_coverage.py`, per-module tenant tests | Tested |
| T-04 | Refresh-token exposure | Sealed credentials, never in logs or exports | `test_integrations.py`, `test_settings_privacy.py` (export excludes sealed values), log scrubber | Tested. Token refresh not built |
| T-05 | Malicious PDF/CSV | Request size cap, scan status, flagged PDF path, no network from parsing | `test_import.py` oversized request, `test_extraction.py` | Partly. PDF size limit and page limit owed; no isolated worker |
| T-06 | Formula injection in exports | Leading quote on `= + - @` tab CR | `test_audit_history.py::test_export_neutralises_csv_formula_cells` | Tested |
| T-07 | Prompt injection | No tools, schema validation, enum actions, span checks, policy gate, human approval | `safety/test_injection_corpus.py`, `unit/test_ai_gateway.py`, `safety/test_critical_negatives.py` | Tested on the fake provider and the corpus only; no live-model result |
| T-08 | AI provider retention | Redaction to tokens, opt-in for PDFs, 30-day payload retention, inspector | `test_settings_privacy.py` | Tested locally. Provider terms review (OPEN-09) is open |
| T-09 | Sensitive data in logs | Scrubber on every log route | `unit/test_platform_adapters.py` (email, token, amount, extras, exceptions, route coverage) | Tested |
| T-10 | API abuse, forged webhooks | Rate limits, request caps, PayPal signature check, event-id dedupe | `test_providers.py::test_a_forged_signature_stores_nothing`, rate-limit tests. Schemathesis run: 6,657 generated cases, 0 server errors (mostly unauthenticated) | Tested |
| T-11 | SSRF | No URL is fetched from content | Design; no fetch code on content paths. No dedicated test | Reviewed, not tested |
| T-12 | Operator access | Least-privilege roles, app role without owner rights, Django admin not installed | Forced RLS tests run as the app role | Reviewed. Break-glass process not built |
| T-13 | Audit tampering | Insert-only privileges, hash chain, verification job | `test_audit_core.py`, `test_audit_history.py`, `safety/test_audit_completeness.py`. Wording: append-only by database permissions, with a hash chain that detects casual edits; not tamper-resistant against a database superuser | Tested. Off-database anchor and nightly schedule not built |
| T-14 | Backups | Restore drill planned in Task 40 | See `docs/acceptance-report.md` | Open (OPEN-09) |
| T-15 | Dependencies | Lockfiles; `npm audit --omit=dev`: 0; `pip-audit`: none known; 10 moderate dev-tool findings (minimatch, lint tooling only) | Task 39 run output | Production dependencies clean on this date. No image scan yet |
| T-16 | Policy bypass | No AI write path, DB CHECKs on reminders, single-use authorization, fail-closed gates | `unit/test_policy_engine.py`, `test_policy.py`, `test_reminders.py`, `meta/test_boundaries.py` | Tested |
| T-17 | Forged customer reply | Claim never marks paid; unmatched sender goes to review | `test_interpretation.py`, `test_conversations.py`, critical negative 1 | Tested. Email authentication signals not built |
| T-18 | XSS, CSRF, fixation | No HTML rendering of messages (no `dangerouslySetInnerHTML` in `frontend/src`), CSRF middleware, HttpOnly cookies, API responses carry `Content-Security-Policy: default-src 'none'` | `test_tenancy.py::test_api_responses_carry_security_headers`, `test_import.py` CSRF test. Fixed in this task: CSP and `Cache-Control: no-store` were missing | Tested for the API. The static host serving the SPA must set its own CSP (see deployment notes) |
| T-19 | Wrong recipient | Recipient from approved contact only, shown at approval, gates re-checked at send | `test_reminders.py`, `safety/test_critical_negatives.py` | Tested |
| T-20 | Incident gaps | Runbooks in `docs/runbooks/` | Written; not rehearsed (tabletop not done) | Written, unrehearsed |

## Findings fixed in Task 39
- Audit History table overflowed the page at 320 and 360 px (found in Task 38, fixed there).
- API responses had no Content-Security-Policy, no Cache-Control and no Permissions-Policy; added by `SecurityHeadersMiddleware`.

## Tools run and what they cover
- axe-core (WCAG 2.0/2.1 A and AA tags) on three public screens and twelve workspace screens in their empty state, plus a first-Tab check. No violations. This is an automated check of empty states, not a WCAG conformance statement.
- Schemathesis 4.33 against the generated OpenAPI: 116 operations, 6,657 cases, no 5xx. 36 operations answered only 401/403 because the run was unauthenticated, so authenticated paths rely on the integration tests.
- `scripts/check_claims.py` (part of `make check`) rejects compliance, certification, accuracy and uptime claims in UI strings and docs.
- detect-secrets runs in `make check`.

## Not done
- k6 is not on this machine's PATH, so the 5,000-invoice load run was not repeated in Task 39. The Task 12 result stands (5 virtual users, Django development server, developer machine: list p95 931 ms, within NFR-01; see the decisions log). It was not re-measured after later tasks, and says nothing about production hardware.
- No independent penetration test, no screen-reader audit, no live AI provider evaluation, no container image scan.
