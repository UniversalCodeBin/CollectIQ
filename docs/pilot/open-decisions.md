# Open decisions: briefs for the owner

Refreshed 2026-11-08 against the repository at that date. These are briefs, not decisions. Nothing here is a legal
conclusion, a vendor endorsement or a purchase, and none of it has been decided on the owner's behalf. A
"recommendation" is only my suggestion; each decision stays open until the owner says otherwise.

Source list of decisions: `CollectIQ_Open_Decisions.md`. Rulings already made: `docs/DECISIONS_LOG.md`.

| ID | Question | Who decides | Blocks | Built so far | Needs from the owner |
|---|---|---|---|---|---|
| OD-04 | Hosting, region, TLS, backups, RPO/RTO | Owner | Staging, pilot | Example compose, env check, encrypted backup and drill, runbooks | Host, region, domain, backup location, recovery targets |
| OD-05 | AI provider, contract, model | Owner | Live AI, PDF extraction | Gateway, fake provider (dev only), invoice brief agent | Provider choice, terms, key, spend limit |
| OD-08 | Retention and deletion periods; data-protection duties | Owner with qualified legal advice | Pilot with real people's data | Configurable retention, export, deletion request | Periods, advice from counsel |
| OD-10 | Real bank and PayPal export samples | Owner | Reliable statement import | Generic CSV parser only | 2-3 redacted exports per source |
| OD-11 | Gmail OAuth client and review path; PayPal sandbox | Owner | Live Gmail and PayPal use | Gmail send path and PayPal connect port, neither exercised live | Google client, test mailbox, PayPal sandbox, path for monitoring |
| OD-14 | Upload malware scanning | Local mechanism built; production use is the owner's | Any real upload | ClamAV adapter, fails closed, tested against a fake server | Approval to run clamd in production; a real clamd to test against |
| SEC-22 | Legal review of data-protection applicability | Owner and counsel | Pilot with real people's data | Export, deletion, retention jobs, audit | Counsel engagement and its outcome |

Each brief below says what is true now, the realistic options, what each costs, my suggestion, what happens if
nothing is decided, and exactly what I need.

---

## OD-04: Hosting, region, TLS, backups, RPO/RTO

**State now.** `deploy/compose.prod.example.yaml`, `scripts/check_deploy_env.py`, `scripts/backup_encrypted.sh`
(backup and restore drill), runbooks for backup/restore, break-glass, incident response and token compromise, and
`docs/operations.md`. A local restore drill was run and recorded; no recovery-time or uptime figure is claimed.
Nothing has run on a real host. The app refuses to start in production with placeholder keys or the fake AI
provider. Forced row security needs two database roles (owner and app), so the host must allow custom Postgres roles.

**Options.**
1. Single VPS or container host, the example compose file, a TLS proxy, scripted encrypted daily dump to a second
   location. Cheapest and simplest; single point of failure; recovery is by hand from the latest dump.
2. Managed container platform with a managed Postgres. Less to operate; check first that it allows the owner and
   app roles and `FORCE ROW LEVEL SECURITY`, and where backups are stored. Higher cost; vendor lock-in.
3. Your own machine or office server for a closed pilot. No hosting cost; availability and security are yours.

**Suggestion (not a decision).** Option 1 in the region nearest the pilot users, since a pilot does not justify more.

**If undecided.** Pilot stays local; no staging, no real users.

**Needed from the owner.** Host and plan, region, domain name, who holds the backup passphrase and where the
second backup copy lives, and target recovery point/time. I will not state RPO/RTO figures until measured on the
chosen host.

## OD-05: AI provider, contract, model

**State now.** `AI_PROVIDER` defaults to `none`, so AI features are off. A gateway with a fake provider exists for
development and tests; it is refused in production. The invoice brief agent (E120) is opt-in per workspace and
off by default; the model sees placeholders, not invoice numbers, names, amounts or message text, and its wording
must pass the reminder linter. Task 32 (a live adapter) is deferred. Known gaps: no cost metering, no per-workspace
rate limit, no live-model evaluation. An AI reading is always shown as unverified.

**Options.**
1. Keep AI off for the pilot. Cost zero; no summaries, no PDF extraction, no reply classification, so disputes
   and promises are found only by reading replies yourself.
2. Enable one provider after reviewing its terms (training on your data, retention, deletion, location of
   processing, subprocessors). I then build the adapter behind the gateway and add metering and a rate limit.
3. Self-hosted open-weight model. No third-party data sharing; needs suitable hardware and quality testing.

**Suggestion (not a decision).** Start with option 1; choose 2 or 3 only once real use shows the need.

**If undecided.** AI stays off. FL-10 and FL-14 AI starts (a reply classified as a dispute; correcting a reading)
cannot occur live.

**Needed from the owner.** Provider and model choice, acceptance of its data terms (see OD-08/SEC-22), an API key
supplied through the environment (never committed), and a monthly spend limit.

## OD-08: Retention and deletion periods; data-protection duties

**State now.** Configurable defaults: AI payloads 30 days (`COLLECTIQ_PAYLOAD_RETENTION_DAYS`), notifications 90
days, data exports expire after 7 days. Workspace export and deletion request endpoints exist. Audit records are
append-only by database permissions, with a hash chain that detects casual edits; not tamper-resistant against a
database superuser. Backups are retained per the owner's chosen policy, so deleted data persists in them until
they expire. Periods for invoices, evidence, messages and audit are not set and no legal basis has been chosen.

