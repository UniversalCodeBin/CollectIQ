"""What the product can honestly list.

File-based and manual paths are not connections and never show as connected.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    key: str
    label: str
    kind: str  # FILE_BASED | MANUAL | PROVIDER
    note: str


ENTRIES: tuple[Entry, ...] = (
    Entry(
        "INVOICE_CSV", "Invoice CSV import", "FILE_BASED", "Upload a CSV file. Nothing syncs automatically."
    ),
    Entry(
        "STATEMENT_CSV", "Bank statement CSV import", "FILE_BASED", "Upload a statement file for matching."
    ),
    Entry("MANUAL_PAYMENT", "Manual payment record", "MANUAL", "A person records a payment by hand."),
    Entry(
        "MANUAL_REMINDER",
        "Manual reminder handoff",
        "MANUAL",
        "A person sends the approved message themselves.",
    ),
    Entry(
        "GMAIL",
        "Gmail (send only)",
        "PROVIDER",
        "Not verified against the provider until a verification succeeds.",
    ),
    Entry(
        "PAYPAL",
        "PayPal webhooks",
        "PROVIDER",
        "Not verified against the provider until a verification succeeds.",
    ),
)

PROVIDERS = tuple(e.key for e in ENTRIES if e.kind == "PROVIDER")
