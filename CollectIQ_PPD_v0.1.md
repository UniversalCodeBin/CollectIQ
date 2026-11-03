# CollectIQ — Product Proposal & Planning Document (PPD)

**Document ID:** COLLECTIQ-PPD-001 | **Version:** 0.1 (Draft for review) | **Date:** 03 November 2026
**Status:** Pre-validation concept. Customer demand, pricing, technical feasibility and provider approvals are untested.
**Foundational source:** *CollectIQ Overall Product Concept and Solution Plan*, v1.0, 03 Nov 2026 (referred to as **"the Foundation"**; section numbers cite it as F§n).

---

## 0. Document Control

### 0.1 Purpose
This PPD turns the Foundation into a single planning-and-design baseline: product vision, users, personas, journeys, features, functional requirements, workflows, screen-level requirements, edge cases, error states, MVP boundary and future enhancements. It is the input for the PRD, System Architecture Document, Technical Specification and UI/UX Design Document.

### 0.2 Naming note and scope conflict (needs approval)
| Item | Foundation (F§13) | This request | Resolution proposed |
|---|---|---|---|
| Meaning of "PPD" | **Product Proposal Document**: purpose, vision, thesis, problem, segment, value proposition, boundaries, differentiators, assumptions, risks (F§1-5, 8, 12) | **Product Planning and Design Document**, adding user stories, screens, interactions, error states | Keep Foundation name and ID. Treat the additional material (§7-§12) as a **baseline appendix-level detail** that the PRD (requirements) and UI/UX document (screens) will refine and supersede. Where this PPD and a later PRD/UX document disagree, the later document wins after a logged decision. |

### 0.3 Dependencies
Foundation v1.0 only. No prior approved downstream documents exist (project doc list is empty). Provider facts (Gmail, Microsoft Graph, PayPal, DPDP) are taken only from Foundation §14 and must be re-verified before implementation.

### 0.4 Labelling convention (per project rules)
| Tag | Meaning |
|---|---|
| **[FND]** | Decision or statement stated in the Foundation. Not to be changed silently. |
| **[DES]** | Design proposal in this PPD that elaborates the Foundation. Needs review. |
| **[ASM]** | Assumption or hypothesis. Not a validated fact. |
| **[OPEN]** | Unresolved decision or dependency (collected in §19). |
| **[MVP]** | In MVP scope. |
| **[FUT]** | Future enhancement; not committed. |
| **[VER]** | External provider fact that must be verified against current official documentation before build. |

No market statistics, competitor feature claims, compliance certifications or provider guarantees are asserted in this document.

---

## 1. Executive Summary

**Product.** CollectIQ is an AI-assisted **receivables operations overlay** for small B2B service businesses [FND F§1]. It is not an invoice editor, accounting ledger, payment processor, credit bureau or collection agency.

**Core promise [FND].** Understand every outstanding invoice, reconcile payments wherever they arrive, and respond to customers intelligently, without sacrificing the relationship or surrendering control.

**Three pillars [FND F§1].**
1. **Payment truth:** reconcile supported PayPal events, bank-statement imports and manual confirmations; distinguish verified paid, partially paid, open, disputed and uncertain.
2. **Conversation understanding:** interpret customer replies (timing, payment sent, dispute, missing documents, clarification, partial-payment proposal, opt-out).
3. **Safe orchestration:** a deterministic policy engine schedules, snoozes, suppresses or escalates; only narrow, reversible, explicitly authorized actions are automated.

**Moat hypothesis [FND F§5, ASM].** Trusted cross-system exception resolution, not LLM-written reminders. Credible only after pilots show measured improvement.

**MVP in one line [FND F§10].** One trustworthy end-to-end loop: CSV invoice import → payment evidence (PayPal sandbox, bank CSV, manual entry) → one connected mailbox → reply interpretation → policy-validated action (snooze / pause / review) → visible audit trail.

---

## 2. Product Vision, Mission and Principles

### 2.1 Vision
Small businesses get paid fairly and on time because an assistant keeps invoice, payment and conversation truth in one place, while the owner stays in control and customer relationships stay intact. [DES, restating F§1]

### 2.2 Mission [DES]
Reduce the manual effort of resolving receivables exceptions while keeping payment-status accuracy high and unnecessary customer contact low (F§11 north-star).

### 2.3 Non-negotiable principles [FND]
| # | Principle | Source |
|---|---|---|
| P1 | **Payment-method-agnostic reconciliation.** PayPal is one source, never the definition of payment truth. | F§3, Q7, Q10 |
| P2 | **"No event received" ≠ "not paid."** Insufficient evidence → *uncertain* → automated contact suppressed. | F§4 critical invariant |
| P3 | **Privacy-first AI processing.** Minimized, purpose-specific, redacted payloads; no secrets to the model; no "strictly private / zero retention" claims without evidence. | F§8, Q13 |
| P4 | **Connected-mailbox sending.** Mail is sent from the user's own Gmail/Outlook via OAuth; send and read are separate permissions. | F§3, Q9, Q14 |
| P5 | **Conversational reply interpretation.** Customer replies are state-changing inputs that the LLM turns into *proposals*. | F§6, Q11, Q16 |
| P6 | **Deterministic policy enforcement.** The LLM never updates the ledger or sends mail; code validates and decides. | F§3, F§6 |
| P7 | **Bounded autonomy.** Automation is narrow, reversible, permissioned, explainable and instantly pausable. | F§8, Q5 |
| P8 | **Overlay, not replacement.** Import and coordinate; never force invoice re-entry or invoice creation. | F§3, Q6 |
| P9 | **Relationship-safe.** No threats, shaming, fake urgency, invented penalties or legal language. Not debt collection. | F§8, Q12 |
| P10 | **Honest claims.** Promise risk reduction and control, not 100% accuracy or safety. | F§3, Q5 |

### 2.4 Explicit non-goals [FND F§3]
Not an invoice creator or system of record; no forced PayPal; no claiming unpaid solely from a missing PayPal event; no legal threats, penalties, contract changes or binding settlements; no 100% accuracy promise; no certification/zero-retention/compliance claims without evidence; no predictive default or "cash-flow risk score" on day one (F§6, Q3).

---

## 3. Problem and Context

### 3.1 Problem statement [FND F§2]
Small B2B service businesses manage receivables across disconnected systems: invoices in accounting tools/spreadsheets/documents, communication in email, and payments via PayPal, bank transfer, NEFT, UPI, cash or others. Scheduled reminders cannot see the latest payment evidence, replies, disputes, partial payments or agreed dates. Owners search threads, reconcile manually and decide by hand whether to follow up, which costs time and risks unnecessary or badly timed messages.

### 3.2 Operational gap [FND F§2]
| Source | Knows | Misses |
|---|---|---|
| Invoice system | Number, due date, balance, customer | Latest conversation; payments elsewhere |
| Email inbox | Commitments, disputes, questions | Does not update invoice status |
| Payment channels | Transaction evidence | May not link to invoice number or payer |
| Owner/bookkeeper | Everything, manually | Acts as the human integration layer |

### 3.3 Why a reminder checkbox is not the product [FND F§5, Q1]
A scheduled reminder is a calendar rule. CollectIQ must demonstrably reduce manual exception handling beyond what a customer's existing tools do. Competitor coverage (QuickBooks, Zoho Books, FreshBooks, regional tools) **must be benchmarked before any comparison claim** [OPEN-12].

---

## 4. Target Users and Personas

### 4.1 Initial segment hypothesis [FND/ASM]
Small B2B agencies, consultancies, studios and service businesses with recurring invoices and mixed payment methods. About 20-200 invoices/month is a **hypothesis**, not research. Qualify by invoice volume, number of payment methods, exception frequency and reconciliation time, not by the label "freelancer". Very low-volume freelancers may be better served by Gmail plus a spreadsheet; large enterprises needing ERP/vendor onboarding/tax capabilities are out of early scope (F§2, Q4, Q8).

### 4.2 Roles [FND F§2, F§7]
Owner/founder; finance admin/bookkeeper; account/project lead; reviewer (permissions entity); customer/AP contact (external, never a CollectIQ user).

### 4.3 Personas
> Personas are **illustrative composites** derived from Foundation role descriptions, not interview findings. Replace with evidence from Phase 0 discovery (15-20 interviews) [ASM].

