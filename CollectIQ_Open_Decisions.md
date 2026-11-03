# CollectIQ — Open Decisions, Assumptions, Conflicts and Required Approvals (TSD v1.0)

Companion to `CollectIQ_Technical_Specification_v1.0.md`. Status values: **OPEN**, **PROPOSED** (default stated, needs approval), **BLOCKS-BUILD**, **BLOCKS-PILOT**. Nothing here is decided by this document.

## A. Decisions requiring human approval

| ID | Decision / question | Default proposed in TSD | Owner (suggested) | Blocks | Source |
|---|---|---|---|---|---|
| OD-01 | SCR-16 and SCR-17 are named in the brief but not defined in UX v0.1 (SCR-01…15). Supply definitions or confirm 15 screens | Map SCR-01…15 only; invent nothing | Product/UX | M1 UI scope | TC-1 |
| OD-02 | "Product & Business Requirements" doc referenced by brief vs PRD v0.1 / PPD naming | Treat PRD v0.1 as the requirements source | Product | — | TC-2 |
| OD-03 | Approve provisional stack: Django/DRF, PostgreSQL, React+TS, DB-backed queue, S3-compatible storage | As SAD AC-11 | Eng lead | **M1** | AC-11 |
| OD-04 | Hosting vendor/region, backups, RPO/RTO, domain, TLS, environments | None invented; AWS ap-south-1 only a planning assumption | Eng/Ops | **Staging**, pilot | OPEN-20 |
| OD-05 | LLM provider, contract (retention, training, residency, subprocessors), model config | Unselected; gateway adapter | Product/Legal | **M5, pilot** | OPEN-09/20 |
| OD-06 | May Finance admin approve reminders for *sensitive* clients? | Owner only | Product | M4 | OPEN-13 |
| OD-07 | Per-invoice and per-client pause (UX DC-7) | Workspace pause only in MVP | Product | M4 | DC-7 |
| OD-08 | Retention periods, DPDP/GDPR obligations, deletion grace period, backup deletion | Values marked [PROP] in SAD §5.2; **no compliance claim** | Legal/Product | **Pilot** | OPEN-09 |
| OD-09 | Matcher weights/bands; AI ordinal thresholds; labelled evaluation set (≥150 replies) | SAD §6.4 provisional; auto-snooze unavailable until eval passes | Product/Data | M3 (weights), M5 (eval) | OPEN-16, AIR-12 |
| OD-10 | Real bank statement/PayPal export samples and formats | Generic CSV mapping | Product | M3 | — |
| OD-11 | Gmail restricted-scope security assessment path (monitoring); PayPal sandbox access and production visibility; Gmail OAuth verification timeline | P0 independent; P1 gated | Product/Security | M6 | OPEN-23, SAD sources |
| OD-12 | Approve the 10 **proposed-new endpoints**: E009 session/CSRF, E023 client profile, E032 coverage, E037 import batch read, E063 messages index, E108 review inbox, E109/E110 AI settings, E111/E112 health | Include in OpenAPI labelled proposed | Eng lead/Product | M1 | TSD §10 |
| OD-13 | Audit `derive()` precedence/corner cases against SAD §6.7 | SAD governs | Eng | M3 | TSD §11 |
| OD-14 | Malware scanning approach for uploads | Required before PDF/file upload goes live | Security | **Pilot** | OPEN-21 |
| OD-15 | Audit tamper resistance beyond append-only convention (WORM/anchoring) | Convention only; no immutability claim | Security | — | ADR-10 |
| OD-16 | Evidence freshness window and attestation policy | 7 days | Product | M3 | OPEN-25 |
| OD-17 | Contact limits, snooze horizon, draft expiry, cooling-off defaults | FR-084/079/094/126 [PROP] values | Product | M4 | OPEN-27 |
| OD-18 | Authentication method and MFA timing | Email/password P0; MFA P1 | Product/Security | M1 | OPEN-24 |
| OD-19 | PDF extraction in MVP | P0-conditional (needs OD-05, OD-14) | Product | M2/M5 | OPEN-06 |
| OD-20 | UX DC-6 bulk approve (per-item calls vs bulk endpoint) and DC-8 `allowed_actions` on DTOs | Per-item approve; `allowed_actions` recommended | UX/Eng | M4 | DC-6/8 |
| OD-21 | Alternative reply intake without restricted mailbox scope (forwarding address) | Not in MVP | Product | P1 | OPEN-26 |
| OD-22 | Per-requirement (not range-level) traceability refinement | Done in M0 | Eng/QA | M0 | TSD §21 |

## B. Assumptions

| ID | Assumption | Impact if wrong |
|---|---|---|
| AS-1 | No code exists; greenfield | Re-baseline TSD against repo audit (M0) |
| AS-2 | Single region, English-only, no FX | Schema impact for FX is large; defer |
| AS-3 | Pilot scale ≈ ≤5,000 invoices per tenant | Index/queue design may need revision |
| AS-4 | Gmail P1 uses send-only scope; monitoring only after separate consent and assessment | Reply automation delayed; paste/.eml remains |
| AS-5 | Provider facts in SAD (Gmail scopes, Graph, PayPal webhooks) were verified at SAD time | Re-verify at M6 |
| AS-6 | UX v0.1 tokens/components are the visual source (no DESIGN.md/Stitch) | Visual rework after export supplied |

## C. Conflicts between sources (with proposed resolution)

TC-1…TC-4 are in TSD §1. Carried forward: PRD C-1…C-12, SAD AC-1…AC-15 (awaiting approval), UX DC-1…DC-14. This TSD introduces no new silent contradiction; where a prior document is summarised, the earlier document governs.

## D. Required approvals before pilot with real customer data
OD-05, OD-08, OD-14, OD-11 (for any mailbox integration), OD-04 (production hosting).

## E. Not claimed anywhere in the product or docs
SOC 2/ISO/PCI/DPDP/GDPR compliance; immutable or tamper-proof audit; calibrated AI confidence; accuracy figures; provider uptime guarantees; completeness of Gmail/Outlook/PayPal feature availability beyond verified sources.
