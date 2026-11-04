# CollectIQ implementation audit

Baseline: commit `a1448f4` on branch `build/m0-m8`, audited 2026-11-04. Written for whoever builds or reviews
the milestones after M0. Authority order when documents disagree: PRD, then SAD, then TSD, then UX and Stitch.

Companion files:
- [Requirement traceability](../CollectIQ_Requirements_Traceability.csv), checked by `scripts/check_traceability.py`.
- [Stitch control dispositions](stitch-control-dispositions.md), one decision per control.
- [Implementation status](implementation-status.md), the running record of what is built.

## 1. Existing functionality

Scaffold only. Nothing a user can do exists yet.

- Backend: Django 5.2 and DRF project under `backend/collectiq`, with empty module packages and import boundaries enforced by import-linter.
- Frontend: Vite, React and TypeScript scaffold under `frontend/src`.
- Database: PostgreSQL 16 in Podman on `127.0.0.1:54329`, with a non-superuser application role (`collectiq_app`, verified `rolsuper=f`, `rolbypassrls=f`).
- Quality gate: `make check` runs ruff, mypy, import-linter, a no-DB-imports check, a float-money check, detect-secrets, an OpenAPI diff, the traceability check, eslint, tsc, pytest and vitest.
- API: `docs/api/endpoint-status.yaml` assigns all 112 catalogue endpoints to a plan task or to deferred. None is implemented.

## 2. Missing functionality

Everything in M1 to M8, which is 37 of the 40 plan tasks. The matrix records all 221 requirements as `Not implemented`. Each of the 187 P0 rows names its owning tasks, endpoints and tests; the 34 P1 and P2 rows stay range-level and are unassigned until plan A4 and T34 pick them up.

| Milestone | Delivers | Plan tasks |
| --- | --- | --- |
| M1 Foundation | Audit, tenant isolation, identity, jobs, frontend shell | T4 to T9 |
| M2 Invoices | Clients, CSV import, queue and dashboard | T10 to T14 |
| M3 Evidence | Accounts, coverage, statements, `derive()`, matcher, allocation | T15 to T20 |
| M4 Follow-ups | Policy engine, disputes, messages, reminders, inbox | T21 to T28 |
| M5 AI | Gateway, reply interpretation, summaries, flagged PDF | T29 to T32 |
| M6 Integrations | Registry, P1 Gmail send-only and PayPal on fake transports | T33, T34 |
| M7 Audit and settings | Audit History, Settings, Payload Inspector, completeness | T35 to T37 |
| M8 Release | End-to-end, accessibility, performance, security, recovery | T38 to T40 |

Deferred with a reason: E096 and TS-019 and TS-026 (Gmail mailbox monitoring, plan A4 and OD-11), and MFA endpoints E007 and E008 (OD-18, P1).

## 3. Discrepancies between sources

| Conflict | Resolution |
| --- | --- |
| UX and TSD call Integrations SCR-11; Stitch calls it SCR-16; UX does not define SCR-17 | One Integrations screen: UX SCR-11 spec with the Stitch SCR-16 design. SCR-17 is backed by TSD M17 (E106 to E108). No separate SCR-11. |
| `DESIGN.md` frontmatter tokens differ from its prose and from the directive | Directive values win. |
| Stitch shows "94% Confidence", "Immutable", "SOC-2", "RBI…", "24h" freshness, inconsistent gate numbers, nav variants | Not reproduced. PRD gate numbers and directive nav govern. See the disposition table. |
| PRD has numeric confidence (T_auto 0.90, TS-010 "0.85"); TSD, SAD and UX are ordinal | Ordinal only. Automated action needs HIGH plus every other condition. TS-010's 0.85 case becomes MEDIUM. |
| Coverage enum: `UNSUPPORTED` (TSD) against `MISSING` (PRD, SAD, TS-032) | `MISSING`. |
| Milestone placement differs across documents | Roadmap dependency order. Inbox and manual handoff in M4; M6 owns the integration lifecycle. |
| Directive lists "planned" integrations; UX UXR-12 forbids showing what does not exist | UI lists only what exists, with truthful status. Planned items appear in documents only, with no connect controls. |
| TSD AS-6 says `DESIGN.md` and Stitch are absent; both exist | Stitch adopted as the visual reference. |
| Routes differ between UX §13.1 and TSD | `/w/:ws/…` scheme, set in T8. |
| Revenue §16 classes Gmail monitoring and auto-snooze as Defer, PDF as "Defer unless demanded"; PRD has auto-snooze and PDF as P0 | PRD governs. Both stay gated or flagged, which leaves them off until their conditions hold. |
| PPD §20.2 C-5: reply-reading scope (labels against inbox) unresolved | No mailbox read in this build (E096 deferred). Stays open under OD-11. |

## 4. Configuration gaps