| | **P-1 Owner "Aarav"** (primary buyer/user) | **P-2 Bookkeeper "Priya"** (daily operator) | **P-3 Project lead "Rohan"** (exception resolver) | **P-4 Customer AP contact "Neha"** (external) |
|---|---|---|---|---|
| Context | Founder of a 12-person design/dev agency; sends own invoices; mixed payment rails | Part-time/outsourced bookkeeper for several small firms | Delivers the work that invoices bill for | Accounts-payable contact at a client company |
| Goals | See what truly needs attention; avoid chasing clients who already paid; protect key relationships | Accurate queue, defensible reconciliation, audit history | Pause chasing when delivery is disputed; respond with project context | Accurate, respectful messages; a clear way to correct or explain an issue |
| Pains | Searching threads; uncertain whether money arrived; fear of looking desperate | Matching unreferenced bank rows to invoices; duplicate amounts | Learning of disputes late via finance | Reminders for paid invoices; wrong PO/invoice references |
| Needs from CollectIQ | Exception-first queue, approval control, one-click pause | Evidence-backed matching, override with attribution, exports | Routed dispute items with summary and original message link | (Indirect) no duplicate/aggressive/incorrect messages; opt-out honored |
| Trust requirement | Must be able to stop automation immediately | Must see evidence & confidence for every match | Sees only items assigned to them | Sender is the real business mailbox |
| Typical permission | Owner (all) | Finance admin | Assigned-exceptions only [DES] | None |

### 4.4 Jobs to be done [FND F§2]
Show which invoices genuinely need attention; tell me whether payment may already have arrived elsewhere; understand replies without rereading threads; resolve missing info/disputes before another reminder from my own mailbox; automate narrow reversible actions while keeping sensitive decisions human.

---

## 5. User Journeys

Each journey lists trigger, steps, system behavior, outcome and the Foundation anchor. All outcomes are logged to the audit trail.

### J-1 First-time setup and activation [DES]
1. Owner signs up, creates tenant (business name, region, timezone, default currency) [OPEN-1 market].
2. Chooses/accepts default automation mode = **manual review** [FND Decision 8 recommendation].
3. Imports invoices via CSV (field mapping, validation, preview) → invoices land in ledger with source IDs preserved.
4. Records or imports payment evidence (bank CSV, manual entries); optionally connects PayPal (sandbox in MVP).
5. Connects mailbox (send first; optional read for reply monitoring with explicit consent and plain-language scope explanation).
6. Reviews policy settings; sees first exception queue.
**Outcome:** user reaches a populated exception-first queue without re-entering invoice data.

### J-2 Routine reminder with approval (happy path) [FND F§4]
Eligible overdue invoice → system refreshes payment/mailbox evidence → pre-send safety gate passes → draft created from facts (amount, currency, reference, recipient) → owner approves (single or batch) → revalidation immediately before send → sent from connected mailbox → message/thread IDs stored → follow-up state *Waiting for customer*.

### J-3 Payroll-timing reply (Foundation Journey A / Q16) [FND]
Reply "We run payroll on the 15th." → linked to thread/invoice → classified *payment timing* (indicative, **not** payment) → date candidate "15th" → deterministic resolver determines month/timezone → if unambiguous **and** user opted into auto-snooze **and** no dispute/uncertainty/limit violation → next routine reminder moved to the 16th; audit entry written. Otherwise → *Needs owner review*, no guess.

### J-4 "I transferred this morning" (Journey B) [FND]
Reply claims payment → intent *payment sent* → **no snooze, no paid mark** → reconciliation searches imported transactions → unique high-confidence match = **proposed** to owner (see §0/§10.3 conflict note on auto-apply) → ambiguous/partial/duplicate/incomplete statement coverage = **Payment uncertain**, routine reminders suppressed until checked.

### J-5 Deliverable dispute (Journey C) [FND]
Reply "Section 3 was not completed. Please revise it before payment." → intent *dispute* → routine reminders paused → exception created and routed to owner/project lead with summary and link to the original message → no further reminders until owner resolves → resolution recorded.

### J-6 Bank statement import and reconciliation [FND Q7, Q15]
Upload bank CSV → map columns → duplicate-row detection → candidate matches scored by reference, amount, currency, date range, payer descriptor → single high-confidence candidate proposed; multiple/low-confidence → *needs review* → user confirms/rejects → balance recomputed deterministically → open reminder jobs re-evaluated.

### J-7 PayPal event arrives [FND F§7]
Webhook received → signature verified (reject if invalid) → idempotency check → stored as payment transaction (evidence: *verified provider event*) → matched/proposed against invoices → outstanding reminders re-evaluated. A missing webhook never implies non-payment.

### J-8 Mailbox degradation [FND F§7]
Token expires/revoked or subscription lapses → status shifts to *Needs reauthorization* / *Degraded monitoring* → banner shown; sending stops if it cannot be authorized; reply-dependent automation (auto-snooze) is disabled because reply monitoring cannot be assumed → owner reauthorizes or disconnects.

### J-9 Owner pauses everything [FND P7]
One control pauses all automation; scheduled jobs are held (not deleted); resume requires explicit action.

### J-10 Disconnect / export / delete [FND F§7, F§11 tests]
User disconnects integration → future sends and monitoring stop → tokens revoked where supported → records remain exportable → deletion workflow runs with completion status recorded.

### J-11 Customer opt-out / wrong recipient [FND F§8]
Reply indicates wrong recipient or stop contact → address suppressed → owner review → no further automated contact to that address.

---

## 6. Domain Model and State Design

### 6.1 Glossary [DES, initial; the shared glossary is a governance item F§13]
| Term | Definition |
|---|---|
| Tenant/Business | Organization boundary for all data and settings |
| Invoice | Imported record of an amount owed (external ID, source system, customer, dates, currency, amounts) |
| Payment transaction | Evidence record from a provider/import/manual entry |
| Reconciliation match | Candidate or confirmed link between a transaction and invoice with factors and confidence |
| Commitment | Customer-stated payment timing/date (candidate or confirmed); a *payment window* is not a firm commitment |
| Exception | Item requiring human judgment (dispute, ambiguity, missing info, etc.) |
| Snooze | Reversible deferral of the next routine reminder |
| Suppression | Prevention of automated contact (uncertainty, opt-out, verified paid, etc.) |
| Approval | Human authorization of a drafted/proposed action |
| Automated action | Action performed without per-item approval under explicit user policy |
| Interpretation | Structured, validated candidate event derived from a message by the LLM |

### 6.2 Three independent state dimensions [FND F§4]
Financial and workflow states are **separate**; email events must never directly mark an invoice paid.

| Dimension | Values [FND] |
|---|---|
| **Financial state** | Open/outstanding; Partially paid; Paid – verified; Payment uncertain; Disputed/under review; Cancelled or written off *(only if supported by source system)* |
| **Workflow (follow-up) state** | Not contacted; Draft ready; Scheduled; Snoozed until date; Waiting for customer; Needs owner review; Suppressed; Resolved |
| **Evidence state** | Verified provider event; Imported transaction; User confirmation; Inferred/candidate match; Missing or stale evidence; Conflicting evidence |

### 6.3 Allowed transition rules [DES, to be formalized in the Tech Spec]
| Event | Financial effect | Workflow effect |
|---|---|---|
| Verified full payment (confirmed match or verified source per OPEN-4) | → Paid – verified | Cancel/re-evaluate all reminder jobs → Resolved |
| Partial payment confirmed | → Partially paid; balance recomputed | Reminder content must reflect remaining balance only |
| Customer says "I paid" (no evidence) | → Payment uncertain (when claim unmatched) | → Suppressed / Needs owner review |
| Dispute detected | → Disputed/under review | → Needs owner review; routine reminders paused |
| Payment timing reply (policy OK) | none | → Snoozed until date |
| Ambiguous match | → Payment uncertain | Suppressed |
| Email message of any kind | **never changes balance directly** | May change workflow only |

### 6.4 Core entities [FND F§7]
Business/Tenant; User/Role; Client/Contact; Invoice; Payment Transaction; Reconciliation Match; Mailbox Connection; Email Thread/Message; Customer Commitment; Dispute/Exception; Follow-up Policy/Scheduled Action; AI Interpretation/Audit Event. Field-level definitions are deferred to the Technical Specification; the list in F§7 is authoritative here.

---

## 7. Feature Catalog

Legend: **MVP** = in scope [FND F§10]; **FUT** = not committed.

