# Authentication outage

Use when people cannot sign in, or sessions are being dropped, or sign-up and reset emails do not arrive.

## 1. Tell the cases apart
1. `GET /api/v1/auth/session` while signed in. A 401 for everyone means the session store or the
   application is unhealthy; a 401 for one person means that person's session ended (12 hour absolute
   limit, or signed out everywhere after a password change).
2. Sign-in refused with a lockout message: the account hit the failed-attempt limit. Wait out the window;
   there is no override. The per-IP limit applies the same way.
3. Emails missing: check `EMAIL_BACKEND_KIND`. In `file` mode messages are written to the local outbox and
   are never delivered. A real delivery backend is not part of this build.
4. Idle for 30 minutes: ordinary reads work, sensitive actions ask the person to sign in again. That is
   intended, not an outage.

## 2. While it lasts
- Pause automation. No reminder can be submitted without a signed-in human anyway.
- Do not edit users or sessions in the database. Sessions are revoked by the application (`revoke_all`).
- Jobs keep running in `run_worker`; they carry their own workspace context and do not need a session.

## 3. Recover
1. Restore the database or the application, then confirm `GET /api/v1/auth/session` for one test user.
2. If you cannot be sure sessions are safe (for example a leaked cookie), have each affected person reset
   their password: that signs out all of their sessions.
3. Resume automation from the header.

## 4. Record
Incident time, who was affected, the cause, and the time of resume. The pause and resume are already in the
audit history.
