# CollectIQ — Revenue Model & Business Strategy v1.0

| Metadata | |
|---|---|
| Document ID | COLLECTIQ-BIZ-001 |
| Version / status | 1.0 — **draft for founder review; nothing here is approved** |
| Date | 3 November 2026 |
| Product | CollectIQ — Payment Relationship Assistant (B2B SaaS, receivables operations) |
| Foundational source | *CollectIQ Overall Product Concept and Solution Plan* ("Foundation", cited F§n) |
| Related documents | PPD v0.1, Problem Statement & Market Research v0.1 ("MR", cited MR[n] for its reference numbers), PRD v0.1, SAD v0.1, UX Design v0.1, Technical Specification v1.0 (TSD), Open Decisions, Implementation Roadmap |
| Currency / basis | INR, excluding GST; USD only where a source quotes it (converted at an assumed ₹88/$) |
| Author role | Business strategy and financial modelling support; not legal, tax or investment advice |

**Evidence labels.** **[SRC]** verified in a CollectIQ source document; **[EXT]** external research with citation (section 24) — vendor, directory or secondary sources are flagged because they can be biased or stale; **[REC]** strategic recommendation (inference, not evidence); **[ASM]** financial assumption (illustrative, replace with measured values); **[HYP]** testable hypothesis; **[DEC]** decision requiring founder approval; **[VER]** verify before relying.

## Table of contents
1. Source review and gaps · 2. Executive business strategy · 3. Business problem and economic value · 4. ICP and segmentation · 5. Market opportunity and sizing · 6. Competitive landscape and positioning · 7. Revenue model · 8. Pricing and packaging · 9. Unit economics and financial model · 10. Go-to-market · 11. Acquisition and distribution · 12. Product-led growth and retention · 13. Operations and support · 14. Cost structure · 15. Trust, privacy and risk · 16. Strategic product prioritization · 17. Partnerships · 18. Expansion · 19. KPI framework · 20. 12-month roadmap · 21. SWOT and risk register · 22. Final recommendations · 23. Decision register and action checklist · 24. Source references

---

## 1. Source Review and Gaps

**Reviewed (in the CollectIQ project):** Foundation PDF; PPD v0.1; Market Research v0.1; PRD v0.1; SAD v0.1; UX Design v0.1; TSD v1.0 with OpenAPI, traceability CSV, Open Decisions and Roadmap. **Not available:** `DESIGN.md`; any customer interview, pilot, revenue, cost, cap-table or competitor-trial data; a separate "Product and Business Requirements" document (PRD v0.1 is treated as that source); any production code.

**Current product stage [SRC].** Specified, not built: no repository, no running software, no customers, no revenue, no partnerships, no funding. Screens in the UX document and endpoints in the OpenAPI file are *designs*, not functionality. Integrations (Gmail send-only, PayPal sandbox, monitoring) are P1 and unverified in operation.

**Team and capital assumption [ASM].** MR §10 planned research for a "three-person student team". This document assumes a **1–3 person founding team with no external funding**; if wrong, sections 13, 14 and 20 change.

**Source conflicts and gaps recorded**

| ID | Conflict / gap | Resolution proposed |
|---|---|---|
| BC-1 | Foundation Decision 1 (India-first vs global-first) is open (MR §16.2, PPD OPEN-01); this brief says "India-first, INR" | Treat India-first as the working assumption pending **[DEC] BD-01** |
| BC-2 | Foundation MVP includes reply ingestion; Gmail restricted scopes may need an annual third-party security assessment (§9.6, §15) | Sell P0 first (paste/.eml reply capture); gate mailbox monitoring on economics **[DEC] BD-06** |
| BC-3 | Foundation price hypothesis ₹999–2,499/month sits at/above Zoho Books Standard (MR §16.2) | Keep hypothesis; test in paid pilots **[DEC] BD-04** |
| BC-4 | MR says "reply interpretation" is commercial elsewhere, weakening it as a moat | Position on payment-evidence-first workflow (§6) |
| BC-5 | No cost data exists; model inputs are placeholders | All numbers labelled [ASM]; section 9 shows how to replace them |

---

## 2. Executive Business Strategy

**What CollectIQ is.** A privacy-first receivables-operations copilot: it imports invoices, reconciles payment evidence (statements, PayPal exports, manual UPI/cash entries) into invoices, interprets customer replies into reviewed proposals, tracks commitments and disputes, and prepares follow-ups that a human approves. Deterministic rules, not the AI, decide what may happen; "no payment event" never means "unpaid"; a customer claim never means "paid" **[SRC: Foundation principles, PRD, TSD]**.

**Problem and why businesses might pay [HYP].** Owners and finance staff of small B2B firms spend time working out *whether an invoice is truly paid* across fragmented channels, and risk embarrassing reminders to customers who paid, disputed or promised a date. Measured late-payment problems are real **[EXT, MR §3]**, but **the CollectIQ-specific pain and willingness to pay are unmeasured [SRC: MR §0.3]**.

**Primary segment [REC].** Small B2B service firms (agencies, studios, consultancies; ~5–50 staff) with ≥ ~30 invoices/month, ≥ 2 payment channels and Gmail/Outlook email — MR's ICP v0 — with *bookkeepers* as a channel to test, not the first customer.

**Revenue model [REC].** Flat-tier monthly/annual subscription per workspace, priced in INR, with transparent fair-use allowances for AI interpretation; no success fees, no payment-processing revenue.

**Market entry [REC].** Validate with 15–20 interviews and a concierge pilot before further build; then 3–5 design partners, a paid controlled pilot, and a limited commercial launch. First channels to test: founder-led outreach into agency/consultancy networks, bookkeeper referrals, and educational content tied to receivables checklists.

**Differentiation [REC].** The defensible position is the *combination*: payment evidence from any rail + explicit uncertain state + conversational reply interpretation + deterministic policy + human approval + auditability, at a price/onboarding fit for small firms. Each element alone is replicable by incumbents **[EXT/SRC: MR §4.6, §5.2]**.

**Most significant risks.** (1) The pain or willingness to pay is lower than hoped; (2) price ceiling set by ledger tools; (3) trust and privacy barriers; (4) Gmail restricted-scope assessment cost; (5) incumbents add equivalent features; (6) reconciliation or AI errors destroying trust; (7) very small revenue relative to fixed cost at modest scale (§9).

**Honest headline from the model [ASM].** At the proposed prices a 12-month plan reaches roughly **₹1.3 lakh to ₹10.6 lakh** annualised run-rate across scenarios and needs **55–87** paying accounts to cover steady-state costs; the product is only commercially viable if cost-to-serve stays low and retention is high, and it is **not** viable if monitored-mailbox access forces a restricted-scope assessment too early (§9.6).

**Next 12 months, in order [REC].** (1) Months 1–3 problem validation and willingness-to-pay tests; (2) months 3–6 build P0 against validated needs and run design-partner sessions on synthetic/protected data; (3) months 6–9 controlled paid pilot; (4) months 9–12 limited commercial launch only if evidence gates in §22.5 pass.

**Current stage vs commercial vision.** *Stage:* validated-by-desk-research concept, designed but unbuilt. *Vision (long-term, unproven):* the trusted evidence-and-follow-up layer for small-business receivables, sold directly and through bookkeepers.

---

## 3. Business Problem and Economic Value Proposition

No savings are quantified; each benefit needs evidence listed in the last-but-one column. "User" = target user; "Limits" = where CollectIQ may not help.

| # | Problem | User | Current workflow | Cost/consequence (qualitative) | CollectIQ intervention | Expected benefit [HYP] | Evidence needed | Limits |
|---|---|---|---|---|---|---|---|---|
| P1 | Manual matching of payments to invoices | Owner / bookkeeper | Bank app + spreadsheet + invoice list | Time; late or missed recording | Statement import, deterministic proposals, human confirm | Fewer hours; fewer mis-recorded payments | Time diaries; error counts (MR §10.7) | Poor references/formats; low volume |
| P2 | Fragmented evidence (bank, PayPal, UPI, cash) | Owner | Check several places | Uncertainty about paid status | Payment-method-agnostic evidence model; coverage tracking | Clearer "what do we know" | Share of invoices with unclear status | Only evidence the user imports; no live bank access |
| P3 | Customer says "we paid" | Owner/ops | Search statements; reply | Wrong reminders or delays | Claim ≠ payment; verification case | Fewer unnecessary reminders | Count of reminders after payment | Cannot verify without evidence |
| P4 | Repeated manual follow-ups | Owner/AR person | Email from scratch | Time; tone risk | Gate-checked drafts, templates, human approval | Faster, safer follow-up | Minutes per follow-up | MVP does not auto-send |
| P5 | Disputes and blockers | Owner/ops | Email threads | Reminders sent into disputes | Dispute/blocker cases suppress reminders | Fewer relationship-damaging contacts | Incidents of reminders during disputes | Does not resolve disputes |
| P6 | Unknown evidence freshness | Owner | Assumed | False "unpaid" | Coverage and freshness status; attestation | Safer eligibility | % reminders blocked correctly | Needs regular imports |
| P7 | Duplicate imports / wrong allocations | Finance | Spreadsheet edits | Wrong balances | Idempotent import, signed ledger, reversals | Fewer ledger errors | Error incidence before/after | Requires adoption discipline |
| P8 | Relationship damage from bad follow-ups | Owner | Gut feel | Lost customers (unquantified) | Sensitivity settings, linter, approval | Fewer complaints | Complaint/opt-out counts | Tone is subjective |
| P9 | Audit-trail burden | Finance/bookkeeper | Reconstruct from email | Time; disputes | Audit history, why-view | Faster explanation | Time to reconstruct a case | Not tamper-proof; no compliance claim |

