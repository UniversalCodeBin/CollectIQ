# Break-glass database access

For the rare case where an engineer must read or repair data outside the application (an incident the
application cannot fix). This is a **procedure**, not a feature: the build has no in-app break-glass role.

## Rules
- Two people: one asks, one approves (the workspace Owner, or the pilot's named contact). Write the reason,
  scope and time limit in a ticket **before** connecting.
- Use the owner role only for schema or integrity work. For reading data use a read-only role created for the
  session and dropped afterwards. Never use the app role to bypass row security; it cannot, by design.
- Nothing is edited by hand. Corrections go through application actions so they are audited. The audit
  history is append-only by database permissions, with a hash chain that detects casual edits. This
  procedure gives someone superuser-level reach, so the stored audit anchor below is the control that matters.

## Steps
1. Record the audit anchor first: `python manage.py audit_anchor > anchor-<date>.jsonl`, and store the file
   somewhere the operator cannot edit (see the audit anchor section of the operations guide).
2. Connect, do the approved work, keep the session log.
3. Afterwards run `python manage.py audit_anchor --check anchor-<date>.jsonl`. Any MISMATCH means audit rows
   changed during the session and must be explained in the ticket.
4. Drop the temporary role, rotate any password that was shared, close the ticket with what was read or changed.