| ID | Feature | Module | Status | Notes / Foundation anchor |
|---|---|---|---|---|
| F-01 | Tenant, users, roles, tenant isolation | Platform | MVP | F§8 controls; exact MVP role set [OPEN-9] |
| F-02 | CSV invoice import with mapping, validation, preview | Invoice intake | MVP | Guaranteed path |
| F-03 | PDF/document upload with extraction + user field confirmation | Invoice intake | MVP-secondary [OPEN-6] | Foundation lists as secondary path; Decision 6 unresolved |
| F-04 | Unified receivables ledger (normalized invoice, source, freshness) | Ledger | MVP | |
| F-05 | Manual payment entry (cash/UPI/bank/other) incl. partial | Reconciliation | MVP | |
| F-06 | Bank-statement CSV import, mapping, duplicate-row detection | Reconciliation | MVP | |
| F-07 | Conservative match engine, confidence bands, uncertain-state | Reconciliation | MVP | |
| F-08 | PayPal sandbox webhook path with signature verification | Reconciliation | MVP (sandbox only) | Production visibility unproven [VER] |
| F-09 | Mailbox OAuth (one provider) – send | Mailbox | MVP | Provider choice [OPEN-2] |
| F-10 | Reply ingestion (read permission, separate consent) + sync fallback | Mailbox | MVP | Scope/label decision [OPEN-3] |
| F-11 | Mailbox health & token lifecycle, disconnect/revoke | Mailbox | MVP | |
| F-12 | Reply intent classification & date/reference extraction | Conversational AI | MVP | 9-category taxonomy |
| F-13 | Thread summary & suggested reply draft | Conversational AI | MVP | LLM drafts are proposals only |
| F-14 | Policy engine (snooze, dispute pause, uncertainty pause, limits, opt-in auto-snooze, idempotency) | Policy | MVP | |
| F-15 | Pre-send safety gate & pre-execution revalidation | Policy | MVP | |
| F-16 | Reminder draft generation, single/batch approval | Orchestration | MVP | |
| F-17 | Exception-first dashboard with explainable priority indicators | UI | MVP | No risk score |
| F-18 | Invoice detail with evidence, conversation, audit timeline | UI | MVP | |
| F-19 | Client profile: sensitivity category, contact rules, tone | Client | MVP | User-entered, not AI-inferred |
| F-20 | AI payload minimization/redaction gateway + payload inspector | Privacy | MVP | Demo step 7 |
| F-21 | Audit trail (who/what/policy/approval) | Audit | MVP | |
| F-22 | Export, disconnect, deletion workflows | Privacy | MVP | |
| F-23 | Global automation pause | Policy | MVP | P7 |
| F-24 | Second mailbox provider | Mailbox | FUT (Phase 6) | |
| F-25 | One accounting integration chosen by pilot demand | Integrations | FUT (Phase 6) | |
| F-26 | Additional bank feeds / live bank aggregation | Reconciliation | FUT | Not MVP; feasibility unvalidated |
| F-27 | Predictive timing/response models | AI/ML | FUT | Only with permissioned data & validation |
| F-28 | Bounded auto-send of routine reminders | Orchestration | FUT [DES] | See §10.6 |
| F-29 | Email forwarding intake for invoices | Invoice intake | FUT [OPEN] | Foundation mentions as MVP-priority option in Q6; not in MVP feature table, resolve in OPEN-6 |

---

## 8. Functional Requirements

Priority: **M** = MVP must; **S** = MVP should; **F** = future. Each requirement has acceptance criteria (AC) in Given/When/Then form where behavior is testable. Requirement IDs are provisional for the PRD.

### 8.1 Platform, identity and tenancy
| ID | Requirement | Pri | AC |
|---|---|---|---|
| FR-PLT-001 | Users authenticate; every user belongs to a tenant with a role. | M | Given an unauthenticated request, when any app API is called, then access is denied. |
| FR-PLT-002 | All data access is tenant-scoped, incl. object storage. | M | Given Tenant A credentials, when requesting a Tenant B invoice/file by ID, then access is denied and logged; verified by explicit cross-tenant tests. |
| FR-PLT-003 | Role-based permissions: Owner, Finance admin/bookkeeper, Project lead (assigned items only) [DES]; reviewer deferred. | M | Given a project lead, when opening an unassigned invoice, then it is not visible. |
| FR-PLT-004 | MFA support and secure sessions [FND F§8]. | S | MFA can be enabled for Owner; sessions expire per policy [OPEN]. |
| FR-PLT-005 | Tenant settings: region, timezone, default currency, business hours, retention policy. | M | Timezone/business hours are used by scheduler and date resolver. |

### 8.2 Invoice intake and ledger
| ID | Requirement | Pri | AC |
|---|---|---|---|
| FR-INV-001 | Import invoices from CSV with column mapping, per-row validation and preview before commit. | M | Given a CSV with invalid rows, when previewing, then invalid rows are listed with reasons and the user can fix/skip; nothing is committed until confirmed. |
| FR-INV-002 | Preserve external ID, source system and original invoice reference for traceability. | M | Each ledger invoice displays its source ID and import batch. |
| FR-INV-003 | Re-importing the same file or overlapping rows must not duplicate invoices (idempotent by source+external ID). | M | Given a repeated import, then zero duplicates created; updates shown as a diff for confirmation. |
| FR-INV-004 | Normalize currency, amounts, dates; compute outstanding balance deterministically. | M | Balance = gross − confirmed payments, calculated in code, never by the LLM. |
| FR-INV-005 | Record evidence freshness per invoice (last payment-evidence refresh; statement coverage period). | M | Stale/missing evidence is visible and feeds the pre-send gate. |
| FR-INV-006 | PDF/document upload → extracted fields shown with confidence; low-confidence fields require confirmation before save. | S [OPEN-6] | No extracted field enters the ledger unconfirmed. |
| FR-INV-007 | Never require invoice creation or re-entry within CollectIQ. | M | No "create invoice" function exists in MVP. |
| FR-INV-008 | Payment-method field per invoice (bank transfer, UPI, cash, PayPal, other) and preserved payment instructions; CollectIQ never rewrites bank details/terms without explicit user action. | M | Reminder drafts only include payment instructions that the user supplied/approved. |

### 8.3 Payment reconciliation
| ID | Requirement | Pri | AC |
|---|---|---|---|
| FR-REC-001 | Manual payment entry (method, amount, currency, date, reference, notes), including partial payments; entered by attributable user. | M | Entry updates balance; audit event lists the user. |
| FR-REC-002 | Bank-statement CSV import with mapping, import-period capture and duplicate-row detection. | M | Re-uploading an overlapping statement does not create duplicate transactions. |
| FR-REC-003 | Candidate matching using invoice reference, exact/near amount, currency, date range, payer descriptor, known identifiers. | M | Each candidate shows factors and confidence band. |
| FR-REC-004 | Multiple candidates or low confidence → *needs review*; invoice marked Payment uncertain; routine reminders suppressed. | M | Two same-amount candidates ⇒ no auto-apply, reminder suppressed. |
| FR-REC-005 | Match evidence and confidence retained; overrides audit-logged and attributable. | M | Audit shows who confirmed/rejected and why. |
| FR-REC-006 | Partial payments: balance accurate; reminder content must not imply the original full amount remains due. | M | Draft after a partial payment states remaining balance. |
| FR-REC-007 | Duplicate transaction detection across sources (e.g., PayPal event + bank row for the same payment). | M | Potential duplicate flagged for review, not double-counted. |
| FR-REC-008 | Overpayment and currency-mismatch cases routed to review. | S [DES] | No automatic balance goes negative. |
| FR-REC-009 | PayPal webhook receiver with signature verification; invalid signature ⇒ rejected, logged, no state change. | M (sandbox) | Replayed/duplicate webhook creates no duplicate payment [FND test]. |
| FR-REC-010 | Evidence-state labels shown on every payment-related claim. | M | UI shows evidence state next to financial state. |
| FR-REC-011 | Whether a bank match may be auto-applied is governed by policy; **MVP default: matches are proposed, never auto-applied** [DES, see §0 conflict C-2]. | M | With default policy, a unique high-confidence match still awaits user confirmation. |
| FR-REC-012 | Absence of a PayPal event never causes "unpaid" conclusion; invoice with insufficient evidence coverage is labeled uncertain where applicable. | M | Test: no webhook + no statement coverage ⇒ evidence state "missing/stale", reminders gated per policy. |

> **UPI/cash note [FND]:** CollectIQ does not integrate with UPI or cash directly. UPI/NEFT/bank payments are evidenced through bank-statement CSV or manual entry; cash through manual entry. Live bank feeds are not MVP.

