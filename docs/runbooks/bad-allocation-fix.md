# Fixing a bad allocation

Use when a payment was allocated to the wrong invoice, for the wrong amount, or a transaction was counted
twice.

Allocations are append-only. They are never edited or deleted; a mistake is fixed by reversing it and, if
needed, allocating again. Every step needs the Owner or Finance admin role and is recorded.

## 1. Look before changing
1. Open the invoice's Payment history and the payment. Note the allocation, its amount and who confirmed it.
2. Audit History: filter by object type `allocation` to see who confirmed it and from which proposal.
3. A duplicated transaction: check whether the same bank line was imported twice. A transaction marked as a
   duplicate (E061) cannot be allocated, and a transaction already allocated cannot be allocated twice.

## 2. Reverse
1. Reverse the wrong allocation (E060) with a reason. The invoice's paid and outstanding amounts and its
   status are recomputed from the remaining allocations, so the invoice returns to the right state.
2. If a manually entered payment was a mistake, void it (E052). Voiding it also withdraws every allocation made
   from it. A statement row is never voided; mark it as a duplicate instead (E061).
3. If a customer's message was wrongly treated as proof, remember that a customer's statement never marks an
   invoice paid; check the invoice shows `AWAITING_VERIFICATION`, not paid.

## 3. Allocate correctly
1. Open Payment Reconciliation. The payment shows again as unmatched or with proposals.
2. Confirm the right proposal or allocate to the right invoice (E059). Amounts are whole minor units.

## 4. Check
- Both invoices show the expected paid and outstanding amounts, and Payment history lists the allocation and
  its reversal.
- Reminders that were drafted against the wrong state are stale; regenerate them.
- Run the integrity job result in the audit view if you suspect drift: a repair is logged as
  `invoice_state.drift_repaired`.