**Where value may be absent [SRC: MR §4.4, §11].** Low-volume single-channel firms; firms fully inside platforms that already pause reminders on bank evidence; firms whose contracts forbid third-party processing.

---

## 4. Ideal Customer Profile and Segmentation

Segmentation by *operational need* (exceptions, channels, reply volume), using MR's analysis plus the brief's list. All "willingness to pay" and "sales cycle" cells are **[HYP]** until interviews.

| Segment | Invoice volume / complexity | Follow-up frequency | Accounting environment | Decision structure | Integration need | Sales cycle | Data sensitivity | Retention outlook | Fit with P0 |
|---|---|---|---|---|---|---|---|---|---|
| **Small agencies/studios/consultancies (ICP)** | Moderate; mixed rails, partials | Frequent | Zoho/QuickBooks/Xero/Tally or sheets [MR §2] | Owner decides, ops/bookkeeper uses | CSV + email now; ledger later | Short–medium | Medium | Medium if exceptions recur | **Best** |
| B2B services, larger (20–50 staff) | Lower count, higher value | Medium; disputes costly | As above + AP portals | Owner + finance | CSV + email | Medium | Medium–high | Medium | Good |
| Distributors/wholesalers | High volume, many small customers | High | Tally/ERP common [VER] | Owner + accountant | ERP sync likely essential | Long | Medium | Unknown | Poor in MVP |
| Small manufacturers | Medium; PO-driven disputes | Medium | ERP/Tally [VER] | Owner/finance | ERP sync | Long | High | Unknown | Poor |
| Recurring-invoice businesses | High, standardised | Low–medium | Billing apps with auto-collect | Owner | Ledger sync | Medium | Medium | Partly automated already | Partial |
| Finance/AR teams (mid-market) | High | Very high | ERP/AR suites | Committee | Deep | Long | High | High | Out of scope |
| **Bookkeepers/outsourced finance** | Aggregate across clients | High | Per-client tools | Firm principal | Multi-client tenancy (not MVP, PPD FUT-11) | Medium | High | Potentially high | Channel candidate, later |

**Recommended initial ICP [REC] (= MR ICP v0, unchanged):** B2B services firm, ~5–50 staff, ≥ ~30 invoices/month, ≥ 2 payment channels or monthly partial/reference mismatches, email-centric, a named person who reconciles and chases manually, comfortable exporting bank CSVs. **Why:** narrowest group where the specific pain can be measured; MVP scope (CSV + manual + paste replies) fits; avoids ledger integration and multi-client tenancy.

| Role | Who (ICP) | Notes |
|---|---|---|
| Buyer | Founder/managing director | Pays; cares about cash visibility and customer relationships |
| Daily user | Ops lead, accountant, part-time bookkeeper | Imports, confirms matches, approves drafts |
| Internal champion | The person who currently reconciles manually | Needs demonstrable time/error reduction |
| Technical evaluator | Usually the owner; IT rarely exists | Cares about mailbox/bank-data access |
| Likely blockers | External accountant who prefers existing tools; customer contracts; owner fear of wrong emails | Address via trust design (§15) |

*Requires interviews:* every volume, channel and decision-structure claim above.

---

## 5. Market Opportunity and Sizing

**Position [SRC: MR §8.1].** No credible TAM/SAM/SOM figure exists; none is asserted here. Below: definitions, formulas, inputs, sources and an **assumption-based scenario** (placeholders, not data).

| Layer | Definition | Formula | Status |
|---|---|---|---|
| TAM | All businesses issuing B2B invoices on credit in the target geography × annual price | N_firms × p_B2B × ARPA×12 | N_firms unknown. Udyam counts (over 7.9 crore registered, Mar 2026, incl. informal micro units) are an *upper bound on registered units only* [EXT: MR[11][12]] |
| SAM | Firms that fit ICP and MVP constraints | N_firms × p_B2B × p_volume × p_multichannel × p_provider | p-values unknown |
| SOM (12–24 months) | What the team can win | **Capacity-bound**, not share-of-market: qualified leads/month × funnel conversion × retention | Funnel in §9.5 |

**Required inputs and where to get them:** N_firms (GST/MCA/Udyam datasets, bookkeeper-network surveys [VER]); p_B2B, p_volume, p_multichannel (interviews, survey of 100+ firms); p_provider (mailbox mix, MR R-3); willingness to pay (paid pilots).

**Illustrative scenario (placeholders) — serviceable accounts per 100,000 firms in a starting universe**

| Illustrative set (placeholders) | p_B2B | p_volume | p_multichannel | p_provider | Serviceable accounts per 100,000 firms | Annual revenue if all served (at base ARPA) | Firms in universe needed for 500 serviceable accounts |
|---|---|---|---|---|---|---|---|
| Low | 0.3 | 0.08 | 0.4 | 0.6 | 576 | ₹93.83 lakh | 86,806 |
| Mid | 0.4 | 0.15 | 0.5 | 0.6 | 1,800 | ₹293.23 lakh | 27,778 |
| High | 0.5 | 0.2 | 0.6 | 0.8 | 4,800 | ₹781.95 lakh | 10,417 |

Base-scenario ARPA used: ₹1,358/month. 500 paying accounts ≈ ₹81.45 lakh ARR; ₹1 crore ARR ≈ 614 accounts at that ARPA.


*Reading [REC]:* depends entirely on unmeasured percentages; it shows **structure and sensitivity**, not market size. Since ARPA is small (≈ ₹1,400/month), hundreds of accounts are needed for ~₹1 crore ARR (consistent with MR §8.4), so the early plan is limited by *reachability and cost-to-serve*, not by a market-size number.

**Initial geography/industry [REC].** India; agencies, studios, consultancies. **Expansion [HYP].** Other South-Asian/English-speaking markets only after retention and unit economics hold (§18). **Trends [EXT: MR §3]:** documented payment delays and policy attention in India (Samadhaan portal data; MSME payment-term rules); growing use of AI in small-business operations — each context, not proof of demand for CollectIQ.

---

## 6. Competitive Landscape and Positioning

Evidence base: MR §4 (desk research, 3 Nov 2026, **no hands-on trials**) plus refreshed pricing [N1][N2]. "Not found" means not found in public sources, not "does not exist". Direct competitors are named only where documented.

| Category | Examples (documented) | Target | Strength vs CollectIQ | Gap / limitation (documented or hypothesised) |
|---|---|---|---|---|
| Accounting platforms | Zoho Books, QuickBooks, Xero, FreshBooks [MR §4.1] | Small businesses | Already hold invoices, bank feeds, reminders; Zoho has Expected Payment Date and UPI status updates [MR[23][25]] | Reminders may not reflect payments recorded outside the ledger [MR[21]][HYP]; no reply-interpretation as per MR evidence |
| AR automation | Chaser, Upflow, Tesorio, Kolleno, Billtrust [MR §4.3] | SMB→enterprise finance teams | Reply-intent AI, promise tracking, workflows [MR[32][35][37][38][39]] | Priced for developed markets (Chaser Compact $259/mo, Core $779, Complete $1,169 on monthly billing, revenue-banded [N2]); Indian-rail reconciliation **not found** |
| Reconciliation software | Bank-feed matching in ledgers [MR §4.1] | Accountants | Mature matching | Ledger-centric; not follow-up aware |
| Collections/communication | Reminder modules, SMS/WhatsApp in Indian GST apps [MR[40][41]] | Micro/small | Cheap, familiar | Reminder-first; payment verification depth unknown |
| AI finance assistants | General LLM tools | Anyone | Flexible | No ledger of evidence, no policy/audit [HYP] |
| Spreadsheets + email | — | Small firms | Free, flexible | Manual; error-prone [HYP] |

**Price benchmarks [EXT].** Zoho Books India (vendor list via tracker checked 26 Oct 2026, excl. tax): Standard ₹749/month billed yearly or ₹899 monthly; Professional ₹1,499/₹1,799; Premium ₹2,999/₹3,599; a Free tier exists [N1] (third-party pages show varying figures — **conflict**, so treat as indicative [VER]). Chaser: Compact **$259**, Core **$779**, Complete **$1,169** per month, revenue bands <$5m/<$13m/<$120m [N2]. Upflow pricing sources conflict [MR[46][47]].

**Competitive positioning matrix [REC/HYP].** (✔ documented, ◐ partial/hypothesised, ✖ not found)

