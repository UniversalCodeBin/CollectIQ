/** Plain words for the readings a person attached to a reply. A reading is never a fact about payment. */
export const LABEL_TEXT: Record<string, string> = {
  PAYMENT_CLAIM: "Customer says they paid",
  COMMITMENT_EXPLICIT: "Firm promise to pay",
  EXPECTATION_TENTATIVE: "Possible timing mentioned",
  DOCUMENT_REQUEST: "Asks for a document",
  DISPUTE: "Disputes the invoice",
  PAUSE_REQUEST: "Asks to pause reminders",
  CLARIFICATION_REQUEST: "Asks a question",
  PARTIAL_PAYMENT_PROPOSAL: "Proposes part payment",
  WRONG_RECIPIENT_OR_OPT_OUT: "Wrong recipient or opt-out",
  UNRELATED_OR_AMBIGUOUS: "Unrelated or unclear",
};

export const labelText = (label: string) => LABEL_TEXT[label] ?? label;