| Gap | Effect now | What closes it |
| --- | --- | --- |
| No AI provider configured (OD-05) | Features run against a fake provider. Real AI output is unverified, and T32 stays conditional. | Provider contract and key. `GEMINI_API_KEY` in the shell is deliberately not read. |
| No hosting target (OD-04) | T40 proves local deploy and recovery only. Production TLS, backups and RPO/RTO are unverified. | Hosting decision. |
| No real statement or PayPal samples (OD-10) | Generic CSV mapping on synthetic fixtures. | Real samples. |
| No Gmail OAuth client or PayPal sandbox (OD-11) | P1 adapters run on fake transports. | Credentials and verification path. |
| No malware scanner (OD-14) | Upload limits and type checks only. Blocks pilot, not M0 to M4. | Scanning choice. |
| Retention and deletion periods are proposed values (OD-08) | Configurable defaults. No compliance claim. | Legal review. |
| CI file written but never run (plan A10) | `make check` is the only verified gate. | A remote that runs it. |
| Billing: PRD and SAD mention it, TSD and UX do not; FR-143 has a permission only | No billing feature is built. Revenue §8 soft limits are not enforced. | Product decision if billing enters scope. |

## 5. Critical decisions

### OD-03 provisional stack

Accepted provisionally, as the plan's assumption A1: Django and DRF, PostgreSQL, React and TypeScript, a DB-backed queue, and S3-compatible storage (filesystem until OD-04 is settled). T1's spike ran the toolchain on this host and confirmed the application role cannot bypass RLS; T4 proves forced RLS itself. The eng lead can still overturn it.

### OD-12 proposed-new endpoints

All ten stay `proposed-new` and need approval. Each is needed by a screen or by operations:

| Endpoint | Purpose | Needed by | Verdict |
| --- | --- | --- | --- |
| E009 | Session and CSRF | Every authenticated screen on load | Build, T7 |
| E023 | Client detail | SCR-14 | Build, T10 |
| E032 | Coverage | SCR-15, FR-053 | Build, T15 |
| E037 | Import batch read | SCR-05 review | Build, T11 |
| E063 | Conversation index | SCR-07 | Build, T23 |
| E108 | Review inbox | SCR-17 | Build, T25 |
| E109 | AI settings read | SCR-13, AIR-13 | Build, T31 |
| E110 | AI settings write | SCR-13, FR-012 | Build, T31 |
| E111 | Liveness | Operations, NFR-12 | Build, T7 |
| E112 | Readiness | Operations, NFR-05, NFR-12 | Build, T7 |

### Endpoint gaps

Checked each P0 screen against the catalogue. These gaps will be added as `proposed-new` in the implementing task and listed in the final report for approval.

| Need | Evidence | Verdict | Task |
| --- | --- | --- | --- |
| Resend verification email | PRD 410; UX 216, 465, 963 | Add `POST /auth/verify-email/resend` | T7 |
| Accept invitation | FR-144; TSD 217 Membership INVITED to ACTIVE | Add `POST /invitations/accept` | T7 |
| Change member role | UX 1225; TSD 221 `member.role_changed` | Add `PATCH /workspaces/{ws}/members/{id}` | T7 |
| Sign out everywhere | PRD 888; UX 1225 | Check E004 first; extend it with a scope parameter rather than add an endpoint | T7 |
| Notification preferences | FR-146; PRD 887 to 888; UX 1224 | Add GET and PATCH preferences | T25 |
| Regenerate wording | UX 406; PRD 441, 946 | Add `POST` regenerate on a reminder; template wording when AI is unconfigured | T31 |
| List attestations | UX 360 reads coverage from E032 | No gap | - |
| List import batches, client notes | Stitch only; no PRD or UX requirement | No gap; controls not built | - |
| Global search | UX 151 uses E042 `q` | No gap | - |

### Accepted defaults

These are the plan's assumptions, and each can be overturned without rework beyond its config or the named task:

- [PROP] values as configurable defaults: 7-day freshness, 24h cooling-off, contact limits of 1 per invoice per 7 days and 1 per contact per 3 days with a maximum of 3, uploads up to 5 MB and 10,000 rows (OD-16, OD-17).
- Owner-only approval for sensitive clients (OD-06), workspace-level pause only (OD-07), per-item bulk approve plus `allowed_actions` (OD-20), email and password auth (OD-18).
- Local-only infrastructure adapters. Git is local-only, with no remote and no push.

### Needs the owner

OD-04 (hosting), OD-05 (AI provider), OD-08 (retention, legal), OD-10 (real statement samples), OD-11 (Gmail and PayPal access), OD-14 (malware scanning). None blocks M0 to M4. OD-22 (requirement-level traceability) is closed by this task.

### Claims the product will not make

No SOC 2, ISO, PCI, DPDP or GDPR compliance, no immutable or tamper-proof audit, no AI accuracy figure, no provider uptime. The audit log is described only as "append-only by database permissions, with a hash chain that detects casual edits; not tamper-resistant against a database superuser".

## 6. Sponsor tool assessment

None is adopted in the product (plan A6). Vendor pages were checked on 2026-11-04. Where a vendor's own page could not be reached, the row says so, and that claim is less certain.

