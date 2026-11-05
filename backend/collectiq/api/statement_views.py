"""Statement import (E053). The rules are in `evidence.service_statements`."""

import json
from datetime import date
from typing import Any
from uuid import UUID

from rest_framework.response import Response
from rest_framework.views import APIView

from collectiq.evidence import service_statements as service
from collectiq.platform.idempotency import idempotent

from .common import invalid
from .registry import endpoint
from .serializers import StatementImportOut

_BODY = {
    "multipart/form-data": {
        "type": "object",
        "properties": {
            "file": {"type": "string", "format": "binary"},
            "source_type": {"type": "string", "enum": list(service.SOURCE_TYPES)},
            "payment_account_id": {"type": "string", "format": "uuid"},
            "mapping": {
                "type": "string",
                "description": "JSON: date, description, amount or credit/debit, ...",
            },
            "date_format": {"type": "string"},
            "include_debits": {"type": "boolean"},
            "coverage_from": {"type": "string", "format": "date"},
            "coverage_to": {"type": "string", "format": "date"},
            "skip_invalid": {"type": "boolean"},
            "confirm_repeated": {"type": "boolean"},
            "dry_run": {"type": "boolean"},
        },
        "required": ["file", "source_type", "payment_account_id", "mapping"],
    }
}


def _flag(data: Any, name: str) -> bool:
    value = str(data.get(name, "false")).strip().lower()
    if value not in ("true", "false", "1", "0", ""):
        raise invalid(name, "Use true or false.")
    return value in ("true", "1")


def _day(data: Any, name: str) -> date | None:
    text = str(data.get(name, "")).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise invalid(name, "Enter a date as YYYY-MM-DD.") from None


def _options(data: Any) -> service.StatementOptions:
    try:
        mapping = json.loads(str(data.get("mapping", "")))
    except ValueError:
        raise invalid("mapping", "The mapping must be JSON.") from None
    if not isinstance(mapping, dict):
        raise invalid("mapping", "The mapping must be a JSON object.")
    return service.StatementOptions(
        source_type=str(data.get("source_type", "")),
        mapping=mapping,
        date_format=str(data.get("date_format", "")).strip() or None,
        include_debits=_flag(data, "include_debits"),
        coverage_from=_day(data, "coverage_from"),
        coverage_to=_day(data, "coverage_to"),
        skip_invalid=_flag(data, "skip_invalid"),
        confirm_repeated=_flag(data, "confirm_repeated"),
        dry_run=_flag(data, "dry_run"),
    )


class StatementImportView(APIView):
    @endpoint("E053", request=_BODY, responses={200: StatementImportOut, 201: StatementImportOut})
    @idempotent
    def post(self, request: Any, ws: UUID) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            raise invalid("file", "Choose a CSV file to upload.")
        try:
            account = UUID(str(request.data.get("payment_account_id", "")))
        except ValueError:
            raise invalid("payment_account_id", "Choose the account this statement belongs to.") from None
        options = _options(request.data)
        report = service.import_statement(request.ctx, account, upload.name, upload.read(), options)
        return Response(report, status=200 if options.dry_run else 201)