| Capability | CollectIQ (target) | Ledger platforms | AR automation tools |
|---|---|---|---|
| Payment evidence from any rail incl. CSV/manual UPI/cash | ◐ (design) | ◐ bank feeds | ✖ in India (not found) |
| Explicit "uncertain" state suppressing reminders | ◐ (design) | ◐ unknown | ◐ unknown |
| Reply interpretation | ◐ (design) | ✖ | ✔ |
| Human approval of every customer message | ✔ (design, MVP) | ◐ | ◐ |
| Audit trail | ◐ (design; not tamper-proof) | ◐ | ◐ |
| Price/onboarding fit for 5–50-person firm | ◐ hypothesis | ✔ | ✖ |

**Positioning statement [REC].** *For small B2B service firms that reconcile payments and chase invoices by hand across several channels, CollectIQ is a payment-relationship assistant that works out what is actually known about each invoice and prepares the next appropriate follow-up for you to approve. Unlike reminder tools that assume the ledger is right, CollectIQ treats uncertainty as a first-class state and never sends or marks paid on its own.*

**Value proposition:** know what is paid, what is uncertain and what to do next — without wrong reminders. **Messaging pillars [REC]:** (1) Evidence before reminders; (2) You approve every message; (3) Works with how you actually get paid (bank, PayPal, UPI, cash); (4) Explains every recommendation; (5) Your data stays minimal and inspectable.

**Defensibility [REC/HYP].** Weak individually: reply AI (already commercial), reminders (commodity). Potential: accumulated per-customer matching aliases and evidence history; workflow trust and audit; accountant relationships; India-specific statement formats. **Where competitors may be stronger:** distribution, integrations, brand, price (free/cheap tiers), the ability to ship an overlapping feature at no extra price **[SRC: MR §4.6]**.

**Claim discipline.** Do not state "first", "only", "best" or accuracy claims without evidence.

---

## 7. Revenue Model

| Model | Fit | Pros | Cons | Verdict [REC] |
|---|---|---|---|---|
| Subscription SaaS (flat tiers) | High | Predictable; simple | Price ceiling vs ledgers | **Primary** |
| Tiers by operational need | High | Aligns value (accounts, users, AI allowance) | Limits must not block essential workflows | **Primary mechanism** |
| Usage-based | Medium | Matches AI cost | Unpredictable bills; erodes trust | Only as soft fair-use caps; metered overage deferred |
| Per workspace/entity | High | Matches data model (one workspace = one business) | Multi-entity not built | Per workspace now |
| Extra seats/entities | Medium | Expansion path | Needs multi-entity (P2) | Later |
| Premium integrations | Medium | Pays for maintenance | Integrations unproven | After validation |
| Governance/audit tier | Medium | Higher WTP possible | Unvalidated | Professional tier feature |
| Partner/accountant-led | Potentially high | Lower CAC | Needs multi-client tenancy; channel conflict | Test later (§17) |
| % of recovered payments | — | — | Misaligned incentives; legal/regulatory risk; conflicts with "human in control" | **Rejected** without legal review |
| Payment processing/fintech revenue | — | — | Changes the product into a regulated-adjacent financial product | **Rejected** (not in Foundation) |

**Recommendation [DEC BD-03]:** subscription per workspace, three public tiers, monthly and annual billing, GST added where applicable **[VER]**, no success fees, no processing revenue, no hard stops that block completing a reconciliation or dispute workflow.

---

## 8. Pricing and Packaging Strategy

All tiers and names are **proposals**. Price basis labels: **FH** provisional founder hypothesis (Foundation ₹999–2,499 range), **CI** competitor-informed, **CB** cost-based. No price is research-backed yet.

| | Starter | Growth | Professional | Business (not offered yet) |
|---|---|---|---|---|
| Target | Small firm, 1 channel mix, low volume | ICP core | Higher volume, stricter control needs | Bookkeeper/multi-entity (needs P2 features) |
| Monthly price (excl. GST) | **₹999** | **₹1,799** | **₹2,499** | Not priced |
| Annual (2 months free) | ₹9,990 | ₹17,990 | ₹24,990 | — |
| Price basis | FH+CI (above Zoho Standard ₹749–899 [N1]) | FH+CI (≈ Zoho Professional ₹1,499–1,799) | FH (top of Foundation range; below Zoho Premium ₹2,999–3,599) | — |
| Users | 2 | 5 | 10 | — |
| Active invoices | up to 150 | up to 500 | up to 1,500 | — |
| Payment accounts | 3 | 8 | 15 | — |
| Imports/reconciliation | Full (CSV, manual) | Full | Full | — |
| AI interpretation allowance (messages/month) | 40 | 150 | 400 | — |
| Integrations | Paste/.eml; Gmail send-only when available (P1) | + PayPal (P1) | + monitoring if approved (§15) | — |
| Audit/reporting | Audit view | Audit view + export | Audit export, extended retention [REC] | — |
| Support | Email, business hours | Email + onboarding call | Priority email + onboarding | — |
| Upgrade trigger | Invoice/AI allowance, more accounts | Need audit export, higher volume | — | — |
| Main cost drivers | Support, infra | AI, support | AI, support | — |
| Contribution margin (model) | see below | see below | see below | — |

Limits are **soft fair-use thresholds** for cost control; reaching one prompts an upgrade conversation, never blocks recording a payment, resolving a dispute, exporting data or deleting the workspace **[REC]**. Free tier: none proposed (support cost, trust risk, and Zoho already offers free accounting [N1]); instead a 14-day or concierge pilot **[DEC BD-05]**.

**Unit economics per tier [ASM]**

| Tier (hypothesis) | List ₹/mo | Effective ₹/mo* | AI cost | Infra | Email/notify | Support (notional) | Pay fee | Variable cost | Contribution ₹/mo | CM % |
|---|---|---|---|---|---|---|---|---|---|---|
| Starter | 999 | 949 | 48 | 60 | 25 | 100 | 24 | 257 | 692 | 73% |
| Growth | 1,799 | 1,709 | 180 | 60 | 25 | 200 | 43 | 508 | 1,201 | 70% |
| Professional | 2,499 | 2,374 | 480 | 60 | 25 | 350 | 59 | 974 | 1,400 | 59% |

*Effective = list × (1 − 30% on annual plan × 16.7% discount). AI cost per interpreted message = ((2000 in × ₹250 + 300 out × ₹1000) ÷ 10⁶) × 1.5 overhead = ₹1.20; allowances {'Starter': 40, 'Growth': 150, 'Professional': 400}. Token prices are **illustrative placeholders**, not any provider's price.


**Observation:** the Professional tier's margin is dominated by the AI allowance and support assumptions; if either is over-estimated the tier is healthier; if under-estimated it may need a lower allowance or higher price.

**Willingness-to-pay validation [REC].** (1) Ask what interviewees *currently pay* for adjacent tools (MR §10.3 Q12), not hypothetical price. (2) Van Westendorp-style questions only after behaviour questions, with a sample ≥ 20 qualified firms, treated as directional. (3) Paid pilot at stated price with a refund option; track conversion to paid at ₹999 / ₹1,799 / ₹2,499 across randomised offers. (4) Landing-page price test (MR §10.5). (5) Treat refusals at ≥ ₹999 as a stop signal (MR risk 12). **Decision rule:** do not finalise pricing until ≥ 10 paid-pilot decisions at stated prices.

## 9. Unit Economics and Financial Model

**Status: illustrative [ASM].** Nothing below is a forecast, a historical result or a guarantee. Every input is a placeholder to be replaced with measured values; the model code lives in the generator used to produce this document and every formula is reproduced so it can be rebuilt in a spreadsheet.

### 9.1 Definitions and formulas

| Metric | Formula |
|---|---|
| MRR | Σ over active accounts of effective monthly price |
| ARR | MRR × 12 (run-rate; not recognised revenue) |
| ARPA | MRR ÷ active paying accounts |
| Effective price | list × (1 − annual_share × annual_discount) |
| Variable cost / account | AI + infra + email + support + payment_fee × price |
| AI cost / account | messages × [(tok_in × price_in + tok_out × price_out) ÷ 10⁶] × overhead |
| Contribution margin (CM) | (MRR − variable costs) ÷ MRR |
| Gross margin (GM) | (MRR − variable costs − fixed hosting) ÷ MRR |
| CAC (cash) | marketing cash spend ÷ new paying accounts (fully-loaded CAC adds founder time at a notional rate) |
| LTV | ARPA × CM ÷ monthly logo churn |
| LTV : CAC | LTV ÷ CAC |
| CAC payback (months) | CAC ÷ (ARPA × CM) |
| Logo churn (monthly) | accounts lost in month ÷ accounts at start of month |
| Revenue churn | MRR lost from cancellations and downgrades ÷ opening MRR |
| NRR | (opening MRR + expansion − contraction − churn) ÷ opening MRR (over 12 months) |
| Activation rate | accounts reaching first verified reconciliation ÷ accounts created |
| Trial/pilot-to-paid | paying accounts ÷ pilots started |
| Expansion revenue | MRR gained from upgrades/extra capacity |
| Support cost / account | support hours × loaded hourly rate ÷ accounts |
| Infrastructure cost / account | (fixed hosting ÷ accounts) + variable infra |
| Integration & onboarding cost | hours of setup/support per new account × rate + provider/assessment costs amortised |
| Break-even accounts | steady-state fixed monthly costs ÷ contribution per account |

