"""Plain words for a decision (SCR-09 why-view). Names no gate codes, tables or internals."""

from .model import Outcome, PolicyDecision

GATE_TEXT = {
    "G1": "The invoice is no longer active.",
    "G2": "The invoice is already verified as paid.",
    "G3": "The invoice is cancelled, written off or archived.",
    "G4": "There is a dispute on this invoice that is not settled yet.",
    "G5": "A task on this invoice still needs a person to decide something.",
    "G6": "The payment evidence is missing or out of date, so the balance may be wrong.",
    "G7": "The payment status is not one that allows a follow-up, for example a payment still being checked.",
    "G8": "Follow-ups are on hold until a snooze or promised date passes.",
    "G9": "The person to contact is not approved, or has been suppressed.",
    "G10": "The limit on how often this customer is contacted has been reached.",
    "G11": "It is outside business hours, so sending is held until they start.",
    "G12": "The facts in the draft no longer match the invoice.",
    "G13": "Automation is paused, switched off, or this case needs a person.",
    "G14": "This exact action was already carried out.",
    "G15": "The connected mailbox is not healthy.",
}

_OTHER = {
    "AUTOMATION_PAUSED": "Automation is paused for this workspace.",
    "FORBIDDEN_ACTION": "This action does not exist in CollectIQ and is always refused.",
    "HUMAN_ONLY": "Only a person with the right role can do this, never the system or the AI.",
    "AI_CONFIDENCE_TOO_LOW": "The reading is not certain enough to act on its own.",
    "INJECTION_SUSPECTED": "The message looks like it gives instructions, so nothing runs on its own.",
    "POLICY_ENGINE_ERROR": "The safety check could not finish, so the action was refused.",
    "APPROVAL_REQUIRED": "A person must approve this before anything is sent.",
}

_HEADLINE = {
    Outcome.ALLOW_AUTOMATIC: "Allowed.",
    Outcome.REQUIRE_APPROVAL: "Waiting for a person to approve.",
    Outcome.DENY: "Refused.",
    Outcome.DEFER: "Held for later.",
    Outcome.PAUSE_FOR_REVIEW: "Held for review.",
    Outcome.CANCEL: "Cancelled; no follow-up is needed.",
}


def explain(decision: PolicyDecision) -> list[str]:
    lines = [_HEADLINE[decision.outcome]]
    for reason in decision.reasons:
        code = reason.split("_", 1)[0]
        if code in GATE_TEXT:
            lines.append(GATE_TEXT[code])
        else:
            key = next((k for k in _OTHER if reason.startswith(k)), None)
            lines.append(_OTHER[key] if key else "A rule held this action.")
    return lines
