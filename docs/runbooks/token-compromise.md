# Token compromise

Use when a Gmail or PayPal credential, a session cookie, a password or the master key may have leaked.

## 1. Contain first
1. Pause automation (E019).
2. Disconnect the integration in Integrations (Owner only). For Gmail, disconnecting deletes the stored
   credential and asks Google to revoke it on a best-effort basis; PayPal disconnect only changes the
   connection state. In both cases confirm at the provider (Google account permissions, or the PayPal
   developer dashboard) that the grant is gone.
3. For a person's credentials: reset the password. That signs out all of their sessions.

## 2. Scope
- Audit History: filter by actor and by `integration.*` actions around the time. Check
  `integration.connected`, `integration.verification_failed` and `integration.disconnected`.
- Webhook events are stored as evidence only; an event never allocates or marks anything paid, so a forged
  event cannot move money. Review `webhook_events` for events you do not recognise.
- Gmail is granted the send scope only. A read scope is refused at connection, so a stolen token cannot read
  the mailbox through this application. Messages could still be submitted only through an approved reminder.

## 3. Rotate
- Reconnect the integration so a new grant is verified and sealed.
- Master key (`COLLECTIQ_MASTER_KEY`): changing it requires re-sealing stored secrets. Key rotation is not
  automated in this build; treat a master key leak as a deployment incident and plan a re-seal with the
  engineer who deploys it.
- Replace the webhook secret at the provider and in the environment.

## 4. Resume
Resume only when the old grant is revoked, the new one shows CONNECTED_VERIFIED, and the audit review found
no unexplained reminder. Record what leaked, when you found out, and when each step was done.
