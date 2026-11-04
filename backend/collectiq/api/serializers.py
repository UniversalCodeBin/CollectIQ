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