**Options.**
1. Keep the defaults and decide the rest after advice from counsel.
2. Set periods now (for example by record type) and implement them. Faster, but risks rework if advice differs.

**Suggestion (not a decision).** Option 1, and make no compliance statement to users.

**If undecided.** The product keeps non-payload data until deleted on request. No compliance claim is made.

**Needed from the owner.** Retention periods per record type, the deletion grace period, backup deletion policy,
and written advice from counsel (links to SEC-22).

## OD-10: Real bank-statement and PayPal export samples

**State now.** Only a generic CSV parser (`evidence/parsers/generic_csv.py`) with column mapping exists, proven on
synthetic files made for tests. No real bank or PayPal export has been seen. PayPal events remain evidence only and
are not match candidates. Statement lines never mark an invoice paid on their own; a person confirms each match.

**Options.**
1. Supply 2-3 redacted exports per bank or PayPal source; I add named parsers and tests from them.
2. Pilot with generic mapping only; users map columns themselves. Works, but each new format costs setup effort
   and errors are likelier.

**Suggestion (not a decision).** Option 1 for the one or two banks the pilot users actually use.

**If undecided.** Generic mapping only; I do not guess at real formats.

**Needed from the owner.** Redacted files (account numbers, names and references replaced) from the actual
sources, and which sources matter first. Do not send unredacted statements.

## OD-11: Gmail OAuth client and review path; PayPal sandbox

**State now.** Gmail: a send path and a connect screen exist, but have never run against a real mailbox; no
Google client exists. Mailbox monitoring (E096) always answers "not available" and token refresh is not built, so
reply capture is by paste or upload. PayPal: connect
(E129) records a merchant id behind a merchant-check port; with no live checker it never reaches verified. Every
customer-facing message still needs human approval, and nothing is sent by the app on its own.

**Options.**
1. Pilot on file-based reply capture and manual send (copy, then record as sent). No accounts or review needed.
2. Add Gmail send only. Needs a Google Cloud OAuth client and test users; sending scopes may still need Google
   review before wider use.
3. Add Gmail monitoring. Uses restricted scopes and needs Google's verification and a security assessment, which
   takes time and may cost money.
4. PayPal sandbox first, to exercise connect and evidence import before any live merchant.

**Suggestion (not a decision).** Option 1 for the pilot; revisit 2 and 4 when there is a sandbox account to test.

**If undecided.** FL-13 (reconnect after an email failure) and the disconnect of a real connection (FL-16) stay
unexercised live; the Gmail button remains "Connect Gmail" and nothing shows as connected.

**Needed from the owner.** Whether to pursue Gmail at all; a Google OAuth client and test mailbox created by the
owner; PayPal sandbox access; the owner's decision on the review path. Credentials go in the environment only.

## OD-14: Upload malware scanning

**State now.** `SCANNER_KIND=clamav` streams uploads to a ClamAV daemon (clamd) and fails closed: a file that
cannot be scanned is refused with 503 `SCAN_UNAVAILABLE`. The default is `none`, which records files as not
scanned and says so. The adapter has been tested only against a local fake server, never a real clamd. The
deployment check flags an unscanned upload path in production.

**Options.**
1. ClamAV beside the API. Free and self-hosted; signature-based, so it misses novel malware; needs the daemon,
   memory and regular signature updates.
2. A paid scanning service. Better coverage; sends customer files to a third party (see OD-08/SEC-22) and costs money.
3. Disable uploads for the pilot (CSV import only). No scanning needed; PDF proofs and statements unavailable.

**Suggestion (not a decision).** Option 1 with fail-closed, after I test it against a real clamd locally. That local
test is free and reversible and I can do it when you say so.

**If undecided.** Uploads are recorded as unscanned; the owner should not enable real customer uploads.

**Needed from the owner.** Approval for production use of the chosen mechanism and a clamd to run it against.

## SEC-22: Legal review of data-protection applicability

**State now.** No legal review has happened and the product makes no compliance claim. Technical controls that
counsel can review: workspace isolation by forced row security, role-based access, encrypted proofs, audit trail,
configurable retention, export and deletion requests, and the break-glass procedure. A written data inventory (what
is stored, where, for how long, and which third parties receive it) has not been prepared; the earlier version of
this brief proposed it.

**Options.**
1. Engage counsel before any real people's data is used. Slower and costs money; the right basis for any claim.
2. Pilot only with sample or synthetic data until advice arrives. No legal exposure from real data.

**Suggestion (not a decision).** Option 2 until option 1 completes. I can prepare the data inventory for counsel as
documentation only, when asked.

**If undecided.** Real-people data stays out of the system.

**Needed from the owner.** Counsel and the scope of advice (jurisdictions of users and customers), and the
outcome, which then drives OD-08.

---

## Work that needs no decision

Product features and local procedures that need no external decision continue in the repository: no purchase, no
account and no real credential is required. ClamAV and SMTP adapters are already built and are not re-opened here.

## What only the owner can supply

Hosting account, region and domain (OD-04); AI provider terms, key and spend limit (OD-05); legal advice and
retention periods (OD-08, SEC-22); redacted sample exports (OD-10); Google OAuth client, test mailbox and PayPal
sandbox (OD-11); SMTP or email-provider credentials; approval to run ClamAV in production (OD-14); pilot
participants and their consent.
