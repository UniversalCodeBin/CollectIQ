# Stitch control dispositions

Every interactive control in the 17 Stitch exports, with the decision for it. The inventory comes from
`scripts/extract_stitch_controls.py`, and `backend/tests/meta/test_stitch_dispositions.py` fails if a
control has no row here.

- **KEEP**: build it as designed, wired to the target.
- **CHANGE**: keep the intent, but the note says what differs from the design.
- **OMIT**: do not build it, for the reason in the note.

Target is an endpoint from the catalogue and/or the plan task that builds the control. Screen `SCR-15m` is the
attestation modal on SCR-15. Sample values in the designs are never reproduced as real data.

Totals: 254 distinct controls: 193 KEEP, 28 CHANGE, 33 OMIT.

| kind | label | screens | disposition | target | note |
| --- | --- | --- | --- | --- | --- |
| button | (no label) | SCR-01, SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-13, SCR-14, SCR-15, SCR-15m, SCR-16, SCR-17 | CHANGE | T8 | Icon-only control; must get an accessible name |
| checkbox | (no label) | SCR-01, SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-13, SCR-14, SCR-15, SCR-15m, SCR-16, SCR-17 | CHANGE | T8 | Icon-only control; must get an accessible name |
| radio | (no label) | SCR-05, SCR-08, SCR-10, SCR-14 | CHANGE | T8 | Icon-only control; must get an accessible name |
| select | #REQ-AI-90214 — Customer Reply Intent & Date Interpretation (INV-2041 / Example Client Ltd) #REQ-AI-90199 — UTR Extract from Scanned Cheque Advice (HDFC-99120 / Bharat Steel) #REQ-AI-90142 — Counterparty TDS Certificate Reconciliation (Form 16A / Q2-FY26) | SCR-13 | KEEP | E105, T36 | Payload inspector |
| button | + | SCR-10 | KEEP | E017, T27 | Policy stepper and defaults |
| button | + Declare Inward Account | SCR-15m | KEEP | E029, T20 | Declare a payment account |
| button | - | SCR-10 | KEEP | E017, T27 | Policy stepper and defaults |
| text | 03 Nov 2026, 17:00 IST | SCR-15m | KEEP | E054, T20 | Attestation; sample values dropped |
| text | 07AAAAA0000A1Z5 | SCR-13 | OMIT | - | GSTIN/PAN sample; neither field is collected (no PRD or UX requirement) |
| number | 3 | SCR-10 | KEEP | E017, T27 | Policy stepper and defaults |
| number | 7 | SCR-10 | KEEP | E017, T27 | Policy stepper and defaults |
| text | ABCDE1234F | SCR-13 | OMIT | - | GSTIN/PAN sample; neither field is collected (no PRD or UX requirement) |
| button | Accept Interpretation | SCR-07 | KEEP | E068, T30 | Accept an interpretation |
| button | Accounts & Coverage (SCR-15) | SCR-06 | KEEP | E029, T20 | Declare a payment account |
| button | Acknowledge & Hold | SCR-14 | OMIT | - | No hold state outside dispute and snooze rules |
| button | Active Feeds (3) | SCR-15 | KEEP | E029, T20 | Declare a payment account |
| button | Add | SCR-01, SCR-02, SCR-03, SCR-04, SCR-06, SCR-07, SCR-13, SCR-15, SCR-15m, SCR-16, SCR-17 | KEEP | T8 | Add menu (UX 144) |
| a | Add / Import | SCR-05, SCR-08, SCR-09, SCR-10, SCR-12, SCR-14 | KEEP | T8 | Add menu (UX 144) |
| button | Add Customer Reply (Paste / Upload) | SCR-07 | KEEP | E062, T26 | Log a customer reply |
| button | Add Integration | SCR-16 | OMIT | - | UXR-12: UI lists only what exists, no connect controls for planned integrations |
| button | Add Internal Memo | SCR-17 | CHANGE | E079, T26 | Dispute note only; there is no client note entity |
| button | Add Internal Note | SCR-08, SCR-14 | CHANGE | E079, T26 | Dispute note only; there is no client note entity |
| button | Add Note | SCR-08 | CHANGE | E079, T26 | Dispute note only; there is no client note entity |
| button | Add Note / Reply | SCR-04 | CHANGE | E079, T26 | Dispute note only; there is no client note entity |
| button | Add Operator Note | SCR-14 | CHANGE | E079, T26 | Dispute note only; there is no client note entity |
| button | AI Payload Inspector Transparency | SCR-13 | KEEP | E105, T36 | Payload inspector |
| button | AI PDF Document Extraction (3 Documents) OCR | SCR-05 | CHANGE | E038, T31 | Shown only when the flag is on |
| button | All | SCR-09 | KEEP | T14-T35 | Tab; count computed live |
| select | All Assignees Priya Raman (3) Sneha Mehta (1) Arun K. (1) | SCR-17 | KEEP | FR-028, T14 | Assignment |
| button | All Declared Accounts (4) | SCR-15 | KEEP | E029, T20 | Declare a payment account |
| button | All Events 16 | SCR-17 | KEEP | E099, T35 | Audit filter |
| button | All invoices 214 | SCR-03 | KEEP | T14-T35 | Tab; count computed live |
| button | All Open (3) | SCR-08 | KEEP | T14-T35 | Tab; count computed live |
| select | All Priorities Urgent (1) Elevated (3) Routine (1) | SCR-17 | KEEP | FR-028, T14 | Assignment |
| select | All Types Payment Claim (2) Telemetry Gap (1) Import Conflict (1) Dispute (1) Draft Invoices (0) | SCR-17 | KEEP | FR-028, T14 | Assignment |
| button | Amount | SCR-03 | KEEP | E047, T14 | Server-ordered column header |
| button | Amount (1) | SCR-08 | KEEP | T14-T35 | Tab; count computed live |
| button | Approve & Mark Ready to Send | SCR-09 | KEEP | E087, T27 | Approve; per-item (OD-20) |
| button | Approve eligible drafts (1) | SCR-03 | KEEP | E087, T27 | Approve; per-item (OD-20) |
| button | Archive | SCR-08 | CHANGE | E076, T26 | Resolved filter, not an archive |
| select | Asia/Kolkata (UTC +05:30 IST) Asia/Dubai (UTC +04:00) Europe/London (UTC +00:00 / +01:00) | SCR-13 | KEEP | E012, T36 | Workspace profile; sample value dropped |
| button | Assign | SCR-03 | KEEP | FR-028, T14 | Assignment |
| button | Assignee | SCR-03 | KEEP | FR-028, T14 | Assignment |
| button | Attest / Ingest Fresh Feed | SCR-16 | OMIT | - | UXR-12: UI lists only what exists, no connect controls for planned integrations |
| button | Attest Check | SCR-15m | KEEP | E054, T20 | Attestation; sample values dropped |
| button | Attest Checked Accounts | SCR-15 | KEEP | E054, T20 | Attestation; sample values dropped |
| button | Attest Nothing Received | SCR-15 | KEEP | E054, T20 | Attestation; sample values dropped |
| button | Attest: ‘Checked — Nothing Received’ | SCR-04 | KEEP | E054, T20 | Attestation; sample values dropped |
| button | Attest: “Checked — Nothing Received” (SCR-15) | SCR-17 | KEEP | E054, T20 | Attestation; sample values dropped |
| button | Attestation Registry | SCR-15 | CHANGE | E032, T20 | Coverage view; there is no attestation list endpoint |
| button | Audit Access Logs | SCR-16 | OMIT | - | UXR-12: UI lists only what exists, no connect controls for planned integrations |
| button | Audit Cert | SCR-07 | OMIT | - | Implies a certification; forbidden claim |
| a | Audit History | SCR-01, SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-13, SCR-14, SCR-15, SCR-15m, SCR-16, SCR-17 | KEEP | T8, T36 | Directive nav |
| button | Audit Log | SCR-17 | KEEP | E099, T35 | Audit filter |
| button | Authorize & Post Resolution | SCR-08 | KEEP | E080, T26 | Resolve a dispute |
| a | Automation | SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-14, SCR-15 | KEEP | T8, T36 | Directive nav |
| a | Automation Rules | SCR-01, SCR-13, SCR-15m, SCR-16, SCR-17 | CHANGE | T8, T36 | Directive nav label governs |
| button | Blocked | SCR-09 | KEEP | T14-T35 | Tab; count computed live |
| button | Cadence Log | SCR-07 | OMIT | - | Cadence lives in Automation settings and the timeline, not as a separate log |
| button | Cadence Rules | SCR-09 | OMIT | - | Cadence lives in Automation settings and the timeline, not as a separate log |
| button | Cancel | SCR-08 | KEEP | T8 | Generic control |
| button | Cancel / Discard | SCR-15m | KEEP | T8 | Generic control |
| button | Cases (0) | SCR-04 | KEEP | T14-T35 | Tab; count computed live |
| button | Clear with Operator Attestation → | SCR-15m | OMIT | - | Bypasses a gate; freshness needs a real attestation (E054) |
| button | Client | SCR-03 | KEEP | E047, T14 | Server-ordered column header |
| a | Clients | SCR-14 | KEEP | T8 | Generic control |
| button | Clients | SCR-03 | KEEP | T8 | Generic control |
| button | Collapse | SCR-04 | KEEP | T8 | Generic control |
| text | CollectIQ India Operations Pvt. Ltd. | SCR-13 | KEEP | E012, T36 | Workspace name; sample value dropped |
| button | Columns | SCR-05 | KEEP | E047, T14 | Server-ordered column header |
| button | Commit 36 Invoices to Active Ledger | SCR-05 | KEEP | E035, T13 | Commit an import |
| button | Configure Connector | SCR-16 | OMIT | - | UXR-12: UI lists only what exists, no connect controls for planned integrations |
| button | Confirm Irreversible Erasure | SCR-13 | KEEP | E104, T36 | Workspace deletion |
| button | Confirm Link | SCR-04 | KEEP | E066, T26 | Message association |
| button | Confirm Match & Apply Allocation | SCR-06 | KEEP | E057, T20 | Confirm a match |
| button | Confirmed Payments 18 | SCR-06 | KEEP | T14-T35 | Tab; count computed live |
| button | Connect QuickBooks | SCR-16 | OMIT | - | UXR-12: UI lists only what exists, no connect controls for planned integrations |
| button | Connect Zoho Books | SCR-16 | OMIT | - | UXR-12: UI lists only what exists, no connect controls for planned integrations |
| button | Conversation 1 unverified | SCR-04 | KEEP | T14-T35 | Tab; count computed live |
| a | Conversations | SCR-01, SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-13, SCR-14, SCR-15, SCR-15m, SCR-16, SCR-17 | KEEP | T8, T36 | Directive nav |
| button | Conversations & Touchpoints 6 | SCR-14 | KEEP | T14-T35 | Tab; count computed live |
| button | Copy Message Text | SCR-09 | KEEP | E089, T27 | Manual handoff |
| button | Correct Classification... | SCR-07 | KEEP | E070, T30 | Correct a classification |
| button | CSV Batch Ingestion (Active Batch #15 — 38 Invoices) | SCR-05 | KEEP | E037, T13 | Import result |
| a | Dashboard | SCR-01, SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-13, SCR-14, SCR-15, SCR-15m, SCR-16, SCR-17 | KEEP | T8, T36 | Directive nav |
| select | DD/MM/YYYY — 4 May 2026 (Confirmed) MM/DD/YYYY — 5 Apr 2026 (Overdue) Manual Entry Override... | SCR-05 | KEEP | E034, T13 | Import mapping and review |
| button | Declare Additional Channel | SCR-01 | KEEP | E029, T20 | Declare a payment account |
| button | Declare New Account | SCR-15 | KEEP | E029, T20 | Declare a payment account |
| textarea | Delivery lead confirmed SOW Addendum #2 fee cap. Issuing ₹ 50,000 credit note authorized. | SCR-08 | OMIT | - | Sample content, not a control |
| button | Discard Batch #15 | SCR-05 | KEEP | E036, T13 | Discard an import |
| button | Discard Changes | SCR-13 | KEEP | T8 | Generic control |
| button | Dismiss informational | SCR-03 | KEEP | FR-028, T27 | Bulk dismiss |
| button | Disputes & Audit 1 | SCR-14 | KEEP | T14-T35 | Tab; count computed live |
| a | Disputes & Blockers | SCR-01, SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-13, SCR-14, SCR-15, SCR-15m, SCR-16, SCR-17 | KEEP | T8, T36 | Directive nav |
| button | Download Validation Error Report (.csv) | SCR-05 | KEEP | E037, T13 | Import result |
| button | Drafts awaiting approval 3 | SCR-09 | KEEP | T14-T35 | Tab; count computed live |
| button | Drop Feed File | SCR-16 | KEEP | E053, T20 | Statement import |
| button | Due Date | SCR-03 | KEEP | E047, T14 | Server-ordered column header |
| button | Edit | SCR-05 | KEEP | T8 | Generic control |
| button | Edit Draft Rules | SCR-16 | OMIT | - | UXR-12: UI lists only what exists, no connect controls for planned integrations |
| button | Endpoint Settings | SCR-15 | OMIT | - | UXR-12: UI lists only what exists, no connect controls for planned integrations |
| button | Export Audit CSV | SCR-14 | KEEP | E099, T35 | Audit filter |
| button | Export Ingestion Schema & Logs | SCR-16 | OMIT | - | UXR-12: UI lists only what exists, no connect controls for planned integrations |
| button | Export JSON Schema with Signatures 4.1 MB | SCR-13 | CHANGE | E102, T36 | Drop 'with signatures'; no signing |
| button | Export Ledger Matrix | SCR-15m | OMIT | - | No such report in the PRD |
| button | Export Signed Log (.csv / .json) | SCR-12 | CHANGE | E100, T35 | Drop 'signed'; the export is not cryptographically signed |
| button | Export Signed SHA-256 Ledger (CSV) 2.8 MB | SCR-13 | CHANGE | E100, T35 | Drop 'signed'; the export is not cryptographically signed |
| button | Export Snapshot | SCR-13 | KEEP | E102, T36 | Export |
| button | Extend Reminder Hold (+48h) | SCR-07 | OMIT | - | No hold extension; snooze rules govern (E074) |
| button | Filter | SCR-14 | KEEP | E042, T14 | List filter |
| button | Filter Actor / Event | SCR-12 | KEEP | E099, T35 | Audit filter |
| text | Filter counter-party, invoice, tags... | SCR-09 | KEEP | E042, T14 | List filter |
| text | Filter event hash, actor, ID... | SCR-12 | KEEP | E099, T35 | Audit filter |
| text | Filter events, customer, invoice ref, hash or policy rule... | SCR-17 | KEEP | E099, T35 | Audit filter over real fields; no hash-based search claim |
| button | Filter Invariants | SCR-08 | CHANGE | E099, T35 | Plain filter wording; no 'invariants' claim |
| text | Filter invoices... | SCR-14 | KEEP | E042, T14 | List filter |
| text | Filter reason, client, reference... | SCR-03 | KEEP | E042, T14 | List filter |
| text | Filter rows... | SCR-05 | KEEP | E034, T13 | Import mapping and review |
| button | Flag New Blocker | SCR-08 | KEEP | E078, T26 | Open a dispute |
| a | Follow-ups | SCR-01, SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-13, SCR-14, SCR-15, SCR-15m, SCR-16, SCR-17 | KEEP | T8, T36 | Directive nav |
| button | Follow-ups & Drafts | SCR-04 | KEEP | T14-T35 | Tab; count computed live |
| button | Formal Notice | SCR-09 | CHANGE | E086, T24 | Firm tone with no legal threat (TS-027) |
| button | Friendly Partner | SCR-09 | KEEP | E017, T27 | Policy stepper and defaults |
| text | From: 29 Oct 2026 | SCR-15 | KEEP | E054, T20 | Attestation; sample values dropped |
| a | Go to Reconciliation | SCR-04 | KEEP | E055, T20 | Link into reconciliation |
| select | HDFC Bank — Corporate Current Account (•••• 9012) — Primary Inward [INR] Standard Chartered — FX Settlement (•••• 4421) [USD] ICICI Bank — Client Security Escrow (•••• 1189) [INR] | SCR-15m | KEEP | E029, T20 | Declare a payment account |
| select | HDFC Bank — Current (•••• 9012) ICICI Bank — Wire (•••• 4410) Axis Bank — Escrow (•••• 7731) | SCR-15 | KEEP | E029, T20 | Declare a payment account |
| button | History & Audit | SCR-04 | KEEP | T14-T35 | Tab; count computed live |
| a | Import & Review | SCR-05, SCR-08, SCR-09, SCR-10, SCR-12, SCR-14 | CHANGE | T8, T36 | Directive nav label governs |
| button | Import Batches (14) | SCR-15 | OMIT | - | No batch list endpoint in the catalogue; no P0 requirement |
| button | Import Feed | SCR-06 | KEEP | E053, T20 | Statement import |
| button | Import invoices | SCR-03 | KEEP | E037, T13 | Import result |
| button | Import Statement | SCR-15 | KEEP | E053, T20 | Statement import |
| button | Import Statement Feed | SCR-15 | KEEP | E053, T20 | Statement import |
| button | Imports 14 batches | SCR-06 | OMIT | - | No batch list endpoint in the catalogue; no P0 requirement |
| button | In Progress 3 | SCR-17 | KEEP | T14-T35 | Tab; count computed live |
| select | Indian Grouping (₹12,34,567.89) Standard International (1,234,567.89) Continental European (1.234.567,89) | SCR-13 | KEEP | E012, T36 | Workspace profile; sample value dropped |
| select | INR (₹) — Indian Rupee USD ($) — United States Dollar EUR (€) — Euro GBP (£) — British Pound | SCR-13 | KEEP | E012, T36 | Workspace profile; sample value dropped |
| button | Inspect AI Payload ("What was sent?") | SCR-07 | KEEP | E105, T36 | Payload inspector |
| button | Inspect Evidence Why | SCR-04 | KEEP | E101, T27 | Why this decision |
| button | Inspect File | SCR-15m | KEEP | E037, T13 | Import result |
| button | Inspect Gap | SCR-16 | KEEP | E032, T20 | Coverage gap |
| a | Inspect Rule Config | SCR-14 | KEEP | E017, T27 | Policy stepper and defaults |
| a | Integrations | SCR-01, SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-13, SCR-14, SCR-15, SCR-15m, SCR-16, SCR-17 | KEEP | T8, T36 | Directive nav |
| button | Invite Delegate | SCR-13 | KEEP | E014, T36 | Invite |
| button | Invoices & Receivables 3 | SCR-14 | KEEP | T14-T35 | Tab; count computed live |
| button | Link Another Invoice | SCR-07 | KEEP | E066, T26 | Message association |
| button | Log Attestation / Ingest Feed | SCR-17 | KEEP | E054, T20 | Attestation; sample values dropped |
| button | Log Bank Statement Attestation | SCR-15m | KEEP | E054, T20 | Attestation; sample values dropped |
| a | Manage | SCR-02 | KEEP | E047, T14 | Queue link |
| button | Manually Match Staging Transaction | SCR-14 | KEEP | E055, T20 | Link into reconciliation |
| textarea | Manually reviewed RTGS/NEFT inward transactions. No credit observed matching Example Client Ltd (₹2,50,000) or Vortex Tech. Statement download pending IT clearance. | SCR-15m | KEEP | E054, T20 | Attestation; sample values dropped |
| button | Match in Reconciliation Queue | SCR-07 | KEEP | E055, T20 | Link into reconciliation |
| button | Match review 5 | SCR-06 | KEEP | T14-T35 | Tab; count computed live |
| button | Members & Permissions | SCR-13 | KEEP | E014, T36 | Invite |
| button | Needs attention 12 | SCR-03 | KEEP | T14-T35 | Tab; count computed live |
| button | Needs Review 5 | SCR-17 | KEEP | T14-T35 | Tab; count computed live |
| button | Neutral (Recommended) | SCR-09 | KEEP | E017, T27 | Policy stepper and defaults |
| button | Next | SCR-05, SCR-12 | KEEP | T8 | Generic control |
| button | Not a Match | SCR-06 | KEEP | E058, T20 | Reject a match |
| button | Open case | SCR-02, SCR-03 | KEEP | E077, T26 | Open a dispute |
| button | Open Dispute Workspace | SCR-17 | KEEP | E077, T26 | Open a dispute |
| button | Open in Email Client | SCR-09 | KEEP | E089, T27 | Manual handoff |
| a | Open the queue | SCR-02 | KEEP | E047, T14 | Queue link |
| button | Overview | SCR-04 | KEEP | T8 | Generic control |
| button | Parser Settings | SCR-05 | OMIT | - | No parser configuration; the mapping step covers this |
| button | Pause All Client Follow-ups | SCR-14 | CHANGE | E019, T27 | Workspace-level pause only (A8, OD-07) |
| a | Payment Accounts & Coverage | SCR-01, SCR-13, SCR-15m, SCR-16, SCR-17 | CHANGE | T8, T36 | Directive nav label governs |
| button | Payment History 2 | SCR-14 | KEEP | T14-T35 | Tab; count computed live |
| text | Payment reminder — Invoice INV-2035 (Kestrel Digital) | SCR-09 | KEEP | E086, T27 | Draft subject |
| button | Payment Status | SCR-03 | KEEP | E047, T14 | Server-ordered column header |
| button | Payments & Matches | SCR-04 | KEEP | T14-T35 | Tab; count computed live |
| button | PO (1) | SCR-08 | KEEP | T14-T35 | Tab; count computed live |
| button | Previous | SCR-05, SCR-12 | KEEP | T8 | Generic control |
| button | Previous: Import Invoices | SCR-01 | KEEP | T28 | Onboarding step |
| button | Re-evaluate Intent | SCR-04 | OMIT | - | No re-evaluate; the correct path is E070 |
| button | Re-run Validation | SCR-05 | KEEP | E034, T13 | Import mapping and review |
| button | Reassign Event | SCR-17 | KEEP | FR-028, T14 | Assignment |
| a | Receivables | SCR-01, SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-13, SCR-14, SCR-15, SCR-15m, SCR-16, SCR-17 | KEEP | T8, T36 | Directive nav |
| button | Recent Import Batches (14 Batches) | SCR-05 | OMIT | - | No batch list endpoint in the catalogue; no P0 requirement |
| a | Reconciliation | SCR-01, SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-13, SCR-14, SCR-15, SCR-15m, SCR-16, SCR-17 | KEEP | T8, T36 | Directive nav |
| button | Record Attestation (24h Valid) | SCR-15m | CHANGE | E054, T20 | Freshness window is the 7-day configurable default (A7), not 24h |
| button | Record Manual Payment | SCR-04 | KEEP | E049, T20 | Manual payment |
| button | Record Payment | SCR-14 | KEEP | E049, T20 | Manual payment |
| button | Record Resolution Outcome | SCR-08 | KEEP | E080, T26 | Resolve a dispute |
| button | Refresh Queue | SCR-17 | KEEP | E047, T14 | Queue link |
| button | Regenerate AI wording | SCR-09 | CHANGE | proposed-new, T31 | Endpoint gap; template wording when AI is unconfigured |
| button | Reject & Delete Draft | SCR-09 | CHANGE | E088, T27 | Reject; the draft is retained for audit, not deleted |
| button | Renew Attestation | SCR-15 | KEEP | E054, T20 | Attestation; sample values dropped |
| button | Reset | SCR-13 | KEEP | T8 | Generic control |
| button | Reset to exception order | SCR-03 | KEEP | E047, T14 | Queue link |
| button | Resolve Staging Conflict | SCR-17 | KEEP | E055, T20 | Link into reconciliation |
| button | Resolved Today 8 | SCR-17 | KEEP | T14-T35 | Tab; count computed live |
| button | Restore Policy Defaults | SCR-10 | KEEP | E017, T27 | Policy stepper and defaults |
| button | Resume Follow-ups | SCR-08 | KEEP | E082, T26 | Resume follow-ups |
| button | Review | SCR-05 | KEEP | T8 | Generic control |
| button | Review Bank Match | SCR-14, SCR-17 | KEEP | E055, T20 | Link into reconciliation |
| button | Review Bank Matches 1 Pending | SCR-04 | KEEP | E055, T20 | Link into reconciliation |
| button | Review Claim & Matches | SCR-04 | KEEP | E055, T20 | Link into reconciliation |
| button | Review commitment | SCR-03 | KEEP | E074, T26 | Snooze |
| button | Review draft | SCR-02, SCR-03 | KEEP | T27 | Link to a draft |
| button | Review in Reconciliation Workspace (SCR-06) | SCR-17 | KEEP | E055, T20 | Link into reconciliation |
| button | Review match ambiguity | SCR-03 | KEEP | E055, T20 | Link into reconciliation |
| button | Review matches | SCR-02, SCR-03 | KEEP | E055, T20 | Link into reconciliation |
| button | Review Snooze Proposal | SCR-17 | KEEP | E074, T26 | Snooze |
| button | Revoke & Disconnect Channel | SCR-16 | KEEP | E097, T33 | Disconnect |
| button | Save & Continue to Safety Policy | SCR-01 | KEEP | T28 | Onboarding step |
| button | Save Changes | SCR-13 | KEEP | T8 | Generic control |
| button | Save Changes 3 | SCR-10 | CHANGE | E012, T36 | Count computed live, not fixed |
| button | Save Profile Settings | SCR-13 | KEEP | E012, T36 | Workspace profile; sample value dropped |
| text | Search counter-parties, accounts, invoices... | SCR-01, SCR-13, SCR-15m, SCR-16, SCR-17 | KEEP | E042, T14 | Global search; wording says clients |
| text | Search counter-parties, invoices, claims... | SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-14, SCR-15 | KEEP | E042, T14 | Global search; wording says clients |
| text | Search reference, UTR, payer... | SCR-06 | KEEP | E042, T14 | Global search; wording says clients |
| button | Security & Compliance | SCR-13 | CHANGE | T36 | Rename 'Data & privacy'; no compliance claim |
| button | Select this candidate | SCR-06 | KEEP | E056, T20 | Candidate choice |
| button | Send Template: "Acknowledged & Verifying" | SCR-07 | OMIT | - | No send in P0; manual handoff only |
| button | Sent history 18 | SCR-09 | KEEP | T14-T35 | Tab; count computed live |
| button | Skip for now (Synthetic Mode) | SCR-01 | KEEP | T28 | Onboarding step |
| button | Snooze Reminder | SCR-09 | KEEP | E074, T26 | Snooze |
| button | Snoozed & committed 2 | SCR-09 | KEEP | T14-T35 | Tab; count computed live |
| button | SOW (1) | SCR-08 | KEEP | T14-T35 | Tab; count computed live |
| button | Split / Partial Allocation... | SCR-06 | KEEP | E059, T20 | Allocation |
| button | Stage P1 Sandbox | SCR-16 | OMIT | - | UXR-12: UI lists only what exists, no connect controls for planned integrations |
| button | Submit Attestation (Valid 24h) | SCR-15 | CHANGE | E054, T20 | Freshness window is the 7-day configurable default (A7), not 24h |
| button | Talk to Ops | SCR-01 | OMIT | - | No support channel in scope |
| button | Tier 1 | SCR-09 | KEEP | E017, T27 | Policy stepper and defaults |
| button | Tier 2 | SCR-09 | KEEP | E017, T27 | Policy stepper and defaults |
| text | To: 03 Nov 2026 | SCR-15 | KEEP | E054, T20 | Attestation; sample values dropped |
| button | Trigger Manual Statement Ingest | SCR-04 | KEEP | E053, T20 | Statement import |
| text | Type 'DELETE-WORKSPACE-T9844' | SCR-13 | KEEP | E104, T36 | Workspace deletion |
| button | Unmatched 3 | SCR-06 | KEEP | T14-T35 | Tab; count computed live |
| button | Upload New Statement | SCR-15 | KEEP | E053, T20 | Statement import |
| button | Upload Statement | SCR-15 | KEEP | E053, T20 | Statement import |
| button | Upload Statement (.csv / .mt940) | SCR-15 | CHANGE | E053, T20 | CSV only |
| button | Upload Statement (.csv) | SCR-16 | KEEP | E053, T20 | Statement import |
| button | Urgency | SCR-09 | KEEP | E047, T14 | Server-ordered column header |
| button | Verify VPA | SCR-15 | OMIT | - | No VPA verification provider |
| a | View All 14 Batches → | SCR-15 | OMIT | - | No batch list endpoint in the catalogue; no P0 requirement |
| a | View all decisions (7) → | SCR-02 | KEEP | E101, T27 | Why this decision |
| button | View Bank Claim Ledger | SCR-09 | KEEP | E055, T20 | Link into reconciliation |
| button | View Docs | SCR-16 | OMIT | - | UXR-12: UI lists only what exists, no connect controls for planned integrations |
| button | View Firewall Rules | SCR-13 | OMIT | - | No firewall feature; implies a security control that does not exist |
| a | View Full Audit Chain | SCR-10 | CHANGE | E099, T35 | Plain link; no integrity claim |
| a | View Full Chronology (6) | SCR-14 | KEEP | E065, T26 | Conversation link |
| a | View Full Conversation Thread (6 previous messages) | SCR-04 | KEEP | E065, T26 | Conversation link |
| a | View log | SCR-05 | KEEP | E037, T13 | Import result |
| button | View Policy Decision 'Why?' | SCR-07 | KEEP | E101, T27 | Why this decision |
| button | View Raw MIME | SCR-07 | OMIT | - | No raw MIME store |
| button | View Receipt | SCR-14 | KEEP | E050, T20 | Payment detail |
| button | View Schemas | SCR-16 | OMIT | - | UXR-12: UI lists only what exists, no connect controls for planned integrations |
| button | View Transactions | SCR-15 | KEEP | E055, T20 | Link into reconciliation |
| button | Waiting for customer 4 | SCR-09 | KEEP | T14-T35 | Tab; count computed live |
| button | Workspace Profile & Exports | SCR-13 | KEEP | E014, T36 | Invite |
| a | Workspace Settings | SCR-01, SCR-02, SCR-03, SCR-04, SCR-05, SCR-06, SCR-07, SCR-08, SCR-09, SCR-10, SCR-12, SCR-13, SCR-14, SCR-15, SCR-15m, SCR-16, SCR-17 | KEEP | T8, T36 | Directive nav |
