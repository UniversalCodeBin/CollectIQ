# Open decisions: alternatives, recommendation, authority

Prepared for the owner. Nothing here is a legal conclusion, a vendor endorsement or a purchase. "I can decide" means
the choice is reversible, local and free; anything involving money, credentials, a contract or law is the owner's.

| ID | Question | Who decides | Recommendation | Unblocks |
|---|---|---|---|---|
| OD-04 | Hosting target, region, TLS, backups, RPO/RTO | Owner (cost, vendor, data location) | One small VPS or container host in the region nearest the pilot users, running the example compose file behind a TLS proxy, with managed or scripted daily `pg_dump` to a second location. Check that the host allows custom Postgres roles (forced RLS needs the owner and app roles). | Staging, pilot |
| OD-05 | AI provider, contract, model | Owner (contract, retention terms, spend) | Start the pilot with AI features off (the default). If AI is wanted, pick a provider whose terms exclude training on API data and allow deletion, then build the Task 32 adapter behind the existing gateway. | Task 32, summaries, PDF extraction |
| OD-08 | Retention and deletion periods; data-protection obligations | Owner with qualified legal advice | Keep the configurable defaults (AI payloads 30 days, notifications 90 days). Do not publish a compliance claim. Ask counsel whether the pilot triggers notice or consent duties. | Pilot with real people's data |
| OD-10 | Real bank-statement and PayPal export samples | Owner (supplies redacted samples) | Provide 2-3 redacted exports per source. Until then only the generic CSV mapping is proven. | Reliable statement import |
| OD-11 | Gmail OAuth client and review path; PayPal sandbox | Owner (accounts, credentials) | Pilot on the file-based reply path and manual send handoff. Add Gmail send later; leave mailbox monitoring (restricted scope, security assessment) out of the pilot. | Gmail/PayPal live adapters |
| OD-14 | Upload malware scanning | I can decide the local mechanism; the owner approves production use | ClamAV (open source, free) via its daemon, run beside the API, failing closed: a file that cannot be scanned is not accepted. Implemented as an adapter behind the existing scan port. | Any real upload |
| SEC-22 | Legal review of data-protection applicability | Owner and counsel | Not something I can resolve. The product makes no compliance claim. Prepare a data inventory (what is stored, where, how long) for counsel; the export and deletion features and the retention jobs are the technical controls to review. | Pilot with real people's data |

## What I will do without waiting

- Build the ClamAV scan adapter and its tests (OD-14 mechanism).
- Add an SMTP email backend driven by environment variables so email can be delivered once the owner supplies credentials; until then the default stays file/memory.
- Build the owed product features that need no external decision (pause per client/invoice, snooze expiry, notification retention, UI gaps).
- Prepare staging, monitoring, backup-encryption and recovery-timing procedures that run locally.

## What only the owner can supply

Hosting account and region (OD-04); AI provider contract and key (OD-05); legal advice (OD-08, SEC-22); real sample
exports (OD-10); Gmail OAuth client and PayPal sandbox (OD-11); SMTP or email-provider credentials; approval to use
ClamAV in production; pilot participants and their consent.
