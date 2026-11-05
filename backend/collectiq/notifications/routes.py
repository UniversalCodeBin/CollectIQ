"""Where each kind of item leads and the action that resolves it. Routes are relative to /w/:ws/."""

from typing import Any

# kind -> (route template, action). The template is filled from the item's subject_ref.
ROUTES: dict[str, tuple[str, str]] = {
    "CASE_OPENED": ("invoices/{invoice_id}/overview", "Review the case"),
    "REMINDER_DRAFT_READY": ("reminders/{reminder_id}", "Review the draft"),
    "CASE": ("invoices/{invoice_id}/overview", "Review the case"),
    "REMINDER_DRAFT": ("reminders/{reminder_id}", "Approve or reject the draft"),
    "MATCH_PROPOSAL": ("reconciliation/review", "Confirm or reject the match"),
    "PAYMENT_CLAIM": ("invoices/{invoice_id}/overview", "Verify the payment claim"),
    "APPROVAL": ("followups", "Approve or reject the request"),
}


def target(kind: str, subject_ref: dict[str, Any]) -> tuple[str, str]:
    template, action = ROUTES[kind]
    return template.format(**subject_ref), action