| Tool | What it is | Assessment | Sources |
| --- | --- | --- | --- |
| AG Grid | Data grid. Community is MIT (sort, filter, paging, editing); Enterprise is commercial (grouping, server-side row model, export). | The queue's order comes from the server, so a plain table is enough. Community is a possible later swap. | [licensing](https://www.ag-grid.com/react-grid/licensing/), [comparison](https://www.ag-grid.com/javascript-data-grid/community-vs-enterprise.md) |
| APIMatic | SDK and developer-portal generator. | openapi-typescript already covers the one client we need. Third-party pricing conflicts and the official page was not reached, so no price is stated. | [Toolradar](https://toolradar.com/tools/apimatic/pricing), [Geekflare](https://geekflare.com/guides/api-sdk-generators/) |
| Astropods | Platform to build, deploy and run AI agents. | Our AI is a constrained gateway, not agents, and this would add a second place for payloads. Based on marketing and blog sources; its docs were not read. | [Postman blog](https://blog.postman.com/build-ai-agents-with-astropods/) |
| Bryntum | Commercial grid, scheduler and Gantt components. | No scheduling UI in scope. Licence sources conflict and the official page was not found. | [FitGap](https://us.fitgap.com/products/bryntum), [AlternativeTo](https://alternativeto.net/software/bryntum/about) |
| Channel3 | Product-catalogue search API for commerce. | No fit. | [FAQ](https://docs.trychannel3.com/faq), [catalog](https://docs.trychannel3.com/ucp/about-catalog) |
| Elastic | Search and observability. The self-managed Basic licence does not expire. | PostgreSQL search and structured logs are enough at this scale. | [licences](https://www.elastic.co/docs/deploy-manage/license) |
| KERNEL | Browser infrastructure for agents, with stealth, CAPTCHA handling and credential vaults. | No fit. Automating bank portals is out of scope. | [features](https://kernel.sh/docs/overview/features), [why](https://kernel.sh/docs/overview/why-kernel) |
| Postman | API collections, monitors and mocks. | schemathesis and pytest cover contract checks. A collection could be an optional developer aid, never a product dependency. | [elements](https://learning.postman.com/docs/getting-started/basics/postman-elements) |
| Render | Web services, workers, cron, and managed Postgres with point-in-time recovery on paid instances. | A candidate deploy target under OD-04. Needs the owner's decision, and a check that its Postgres roles allow forced RLS. T40 stays local. | [service types](https://render.com/docs/service-types), [pricing](https://render.com/pricing) |
| Zapier | Automation across thousands of apps. | Conflicts with the no-auto-send and no-auto-allocate rules. | [AI actions](https://docs.zapier.com/platform/reference/ai-actions) |

## 7. Stitch dispositions

[The table](stitch-control-dispositions.md) covers all 254 distinct controls from the 17 exports: 193 KEEP, 28 CHANGE and 33 OMIT. `backend/tests/meta/test_stitch_dispositions.py` fails if a control has no row. The main patterns:

- **OMIT:** connect controls for integrations that do not exist; anything implying a certification or a security control; batch lists with no requirement behind them; send actions in P0.
- **CHANGE:** "signed" exports lose the word; 24h attestation becomes the 7-day default; "Reject & Delete" keeps the draft for audit; pause is workspace-level; icon-only buttons get accessible names.

## 8. Sequence

Follow the plan's M0 to M8 order. The dependencies that cannot move:

1. Tenant isolation (T4) comes before any tenant table, and the audit write path (T5) before any audited action.
2. Idempotency and jobs (T6) come before imports and reminders.
3. `derive()` (T17) comes before the matcher, allocation and every screen that shows a payment state.
4. The policy engine (T21) comes before reminders, so that no draft can bypass a gate.
5. The AI gateway (T29) comes before any AI feature, so that no payload can bypass it.

Fresh reviews run at the M3 and M4 gates and on the whole branch at the end.

## 9. Tests

| Layer | Tooling | Status |
| --- | --- | --- |
| Static and boundary | ruff, mypy, import-linter, custom checks | Running in `make check` |
| Traceability and Stitch coverage | `check_traceability.py`, `test_stitch_dispositions.py` | Running in `make check` |
| Unit and property | pytest, hypothesis, Vitest | Scaffold tests only |
| Tenant and authorization | pytest against PostgreSQL with RLS | From T4 |
| Contract | schemathesis | With the first endpoints; the plan names no start task |
| Mutation | mutmut on `policy/domain` | At T21 |
| End-to-end, accessibility | Playwright, axe | From T9; complete at T38 and T39 |

The 35 PRD scenarios are all accounted for: 33 have an owning task and 2 are deferred with a reason (TS-019, TS-026). The owners live in `scripts/check_traceability.py`.

## 10. Limits of this audit

- PPD, Market Research, Revenue and the Foundation PDF were read by targeted search, not end to end. They produced the two PPD items, the Revenue conflicts and the billing gap above, and no new requirement. Something elsewhere in those documents could have been missed.
- Stitch dispositions were assigned from control labels by rule, with sources checked for the conflicting ones. They were not reviewed screen by screen, so a label used differently on two screens gets one decision. Implementers should recheck when building each screen.
- `CollectIQ_Post_Implementation_Audit.md` at the repo root predates commit `a1448f4`. It is stale and is not part of this audit.
