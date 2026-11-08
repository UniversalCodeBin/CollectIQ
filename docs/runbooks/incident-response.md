# Incident response (pilot)

One page for the first hour. It assumes a small team; adjust names in the pilot contact sheet.

## Severity
- **S1** possible wrong customer message sent, cross-tenant data visible, credential leak, money state wrong.
- **S2** feature down for everyone (sign-in, imports, queue), failing backups.
- **S3** one user or one workspace affected, cosmetic.

## First hour
1. Name an incident lead. Start a timeline (time, what was seen, what was done).
2. S1: pause automation (E019) for every affected workspace, then use the matching runbook:
   [wrong send](wrong-send-suspicion.md), [token compromise](token-compromise.md),
   [bad allocation](bad-allocation-fix.md), [auth outage](auth-outage.md).
3. Check `GET /api/v1/health/ready` and the structured logs (secrets are scrubbed at the formatter) around the first report.
4. Do not restore a backup over production as a first move. Restore to a scratch database
   ([backup and restore](backup-restore.md)), compare, then decide.
5. Tell affected customers what happened in plain words, only after the lead and the Owner agree. Legal or
   contractual notification duties are the customer's and the operator's to decide; this repository makes no
   compliance claim.

## After
Write what happened, the cause, what was changed, and what test or check now guards it. A fix that has no test
is not finished. Add the audit-anchor check result if database access was involved.
