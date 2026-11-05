"""Request validation and the response shapes the OpenAPI document describes."""

from typing import Any
from zoneinfo import available_timezones

from rest_framework import serializers

from collectiq.platform.money import ISO_4217_CODES

_BIGINT_MAX = 2**63 - 1


class StrictSerializer(serializers.Serializer):
    """An unexpected field is refused, so a typo cannot pass as an optional field left out."""

    def to_internal_value(self, data: Any) -> Any:
        if hasattr(data, "keys"):
            unknown = sorted(set(data.keys()) - set(self.fields))
            if unknown:
                raise serializers.ValidationError({name: "This field is not accepted." for name in unknown})
        return super().to_internal_value(data)


def _password(max_length: int = 1024) -> serializers.CharField:
    return serializers.CharField(trim_whitespace=False, max_length=max_length)


def _validate_timezone(value: str) -> str:
    if value not in available_timezones():
        raise serializers.ValidationError("Use an IANA time zone, such as Asia/Kolkata.")
    return value


def _validate_currency(value: str) -> str:
    if value not in ISO_4217_CODES:
        raise serializers.ValidationError("Use an ISO 4217 currency code, such as INR.")
    return value


def _email() -> serializers.EmailField:
    return serializers.EmailField(max_length=254)


class CredentialsIn(StrictSerializer):
    email = _email()
    password = _password()


class EmailIn(StrictSerializer):
    email = _email()


class TokenIn(StrictSerializer):
    token = serializers.CharField(max_length=512)


class PasswordResetConfirmIn(StrictSerializer):
    token = serializers.CharField(max_length=512)
    new_password = _password()


class WorkspaceCreateIn(StrictSerializer):
    name = serializers.CharField(max_length=200)
    country = serializers.RegexField(
        r"^[A-Z]{2}$", error_messages={"invalid": "Use a two-letter country code."}
    )
    timezone = serializers.CharField(max_length=64, validators=[_validate_timezone])
    default_currency = serializers.CharField(max_length=3, validators=[_validate_currency])
    business_hours = serializers.DictField(required=False)


class WorkspaceUpdateIn(StrictSerializer):
    name = serializers.CharField(max_length=200, required=False)
    timezone = serializers.CharField(max_length=64, required=False, validators=[_validate_timezone])
    default_currency = serializers.CharField(max_length=3, required=False, validators=[_validate_currency])
    business_hours = serializers.DictField(required=False)


class InvitationIn(StrictSerializer):
    email = _email()
    # PROJECT_LEAD is P1. It is refused here until it can be assigned to projects.
    role = serializers.ChoiceField(choices=["OWNER", "FINANCE_ADMIN"])


class MemberRoleIn(StrictSerializer):
    role = serializers.ChoiceField(choices=["OWNER", "FINANCE_ADMIN"])


class DetailOut(serializers.Serializer):
    detail = serializers.CharField()


