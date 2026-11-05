"""Request validation and the response shapes the OpenAPI document describes."""

from typing import Any
from zoneinfo import available_timezones

from rest_framework import serializers

from collectiq.platform.money import ISO_4217_CODES


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
