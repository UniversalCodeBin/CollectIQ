# Integrations: setup and revocation

Status as built (Task 34). Gmail send-only and the PayPal webhook exist behind fake transports and are off by default (`FEATURE_GMAIL_SEND`, `FEATURE_PAYPAL_WEBHOOK`). Neither has been tested against the real provider.

- **File based:** invoice CSV and bank statement CSV imports. Nothing syncs on its own.
- **Manual:** payment records and reminder handoff are done by a person.
- **Providers (Gmail send-only, PayPal webhooks):** a provider shows "Connected and verified" only after a verification call succeeds. The database refuses that state without a verification time. A failed or unreachable verification leaves it unconnected and is audited as `integration.verification_failed`.
- **Who can change it:** Owner only (connect and disconnect, each audited). Owner and Finance admin can read.
- **Revocation:** disconnect sets the state to Disconnected and is audited. Gmail disconnect deletes the stored credential and asks the transport to revoke it (best effort); nothing is claimed as revoked at Google until a live transport exists.
- No Zoho, QuickBooks, Xero or Tally control exists.
- Sending shows "submitted", never "delivered". If the connection drops mid-send the result is "unknown" and a person decides; the system never retries it.