### 8.4 Mailbox integration
| ID | Requirement | Pri | AC |
|---|---|---|---|
| FR-MBX-001 | Connect one provider (Gmail or Outlook) via OAuth, **send permission first**; do not request inbox read to merely send. | M | Connecting for send-only never requests read scopes. |
| FR-MBX-002 | Reminders are sent from the user's connected mailbox (appearing in Sent Items); no generic CollectIQ sender for the primary workflow. | M | Sender identity = connected mailbox. |
| FR-MBX-003 | Reply monitoring requires a separate, explicit consent step stating exactly what is read. | M | Without read consent, reply-dependent features show "not monitored". |
| FR-MBX-004 | Reply association uses provider message/thread IDs, never subject alone. | M | Reply with altered subject still links via thread ID. |
| FR-MBX-005 | Notification lifecycle: handle watch/subscription renewal, delay, loss; periodic sync fallback. | M | Missed push is recovered by sync. |
| FR-MBX-006 | Connection statuses visible: Connected; Needs reauthorization; Degraded monitoring; Disconnected. | M | Product never implies monitoring is active when it is not. |
| FR-MBX-007 | Token revoked/expired ⇒ sends and auto-snooze halt and status updates. | M | [FND test] |
| FR-MBX-008 | Disconnect: stop sending/monitoring, revoke tokens where supported, keep export available. | M | Completion recorded in audit. |
| FR-MBX-009 | Documented scopes and provider verification/review path; no assumption that approvals are automatic. | M | OAuth scope register exists [VER]. |
| FR-MBX-010 | Handle send failures, throttling, bounces/non-delivery with retries (idempotent) and visible status. | M | Duplicate send prevented by idempotency key. |
| FR-MBX-011 | Reply-reading scope: only designated label/folder vs. entire inbox. | M | Behavior per decision [OPEN-3]. Proposal in §19. |

### 8.5 Conversational intelligence
| ID | Requirement | Pri | AC |
|---|---|---|---|
| FR-AI-001 | Classify into: payment timing, payment sent, dispute, question, missing documentation, partial payment, wrong recipient, opt-out, other/uncertain [FND Q11]. | M | Evaluation set reports per-class accuracy. |
| FR-AI-002 | Output contract fields: intent category; invoice/thread candidate; extracted date or payment reference; confirmed-fact / proposal / vague indication; confidence; evidence excerpt; recommended action; escalation reasons [FND F§6]. | M | Output must pass schema validation; invalid output ⇒ treated as uncertain → review. |
| FR-AI-003 | Unknown/ambiguous values stay **unknown**; never silently guessed. | M | "15th" with no resolvable month ⇒ owner review. |
| FR-AI-004 | LLM output is a proposal; deterministic validators check invoice association, date interpretation, allowed action, evidence, policy and approval. | M | No code path lets LLM output write balances or send mail. |
| FR-AI-005 | Distinguish payment window/indication from firm commitment; never describe timing as guaranteed payment. | M | UI wording differentiates "indicated" vs "committed". |
| FR-AI-006 | Treat customer email and invoice text as untrusted; resist prompt injection; embedded instructions cannot grant tool access or change policy. | M | Injection test set: no policy/permission change. |
| FR-AI-007 | Thread summary and suggested reply draft; drafts forbidden from threats, fake urgency, invented fees, legal conclusions. | M | Draft checker blocks prohibited content. |
| FR-AI-008 | Contradictory replies (e.g., “paid” and “dispute”) ⇒ pause + review. | M | |
| FR-AI-009 | Record model/provider version, fields processed, structured result, validation outcome, policy decision, user override. | M | Audit event per interpretation. |
| FR-AI-010 | Payload minimization gateway: purpose-specific payloads, identifier/price/project-detail redaction where possible, smallest relevant text span, no secrets ever. | M | Payload inspector shows exactly what was sent. |
| FR-AI-011 | Provider timeout/retry policy; on AI failure the system fails safe (no action, route to review). | M | Outage ⇒ no auto-snooze, replies queued for review. |
| FR-AI-012 | No training on client data without lawful basis and controls [FND F§4 "Learn"]. | M | MVP records outcomes only. |

### 8.6 Policy and workflow engine
| ID | Requirement | Pri | AC |
|---|---|---|---|
| FR-POL-001 | Automation modes: manual review (default), batch review of low-risk drafts, bounded automation for explicitly authorized low-risk actions [FND Q8, Decision 8]. | M | New tenants default to manual review. |
| FR-POL-002 | **Pre-send safety gate** (see §9.2) must pass before any send is queued. | M | |
| FR-POL-003 | Every scheduled action is revalidated immediately before execution against latest payment, dispute, consent and policy state. | M | Payment arrives after scheduling ⇒ job cancelled. |
| FR-POL-004 | Idempotency key enforced for jobs and sends. | M | Retries never duplicate reminders. |
| FR-POL-005 | Contact-frequency limits, business hours, customer preferences, snooze dates, opt-outs. | M | |
| FR-POL-006 | Auto-snooze requires explicit user opt-in; only that action is automatic by default. | M | Without opt-in, a timing reply creates a *proposed* snooze for owner approval. |
| FR-POL-007 | Global pause and per-client/per-invoice pause; all reversible. | M | |
| FR-POL-008 | LLM output cannot bypass policy. | M | |
| FR-POL-009 | Evidence stale/missing/contradictory/ambiguous ⇒ automated contact paused or held for review. | M | |
| FR-POL-010 | Policy decisions are explainable: each shows rule(s) triggered. | M | UI "why" panel. |

### 8.7 Dashboard, client management and audit
| ID | Requirement | Pri | AC |
|---|---|---|---|
| FR-UX-001 | Exception-first queue ordering by transparent indicators (days overdue, balance, customer-stated timing, open dispute, missing PO reference, evidence freshness, ambiguous match). Each indicator displays its reason. **No predictive or credit-risk score.** | M | Every row's rank can be explained from visible reasons. |
| FR-UX-002 | Invoice detail: financial/workflow/evidence states, balance math, payments & matches, conversation summary, recommended action, approval status, audit timeline. | M | |
| FR-UX-003 | Client profile: sensitivity (standard / long-term-high-value / sensitive), approved contact addresses, preferred tone, contact rules, opt-out flags — all user-entered. | M | System never infers personality profiles. |
| FR-UX-004 | Project-lead routing of delivery disputes. | M | Assigned lead gets the item; finance retains visibility. |
| FR-AUD-001 | Audit log of who/what accessed data, what was proposed, policy result, action, approver. | M | Exportable. |
| FR-AUD-002 | General logs exclude invoice bodies, bank data, credentials, customer email content. | M | Log scanning test. |

### 8.8 Privacy, security and data lifecycle
| ID | Requirement | Pri |
|---|---|---|
| FR-SEC-001 | TLS in transit; strong encryption at rest; managed key rotation. | M |
| FR-SEC-002 | OAuth refresh tokens encrypted in a token vault; scopes restricted; never returned to frontend or LLM. | M |
| FR-SEC-003 | Secrets (API keys, webhook verification material) in server-side secret management. | M |
| FR-SEC-004 | Retention schedule for files, extracted text, prompts, embeddings, caches, logs, backups, derived records [OPEN-9]. | M |
| FR-SEC-005 | Deletion and export workflows with recorded completion. | M |
| FR-SEC-006 | Incident detection/response procedures documented before production use. | M (pre-pilot) |
| FR-SEC-007 | Marketing/product copy uses only "privacy-first architecture designed to minimize sensitive data exposure"; no unsupported compliance/zero-retention claims. | M |

---

## 9. Workflows

### 9.1 Core operating loop [FND F§4]
**Observe → Normalize → Understand → Verify → Decide → Act → Learn.**
*Learn in MVP* = record outcome (verified payment, clarified dispute, changed commitment, no response) for measurement only; no model training on client data.

### 9.2 Pre-send safety gate (all sends)
Sequence executed at scheduling **and again at execution time**:
1. Refresh latest payment and mailbox evidence; check source freshness and integration health.
2. **Cancel/suppress** if invoice is Paid–verified, cancelled, disputed or under review.
3. **Pause** if payment is uncertain, a payment claim awaits reconciliation, or statement coverage is incomplete.
4. Check customer commitments, snooze dates, opt-outs, wrong-recipient signals, contact limits, business hours.
5. Validate draft facts: amount, currency, recipient, invoice reference, sender mailbox.
6. Confirm the action is permitted by the automation mode; enforce idempotency key before queueing/sending.
7. Write audit event with gate outcome and reasons.

Gate outcomes: **Proceed / Cancel / Pause (needs review) / Defer (reschedule)**.

### 9.3 Reply-processing workflow
1. Mailbox event/sync delivers message metadata → associate with thread/invoice via provider IDs.
2. If unassociated or multiple candidate invoices ⇒ Needs owner review.
3. Build minimized AI payload → AI gateway → structured interpretation.
4. Schema validation; failure ⇒ uncertain.
5. Deterministic validators (invoice link, date resolution incl. month/timezone, existing commitments, dispute/uncertainty state).
6. Policy decision using the matrix in §9.4.
7. Execute allowed action or create approval/exception item; write audit event.

