# Wrong-send suspicion

Use when someone thinks a reminder went to the wrong person, said the wrong amount, or went out when it
should have been blocked.

What the system guarantees: nothing is sent without a person approving the exact text, and the send
button re-checks every gate at that moment. The word shown is "submitted", never "delivered".

## 1. Contain
1. Pause automation (E019) so no further reminder is approved or submitted.
2. Open the reminder. Note its status:
   - `APPROVED`: nothing was submitted by the system.
   - `SUBMITTING`: a send is in progress or was interrupted.
   - `SUBMITTED`: the provider accepted the message.
   - `SUBMISSION_UNKNOWN`: the outcome could not be known. The system never retries it.

## 2. Find out what happened
1. Audit History: filter by object type `reminder` and the reminder's ID. Read, in order: created, approved
   (who, which text), `reminder.submitting`, `reminder.submitted` or `reminder.submission_unknown`.
2. Compare the approved text with the invoice at that time: the amount, recipient and invoice number are in
   the draft facts. A draft goes stale when the invoice changes, and a stale draft cannot be approved.
3. Open the conversation thread and the sent folder of the connected mailbox to see whether the message
   really left. The mailbox is the source of truth for "sent".

## 3. Resolve
- `SUBMISSION_UNKNOWN` and the mailbox shows it was sent: answer **Was sent** (E091). It becomes SUBMITTED.
- `SUBMISSION_UNKNOWN` and the mailbox shows nothing: answer **Not sent**. It returns to APPROVED and a person
  may send it again later.
- A wrong message was sent: contact the customer yourself. The system does not retract email. Add a case
  note on the invoice, and open a case if there is a dispute so reminders stay blocked.
- A recipient was wrong: suppress that contact (E027) so no reminder can use it, then correct the contact.

## 4. Before resuming
Confirm the cause (wrong recipient data, stale draft approved, or a gate that should have blocked). If a
gate should have blocked and did not, stop and report it; do not resume. Then resume automation.
