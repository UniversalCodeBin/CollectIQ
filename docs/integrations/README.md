# Integrations: setup and revocation

Status as built (Task 33). No provider adapter exists yet, so Gmail and PayPal always show "Needs configuration".

- **File based:** invoice CSV and bank statement CSV imports. Nothing syncs on its own.
- **Manual:** payment records and reminder handoff are done by a person.
- **Providers (Gmail send-only, PayPal webhooks):** a provider shows "Connected and verified" only after a verification call succeeds. The database refuses that state without a verification time. A failed or unreachable verification leaves it unconnected and is audited as `integration.verification_failed`.
- **Who can change it:** Owner only (connect and disconnect, each audited). Owner and Finance admin can read.
- **Revocation:** disconnect sets the state to Disconnected and is audited. Revoking tokens at the provider arrives with the adapters (Task 34); nothing is claimed as revoked until then.
- No Zoho, QuickBooks, Xero or Tally control exists.