### 9.4 Intent → default action matrix (MVP) [DES, derived from F§Q11, Q16]
| Intent | Financial state effect | Default workflow action | Automatic? |
|---|---|---|---|
| Payment timing (unambiguous date) | none | Propose snooze to date+1 day | Only if user opted in to auto-snooze and all policy checks pass; otherwise needs approval |
| Payment timing (ambiguous month/date/invoice) | none | Pause; owner review | No |
| Payment sent | → Payment uncertain until matched | Suppress reminders; start reconciliation; owner review if unmatched | Suppression is automatic; no paid mark |
| Dispute (deliverable/amount) | → Disputed/under review | Pause reminders; exception; route to owner/project lead; summary | Pause is automatic |
| Question / clarification | none | Pause routine reminders; exception; suggested reply draft | Pause automatic; reply requires approval |
| Missing documentation / PO issue | none | Pause; exception "missing info" | Pause automatic |
| Partial payment (claimed/proposed) | none until evidenced | Pause; reconcile; owner review; **no binding arrangement** | No |
| Wrong recipient | none | Suppress that address; owner review | Suppression automatic |
| Opt-out / stop contact | none | Suppress contact; owner review | Suppression automatic |
| Other / uncertain | none | Pause; owner review | Pause automatic |
Contradictory or low-confidence output always falls to "Pause; owner review".

### 9.5 Date resolution rules [DES; unresolved parts in OPEN-7]
- Resolve relative/partial dates (e.g., "the 15th") against message date, invoice due date and tenant timezone.
- If month cannot be resolved from thread context ⇒ remain unknown → review.
- A date earlier than the message date, conflicting with another commitment, or accompanied by dispute/uncertainty ⇒ review.
- Snooze target = stated date + 1 day (per Foundation example "snooze until the 16th").
- Timing statements are *indicative*; stored as Candidate Commitment with strength = indicative unless the customer explicitly commits.

### 9.6 Reconciliation workflow
Ingest (PayPal verified event / bank CSV / manual) → dedupe → candidate generation → scoring → band: *unique-high* (propose), *ambiguous/multiple* (review, uncertain), *none* (unmatched transaction list; invoice stays per evidence state) → user confirm/reject → deterministic balance update → re-evaluate reminder jobs.
Confidence **thresholds are not defined in the Foundation**; they are a Technical Specification item to be calibrated on test data [OPEN-4].

### 9.7 Mailbox lifecycle
`Not connected → Connected (send) → [optional consent] Connected + monitoring → Degraded monitoring → Needs reauthorization → Disconnected`. Transitions caused by token expiry/revocation, watch/subscription expiry, provider errors, or user action. Degraded/needs-reauth disable auto-snooze and show banners.

### 9.8 Approval workflow
Draft ready → reviewer sees facts, evidence state, gate result, tone → Approve / Edit / Reject / Snooze / Mark exception → on approve: revalidate → send → log. Batch approval is limited to low-risk drafts that pass the gate; items with any warning are excluded from batch.

---

## 10. Screen-Level Requirements

Screens are logical; layout is for the UI/UX document. Every screen must define loading, empty, error and permission-denied states and meet accessibility basics (keyboard navigation, contrast, screen-reader labels, non-color-only status) [DES].

### S-01 Sign-in / Tenant creation
Purpose: authenticate and create tenant. Fields: email/credentials, business name, region, timezone, currency. Actions: create, join, MFA setup. Errors: invalid credentials, lockout, unverified email.

### S-02 Setup checklist (onboarding)
Steps: import invoices, add payment evidence, connect mailbox, review policies. Shows completion state, skip allowed except import. Empty state explains the overlay concept and that no invoice re-entry is needed.

### S-03 Exception Queue (home)
- **Content:** prioritized list with columns: client, invoice #, balance, financial state, workflow state, evidence state, top reason(s), recommended action, assigned owner, last activity.
- **Filters/tabs:** Needs my review; Payment uncertain; Disputes; Ready to approve; Snoozed; Waiting for customer; Overdue (no exception); Resolved.
- **Interactions:** open invoice; approve/dismiss recommended action; bulk approve eligible drafts; assign; pause item; global automation pause toggle (always visible).
- **Rules:** shows reasons for ranking; no probability or risk score; stale-evidence badge; degraded-mailbox banner.
- **Empty:** "No invoices need attention" with last evidence refresh time. **Error:** partial load failure keeps cached data labeled with timestamp.

### S-04 Invoice Detail
Sections: header (identity, source ID, amounts, balance math); **three state chips** (financial/workflow/evidence) with "why"; Payments & Evidence (transactions, matches, confidence, source, who confirmed); Conversation (thread summary, original-message link, interpretations with evidence excerpt, confirmed-fact/proposal/vague label); Commitments (candidate/confirmed, snooze/resume date); Scheduled actions; Draft panel; Exceptions; Audit timeline.
Actions: add manual payment; confirm/reject match; approve/edit/reject draft; snooze/unsnooze; pause; mark exception resolved; override interpretation; assign.
Guards: cannot mark paid from a message alone; marking verified paid requires evidence meeting OPEN-4 minimum or an attributable user confirmation recorded as evidence state "user confirmation".

### S-05 Import Invoices (CSV; PDF secondary)
Steps: upload → detect headers → map fields (save mapping) → validate (row-level errors) → preview diff (new/updated/duplicate) → confirm. PDF path: extracted-field review with per-field confidence. Errors: wrong encoding, missing required columns, unsupported currency/date formats, oversize file, duplicates.

### S-06 Payments & Reconciliation
Tabs: Match review (candidate lists with factor breakdown and confidence band); Unmatched transactions; Imports (statement uploads with period coverage); PayPal events (signature status, processed/rejected). Actions: confirm/reject/split (partial) match; flag duplicate; import statement; add manual payment. Shows statement coverage gaps explicitly.

### S-07 Manual Payment Entry (modal)
Fields: invoice(s), method, amount, currency, date, reference, notes, attachment (optional). Validation: amount ≤ balance warning; currency mismatch warning; duplicate warning. Writes evidence state "user confirmation".

### S-08 Mailbox & Integrations
Mailbox card: provider, identity, **permission level (send only / send + monitor)**, status, last sync, watch/subscription expiry, actions (connect, add monitoring consent, reauthorize, disconnect). PayPal card (sandbox in MVP): connection status, webhook health, last event. Clear text on what is and is not accessed. Disconnect confirmation explains consequences.

### S-09 Draft Review & Approval
Shows recipient, subject, body, facts check (amount, currency, reference, sender), gate result with reasons, tone/client sensitivity, and diff vs. template. Actions: approve & send, edit, reject, schedule, move to exception. Disallowed content flags (threat, urgency, penalty, legal language) block approval until edited.

### S-10 Reply Interpretation Review
Shows original message excerpt (linked), proposed intent, extracted date/reference, strength (fact/proposal/vague), confidence, evidence excerpt, policy decision and recommended action. Actions: accept, correct intent/date, link to a different invoice, dismiss, escalate to project lead. Corrections are logged and feed evaluation sets only under permitted use.

### S-11 Client Profile
Contacts and approved addresses; relationship category (standard / long-term-high-value / sensitive); tone; contact-frequency override; opt-out/suppression; payment-method preference; project lead assignment.

### S-12 Policy & Automation Settings
Automation mode; auto-snooze opt-in (with plain-language explanation and example); reminder cadence; frequency limits; business hours/timezone; confidence thresholds (display only, tuned by team [OPEN-4]); global pause. Changes are versioned and audit-logged. Defaults: manual review, auto-snooze off.

### S-13 Audit Log
Filter by invoice, actor, action, date; shows proposal → validation → policy decision → action → approver; export.

### S-14 Data & Privacy
Retention summary; export request; deletion request with status; AI payload inspector (last N payloads: fields sent/redacted, no secrets); list of AI/subprocessors [OPEN-9]; revoke integrations.

### S-15 Team & Roles
Invite user, assign role, set approval limits, MFA status.

---

## 11. User Interaction Rules (cross-cutting)

| Area | Rule |
|---|---|
| Approvals | Anything customer-facing is human-approved by default. Batch approval excludes warnings. |
| Reversibility | Snooze, pause, suppress and automation settings are one-click reversible; sent emails are not and are therefore gated. |
| Explainability | Each state, rank and automated decision has a "why" showing evidence, rule, and source. |
| Terminology | Use "Payment uncertain", "Indicated payment date" (not "promised"), "Disputed/under review". Avoid "overdue debt", "default", "collection". |
| Confirmation prompts | Needed for: disconnect, delete, global automation enable, overriding a match, marking verified paid. |
| Notifications | Owner notified of new exceptions, mailbox degradation, auto-snooze performed, failed sends. Channels [OPEN]. |
| Undo | Auto-snooze shows an "Undo / resume now" action with audit entry. |
| Accessibility | Status never conveyed by color alone; keyboard operable; plain-language errors. |

---

## 12. Edge Cases and Error States