class UserOut(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    email_verified = serializers.BooleanField()


class WorkspaceSummaryOut(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    role = serializers.CharField()


class LoginOut(serializers.Serializer):
    user = UserOut()
    workspaces = WorkspaceSummaryOut(many=True)


class SessionOut(LoginOut):
    csrf_token = serializers.CharField()


class WorkspaceOut(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    country = serializers.CharField()
    timezone = serializers.CharField()
    default_currency = serializers.CharField()
    business_hours = serializers.DictField()
    status = serializers.CharField()
    version = serializers.IntegerField()


class MemberOut(serializers.Serializer):
    id = serializers.UUIDField()
    user_id = serializers.UUIDField(allow_null=True)
    email = serializers.EmailField()
    role = serializers.CharField()
    status = serializers.CharField()


class MemberPageOut(serializers.Serializer):
    items = MemberOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class InvitationOut(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    role = serializers.CharField()
    status = serializers.CharField()
    expires_at = serializers.DateTimeField()


class InvitationAcceptedOut(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    role = serializers.CharField()


class HealthOut(serializers.Serializer):
    status = serializers.CharField()


_SENSITIVITY = ("STANDARD", "LONG_TERM", "SENSITIVE")
_TONE = ("NEUTRAL", "FRIENDLY", "FORMAL")


class ClientIn(StrictSerializer):
    display_name = serializers.CharField(max_length=200)
    sensitivity = serializers.ChoiceField(choices=_SENSITIVITY, required=False)
    tone = serializers.ChoiceField(choices=_TONE, required=False)


class ClientUpdateIn(StrictSerializer):
    display_name = serializers.CharField(max_length=200, required=False)
    sensitivity = serializers.ChoiceField(choices=_SENSITIVITY, required=False)
    tone = serializers.ChoiceField(choices=_TONE, required=False)


class ContactIn(StrictSerializer):
    email = _email()
    name = serializers.CharField(max_length=200, required=False)


class ContactUpdateIn(StrictSerializer):
    email = serializers.EmailField(max_length=254, required=False)
    name = serializers.CharField(max_length=200, required=False)


class SuppressionIn(StrictSerializer):
    reason = serializers.CharField(max_length=500)


class SuppressionClearIn(StrictSerializer):
    reason = serializers.CharField(max_length=500, required=False)


class ClientOut(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    normalized_name = serializers.CharField()
    sensitivity = serializers.CharField()
    tone = serializers.CharField()
    version = serializers.IntegerField()


class ClientPageOut(serializers.Serializer):
    items = ClientOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class ContactOut(serializers.Serializer):
    id = serializers.UUIDField()
    client_id = serializers.UUIDField()
    email = serializers.EmailField()
    name = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    suppression_reason = serializers.CharField(allow_null=True)


class AliasOut(serializers.Serializer):
    id = serializers.UUIDField()
    text = serializers.CharField()
    kind = serializers.CharField()


class ClientSummaryOut(serializers.Serializer):
    contacts_total = serializers.IntegerField()
    contacts_active = serializers.IntegerField()
    contacts_suppressed = serializers.IntegerField()


class ClientProfileOut(ClientOut):
    contacts = ContactOut(many=True)
    aliases = AliasOut(many=True)
    summary = ClientSummaryOut()


class ImportFieldErrorOut(serializers.Serializer):
    field = serializers.CharField()
    message = serializers.CharField()


class ImportRowOut(serializers.Serializer):
    row = serializers.IntegerField()
    status = serializers.CharField()
    invoice_number = serializers.CharField(allow_null=True)
    client_name = serializers.CharField(allow_null=True)
    currency = serializers.CharField(allow_null=True)
    errors = ImportFieldErrorOut(many=True)
    diffs = serializers.ListField(child=serializers.JSONField())
    matches = serializers.ListField(child=serializers.JSONField())
    allowed_decisions = serializers.ListField(child=serializers.CharField())
    conflict = serializers.JSONField(allow_null=True)


class ImportCandidateOut(serializers.Serializer):
    client_id = serializers.UUIDField()
    display_name = serializers.CharField()
    reason = serializers.CharField()


class ImportClientMatchOut(serializers.Serializer):
    name = serializers.CharField()
    display_name = serializers.CharField()
    rows = serializers.IntegerField()
    candidates = ImportCandidateOut(many=True)
    in_file = serializers.ListField(child=serializers.CharField())
    decision_required = serializers.BooleanField()


class AllowedActionOut(serializers.Serializer):
    action = serializers.CharField()
    allowed = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True)


class ImportBatchOut(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    status = serializers.CharField()
    file_name = serializers.CharField()
    scan_status = serializers.CharField()
    headers = serializers.ListField(child=serializers.CharField())
    suggested_mapping = serializers.DictField(child=serializers.CharField())
    date_format_options = serializers.ListField(child=serializers.CharField())
    mapping = serializers.DictField(child=serializers.CharField(), allow_null=True)
    date_format = serializers.CharField(allow_null=True)
    counts = serializers.DictField(child=serializers.IntegerField())
    rows = ImportRowOut(many=True)
    next_row = serializers.IntegerField(allow_null=True)
    client_matches = ImportClientMatchOut(many=True)
    failure_reason = serializers.CharField(allow_null=True)
    allowed_actions = AllowedActionOut(many=True)


class ImportMappingIn(StrictSerializer):
    mapping = serializers.DictField(child=serializers.CharField())
    date_format = serializers.CharField(required=False, allow_null=True)


class ImportRowDecisionIn(StrictSerializer):
    action = serializers.ChoiceField(["UPDATE", "IGNORE", "KEEP_BOTH", "MERGE"], required=False)
    total_source = serializers.ChoiceField(["TOTAL", "SUM"], required=False)


class ImportClientDecisionIn(StrictSerializer):
    action = serializers.ChoiceField(["LINK", "SAME_AS", "NEW"])
    client_id = serializers.UUIDField(required=False)
    name = serializers.CharField(required=False, max_length=200)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["action"] == "LINK" and "client_id" not in attrs:
            raise serializers.ValidationError({"client_id": "Choose the client to link to."})
        if attrs["action"] == "SAME_AS" and "name" not in attrs:
            raise serializers.ValidationError({"name": "Choose the name this one is the same as."})
        return attrs


class ImportDecisionsIn(StrictSerializer):
    skip_invalid = serializers.BooleanField(required=False)
    rows = serializers.DictField(child=ImportRowDecisionIn(), required=False)
    clients = serializers.DictField(child=ImportClientDecisionIn(), required=False)


class ImportCommitIn(StrictSerializer):
    decisions = ImportDecisionsIn(required=False)


class ReasonOut(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    link = serializers.CharField()


class WhyNotOut(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()


class RecommendedActionOut(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    can_act = serializers.BooleanField()
    performed_by = serializers.ListField(child=serializers.CharField())
    reason = serializers.CharField(allow_null=True)


class InvoiceRowOut(serializers.Serializer):
    id = serializers.UUIDField()
    invoice_number = serializers.CharField()
    client_id = serializers.UUIDField()
    client_name = serializers.CharField()
    currency = serializers.CharField()
    status = serializers.CharField()
    due_date = serializers.DateField()
    outstanding_minor = serializers.IntegerField()
    paid_minor = serializers.IntegerField()
    payment_status = serializers.CharField()
    dispute_status = serializers.CharField()
    reminder_status = serializers.CharField()
    evidence_coverage = serializers.CharField()
    evidence_as_of = serializers.DateTimeField(allow_null=True)
    days_overdue = serializers.IntegerField()
    due_bucket = serializers.CharField()
    allowed_actions = AllowedActionOut(many=True)


class InvoicePageOut(serializers.Serializer):
    items = InvoiceRowOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class QueueItemOut(InvoiceRowOut):
    tier = serializers.IntegerField()
    reasons = ReasonOut(many=True)
    why_not = WhyNotOut(many=True)
    recommended_action = RecommendedActionOut(allow_null=True)
    sample = serializers.BooleanField()


class QueuePageOut(serializers.Serializer):
    items = QueueItemOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class InvoiceDetailOut(serializers.Serializer):
    version = serializers.IntegerField()
    facts = serializers.DictField()
    derived = serializers.DictField()
    ai_claims = serializers.ListField(child=serializers.DictField())
    provenance = serializers.DictField()
    recommended_action = RecommendedActionOut(allow_null=True)
    reasons = ReasonOut(many=True)
    why_not = WhyNotOut(many=True)
    allowed_actions = AllowedActionOut(many=True)


class InvoiceCorrectionIn(StrictSerializer):
    invoice_number = serializers.CharField(max_length=64, required=False)
    due_date = serializers.DateField(required=False)
    issue_date = serializers.DateField(required=False)
    gross_minor = serializers.IntegerField(min_value=0, required=False)
    po_number = serializers.CharField(max_length=64, required=False, allow_null=True)
    project_ref = serializers.CharField(max_length=64, required=False, allow_null=True)
    description = serializers.CharField(max_length=500, required=False, allow_null=True)
    payment_terms = serializers.CharField(max_length=64, required=False, allow_null=True)
    reason = serializers.CharField(max_length=500)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if len(attrs) < 2:
            raise serializers.ValidationError({"invoice_number": "Change at least one field."})
        return attrs


class InvoiceReasonIn(StrictSerializer):
    reason = serializers.CharField(max_length=500)


class DashboardEntryOut(serializers.Serializer):
    count = serializers.IntegerField()
    amount_minor = serializers.IntegerField()
    filter = serializers.DictField(child=serializers.CharField())


class DashboardTileOut(DashboardEntryOut):
    key = serializers.CharField()


class DashboardAgingOut(DashboardEntryOut):
    bucket = serializers.CharField()


class DashboardCurrencyOut(serializers.Serializer):
    currency = serializers.CharField()
    tiles = DashboardTileOut(many=True)
    aging = DashboardAgingOut(many=True)


class DashboardOut(serializers.Serializer):
    currencies = DashboardCurrencyOut(many=True)
    has_sample_data = serializers.BooleanField()
    as_of_date = serializers.DateField()


# ---- payment accounts, coverage and attestations (E029-E032, E054) -----------------------------

_ACCOUNT_KIND = ["BANK", "PAYPAL", "UPI", "CASH"]
_ACCOUNT_STATUS = ["ACTIVE", "INACTIVE"]


class PaymentAccountIn(StrictSerializer):
    kind = serializers.ChoiceField(choices=_ACCOUNT_KIND)
    label = serializers.CharField(max_length=100)
    currency = serializers.ChoiceField(choices=sorted(ISO_4217_CODES))


class PaymentAccountUpdateIn(StrictSerializer):
    label = serializers.CharField(max_length=100, required=False)
    status = serializers.ChoiceField(choices=_ACCOUNT_STATUS, required=False)


class PaymentAccountOut(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    label = serializers.CharField()
    currency = serializers.CharField()
    status = serializers.CharField()
    version = serializers.IntegerField()


class PaymentAccountSummaryOut(PaymentAccountOut):
    covered_through = serializers.DateField(allow_null=True)
    statements_through = serializers.DateField(allow_null=True)
    attested_through = serializers.DateField(allow_null=True)
    coverage_status = serializers.CharField()
    gaps = serializers.ListField(child=serializers.DictField())


class PaymentAccountPageOut(serializers.Serializer):
    items = PaymentAccountSummaryOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class AccountCoverageOut(serializers.Serializer):
    account = PaymentAccountOut()
    covered_through = serializers.DateField(allow_null=True)
    statements_through = serializers.DateField(allow_null=True)
    attested_through = serializers.DateField(allow_null=True)
    coverage_status = serializers.CharField()
    freshness_window_days = serializers.IntegerField()
    fresh_until = serializers.DateField(allow_null=True)
    gaps = serializers.ListField(child=serializers.DictField())
    ranges = serializers.ListField(child=serializers.DictField())
    attestations = serializers.ListField(child=serializers.DictField())


class AttestationIn(StrictSerializer):
    scope = serializers.ChoiceField(choices=["ACCOUNT", "INVOICE"])
    account_id = serializers.UUIDField(required=False)
    invoice_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=False)
    as_of = serializers.DateTimeField()
    note = serializers.CharField(max_length=1000, required=False, allow_blank=False)


class AttestationOut(serializers.Serializer):
    scope = serializers.CharField()
    as_of = serializers.DateTimeField()
    coverage_date = serializers.DateField()
    attestation_ids = serializers.ListField(child=serializers.UUIDField())


class StatementCountsOut(serializers.Serializer):
    total_rows = serializers.IntegerField()
    added = serializers.IntegerField()
    skipped_duplicate = serializers.IntegerField()
    held_for_confirmation = serializers.IntegerField()
    discarded_debits = serializers.IntegerField()
    invalid = serializers.IntegerField()


class StatementRowErrorOut(serializers.Serializer):
    row = serializers.IntegerField()
    field = serializers.CharField()
    message = serializers.CharField()


class StatementHeldRowOut(serializers.Serializer):
    row = serializers.IntegerField()
    reason = serializers.CharField()


class StatementCoverageOut(serializers.Serializer):
    covers_from = serializers.DateField()
    covers_to = serializers.DateField()


class StatementImportOut(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True)
    status = serializers.CharField()
    dry_run = serializers.BooleanField()
    counts = StatementCountsOut()
    errors = StatementRowErrorOut(many=True)
    held_rows = StatementHeldRowOut(many=True)
    coverage = StatementCoverageOut(allow_null=True)


class UnmatchedTransactionOut(serializers.Serializer):
    id = serializers.UUIDField()
    amount_minor = serializers.IntegerField()
    currency = serializers.CharField()
    value_date = serializers.DateField()
    reference = serializers.CharField(allow_null=True)
    payer_descriptor = serializers.CharField(allow_null=True)
    account_label = serializers.CharField(allow_null=True)
    source_type = serializers.CharField()
    remaining_minor = serializers.IntegerField()
    proposal_count = serializers.IntegerField()


class UnmatchedPageOut(serializers.Serializer):
    items = UnmatchedTransactionOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class ProposalReasonOut(serializers.Serializer):
    code = serializers.CharField()
    text = serializers.CharField()


class ProposalOut(serializers.Serializer):
    id = serializers.UUIDField()
    label = serializers.ChoiceField(choices=["Strong", "Possible", "Weak"])
    ambiguous = serializers.BooleanField()
    reasons = ProposalReasonOut(many=True)
    transaction = serializers.DictField()
    invoice = serializers.DictField()


class ProposalPageOut(serializers.Serializer):
    items = ProposalOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class _StrictIntegerField(serializers.IntegerField):
    """Money is a JSON integer. "100", 100.0 and true are refused rather than coerced."""

    def to_internal_value(self, data: Any) -> int:
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class _StrictBooleanField(serializers.BooleanField):
    """A money decision is a JSON boolean, never "true" or 1 by accident."""

    def to_internal_value(self, data: Any) -> bool:
        if not isinstance(data, bool):
            self.fail("invalid", input=data)
        return data


def _amount_minor() -> _StrictIntegerField:
    return _StrictIntegerField(min_value=1, max_value=_BIGINT_MAX)


def _reason_text(required: bool = True) -> serializers.CharField:
    return serializers.CharField(max_length=500, required=required)


class AllocationLineIn(StrictSerializer):
    invoice_id = serializers.UUIDField()
    amount_minor = _amount_minor()
    overpayment_confirmed = _StrictBooleanField(required=False, default=False)


class AllocationIn(StrictSerializer):
    transaction_id = serializers.UUIDField()
    allocations = AllocationLineIn(many=True, allow_empty=False)


class ProposalConfirmIn(StrictSerializer):
    allocations = AllocationLineIn(many=True, allow_empty=False)


class ProposalRejectIn(StrictSerializer):
    reason = _reason_text(required=False)


class ReasonIn(StrictSerializer):
    reason = _reason_text()


class DuplicateIn(StrictSerializer):
    duplicate_of = serializers.UUIDField()


class MoneyIn(StrictSerializer):
    amount_minor = _amount_minor()
    currency = serializers.ChoiceField(choices=sorted(ISO_4217_CODES))


class PaymentIn(StrictSerializer):
    method = serializers.ChoiceField(choices=["BANK_TRANSFER", "UPI", "CASH", "PAYPAL_MANUAL", "OTHER"])
    amount = MoneyIn()
    value_date = serializers.DateField()
    reference = serializers.CharField(max_length=140, required=False)
    payer = serializers.CharField(max_length=200, required=False)
    notes = serializers.CharField(max_length=500, required=False)
    allocations = AllocationLineIn(many=True, required=False)


class PaymentAttachmentOut(serializers.Serializer):
    file_name = serializers.CharField()
    size_bytes = serializers.IntegerField()
    content_type = serializers.CharField()


class PaymentOut(serializers.Serializer):
    id = serializers.UUIDField()
    source_type = serializers.CharField()
    method = serializers.CharField(allow_null=True)
    amount_minor = serializers.IntegerField()
    currency = serializers.CharField()
    allocated_minor = serializers.IntegerField()
    unallocated_minor = serializers.IntegerField()
    value_date = serializers.DateField()
    reference = serializers.CharField(allow_null=True)
    payer_descriptor = serializers.CharField(allow_null=True)
    notes = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    evidence_type = serializers.CharField()
    lower_assurance = serializers.BooleanField()
    account_label = serializers.CharField(allow_null=True)
    entered_by = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    void_reason = serializers.CharField(allow_null=True)
    duplicate_of_transaction_id = serializers.UUIDField(allow_null=True)
    attachment = PaymentAttachmentOut(allow_null=True)


class PaymentPageOut(serializers.Serializer):
    items = PaymentOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class PaymentAllocationOut(serializers.Serializer):
    id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    invoice_number = serializers.CharField(required=False)
    amount_minor = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=["ALLOCATION", "REVERSAL"])
    reverses_allocation_id = serializers.UUIDField(allow_null=True)
    match_id = serializers.UUIDField(allow_null=True)
    overpayment_confirmed = serializers.BooleanField()
    evidence_type = serializers.CharField()
    confirmed_by = serializers.UUIDField()
    note = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()


class InvoicePaymentHistoryItemOut(PaymentAllocationOut):
    transaction_id = serializers.UUIDField()
    value_date = serializers.DateField()
    payer_descriptor = serializers.CharField(allow_null=True)
    currency = serializers.CharField()


class InvoicePaymentHistoryOut(serializers.Serializer):
    items = InvoicePaymentHistoryItemOut(many=True)


class InvoiceStateOut(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    payment_status = serializers.CharField()
    paid_minor = serializers.IntegerField()
    outstanding_minor = serializers.IntegerField()
    overpayment_flag = serializers.BooleanField()
    reminder_status = serializers.CharField()
    version = serializers.IntegerField()


class LedgerResultOut(serializers.Serializer):
    payment = PaymentOut()
    allocations = PaymentAllocationOut(many=True)
    invoice_states = InvoiceStateOut(many=True)


class PaymentMatchOut(serializers.Serializer):
    id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    status = serializers.CharField()
    label = serializers.ChoiceField(choices=["Strong", "Possible", "Weak"])
    ambiguous = serializers.BooleanField()
    decided_at = serializers.DateTimeField(allow_null=True)
    decision_reason = serializers.CharField(allow_null=True)


class PaymentDetailOut(PaymentOut):
    allocations = PaymentAllocationOut(many=True)
    matches = PaymentMatchOut(many=True)


class ProposalRejectedOut(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["REJECTED"])
    invoice_states = InvoiceStateOut(many=True)


# --- policy (E016-E020, E092, E101) -------------------------------------------------------------------------


class PolicyLimitsIn(StrictSerializer):
    max_contacts = serializers.IntegerField(min_value=1, max_value=20, required=False)


class PolicyIn(StrictSerializer):
    mode = serializers.ChoiceField(choices=["MANUAL", "ASSISTED"], required=False)
    auto_snooze_enabled = serializers.BooleanField(required=False)
    cadence = serializers.DictField(
        child=serializers.IntegerField(min_value=0, max_value=365), required=False
    )
    limits = PolicyLimitsIn(required=False)
    business_hours = serializers.DictField(required=False)
    sensitivity_defaults = serializers.DictField(child=serializers.CharField(max_length=100), required=False)


class PauseIn(StrictSerializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=False)


class PolicyOut(serializers.Serializer):
    version = serializers.IntegerField()
    mode = serializers.ChoiceField(choices=["MANUAL", "ASSISTED"])
    automation_paused = serializers.BooleanField()
    auto_snooze_enabled = serializers.BooleanField()
    auto_snooze_available = serializers.BooleanField()
    cadence = serializers.DictField()
    limits = serializers.DictField()
    business_hours = serializers.DictField()
    sensitivity_defaults = serializers.DictField()
    changed_by = serializers.UUIDField(allow_null=True)
    effective_from = serializers.DateTimeField()


class PolicyVersionsOut(serializers.Serializer):
    items = PolicyOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class ApprovalDecisionIn(StrictSerializer):
    decision = serializers.ChoiceField(choices=["APPROVED", "REJECTED"])
    note = serializers.CharField(max_length=500, required=False, allow_blank=False)


class ApprovalOut(serializers.Serializer):
    id = serializers.UUIDField()
    decision_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["PENDING", "APPROVED", "REJECTED"])
    decided_by = serializers.UUIDField(allow_null=True)
    decided_at = serializers.DateTimeField(allow_null=True)
    note = serializers.CharField(allow_null=True)


class GateOut(serializers.Serializer):
    gate = serializers.CharField()
    passed = serializers.BooleanField()
    text = serializers.CharField()


class PolicyDecisionOut(serializers.Serializer):
    id = serializers.UUIDField()
    action_type = serializers.CharField()
    outcome = serializers.CharField()
    explanation = serializers.ListField(child=serializers.CharField())
    gates = GateOut(many=True)
    policy_version = serializers.IntegerField()
    rules_version = serializers.CharField()
    state_version = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    consumed_at = serializers.DateTimeField(allow_null=True)
    approval = ApprovalOut(allow_null=True)


# --- cases (E076-E082) ---


class CaseIn(StrictSerializer):
    invoice_id = serializers.UUIDField()
    type = serializers.ChoiceField(choices=["DISPUTE", "MISSING_DOCUMENT", "QUESTION", "PROPOSAL"])
    summary = serializers.CharField(max_length=2000)
    dispute_type = serializers.ChoiceField(
        choices=["AMOUNT", "DELIVERABLE", "SERVICE", "OTHER"], required=False
    )
    source_message_id = serializers.UUIDField(required=False)


class CaseUpdateIn(StrictSerializer):
    assignee_id = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=["OPEN", "IN_REVIEW", "AWAITING_CUSTOMER"], required=False)
    note = serializers.CharField(max_length=2000, required=False)


class CaseResolveIn(StrictSerializer):
    outcome = serializers.ChoiceField(
        choices=["NO_CHANGE", "INVOICE_CORRECTED", "ADJUSTMENT_AGREED", "WITHDRAWN_BY_CUSTOMER", "OTHER"]
    )
    note = serializers.CharField(max_length=2000, required=False)


class CaseReopenIn(StrictSerializer):
    reason = serializers.CharField(max_length=2000)


class CaseNoteOut(serializers.Serializer):
    id = serializers.UUIDField()
    author_id = serializers.UUIDField()
    kind = serializers.CharField()
    body = serializers.CharField()
    created_at = serializers.DateTimeField()


class CaseOut(serializers.Serializer):
    id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    invoice_number = serializers.CharField()
    type = serializers.CharField()
    status = serializers.CharField()
    dispute_type = serializers.CharField(allow_null=True)
    summary = serializers.CharField()
    summary_is_ai_derived = serializers.BooleanField()
    source_message_id = serializers.UUIDField(allow_null=True)
    assignee_id = serializers.UUIDField(allow_null=True)
    opened_by_kind = serializers.CharField()
    opened_at = serializers.DateTimeField()
    resolution_outcome = serializers.CharField(allow_null=True)
    resolution_note = serializers.CharField(allow_null=True)
    resolved_by = serializers.UUIDField(allow_null=True)
    resolved_at = serializers.DateTimeField(allow_null=True)
    reopen_count = serializers.IntegerField()
    version = serializers.IntegerField()


class CaseDetailOut(CaseOut):
    notes = CaseNoteOut(many=True)


class CasePageOut(serializers.Serializer):
    items = CaseOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class ResumeIn(StrictSerializer):
    approval_id = serializers.UUIDField()


class ResumeOut(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    dispute_status = serializers.CharField()
    reminder_status = serializers.CharField()


class AssociationIn(StrictSerializer):
    invoice_id = serializers.UUIDField()
    labels = serializers.ListField(
        child=serializers.ChoiceField(
            choices=[
                "PAYMENT_CLAIM",
                "COMMITMENT_EXPLICIT",
                "EXPECTATION_TENTATIVE",
                "DOCUMENT_REQUEST",
                "DISPUTE",
                "PAUSE_REQUEST",
                "CLARIFICATION_REQUEST",
                "PARTIAL_PAYMENT_PROPOSAL",
                "WRONG_RECIPIENT_OR_OPT_OUT",
                "UNRELATED_OR_AMBIGUOUS",
            ]
        ),
        required=False,
        max_length=10,
    )


class AssociationsIn(StrictSerializer):
    invoice_ids = AssociationIn(many=True, max_length=20)


class AssociationOut(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    invoice_number = serializers.CharField()
    labels = serializers.ListField(child=serializers.CharField())


class EffectOut(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    label = serializers.CharField()
    effect = serializers.CharField(allow_null=True)


class MessageOut(serializers.Serializer):
    id = serializers.UUIDField()
    source = serializers.CharField()
    sender = serializers.CharField(allow_null=True)
    subject = serializers.CharField(allow_null=True)
    received_at = serializers.DateTimeField()
    uploaded_by = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    is_customer_statement = serializers.BooleanField()
    associations = AssociationOut(many=True)
    body = serializers.CharField(required=False)
    preview = serializers.CharField(required=False)
    effects = EffectOut(many=True, required=False)


class MessagePageOut(serializers.Serializer):
    items = MessageOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class TimelinePageOut(serializers.Serializer):
    items = serializers.ListField(child=serializers.DictField())
    next_cursor = serializers.CharField(allow_null=True)


class CommitmentIn(StrictSerializer):
    invoice_id = serializers.UUIDField()
    strength = serializers.ChoiceField(choices=["EXPLICIT", "TENTATIVE"])
    date = serializers.DateField(required=False)
    window_start = serializers.DateField(required=False)
    window_end = serializers.DateField(required=False)
    note = serializers.CharField(max_length=1000, required=False)


class CommitmentUpdateIn(StrictSerializer):
    status = serializers.ChoiceField(choices=["WITHDRAWN", "BROKEN"], required=False)
    note = serializers.CharField(max_length=1000, required=False)


class SnoozeProposalOut(serializers.Serializer):
    outcome = serializers.CharField()
    reasons = serializers.ListField(child=serializers.CharField())
    approval_id = serializers.UUIDField(allow_null=True)
    until = serializers.DateField()


class SnoozeOut(serializers.Serializer):
    id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    commitment_id = serializers.UUIDField(allow_null=True)
    until = serializers.DateField()
    status = serializers.CharField()
    approval_id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    activated_at = serializers.DateTimeField(allow_null=True)
    ended_at = serializers.DateTimeField(allow_null=True)


class CommitmentOut(serializers.Serializer):
    id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    source_message_id = serializers.UUIDField(allow_null=True)
    strength = serializers.CharField()
    promised_date = serializers.DateField(allow_null=True)
    window_start = serializers.DateField(allow_null=True)
    window_end = serializers.DateField(allow_null=True)
    status = serializers.CharField()
    note = serializers.CharField(allow_null=True)
    created_by = serializers.UUIDField()
    version = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class CommitmentRecordedOut(CommitmentOut):
    snooze = SnoozeProposalOut(allow_null=True)
    snooze_note = serializers.CharField(allow_null=True)


class CommitmentPageOut(serializers.Serializer):
    items = CommitmentOut(many=True)
    snoozes = SnoozeOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class SnoozeApproveIn(StrictSerializer):
    approval_id = serializers.UUIDField()


class SnoozeUndoIn(StrictSerializer):
    reason = serializers.CharField(max_length=500, required=False)


class SnoozeStartedOut(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    reminder_status = serializers.CharField()
    until = serializers.DateField()


class SnoozeUndoneOut(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    reminder_status = serializers.CharField()


class GateResultOut(serializers.Serializer):
    gate = serializers.CharField()
    passed = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True)


class GateReadingOut(serializers.Serializer):
    outcome = serializers.CharField()
    reasons = serializers.ListField(child=serializers.CharField())
    gate_results = GateResultOut(many=True)


class ReminderOut(serializers.Serializer):
    id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    invoice_number = serializers.CharField()
    contact_id = serializers.UUIDField()
    recipient = serializers.CharField()
    sequence = serializers.IntegerField()
    intended_date = serializers.DateField()
    status = serializers.CharField()
    subject = serializers.CharField()
    body = serializers.CharField()
    fact_block = serializers.DictField()
    approved_by = serializers.UUIDField(allow_null=True)
    approved_at = serializers.DateTimeField(allow_null=True)
    sent_at = serializers.DateTimeField(allow_null=True)
    method = serializers.CharField(allow_null=True)
    marked_by = serializers.UUIDField(allow_null=True)
    reason = serializers.CharField(allow_null=True)
    version = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class ReminderDetailOut(ReminderOut):
    gates = GateReadingOut(allow_null=True)


class ReminderPageOut(serializers.Serializer):
    items = ReminderOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class ReminderEvaluationOut(GateReadingOut):
    invoice_id = serializers.UUIDField()
    reminder = ReminderOut(allow_null=True)


class ReminderEditIn(StrictSerializer):
    body = serializers.CharField(max_length=5000, trim_whitespace=False)


class ReminderRejectIn(StrictSerializer):
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=False)


class ReminderSentIn(StrictSerializer):
    sent_at = serializers.DateTimeField()
    method = serializers.ChoiceField(choices=["EMAIL", "WHATSAPP", "PHONE", "OTHER"])


class NotificationOut(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.ChoiceField(choices=["CASE_OPENED", "REMINDER_DRAFT_READY"])
    subject_ref = serializers.DictField(child=serializers.CharField())
    target_route = serializers.CharField()
    action = serializers.CharField()
    created_at = serializers.DateTimeField()
    read_at = serializers.DateTimeField(allow_null=True)


class NotificationPageOut(serializers.Serializer):
    items = NotificationOut(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class InboxItemOut(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=["CASE", "REMINDER_DRAFT", "MATCH_PROPOSAL", "PAYMENT_CLAIM", "APPROVAL"]
    )
    subject_ref = serializers.DictField(child=serializers.CharField())
    target_route = serializers.CharField()
    action = serializers.CharField()
    created_at = serializers.DateTimeField()


class InboxOut(serializers.Serializer):
    items = InboxItemOut(many=True)
    counts = serializers.DictField(child=serializers.IntegerField())
