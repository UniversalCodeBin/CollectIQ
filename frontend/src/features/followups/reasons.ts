/** Plain words for why a follow-up is held. The server sends codes such as G4_DISPUTE; people never see them. */
const BY_GATE: Record<string, string> = {
  G1: "The invoice is no longer active.",
  G2: "The invoice is already verified as paid.",
  G3: "The invoice is cancelled, written off or archived.",
  G4: "There is a dispute on this invoice that is not settled yet.",
  G5: "A task on this invoice still needs a person to decide something.",
  G6: "The payment evidence is missing or out of date, so the balance may be wrong.",
  G7: "The payment status does not allow a follow-up, for example a payment still being checked.",
  G8: "Follow-ups are on hold until a snooze or promised date passes.",
  G9: "The person to contact is not approved, or has been suppressed.",
  G10: "The limit on how often this customer is contacted has been reached.",
  G11: "It is outside business hours, so sending is held until they start.",
  G12: "The facts in the draft no longer match the invoice. Refresh the draft.",
  G13: "Reminders are paused (workspace, client or invoice), or this case needs a person.",
  G14: "This exact reminder was already handled.",
  G15: "The connected mailbox is not healthy.",
};
const OTHER: Record<string, string> = {
  AUTOMATION_PAUSED: "Automation is paused for this workspace.",
  APPROVAL_REQUIRED: "A person must approve this before anything is sent.",
};
const FALLBACK = "A rule is holding this reminder.";

export function plainReason(code: string): string {
  const gate = /^(G\d{1,2})(?:_|$)/.exec(code)?.[1];
  if (gate) return BY_GATE[gate] ?? FALLBACK;
  return OTHER[code] ?? FALLBACK;
}

/** Every reason worth showing, once each, in plain words. An approval prompt is not a block. */
export function plainReasons(reasons: string[]): string[] {
  return [...new Set(reasons.filter((r) => r !== "APPROVAL_REQUIRED").map(plainReason))];
}

export const STATUS_TEXT: Record<string, string> = {
  DRAFT: "Draft awaiting approval",
  APPROVED: "Ready to send",
  MARKED_SENT: "Marked sent",
  SUBMITTING: "Sending to Gmail",
  SUBMITTED: "Handed to Gmail. Delivery is not confirmed.",
  SUBMISSION_UNKNOWN: "We could not tell whether Gmail took it",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
};