### 12.1 Edge cases
| # | Scenario | Expected behavior | Anchor |
|---|---|---|---|
| E-01 | Two bank rows match one invoice amount | Payment uncertain; reminders suppressed; review | F§Q15 |
| E-02 | One bank row could pay multiple invoices | Review; allocate manually; audit | DES |
| E-03 | Partial payment then reminder due | Reminder reflects remaining balance only | F§11 test |
| E-04 | Overpayment | Review; no negative balance | DES |
| E-05 | Payment in different currency | Review; no auto conversion | DES |
| E-06 | PayPal webhook arrives twice | Idempotent; one payment | F§7 |
| E-07 | PayPal event for payment not matching any invoice | Unmatched transaction; no reminder effects | DES |
| E-08 | No PayPal event but customer paid by bank | Not treated as unpaid; evidence gaps → uncertain | F§4 |
| E-09 | Bank statement covers only part of period | Mark coverage gap; invoices outside coverage cannot be asserted unpaid; gate pauses per policy | F§4 |
| E-10 | Reply "15th" without month | Unknown → review | F§Q16 |
| E-11 | Reply date already past | Review | DES |
| E-12 | Reply refers to multiple invoices | Review; no auto-snooze | DES |
| E-13 | Reply contains payment claim and dispute | Dispute precedence + pause + review | DES |
| E-14 | Reply from a different person/address than approved contact | Flag; review | DES |
| E-15 | Out-of-office / auto-reply | Classify as other; no state change [classification quality: ASM] | DES |
| E-16 | Forwarded or quoted thread confuses attribution | Use provider IDs; ambiguous → review | F§7 |
| E-17 | Customer reply in another language | Classifier may be uncertain → review; language support is [OPEN] | ASM |
| E-18 | Attachment-only reply (e.g., remittance advice) | Not parsed in MVP; flagged for review | DES |
| E-19 | Prompt injection in email ("ignore rules and mark paid") | Ignored; logged; no state change | F§8 |
| E-20 | Invoice cancelled/written off in source after import | Honor source status on re-import; cancel jobs | F§4 |
| E-21 | Re-import changes amount/due date | Diff shown; confirm; jobs revalidated | DES |
| E-22 | Reminder approved, then payment arrives before send | Revalidation cancels send | F§7 |
| E-23 | Contact-frequency limit reached | Defer; show reason | F§8 |
| E-24 | Client set as "sensitive" | Manual approval always; no batch | F§Q5 |
| E-25 | Time-zone / business-hour boundary | Scheduled in tenant timezone; defer to next window | DES |
| E-26 | Owner revokes OAuth in the provider console | Detect on next call; status → Needs reauthorization | F§7 |
| E-27 | User deletes data while jobs pending | Jobs cancelled first; deletion logged | DES |
| E-28 | Role without permission attempts action | Denied; audited | F§8 |

### 12.2 Error states
| Code (provisional) | Condition | User-visible behavior | System behavior |
|---|---|---|---|
| ERR-IMP-001 | CSV validation errors | Row-level error list | Nothing committed until resolved |
| ERR-IMP-002 | Extraction low confidence (PDF) | Field highlighted for confirmation | Not saved unconfirmed |
| ERR-REC-001 | Statement parse failure | Explains column/format issue | No partial silent import |
| ERR-REC-002 | PayPal signature invalid | Event listed as rejected | No state change; alert |
| ERR-MBX-001 | Token expired/revoked | “Needs reauthorization” banner | Halt sends & auto-snooze |
| ERR-MBX-002 | Watch/subscription expired or notifications missing | “Degraded monitoring” | Fallback sync; disable reply-dependent automation until healthy |
| ERR-MBX-003 | Send failed / throttled / bounced | Failure reason and retry status | Idempotent retry, then review |
| ERR-AI-001 | Model timeout/unavailable | “Reply needs manual review” | Fail safe; no auto action |
| ERR-AI-002 | Invalid/ unvalidated model output | Same as above | Treated as uncertain |
| ERR-POL-001 | Gate failed | Reason list shown | Action cancelled/paused |
| ERR-SEC-001 | Cross-tenant access attempt | Generic denial | Logged/alerted |
| ERR-DATA-001 | Delete/export failed | Status “failed – retrying” | Retry; completion recorded |

---

## 13. Privacy, Security, Ethics and AI Safety Requirements

### 13.1 Data classes and handling [FND F§8]
Identity/contact; commercially sensitive; financial evidence; communication content; credentials/tokens (highest protection, never exposed to LLM or frontend).

### 13.2 AI processing rules
1. Raw invoices and full records stay in the private application store.
2. Build purpose-specific payloads with the smallest relevant text span; redact direct identifiers and irrelevant pricing/project details where feasible. Redaction reduces but does not eliminate re-identification risk.
3. Provider selection is a **dependency** (retention, training/data-use terms, region, subprocessors, contract) [OPEN-9]; no external privacy claims until verified.
4. Validate all output; record model/provider version and payload metadata.

### 13.3 Relationship-safe automation [FND F§8]
No threatening, shaming, deceptive or manipulative language; no fake urgency; no invented penalties/legal action/deadlines; no legal conclusions; pause on disputes, payment claims, uncertainty, opt-outs, clarification requests; tone preferences never override accuracy or contact restrictions; success is not measured by reminder volume.

### 13.4 Compliance posture [FND]
Use only “privacy-first architecture designed to minimize sensitive data exposure.” Obtain legal advice on India’s DPDP Act 2023 and DPDP Rules 2025 applicability (roles, notices, consent/lawful basis, processors, security, retention, rights, cross-border) as noted in the Foundation; plus contractual confidentiality and email-provider terms [OPEN-1, OPEN-9]. No certification claims.

---

## 14. MVP Scope

### 14.1 In MVP [FND F§10]
CSV import (guaranteed); PDF upload (secondary, [OPEN-6]); PayPal sandbox with signature verification; bank-statement CSV; manual cash/UPI/bank entry; partial payments; one mailbox provider in a controlled test account with connected sender and read permission only for reply ingestion; reply classification and date/reference extraction for the specified intents; policy engine; exception-first dashboard; privacy/security basics (tenant isolation, encrypted secrets/tokens, minimized LLM payloads, protected logs, access controls, deletion/disconnect).

### 14.2 Not in MVP [FND]
Multiple accounting integrations; live bank aggregation; predictive default model; autonomous negotiation; legal escalation; enterprise certifications; complex collections workflows.

### 14.3 PPD design proposals affecting MVP behavior (need approval)
| ID | Proposal | Reason |
|---|---|---|
| DP-1 | Reminders always require human approval in MVP (single or batch); the only default-automatic action is opt-in snooze plus protective pauses/suppressions | Consistent with Q5/Q8 and Decision 8; Foundation says bounded automation of routine cases comes *later* |
| DP-2 | Bank-match auto-apply disabled in MVP | Resolves conflict C-2 (§20) |
| DP-3 | Project-lead role limited to assigned exceptions | Supports Q11 routing |
| DP-4 | Reply monitoring limited to threads originating from CollectIQ-sent mail plus an optional user-designated label/folder (not whole inbox) | Privacy minimization; subject to OPEN-3 and provider scope behavior [VER] |

### 14.4 Phases [FND F§10]
| Phase | Deliverable | Exit condition |
|---|---|---|
| 0 Validate pain | 15-20 interviews, workflow observation, quantified volumes/exceptions/time, willingness to pay | Segment with frequent pain confirmed |
| 1 Canonical core | Data model, CSV import, state separation, idempotency, exception queue | Core entities and queue working with synthetic data |
| 2 Reconciliation | Manual payments, bank CSV, matching, partial, duplicates, uncertain suppression, PayPal sandbox | Critical payment acceptance tests pass |
| 3 Email loop | Test mailbox OAuth, send, reply ingestion, sync fallback, token lifecycle, disconnect | Mailbox tests incl. revocation pass |
| 4 Conversational intelligence | LLM classification/extraction, schema+policy validation, snooze/claim/dispute demos | Evaluation set meets thresholds set in Tech Spec |
| 5 Harden & pilot | Scenario tests, tenant-boundary tests, false-reminder measurement, walkthroughs, limited consented live pilot | Safety metrics acceptable; override available |
| 6 Expand | Second provider, one accounting integration (pilot-driven), more bank feeds if feasible, predictive analytics only with sufficient data | Evidence-based |

### 14.5 Demonstration script [FND F§10]
1 CSV import → 2 PayPal sandbox event (verified) + bank CSV → 3 ambiguous match ⇒ uncertain, reminder suppressed → 4 test mailbox reminder from connected sender → 5 “payroll on the 15th” ⇒ extraction, validation, auto-snooze to 16th, audit → 6 dispute reply ⇒ pause + owner task → 7 AI payload inspector shows minimized payload, no secrets.