### 9.2 Assumptions (all [ASM])

| Input | Value | Basis |
|---|---|---|
| List prices | ₹999 / ₹1,799 / ₹2,499 per month | §8 hypotheses |
| Annual-plan share, discount | 30%, 2 months free | Placeholder |
| AI tokens per interpretation | 2,000 in, 300 out; overhead ×1.5 | Placeholder (retries, summaries) |
| AI price | ₹250 / ₹1,000 per million input/output tokens | **Placeholder; provider unselected (TSD OD-05)** |
| Variable infra, email | ₹60, ₹25 per account/month | Placeholder |
| Support (notional) | ₹100 / ₹200 / ₹350 per account by tier | Placeholder hours × notional rate |
| Payment-collection fee | 2.5% of revenue | Placeholder **[VER]** — billing provider unselected |
| Fixed hosting | ₹3,000 (M1–3), ₹12,000 (M4–6), ₹25,000 (M7–12) per month | Placeholder |
| Tooling, legal/accounting | ₹4,000 and ₹8,000 per month; one-off legal review ₹60,000 (M3); one-off independent security review ₹1,00,000 (M6) | Placeholders; get quotes |
| Founder pay | **₹0** in cash model | Notional cost excluded — see §9.4 |
| Revenue start | Month 7 (after validation and build) | Depends on TSD roadmap M0–M8; no velocity data |
| Exchange rate | ₹88/$ | Used by one tracker in MR[44]; **[VER]** |

### 9.3 Scenarios

| Parameter | Conservative | Base | Optimistic |
|---|---|---|---|
| New paying accounts, months 7–12 | 1, 1, 2, 2, 2, 2 (total 10) | 2, 3, 4, 5, 6, 7 (total 27) | 3, 6, 9, 12, 15, 18 (total 63) |
| Monthly logo churn (applied to opening accounts) | 7% | 5% | 3% |
| Tier mix Starter/Growth/Professional | 70/25/5 % | 55/35/10 % | 45/40/15 % |
| Marketing cash ₹/mo (M4–6 / M7–12) | 5,000 / 10,000 | 10,000 / 25,000 | 20,000 / 50,000 |


| Output (month 12 unless stated) | Conservative | Base | Optimistic |
|---|---|---|---|
| Paying accounts (end M12) | 8.6 | 24.6 | 59.9 |
| MRR | ₹10,460 | ₹33,441 | ₹87,924 |
| Annualised run-rate (MRR×12) | ₹125,517 | ₹401,288 | ₹1,055,089 |
| Revenue recognised in months 1–12 | ₹33,935 | ₹97,705 | ₹237,400 |
| Blended ARPA / month | ₹1,210 | ₹1,358 | ₹1,467 |
| Variable costs, year 1 | ₹9,964 | ₹29,965 | ₹75,223 |
| Operating cash costs, year 1 (fixed, marketing, one-offs) | ₹574,000 | ₹679,000 | ₹859,000 |
| Contribution margin % (variable costs only) | 71% | 69% | 68% |
| Gross margin % incl. fixed hosting (M12) | -168% | -5% | 40% |
| Cash CAC (marketing ÷ new accounts) | ₹7,500 | ₹6,667 | ₹5,714 |
| LTV = ARPA × CM% ÷ churn | ₹12,213 | ₹18,824 | ₹33,401 |
| LTV : cash CAC | 1.6 | 2.8 | 5.8 |
| CAC payback (months) | 8.8 | 7.1 | 5.7 |
| Cumulative cash position after 12 months (cash costs only) | ₹-550,029 | ₹-611,260 | ₹-696,822 |
| Peak cash requirement (excl. founder pay, CASA) | ₹5.50 lakh | ₹6.11 lakh | ₹6.97 lakh |
| Steady-state fixed costs/month (host+tooling+legal+marketing) | ₹47,000 | ₹62,000 | ₹87,000 |
| Contribution per account/month | ₹855 | ₹941 | ₹1,002 |
| Break-even paying accounts (fixed ÷ contribution) | 55 | 66 | 87 |


*Reading the table [REC].* (a) Twelve-month revenue is small in every scenario; the business is a **cash-consuming validation phase** in year one. (b) Contribution margins of ~70% depend on low support and AI cost; they are unproven. (c) "Gross margin incl. fixed hosting" is negative in conservative because ₹25,000/month hosting is spread over under ten accounts. (d) LTV:CAC uses *cash* marketing cost only; founder selling time is the real cost (§9.4). (e) The optimistic case shows a larger negative cumulative figure because spending ramps faster than revenue within the 12 months.

### 9.4 Cash requirement, founder cost and break-even
- **Cash-only requirement** (table above) ≈ ₹5.5–7.0 lakh over 12 months **excluding** any founder pay, any Gmail restricted-scope assessment, and any production-grade compliance work.
- **Notional founder cost:** if a founder's selling/support time were costed at a notional rate, CAC and payback would be materially higher. The rate is a founder decision **[DEC BD-09]**; the model keeps it separate so it cannot hide real cost.
- **Break-even [ASM]:** the steady-state fixed cost base (₹47,000–87,000/month depending on marketing intensity) needs roughly **55–87** paying accounts at the modelled contribution. A leaner fixed-cost base (lower marketing, shared hosting) lowers this; it is a design target for the team, not a prediction.
- **Conditions for break-even:** retention ≥ the scenario churn, contribution ≥ ₹850–1,000/account/month, marketing ≤ the scenario level.

**Monthly base-scenario trace (for spreadsheet transfer)**

| Month | New | Active | MRR ₹ | Variable ₹ | Fixed host ₹ | Marketing ₹ | Total opex ₹ | Profit ₹ | Cumulative ₹ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0 | 0.0 | 0 | 0 | 3,000 | 0 | 15,000 | -15,000 | -15,000 |
| 2 | 0 | 0.0 | 0 | 0 | 3,000 | 0 | 15,000 | -15,000 | -30,000 |
| 3 | 0 | 0.0 | 0 | 0 | 3,000 | 0 | 75,000 | -75,000 | -105,000 |
| 4 | 0 | 0.0 | 0 | 0 | 12,000 | 10,000 | 34,000 | -34,000 | -139,000 |
| 5 | 0 | 0.0 | 0 | 0 | 12,000 | 10,000 | 34,000 | -34,000 | -173,000 |
| 6 | 0 | 0.0 | 0 | 0 | 12,000 | 10,000 | 134,000 | -134,000 | -307,000 |
| 7 | 2 | 2.0 | 2,715 | 833 | 25,000 | 25,000 | 62,000 | -60,118 | -367,118 |
| 8 | 3 | 4.9 | 6,652 | 2,040 | 25,000 | 25,000 | 62,000 | -57,388 | -424,506 |
| 9 | 4 | 8.7 | 11,750 | 3,603 | 25,000 | 25,000 | 62,000 | -53,854 | -478,359 |
| 10 | 5 | 13.2 | 17,950 | 5,505 | 25,000 | 25,000 | 62,000 | -49,555 | -527,915 |
| 11 | 6 | 18.6 | 25,198 | 7,728 | 25,000 | 25,000 | 62,000 | -44,530 | -572,445 |
| 12 | 7 | 24.6 | 33,441 | 10,256 | 25,000 | 25,000 | 62,000 | -38,815 | -611,260 |


### 9.5 Funnel implied by the scenarios [ASM]

| Scenario | Qualified lead→demo | Demo→pilot | Pilot→paid | Overall lead→paid | Peak new paid/month | Qualified leads needed/month at peak |
|---|---|---|---|---|---|---|
| Conservative | 25% | 35% | 40% | 3.5% | 2 | 57 |
| Base | 25% | 40% | 50% | 5.0% | 7 | 140 |
| Optimistic | 30% | 45% | 60% | 8.1% | 18 | 222 |


*Reading:* even the base case needs ~140 qualified leads a month at peak — a heavy load for a 1–3 person team. If that is unrealistic, the scenarios are optimistic. Measure the real funnel in Phase A–C before trusting any scenario.

### 9.6 Sensitivities and the mailbox-assessment risk

| Base-scenario sensitivity | MRR M12 | CM % | LTV : cash CAC | Break-even accounts | Peak cash need |
|---|---|---|---|---|---|
| Base case | ₹33,441 | 69% | 2.8 | 66 | ₹6.11 lakh |
| Prices −20% | ₹26,753 | 62% | 2.0 | 92 | ₹6.30 lakh |
| Prices +20% | ₹40,129 | 74% | 3.6 | 51 | ₹5.92 lakh |
| Churn 8%/month | ₹31,677 | 69% | 1.8 | 66 | ₹6.14 lakh |
| Churn 3%/month | ₹34,683 | 69% | 4.7 | 66 | ₹6.09 lakh |
| AI cost ×3 | ₹33,441 | 49% | 2.0 | 93 | ₹6.31 lakh |
| AI cost ×0 | ₹33,441 | 79% | 3.2 | 57 | ₹6.01 lakh |


