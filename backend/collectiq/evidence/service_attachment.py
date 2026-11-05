"""The optional proof file on a manual payment (FR-032). Content decides the type; the name never does."""

import hashlib
from typing import Any
from uuid import UUID, uuid4

from django.db import IntegrityError

from collectiq.audit import record
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.platform.scan import get_scanner
from collectiq.platform.storage import get_storage, storage_key
from collectiq.tenancy.permissions import FINANCE_READ, LEDGER_WRITE, authorize

KIND = "PAYMENT_ATTACHMENT"
MAX_BYTES = 5 * 1024 * 1024
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"%PDF-", "application/pdf"),
)


def _invalid(message: str) -> ProblemError:
    return ProblemError(
        "VALIDATION_FAILED",
        422,
        "Some fields are invalid.",
        {"errors": [{"field": "file", "message": message}]},
    )


def sniff(data: bytes) -> str:
    for signature, content_type in _SIGNATURES:
        if data.startswith(signature):
            return content_type
    raise _invalid("Attach a PNG, JPEG or PDF file.")


def _safe_name(name: str) -> str:
    cleaned = "".join(c for c in name.replace("\\", "/").rsplit("/", 1)[-1] if c.isprintable()).strip()
    return cleaned[:255] or "attachment"


def attach(ctx: RequestContext, transaction_id: UUID, name: str, data: bytes) -> dict[str, Any]:
    authorize(ctx, LEDGER_WRITE)
    if not data:
        raise _invalid("That file is empty.")
    if len(data) > MAX_BYTES:
        raise _invalid("That file is larger than 5 MB.")
    content_type = sniff(data)
    name = _safe_name(name)
    file_id = uuid4()
    key = storage_key(ctx, "payments", str(file_id))
    with tenant_tx(ctx):
        payment = fetch_one(
            "SELECT source_type, status FROM payment_transactions WHERE id = %s FOR NO KEY UPDATE",
            [transaction_id],
        )
        if payment is None:
            raise ProblemError("NOT_FOUND", 404, "That payment does not exist.")
        if payment["source_type"] != "MANUAL":
            raise _invalid("Only a payment you entered by hand can carry a proof file.")
        if payment["status"] != "ACTIVE":
            raise ProblemError(
                "STATE_TRANSITION_INVALID", 409, "A voided or duplicate payment cannot take a file."
            )
        if fetch_one("SELECT 1 AS one FROM payment_attachments WHERE transaction_id = %s", [transaction_id]):
            raise ProblemError("STATE_TRANSITION_INVALID", 409, "This payment already has a file.")
        get_storage().put(ctx, key, data)
        try:
            execute(
                "INSERT INTO stored_files (id, workspace_id, kind, storage_key, file_name, content_sha256,"
                " size_bytes, scan_status, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    file_id,
                    ctx.workspace_id,
                    KIND,
                    key,
                    name,
                    hashlib.sha256(data).digest(),
                    len(data),
                    get_scanner().scan(data),
                    ctx.user_id,
                ],
            )
            execute(
                "INSERT INTO payment_attachments (workspace_id, transaction_id, file_id, content_type,"
                " created_by) VALUES (%s, %s, %s, %s, %s)",
                [ctx.workspace_id, transaction_id, file_id, content_type, ctx.user_id],
            )
        except IntegrityError:
            get_storage().delete(ctx, key)
            raise ProblemError("STATE_TRANSITION_INVALID", 409, "This payment already has a file.") from None
        record(
            ctx,
            "payment.attachment_added",
            "payment_transaction",
            str(transaction_id),
            after={"file_name": name, "size_bytes": len(data), "content_type": content_type},
            reason_codes=["USER_CONFIRMATION"],
        )
    return {"file_name": name, "size_bytes": len(data), "content_type": content_type}


def read(ctx: RequestContext, transaction_id: UUID) -> tuple[bytes, str, str]:
    authorize(ctx, FINANCE_READ)
    with tenant_tx(ctx):
        row = fetch_one(
            "SELECT f.storage_key, f.file_name, p.content_type, f.scan_status FROM payment_attachments p"
            " JOIN stored_files f ON f.id = p.file_id AND f.workspace_id = p.workspace_id"
            " WHERE p.transaction_id = %s AND f.deleted_at IS NULL",
            [transaction_id],
        )
    if row is None or row["scan_status"] == "QUARANTINED":
        raise ProblemError("NOT_FOUND", 404, "That payment has no file.")
    return get_storage().get(ctx, row["storage_key"]), row["file_name"], row["content_type"]