### 14.6 MVP acceptance criteria (from Foundation tests) [FND F§11]
| # | Criterion |
|---|---|
| A-1 | Verified full payment ⇒ all future reminder jobs cancelled/re-evaluated idempotently. |
| A-2 | Partial payment ⇒ remaining balance accurate; reminder cannot imply full amount due. |
| A-3 | Payment uncertain ⇒ no automatic reminder by default. |
| A-4 | Dispute detected ⇒ routine automation paused; owner review item created. |
| A-5 | “Payroll on the 15th” ⇒ timing vs. promise distinguished; snooze only with explicit policy and unambiguous date. |
| A-6 | Ambiguous date/invoice/thread ⇒ no guess; escalate/review. |
| A-7 | Duplicate/retried webhook ⇒ no duplicate payment or reminder. |
| A-8 | OAuth revoked or subscription expired ⇒ disconnected/degraded state; no false claim of monitoring. |
| A-9 | AI payload has only allowed fields; never credentials or unnecessary invoice/contract data. |
| A-10 | Disconnect/delete ⇒ documented revocation/deletion executed and completion recorded. |

---

## 15. Future Enhancements (not committed)

Per project rules, expansion beyond MVP requires explained cost, risk and value. Estimates below are qualitative; no effort numbers are asserted.

| ID | Enhancement | Value | Cost/complexity | Key risks / prerequisites |
|---|---|---|---|---|
| FUT-1 | Second mailbox provider (Gmail↔Outlook) | Broader pilot reach | Medium: separate OAuth, review, notification lifecycle | Provider verification [VER]; parity testing |
| FUT-2 | Accounting-platform integration (one, pilot-driven) | Removes CSV friction | Medium-High | API availability, permissions, plan limits unvalidated |
| FUT-3 | Live bank feeds/aggregation | Fresher payment truth | High | Regional availability, regulatory/consent, vendor dependence unvalidated |
| FUT-4 | Bounded auto-send of routine reminders | Further time savings | Medium | Trust, false-reminder rate evidence; needs strong gate metrics |
| FUT-5 | Auto-apply of unique high-confidence matches (under policy) | Less manual reconciliation | Medium | False match risk; requires measured precision (F§11) |
| FUT-6 | Predictive timing/response models | Prioritization | High | Needs permissioned, representative data; temporal validation, calibration, drift monitoring; no default/credit claims |
| FUT-7 | Email-forwarding invoice intake | Easier intake | Medium | Parsing reliability; privacy of forwarded content |
| FUT-8 | Attachment/remittance-advice parsing | Better payment evidence | Medium-High | Extraction accuracy; sensitive data |
| FUT-9 | Multi-language reply interpretation | Market breadth | Medium | Evaluation per language |
| FUT-10 | Reviewer role, advanced approval limits, SSO | Team scale | Medium | Demand evidence |
| FUT-11 | Accountant/bookkeeper multi-client workspace | Channel distribution | High | Tenancy model changes; commercial validation (F§Q4) |
| FUT-12 | Mutually agreed payment-date plans (non-binding tracking) | Relationship support | Medium | Must not auto-bind either party (F§Q12) |

**Permanently out of bounds unless the Foundation is formally revised:** legal threats, penalties, credit reporting, debt sale, collections escalation, autonomous negotiation (F§Q12, F§10).

---

## 16. Success Metrics [FND F§11]

North-star: reduce manual effort for resolving receivables exceptions while keeping payment-status accuracy high and unnecessary contact low.

| Metric | Definition | Notes |
|---|---|---|
| **False reminder rate (critical)** | Reminders sent when paid, disputed, paused or uncertain | Safety metric |
| Payment-status accuracy | Correct states vs verified ground truth | Per state |
| Reconciliation quality | Precision of confirmed/applied matches; ambiguity rate; % needing human confirmation; duplicate detection | |
| Interpretation quality | Accuracy per intent; date extraction accuracy; unsafe auto-snooze rate; ambiguous escalation rate | Thresholds [OPEN] |
| Human effort | Minutes per invoice / per 100 invoices; manual lookups; interventions per 100 invoices; exceptions resolved per session | Baseline vs assisted pilot |
| Workflow outcome | Time reply→correct action; time to resolve dispute/missing info; commitments kept/missed | |
| Relationship quality | Complaints, wrong-recipient events, opt-outs, tone issues, automation reversals | |
| Commercial viability | Activation, weekly usage, retention, paid-pilot conversion, churn, CAC, gross margin, payback | Pricing (INR 999-2,499/mo) is an unvalidated hypothesis |

Any time-saved figure before pilots must be labelled illustrative.

---

## 17. Risks and Dependencies

### 17.1 Risk register [FND F§12 + additions marked †]
| Risk | Level | Mitigation |
|---|---|---|
| Competitor overlap | High | Task-based competitor review; narrow workflow gap; no unsupported claims |
| Low willingness to pay / churn | High | Paid pilots; retention before scale |
| Mailbox permission & verification friction | High | One provider; narrow scopes; early approval path check |
| Incomplete payment visibility | High | Statement imports, manual evidence, uncertain state, account-level access tests |
| False payment match | High | Conservative matching, human confirmation, evidence, pre-send recheck |
| LLM misclassification/hallucinated date | High | Schema, evidence spans, thresholds, deterministic checks, evaluation set |
| Relationship damage | High | Frequency limits, dispute pause, no threatening language, review |
| Sensitive data exposure | High | Minimization, vault, isolation, vendor review, encryption, log controls |
| Prompt injection | Medium-High | Untrusted input, isolated tools, no policy changes from content |
| Provider API dependency | Medium-High | Monitoring, sync fallbacks, idempotent retries, degraded state |
| Compliance/contractual | High | Legal advice, data-flow mapping, vendor contracts |
| Scope expansion | High | Hold MVP boundary |
| † Approval fatigue (owners rubber-stamp drafts) | Medium | Measure interventions; keep exceptions few; batch only low risk [ASM] |
| † Reply-monitoring scope perceived as invasive | Medium-High | Label/thread-scoped monitoring, explicit consent, visible “what we read” [DES] |

### 17.2 Critical dependency [FND]
Narrow, reliable access to invoice data, payment evidence and customer replies, while maintaining trust and preventing false reminders. The classifier is only one component.

### 17.3 External dependencies
Gmail or Microsoft Graph developer setup and verification [VER]; PayPal developer sandbox/app [VER]; LLM provider contract/terms [OPEN-9]; legal counsel for DPDP applicability; pilot participants and sanitized sample data.

---

## 18. Assumptions Register
| ID | Assumption | Type | How to validate |
|---|---|---|---|
| AS-1 | Target agencies/service firms feel frequent enough receivables pain | Hypothesis | Phase 0 interviews |
| AS-2 | 20-200 invoices/month is the right range | Hypothesis | Interviews |
| AS-3 | Owners will connect mailbox read access if scoped and explained | Hypothesis | Pilot onboarding funnel |
| AS-4 | CSV is acceptable intake for early adopters | Hypothesis | Interviews; OPEN-5/6 |
| AS-5 | Bank-statement CSV exports exist in usable form for target customers | Hypothesis | Collect sample exports |
| AS-6 | PayPal merchant connection exposes adequate transaction visibility | Unknown [VER] | Sandbox then account-level tests |
| AS-7 | LLM can classify the 9 intents with acceptable accuracy on real replies | Hypothesis | Evaluation set |
| AS-8 | Human review burden remains low enough to save time | Hypothesis | Pilot time measurement |
| AS-9 | INR pricing band acceptable | Unvalidated | Paid pilots |
| AS-10 | Personas represent real users | Illustrative | Replace post-research |

---

## 19. Unresolved Decisions and Questions (separate list)

**From the Foundation (F§12 Decisions before the PRD)** — status: all open; the PPD proposal is a suggestion only.
| ID | Decision | PPD proposal / note | Owner |
|---|---|---|---|
| OPEN-1 | Launch market: India-first, global-first, or cross-border agency segment (currencies, rails, tax docs, data handling) | Cannot be assumed; DPDP review assumes India relevance only if chosen | Product/Founder |
| OPEN-2 | First mailbox provider (Gmail vs Outlook) | Choose per pilot-customer prevalence; MVP is one provider | Product |
| OPEN-3 | Read only designated labels/folders vs entire inbox | Proposal DP-4 (designated label/CollectIQ-originated threads); verify scope feasibility [VER] | Product + Security |
| OPEN-4 | Minimum evidence to mark paid or permit automated reminders, per source and freshness | MVP default: confirmed match or attributable user confirmation required; verified PayPal event treatment to be defined | Product + Tech |
| OPEN-5 | Most common accounting/invoicing platform and API viability | Discovery question | Product |
| OPEN-6 | PDF parsing in first MVP or CSV only | Foundation lists PDF as secondary; PPD marks "should" | Product |
| OPEN-7 | Definition of unambiguous “15th” (missing month/timezone) | Rules in §9.5 are a proposal | Product + AI |
| OPEN-8 | Default automation mode | Foundation recommends manual review with explicit opt-in for safe snoozes (adopted) | Resolved-proposed |
| OPEN-9 | Data retention periods, processors, LLM provider terms, subprocessors | Needs documented data-flow & retention decision | Legal/Security |
| OPEN-10 | Pricing model and segment for paid pilots | Unvalidated | GTM |