**Gmail restricted-scope assessment [EXT, unverified].** Google classifies `gmail.send` as sensitive (verification, no assessment) and `gmail.readonly`/`gmail.metadata`/`gmail.modify`/`gmail.compose` as restricted, requiring an annual third-party security assessment for apps that store or transmit restricted data on servers [N3, consistent with SAD sources]. One vendor claims assessment costs of $15,000–$75,000 per year [N4] — a **sales claim from a vendor selling a workaround, not a quote**; other sources describe no committed timeline [N5]. Illustrative impact:

| Assumed annual security-assessment cost (third-party claim, unverified) | ₹ at ₹88/$ | Account-years of base contribution needed to recover one year's cost |
|---|---|---|
| $15,000 | ₹13.20 lakh | 117 |
| $75,000 | ₹66.00 lakh | 584 |


**Implication [REC]:** at the modelled contribution, recovering even the low end needs over a hundred account-years of contribution; **read-only mailbox monitoring should not be built or promised until paying accounts and retention justify the cost, or a cheaper compliant path (e.g. user-forwarded replies, OD-21; or a verified aggregator) is validated [DEC BD-06]**. P0 (paste/.eml capture) and send-only drafting remain commercially viable without it, and this is consistent with the TSD gating.

---

## 10. Go-to-Market Strategy

Phases are sequential gates; durations are assumptions measured from approval of this plan (month 1).

| Phase | Deliverables | Timeline [ASM] | Dependencies | Risks | Exit criteria (proposed thresholds) |
|---|---|---|---|---|---|
| **A. Problem validation** | 15–20 interviews (MR §10.2–10.3); competitor trials (MR §10.4); time/error baseline; WTP probes; landing page | Months 1–3 | Interview access; ethics/consent for any shared artefacts | Founder bias; polite interviewees | ≥ 8 ICP firms report recurring pain with evidence; ≥ 5 agree to a pilot; no stop-signal in MR §11.1 |
| **B. Design-partner validation** | 3–5 partners; clickable UX + synthetic data; test import, reconciliation proposals, review flows; measure completion/errors/trust | Months 3–6 | UX v0.1; P0 vertical slice (TSD M1–M3) | Building before evidence; trust refusal | ≥ 3 partners complete full workflow on protected/synthetic data; trust objections catalogued |
| **C. Controlled paid pilot** | Eligibility criteria (ICP v0 + consent + exportable bank CSV); onboarding checklist; support SLA (business-hours, best effort); data-handling & incident procedure; feedback and exit terms | Months 6–9 | P0 (TSD M1–M5); decisions OD-05/08/14 closed; written pilot agreement | Wrong allocation, wrong draft, data incident | ≥ 10 paid-pilot decisions at stated prices; zero unauthorised actions; zero incorrect confirmed allocations unnoticed; activation criteria in §12 met by ≥ 60% of pilots (proposed) |
| **D. Commercial launch (limited)** | Chosen pricing; onboarding and support; documentation; permissioned references; usage/retention tracking | Months 9–12 | Evidence gate §22.5; billing set-up; legal terms | Over-claiming; support overload | Week-8 retention and renewal intent measured; CAC and funnel measured; go/no-go for scaling |

**Hard rule:** no claim of production readiness before verification; synthetic or protected data in all demos; no customer logos or quotes without written permission.

---

## 11. Customer Acquisition and Distribution

Ranking: 1 = best. Cost/credibility/time-to-learn/conversion/difficulty are **[HYP]** judgements, not data.

| Channel | Cost | Credibility | Time to learn | Conversion potential | Difficulty | Rank |
|---|---|---|---|---|---|---|
| Founder-led outreach (network, warm intros) | Low | High | Fast | High (small n) | Medium | **1** |
| Bookkeepers/accountants (referral pilots) | Low | High | Medium | Medium–high (multiplier) | Medium (multi-client not built) | **2** |
| Educational content + templates (receivables checklist, reconciliation guide) | Low | Medium | Slow | Medium | Low | **3** |
| LinkedIn/professional communities | Low–medium | Medium | Medium | Low–medium | Medium | 4 |
| Webinars/demos | Low | Medium | Medium | Medium | Medium | 5 |
| Product-led trial/self-serve | Medium (build) | Low until trust built | Slow | Unknown | High (onboarding friction) | 6 |
| Referral programme | Low | High | Slow | Depends on retention | Low | 7 (after retention) |
| Integration marketplaces | High (integration) | High | Slow | Medium | High | 8 (needs ledger integration) |
| Paid advertising | High | Low | Medium | Unknown | Medium | Not before retention proven |
| Consultant partnerships (software implementers) | Medium | Medium | Slow | Unknown | High | Later |

**Recommend testing first [REC]:** (1) founder-led outreach into agency/consultancy networks, (2) 4–6 bookkeeper conversations to test referral willingness (interview, not build), (3) one educational asset to harvest qualified leads. Paid ads, viral growth and partnership distribution are **assumed not to work** until validated.

---

## 12. Product-Led Growth and Retention

**Time-to-first-value path [HYP].** Account → workspace setup (currency, timezone) → declare payment accounts → import invoices (CSV) → import a statement and coverage range → review first reconciliation proposals → confirm first allocation → first review-inbox decision → first approved follow-up (manual send in P0). Because onboarding includes bank CSV and column mapping, **assisted onboarding** (live call, mapping templates) is expected for the first customers.

| Stage | Metric (proposed) | Notes |
|---|---|---|
| Activated | First *verified* reconciliation (human-confirmed allocation) within 7 days of signup | Better than logins |
| Value realised | ≥ 1 exception resolved via the review inbox/queue weekly | Reflects workflow value, not clicks |
| Repeat use | Statement import and ≥ 1 reconciliation action in ≥ 3 of 4 weeks | Workflow reliability |
| Renewal trigger | Month-end close with fewer manual checks; avoided wrong reminder | Capture as customer-reported value |
| Expansion | Tier upgrade due to volume, accounts or audit-export need; later multi-entity | |
| Churn reasons to track | Low volume; price; ledger overlap; trust; onboarding friction; switched to ledger feature | Exit survey mandatory |
| Feedback loops | Monthly call with each pilot; in-app "why was this wrong?" on corrected matches/interpretations; correction-rate dashboards | Corrections feed matcher tuning (human-reviewed) |

**Avoid vanity metrics:** sessions, page views, AI-message counts. Prefer completed reconciliations, correction rates, exception resolution time, retained workflows.

---

## 13. Business Operations and Support

| Function | Initial owner (1–3 people [ASM]) | Needs specialists / external help |
|---|---|---|
| Product & customer discovery | Founder A (product/GTM) | — |
| Engineering & security ownership | Founder B (tech lead) with a named security owner | Independent security review before pilot (budgeted); legal counsel for terms, privacy, DPAs |
| Customer onboarding | Founder A (calls, mapping templates) | Part-time support contractor after ~15 accounts |
| Technical support | Tech lead rota; documented runbooks (TSD M7) | On-call rotation grows with accounts |
| Billing & subscription management | Founder A with a billing provider [VER: unselected] | Accountant for GST/invoicing [VER] |
| Integration maintenance | Tech lead | Provider verification work (Google, PayPal) |
| Incident response | Documented runbook: wrong-send suspicion, token compromise, bad-allocation fix, data-incident notification | Legal advice on notification obligations |
| Feedback & prioritisation | Founder A, monthly | — |
| Vendor/AI-provider management | Tech lead | Legal review of AI-provider terms (TSD OD-05) |

**One-founder limits [REC].** A single founder can run discovery, onboarding and support for ≈ 10–15 accounts; beyond that quality and engineering velocity degrade. No large team or funding is assumed.

---

## 14. Cost Structure and Financial Discipline

| Category | Type | Notes / controls |
|---|---|---|
| Software development | Fixed (people time) | Largest real cost; unpaid in cash model — **BD-09** |
| Hosting & infrastructure | Fixed + variable | Single region; right-size; no vendor selected (TSD OD-04) |
| Database & backups | Fixed + volume | Restore drills; cost grows with data retention (TSD OD-08) |
| AI inference | Variable | Per-tenant caps, kill switch, summary/explanation calls limited; cost ∝ messages |
| Email/communication services | Variable | Only if notification emails are added (P1) |
| Monitoring/error tracking | Fixed | Scrub PII |
| Security assessments | Lumpy | Independent review before pilot; **restricted-scope assessment is contingent (§9.6)** |
| Legal & accounting | Fixed + lumpy | Terms, privacy notice, DPA, tax; engage counsel before real customer data |
| Customer support | Variable | Notional in model |
| Sales & marketing | Fixed/discretionary | Cash CAC tracked weekly |
| Integration maintenance | Fixed + lumpy | Provider verification/renewals |

**Cost-control strategies [REC].** Soft allowances per tier; AI only on confirmed associations; cache and de-duplicate interpretations; batch jobs; no AI for extraction in P0 unless validated (OD-19); defer Gmail monitoring; avoid per-customer custom work; monthly cost review against contribution per account.

