# Runbooks

Six procedures for the situations that need a person. Each says what to check first, what to do, and what
to record. They use only features that exist today; where a step needs something not built, it says so.

- [Authentication outage](auth-outage.md)
- [Wrong-send suspicion](wrong-send-suspicion.md)
- [Token compromise](token-compromise.md)
- [Fixing a bad allocation](bad-allocation-fix.md)
- [Break-glass database access](break-glass.md)
- [Incident response](incident-response.md)

Ground rules for all of them:

- Pause first (Owner or Finance admin: the pause control in the header, E019). Pausing stops reminders from
  being approved or submitted; it does not change any invoice, payment or allocation.
- Nothing here edits the database by hand. The audit history is append-only by database permissions, with a
  hash chain that detects casual edits; it is not tamper-resistant against a database superuser.
- Write down what you saw and what you did. Every app action below is already recorded in the audit history.