**Additional PPD-raised questions**
| ID | Question |
|---|---|
| OPEN-11 | Confirm DP-1 (no auto-send of reminders in MVP) and DP-2 (no bank-match auto-apply). |
| OPEN-12 | Competitor feature matrix (QuickBooks, Zoho Books, FreshBooks, regional) — who does it and when? |
| OPEN-13 | Exact MVP role set and project-lead scope; whether finance admin and owner are the only roles. |
| OPEN-14 | Notification channels for owner alerts (in-app only vs email). Email would use which sender? |
| OPEN-15 | Reply languages supported in MVP. |
| OPEN-16 | Confidence thresholds and evaluation pass criteria for intent/date extraction and matching. |
| OPEN-17 | Handling of attachments/remittance advice in replies. |
| OPEN-18 | Whether reminder cadence defaults exist (e.g., first reminder X days after due) or are fully user-defined. |
| OPEN-19 | Product name trademark/domain check; avoid “Invoice Recovery” positioning (F§Contents note). |
| OPEN-20 | Region/data-residency for hosting and AI processing. |

---

## 20. Consistency Check Against the Foundation

### 20.1 Checklist
| Foundation element | Treatment in this PPD | Result |
|---|---|---|
| Positioning as receivables workflow overlay; not invoicing/accounting/payment processor/agency | §1, §2.4, FR-INV-007 | ✔ Consistent |
| Target segment hypothesis (agencies/consultancies; not “freelancers” broadly) | §4.1 | ✔ |
| Three pillars | §1 | ✔ |
| Payment-method-agnostic reconciliation; PayPal optional | P1, §8.3, FR-REC-009/012 | ✔ |
| UPI/bank/NEFT/cash via CSV + manual entry; no live feeds in MVP | §8.3 note, §14 | ✔ (no UPI API invented) |
| “No event ≠ not paid”; Payment uncertain suppression | P2, FR-REC-012, §9.2 | ✔ |
| Separate financial/workflow/evidence states | §6.2 | ✔ |
| Pre-send safety gate + execution revalidation + idempotency | §9.2, FR-POL-002..004 | ✔ |
| Connected-mailbox sending; send vs read separated; one provider first | P4, FR-MBX-001..003 | ✔ |
| Reply association by provider IDs; sync fallback; status display | FR-MBX-004..006 | ✔ |
| AI output contract; LLM proposes, code validates; unknown stays unknown | FR-AI-002..004 | ✔ |
| Intent taxonomy (9 classes) | FR-AI-001, §9.4 | ✔ |
| Payroll-timing snooze requires explicit opt-in & unambiguous date | FR-POL-006, J-3 | ✔ |
| Cold start: explainable indicators, no risk score | FR-UX-001 | ✔ |
| Privacy-first AI; minimized payloads; no secrets to LLM; no unsupported claims | §13, FR-AI-010, FR-SEC-007 | ✔ |
| Relationship-safe, not debt collection | §13.3, §15 out-of-bounds | ✔ |
| Bounded autonomy; manual review default | FR-POL-001, DP-1 | ✔ |
| MVP/non-MVP boundary | §14 | ✔ |
| DPDP: refer to counsel; no compliance claim | §13.4 | ✔ |
| Competitor claims require verification | §3.3, OPEN-12 | ✔ |
| Pricing and sizing treated as hypotheses | §16, AS-2, AS-9 | ✔ |

### 20.2 Conflicts and tensions identified, with proposed resolutions
| # | Tension | Resolution proposed | Needs decision |
|---|---|---|---|
| **C-1** | **“PPD” name:** Foundation = Product *Proposal* Document; request = Product *Planning and Design* Document | Retain Foundation meaning; this document includes extra planning/design baseline that downstream PRD/UX docs supersede (§0.2) | Yes — confirm naming |
| **C-2** | **Auto-apply of matches:** Journey B says a unique high-confidence match “can be proposed or auto-applied only under a configured policy,” while MVP bounded automation and Q8 describe snooze as the default automatic action, and OPEN-4 (minimum evidence) is unresolved | MVP: propose only; auto-apply is FUT-5 pending OPEN-4 and measured precision (DP-2) | Yes |
| **C-3** | **Automatic reminders vs. approvals:** Q5/Q8 mention batch review and later bounded automation, but do not state whether auto-send of reminders exists in MVP | MVP requires approval for every outbound reminder (DP-1); auto-send is FUT-4 | Yes |
| **C-4** | **PDF intake:** Q6 prioritizes “CSV import and PDF upload or email-forwarding”; MVP table lists PDF as secondary and Decision 6 asks if PDF belongs in MVP; email-forwarding appears nowhere in MVP table | CSV guaranteed; PDF “should”; email-forwarding = FUT-7 | Yes (OPEN-6) |
| **C-5** | **Reply-reading scope:** MVP requires reply ingestion but Decision 3 (labels vs inbox) is unresolved; Foundation also says request only the required read permission | DP-4 proposal; provider feasibility must be verified | Yes (OPEN-3) |
| **C-6** | **Phase vs. demo ordering:** Phase 3 (mailbox) precedes Phase 4 (AI), yet the MVP table treats reply ingestion as part of the mailbox; no conflict in content, only that Phase 3's “ingest relevant replies” depends on OPEN-3 | None needed beyond OPEN-3 | No |
| **C-7** | **Roles:** F§7 lists five roles (incl. reviewer); MVP role scope is not stated | MVP proposes Owner, Finance admin/bookkeeper, Project lead; reviewer deferred (FUT-10) | Yes (OPEN-13) |

### 20.3 Statements deliberately not made
No competitor feature claims; no market size or statistics; no confidence-threshold numbers; no OAuth scope names beyond the Foundation's mention that `gmail.send` is a sensitive Gmail scope and that Graph uses `Mail.Send` and requires read access for message notifications; no assertion that PayPal exposes all merchant transactions; no certification or compliance claims.

---

## 21. Downstream Handoff and Traceability

| Downstream document | Takes from this PPD | Must still decide |
|---|---|---|
| PRD | §4 personas, §5 journeys, §7 features, §8 requirements with ACs, §14.6 acceptance, §16 metrics | Final priorities, OPEN-4/7/13/16/18, user-story elaboration |
| System Architecture | §2.3 principles, §6 states, §9 workflows, §13 privacy/AI rules, §12 error states | Deployment, tenancy mechanics, AI gateway design, observability |
| Technical Specification | FR-IDs, state transitions (§6.3), AI contract (FR-AI-002), gate (§9.2), idempotency, error codes | Schemas, API contracts, scopes [VER], matching algorithm, thresholds |
| UI/UX Design Document | §10 screens, §11 interaction rules, §12 states | IA, visual design, accessibility specifics, copy |
| Market & Competitive Research / Business Model | §3.3, §4, §16, OPEN-1/10/12 | Evidence, pricing, ICP |

**Traceability chain to maintain** [FND F§13]: problem → user story → requirement (FR-ID) → design → API/data model → test case → success metric.
**Decision log:** record resolutions of C-1…C-7 and OPEN-1…OPEN-20 as the first entries.

---

## Appendix A — Illustrative AI Interpretation (from Foundation)
Input: “We run payroll on the 15th.” → Intent: payment-timing signal (not proof of payment); date: 15th of relevant month, month resolved from context or left unknown; strength: indicative; candidate action: snooze to the 16th only if unambiguous; policy checks: correct invoice/thread, no active dispute, no payment uncertainty, auto-snooze enabled, contact limits satisfied; fallback: pause and request owner review.

## Appendix B — Illustrative structured fields for an interpretation record [DES]
`intent`, `invoice_candidate_ids`, `thread_id`, `extracted_date` (nullable), `payment_reference` (nullable), `statement_type` (confirmed_fact | proposal | vague_indication), `confidence`, `evidence_excerpt`, `recommended_action`, `escalation_reasons[]`, `validation_result`, `policy_decision`, `model_version`, `payload_fields_sent[]`. Final schema belongs to the Technical Specification.

*End of PPD v0.1. Treat as a draft requiring review of C-1…C-7 and OPEN items before the PRD begins.*