**Features likely to become expensive before they pay back:** reply monitoring via restricted scopes; PDF extraction (AI cost, malware scanning); ledger integrations (maintenance); SMS/WhatsApp channels (not in scope); multi-client tenancy for bookkeepers.

---

## 15. Trust, Privacy and Risk Management

Trust is a **sales gate**, not a feature. Interview-based evidence of trust barriers is still absent.

| Area | Business implication | Control (design/ops) | Advice needed |
|---|---|---|---|
| Access to financial records | Customers must trust CollectIQ with statements | Minimal data, user-supplied files, no bank credentials, inspector for AI payloads | Privacy counsel |
| AI-provider processing | Provider terms, residency and retention unresolved | Gateway redaction, kill switch, provider chosen after legal review | Legal review before real data |
| Confidentiality & tenant isolation | Cross-tenant leak is existential | Forced RLS + isolation tests (TSD §9, §18) | Independent security review |
| Security incidents | Reputational and legal | Runbooks; log scrubbing; incident drills | Legal on notification duties |
| Incorrect matching | Wrong balances → wrong reminders | Human-confirmed allocations; invariants; reversal-only corrections | — |
| Inappropriate follow-ups | Relationship damage | Gates, linter, approval, no auto-send in MVP | — |
| Dispute handling | Mishandled disputes | Dispute cases suppress reminders; human resolution | — |
| Integration failures | Silent errors | Health banners, paused automation, review inbox | — |
| Retention & deletion | Obligations unresolved | Export/deletion flows, crypto-shredding (provisional) | Legal (retention periods; DPDP applicability) |
| Auditability | Customer expectation | Append-only audit convention; **no immutability or compliance claim** | — |
| Vendor dependency | AI/hosting/Google changes | Adapter pattern; avoid single-vendor lock-in | — |
| Regulatory/contractual | Customer contracts may prohibit processing | Disqualifier in ICP; DPA template | Legal |

**Differentiation through human-in-control [REC].** "We never send or mark paid on our own, and you can see exactly what the AI saw" can be a *credible trust claim for small firms*, but only the observable behaviours may be claimed — not certifications, immutability or accuracy. **Professional advice required** before: processing real customer data; publishing terms/privacy; choosing an AI provider; any statement about compliance (DPDP or otherwise); launching mailbox integrations; GST/invoicing for CollectIQ's own billing; any success-fee or financial-product idea.

---

## 16. Strategic Product Prioritization

Ratings are qualitative **[REC]**: Value (customer), Rev (revenue relevance), Ret (retention), Cx (build complexity), Cost (operating), Sec (security risk), Dep (external dependency). Evidence = what must be true before launch.

| Capability | Value | Rev | Ret | Cx | Cost | Sec | Dep | Class | Evidence required before launch |
|---|---|---|---|---|---|---|---|---|---|
| CSV invoice import + validation | H | H | M | L | L | L | – | **Launch essential** | Import success on pilot files |
| Statement import + matcher + human-confirmed allocation | H | H | H | H | M | M | – | **Launch essential** | Match precision on real statements (MR assumption 4) |
| Evidence coverage / uncertain state | H | M | H | M | L | L | – | **Launch essential** | Reduced wrong reminders in pilot |
| Policy engine + approval flow | H | M | H | H | L | M | – | **Launch essential** | Safety tests (TSD §18) |
| Disputes/blockers + review inbox | M–H | M | M | M | L | L | – | Launch essential (minimal) | Dispute handling interviews |
| Reply capture (paste/.eml) + interpretation (human-reviewed) | M–H | M | M | M | M | M | AI provider | Launch if AI evaluation passes | ≥150-reply evaluation with zero unsafe auto-actions |
| Audit history + payload inspector | M | M | M | M | L | L | – | Launch (lite) | Customer trust interviews |
| Gmail send-only | M | M | M | M | L | M | Google verification | Important post-launch | Verification path/time confirmed |
| PayPal sandbox/production | M | L–M | L | M | L | M | PayPal | Post-launch | Demand among pilots |
| Gmail reply monitoring (restricted) | M | M | M | H | H | H | Google assessment | **Defer** (BD-06) | Economics in §9.6 + consent |
| Auto-snooze (opt-in) | M | L | M | M | M | H | AI eval | Defer | AIR-12 passed per TSD |
| PDF extraction | M | M | M | M | M | M | AI + malware scan | Defer unless demanded | OD-19, OD-14 |
| Multi-client (bookkeeper) tenancy | M–H | H (channel) | H | H | M | M | – | Build only after channel validation | 4–6 bookkeeper interviews + pilots |
| Ledger integrations (Zoho/QuickBooks/Xero/Tally) | H | H | H | H | H | M | Providers | After one dominant ledger emerges | Interview data (Foundation Q5) |
| Outlook | M | M | M | M | M | M | Microsoft | Defer | Demand |
| Predictive risk scores | ? | ? | ? | H | M | M | Data | **Do not build** | Permissioned outcome data; Foundation rules |
| Auto-send | ? | ? | ? | L | L | H | Policy | **Do not build** (MVP principle) | Long-term trust evidence |

**Rule:** a screen existing in the UX document is not a reason to build the feature (UX handoff records are designs only).

## 17. Partnerships and Ecosystem Strategy

**None of the following exists today; all are hypotheses to validate.**

| Category | Mutual value | Dependencies | Commercial model (options) | Integration effort | Risks | Validation steps |
|---|---|---|---|---|---|---|
| Accounting/bookkeeping firms | They save hours across clients; CollectIQ gains distribution | Multi-client tenancy (not in MVP) | Referral fee or client-pack pricing [HYP] | Medium–high (tenancy, roles) | Channel conflict; they may prefer existing tools | 4–6 interviews; one pilot with a firm's own client |
| Finance consultants | Credibility, implementation help | Reputation, case studies with permission | Referral/co-selling | Low | Low volume | 3 conversations |
| Accounting-software ecosystems (Zoho, QuickBooks, Xero, Tally [VER]) | Marketplace reach; data access | Ledger integration; platform approval | Marketplace listing | High | Platform dependency; overlap with their features | Identify dominant ledger in interviews (Foundation Q5) before any build |
| Payment service providers (PayPal, others [VER]) | Evidence feeds | Provider onboarding/visibility proof (TSD OD-11) | None initially (no revenue share) | Medium | Provider rule changes | Sandbox tests only |
| AI infrastructure providers | Inference at acceptable cost/terms | Contract terms, residency (TSD OD-05) | Usage-based cost (a cost, not revenue) | Low–medium | Vendor lock-in, price changes | Compare ≥ 2 providers after legal review |
| Business-software resellers | Reach | Maturity, support capacity | Reseller margin | Medium | Margin erodes thin pricing | Defer until ≥ 50 accounts |

Distinguish clearly in all external communication: **no partnership is established**.

---

## 18. Expansion Strategy

Sequence [REC]; each step has prerequisites; do not run two expansions simultaneously.

| Stage | Expansion | Prerequisites (all must hold) |
|---|---|---|
| E0 | Beachhead: ICP in India, P0 | Evidence gates in §22.5 |
| E1 | Adjacent segments (e.g., larger B2B services, recurring-invoice firms with exceptions) | Retention ≥ target for 3 consecutive months [proposed 90% monthly logo retention]; support time/account within model |
| E2 | Higher-volume workspaces | Performance targets measured (TSD §20); AI cost/account within contribution |
| E3 | Bookkeeper/multi-client | Multi-client tenancy built and security-reviewed; ≥ 3 firms willing to pilot |
| E4 | Ledger/payment integrations (one at a time) | One ledger dominates the customer base; API terms permit; maintenance cost covered by tier uplift |
| E5 | Multi-entity workspaces, advanced reporting and governance | Demand from Professional/Business pilots |
| E6 | Additional geographies | Unit economics positive in India; localisation of statement formats, tax, legal review; separate payment-rail evidence |
| E7 | Partner-led distribution at scale | Reference accounts; support capacity; channel economics proven |

Prerequisites also include: security review clean, integration reliability measured, and positive contribution after support cost.

---

## 19. Business Metrics and KPI Dashboard

All targets are **proposed** until baseline data exist. Owners are roles: **PM** product/GTM founder, **TL** tech lead, **SO** security owner.

| Group | KPI | Formula | Data source | Frequency | Owner | Interpretation / proposed target |
|---|---|---|---|---|---|---|
| Acquisition | Qualified leads | Leads meeting ICP v0 criteria | CRM sheet | Weekly | PM | Funnel input |
| | Lead→demo | demos ÷ qualified leads | CRM | Weekly | PM | Compare with §9.5 assumptions |
| | Demo→pilot | pilots ÷ demos | CRM | Weekly | PM | — |
| | CAC (cash / loaded) | spend ÷ new paying accounts | Finance sheet | Monthly | PM | LTV:CAC ≥ 3 target [proposed] |
| Activation | Time to first successful import | first import time − signup | Product events | Per account | PM | ≤ 1 day assisted [proposed] |
| | Time to first verified reconciliation | first confirmed allocation − signup | Ledger | Per account | PM | ≤ 7 days [proposed] |
| | Onboarding completion | accounts completing checklist ÷ accounts created | Product events | Weekly | PM | ≥ 60% pilots [proposed] |
| | First-value achieved | activation definition in §12 | Product events | Weekly | PM | — |
| Product value | Reconciliation workflow completion | proposals resolved ÷ proposals created | Ledger | Weekly | PM | Rising = trust in matcher |
| | Payment-match correction rate | reversals of confirmed allocations ÷ confirmed allocations | Allocations | Weekly | TL | Lower is better; investigate any spike |
| | Time saved (when measured) | baseline minutes − current minutes (diary/interview) | Pilot study | Per pilot | PM | Only claim measured values |
| | Review-inbox resolution time | median time from item creation to decision | Queue | Weekly | PM | — |
| | Reminder approval / exception rates | approvals ÷ drafts; gate blocks ÷ evaluations | Reminders/decisions | Weekly | PM | High blocks may mean stale evidence |
| Revenue | MRR / ARR | per §9.1 | Billing | Monthly | PM | Run-rate, not recognised revenue |
| | ARPA | MRR ÷ accounts | Billing | Monthly | PM | — |
| | Paid conversion | paying ÷ pilots | CRM | Monthly | PM | — |
| | Expansion revenue | upgrade MRR | Billing | Monthly | PM | — |
| | Gross margin | per §9.1 | Finance + infra bill | Monthly | PM/TL | ≥ 65% contribution [proposed] |
| Retention | Logo churn | lost ÷ opening accounts | Billing | Monthly | PM | ≤ 5% monthly [proposed ceiling] |
| | Revenue churn / NRR | per §9.1 | Billing | Monthly | PM | — |
| | Renewal rate | renewed ÷ due | Billing | Monthly | PM | — |
| | Active-customer retention | accounts with weekly workflow use ÷ paying | Product events | Weekly | PM | Workflow reliability |
| | Customer-reported value | structured question at 30/90 days | Survey | Per account | PM | Qualitative |
| Reliability & trust | Incorrect confirmed allocations | corrected-after-confirmation ÷ confirmations (and incident count) | Ledger + incident log | Weekly | TL | **Target 0 unnoticed incidents** |
| | Duplicate processing incidents | count | Logs/invariant monitors | Daily | TL | **0** |
| | Unauthorised actions | consequential actions without valid decision | Audit/decisions | Daily | TL/SO | **0**; any occurrence = Sev-1 |
| | AI interpretation correction rate | corrected ÷ interpretations | Interpretations | Weekly | PM | Informs AIR-12 gate; no accuracy claim |
| | Failed imports | failed ÷ attempted | Import batches | Weekly | TL | — |
| | Integration errors | errors ÷ calls; time in NEEDS_REAUTH | Integration logs | Daily | TL | — |
| | Security incidents | count and severity | Incident log | Monthly | SO | **0**; each reviewed |

---

## 20. Strategic Roadmap (12 months)

Months are counted from approval of this plan. Phases map to §10 and to TSD M0–M8; **dates move with evidence, not the calendar**. Cash figures are the base-scenario model [ASM].

| Phase | Primary objective | Customer-validation activities | Product milestones | Revenue experiments | Distribution experiments | Budget assumption (base) | Metrics | Dependencies | Risks | Exit criteria |
|---|---|---|---|---|---|---|---|---|---|---|
| **R1 Months 1–3** | Prove the pain and price | 15–20 interviews; competitor trials; time/error baselines | TSD M0 (repo scaffold, approvals) only | Pricing probes; landing-page price test | Founder outreach; 4–6 bookkeeper interviews | ≈ ₹1.05 lakh cumulative (incl. ₹60k legal review) | Qualified leads, interview insight counts, WTP signals | Interview access | Founder bias | MR §10.8 / §22.5 gates 1–2 |
| **R2 Months 3–6** | Show the core workflow works on protected data | 3–5 design partners on synthetic data; trust objections | TSD M1–M3 slice (auth/tenancy, import, reconciliation) + UX prototype | Offer paid-pilot terms | Referrals from R1 | ≈ ₹2.0 lakh in months 4–6 (incl. ₹1 lakh security review) | Workflow completion; correction rate | OD-03/12 approved; sample bank files | Scope creep; build before evidence | ≥ 3 partners complete workflow |
| **R3 Months 6–9** | Controlled paid pilot | 8–12 pilots with written terms | TSD M4–M5 (policy, approvals, AI-reviewed interpretation if eval passes) | Randomised price offers ₹999/₹1,799/₹2,499 | Bookkeeper-referred pilots | ≈ ₹1.7 lakh net burn (months 7–9) | Activation, paid conversion, support hours, AI cost/account | OD-05/08/14 closed; billing set up | Data incident; low conversion | ≥ 10 paid decisions; zero unauthorised actions |
| **R4 Months 9–12** | Limited commercial launch and learning | Renewal and churn interviews | TSD M6–M8 subset (Gmail send-only if verified; audit, settings, hardening, E2E) | Annual-plan offer; Professional tier test | Content + referral programme | ≈ ₹1.3 lakh net burn (months 10–12) | CAC, retention, NRR, gross margin | Evidence gate §22.5 | Over-claiming; support overload | Scale / pivot / pause decision |

*Total base-scenario cumulative cash after 12 months ≈ ₹6.1 lakh [ASM] (see §9.3).*

---

## 21. SWOT and Risk Analysis

**Strengths.** Clear, narrow ICP and well-documented principles (human control, evidence-first); consistent spec set (PRD, SAD, UX, TSD) lowers build ambiguity; low initial burn; safety-first design that can be explained to cautious owners.
**Weaknesses.** Nothing built; no customer evidence; tiny team; pain and WTP unmeasured; price at/above ledger tools; dependence on bank-statement quality; limited brand.
**Opportunities.** Documented payment-delay environment in India [MR §3]; gap in Indian-rail evidence handling among AR tools (not found in public sources) [MR §4.3]; bookkeeper distribution; trust positioning against over-automation; add-on revenue from governance features.
**Threats.** Incumbents (Zoho etc.) shipping overlapping features at no extra price [MR §4.6]; Gmail restricted-scope costs; AI-provider terms/price changes; a trust incident; regulation/market changes in payment timelines; customers' reluctance to share financial data.

**Risk register** (L = likelihood, I = impact, H/M/L; assessments are **[REC] judgements**; "trigger" = review date or event)

| # | Risk (type) | L | I | Early warning | Mitigation | Owner | Review trigger |
|---|---|---|---|---|---|---|---|
| R1 | Pain/WTP lower than assumed (commercial) | M | H | Interviews show negligible time cost; refusals at ≥ ₹999 | Narrow ICP, reposition per MR §11.1, or pause | PM | End of R1 |
| R2 | Price ceiling set by ledgers (commercial) | H | H | Pilots cite Zoho Standard price | Test lower Starter; bundle value (evidence + replies) | PM | Each pilot cohort |
| R3 | Incumbent ships equivalent (competitive) | M | H | Release notes from Zoho/QuickBooks/Xero | Differentiate on multi-rail evidence + trust; focus niche | PM | Monthly scan |
| R4 | Gmail restricted-scope assessment cost/time (financial/technical) | H | M–H | Need for read access surfaces in pilots | Defer monitoring; paste/.eml; forwarding intake; revisit at scale | TL | Before any read-scope work |
| R5 | AI provider terms/cost unsuitable (technical/financial) | M | M | Contract review; cost per message spikes | Provider adapter; caps; kill switch | TL | Before M5 |
| R6 | Wrong allocation or reminder erodes trust (trust) | M | H | Correction rate spike; complaint | Human confirmation, invariants, incident runbook | TL | Weekly |
| R7 | Data breach / tenant leakage (trust/technical) | L | H | Isolation test failure; anomaly | RLS suite, review, minimal data | SO | Continuous; pre-pilot review |
| R8 | Poor statement formats prevent reliable matching (technical) | H | M–H | Match precision low on samples | Collect samples early; mapping templates; keep manual path | TL | R2 |
| R9 | Small ARPA vs fixed cost (financial) | H | H | Break-even accounts > feasible reach | Cut fixed costs; raise price; add higher tier; revisit scope | PM | Monthly |
| R10 | Onboarding friction blocks activation (operational) | H | M | Time-to-first-reconciliation > 7 days | Assisted onboarding; templates | PM | Per account |
| R11 | Founder overload (operational) | H | M | Support backlog; slipping milestones | Cap pilots; contractor after ~15 accounts | PM | Monthly |
| R12 | Legal/regulatory misstep (compliance) | M | H | Unanswered counsel questions | Counsel before real data; no compliance claims | PM | Pre-pilot |
| R13 | Over-claiming in marketing (trust/legal) | M | H | Claims without evidence in drafts | Claim register; review before publish | PM | Every publication |
| R14 | Integration provider changes (technical) | M | M | Provider notices; failures | Adapters; monitoring; polling fallback | TL | Quarterly |
| R15 | Retention low due to volume (commercial) | M | H | Week-4/8 usage drop | Target higher-exception firms; value reviews | PM | Monthly |
| R16 | Payment-collection/billing complexity (operational/financial) | M | L–M | Failed billing; GST confusion | Accountant; billing provider chosen early | PM | Before R3 |

---

## 22. Final Strategic Recommendations

**22.1 Initial customer segment [REC].** Small B2B service firms (agencies, studios, consultancies, ~5–50 staff) in India meeting ICP v0; bookkeepers tested as a channel only.
**22.2 Pricing model [REC].** Per-workspace subscription, three tiers, annual option, fair-use allowances, no success fees, no processing revenue.
**22.3 Initial pricing hypotheses [HYP/FH].** ₹999 / ₹1,799 / ₹2,499 per month excl. GST (annual: 2 months free); "Business" tier unpriced until multi-entity/multi-client features exist.
**22.4 Primary acquisition channels [REC].** (1) Founder-led outreach, (2) bookkeeper referral conversations, (3) educational content. Paid ads and marketplaces are not first tests.
**22.5 Minimum evidence before commercial launch (proposed gates).**
1. ≥ 8 ICP firms evidence recurring reconciliation/exception pain (time and error data, not opinions).
2. ≥ 10 paid-pilot decisions at stated prices and a majority of paying pilots retained at week 8 (threshold to be confirmed by founder).
3. Match precision and correction rate on real (consented) statements acceptable to pilots; zero unnoticed incorrect confirmed allocations.
4. Zero unauthorised actions; AI evaluation (≥ 150 labelled replies) passed before any AI-driven automation; human-approved follow-ups only.
5. Legal terms/privacy notice and AI-provider contract reviewed; open decisions blocking pilot closed (TSD OD-05, OD-08, OD-14).
6. Unit economics: contribution ≥ ~₹850/account/month and a credible path to the break-even account count in §9.4.
**22.6 Pilot strategy [REC].** 8–12 ICP-fit firms, written pilot terms, assisted onboarding, protected data, paid at stated price with refund option, weekly check-ins, explicit exit criteria.

**22.7 Top five immediate actions**
1. Approve or amend BD-01…BD-06 (this document's decision register).
2. Schedule 15–20 interviews using MR §10.2–10.3; recruit through personal networks first.
3. Run hands-on competitor trials (MR §10.4) and capture dated pricing screenshots.
4. Obtain 5–10 real (consented, redacted) bank/PayPal export samples for matching feasibility (TSD OD-10).
5. Put counsel and an accountant on call for terms, privacy, GST and AI-provider review before any real data.

**22.8 Conditions that would change the strategy**
- Pain exists mainly for bookkeepers → switch buyer and prioritise multi-client tenancy.
- Reply interpretation valued, reconciliation not (or vice versa) → restructure MVP around the valued half (MR §11.1).
- Only "pause reminders when paid" is valued → consider a plug-in/feature rather than a product.
- Customers will not pay ≥ ₹999 → reconsider price, segment, or pause.
- A cheap compliant mailbox path appears → bring monitoring forward; otherwise keep it deferred.
- A dominant ledger emerges → prioritise that integration over new features.

**22.9 Decision summary.** *Confirmed (in source documents):* product principles, MVP scope, no auto-send, no success fees/financial products (Foundation boundary), human approval, INR/India-first as the brief's working direction. *Recommendations requiring approval:* everything labelled [DEC] in section 23.

---

## 23. Decision Register and Final Action Checklist

| ID | Decision requiring founder approval | Recommendation | Dependencies | Needed by |
|---|---|---|---|---|
| BD-01 | India-first and INR pricing (Foundation Decision 1) | Yes, as working assumption | Interviews in India | R1 |
| BD-02 | Initial ICP = MR ICP v0; bookkeepers as channel only | Approve | — | R1 |
| BD-03 | Revenue model: tiered subscription; reject success fee/processing revenue | Approve | Legal view if reconsidered | R1 |
| BD-04 | Price hypotheses ₹999/₹1,799/₹2,499 and WTP test plan; no final price before ≥ 10 paid decisions | Approve as hypotheses | R1–R3 data | R1 |
| BD-05 | No free tier; use concierge/paid pilots with refund option | Approve | — | R2 |
| BD-06 | Defer restricted-scope Gmail monitoring; ship paste/.eml first; revisit when economics justify (§9.6); evaluate forwarding intake (TSD OD-21) | Approve | Google docs [VER], TSD OD-11 | R2 |
| BD-07 | Bookkeeper channel: interviews first, multi-client build only after validation | Approve | R1 | R2 |
| BD-08 | Team/capital assumption (1–3 people, no funding) and role owners (PM/TL/SO) | Confirm or correct | — | R1 |
| BD-09 | Notional founder-time cost used in CAC and whether any founder pay is budgeted | Decide | — | R1 |
| BD-10 | Billing provider, GST handling, invoicing for CollectIQ itself | Decide with accountant | Provider selection [VER] | R3 |
| BD-11 | Evidence-gate thresholds in §22.5 and decision rules | Approve or revise | — | R1 |
| BD-12 | AI-provider selection timing, per-tenant cost caps, allowance sizes | Decide after legal review | TSD OD-05 | R2 |
| BD-13 | Timing of the "Business" tier (not before multi-client/multi-entity exists) | Defer | Product roadmap | R4 |
| BD-14 | Reposition/narrow rules if only part of the value is validated | Approve MR §11.1 rules | R1 results | R1 |

**Final action checklist**
- [ ] Founder decisions BD-01…BD-14 recorded (approve / amend / reject).
- [ ] Interview plan and consent script ready; 15–20 interviews scheduled.
- [ ] Competitor trial checklist executed; pricing screenshots dated.
- [ ] Model inputs replaced with measured values after R1; scenarios rerun.
- [ ] Sample statement files obtained; match-feasibility test defined.
- [ ] Counsel + accountant engaged; privacy notice, terms, DPA template drafted.
- [ ] Claim register created (no compliance, immutability, accuracy, "first/only/best" claims).
- [ ] Billing provider and GST approach decided.
- [ ] Security review and incident runbook scheduled before the pilot.
- [ ] Re-baseline this document after each phase gate.

---

## 24. Source References

**Project sources:** Foundation PDF; PPD v0.1; Problem Statement & Market Research v0.1 (MR, with its reference list §14, including MR[11][12] Udyam data, MR[21]–[26] ledger features, MR[32]–[39] AR tools, MR[40][41] Indian billing apps, MR[44]–[47] pricing listings); PRD v0.1; SAD v0.1; UX Design v0.1; TSD v1.0 + Open Decisions + Roadmap.

**New external sources (retrieved 3 November 2026 via web search; excerpts only, pages not independently re-verified):**
- [N1] ProductGrowth, *Zoho Books* — Standard ₹749/org/month billed yearly, ₹899 monthly; Professional ₹1,499/₹1,799; Premium ₹2,999/₹3,599; "checked from zoho.com/in/books/pricing on 26 Oct 2026". https://productgrowth.in/tools/payments/zoho-books/ **[EXT, aggregator]**. Conflicting third-party figures exist (e.g. Patron Accounting, April 2026: Standard ₹899, Professional ₹1,499, Premium ₹2,999, Free tier for revenue < ₹25 lakh) https://www.patronaccounting.com/blog/zoho-books-pricing-india-2026 — prices are indicative; check zoho.com/in/books/pricing **[VER]**.
- [N2] Chaser, *Pricing* (UK/global page; Compact $259/mo, Core $779/mo, Complete $1,169/mo, monthly billing, revenue bands) https://chaserhq.com/en-gb/pricing **[EXT, vendor]**; Compact $259 also in Software Advice listing (date not shown) https://www.softwareadvice.com/debt-collection/chaser-profile.
- [N3] Gmail scope tiers (sensitive: `gmail.send`; restricted: `gmail.readonly`, `gmail.metadata`, `gmail.modify`, `gmail.compose`; assessment for restricted data stored on servers) — third-party summary https://docs.unified.to/skills/gmail-oauth-app/SKILL.md and a Google developer-forum thread quoting Google's restricted-scope verification wording https://discuss.google.dev/t/gmail-restricted-scope-is-the-casa-assessment-required-when-mail-is-processed-on-device-and-only-a-derived-subscription-list-reaches-our-server/398372 **[EXT; consistent with SAD v0.1 verification; one other site (Unipile) describes send/readonly differently — verify against Google's own documentation [VER]]**.
- [N4] Truto, *Google integration API* — vendor claim of $15,000–$75,000 annual assessment cost https://truto.one/google.md **[EXT, vendor marketing, unverified]**.
- [N5] Google OAuth verification service page — "Google publishes no committed timeline" https://singhamandeep.com/google-oauth-internal-vs-external-user-type/ **[EXT, service-provider site]**.

**Not researched (stated, not assumed):** Indian business counts by invoice volume; willingness to pay; support/AI actual costs; billing provider fees; GST treatment; DPDP applicability; competitor hands-on behaviour.

