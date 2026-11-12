"""PayPal REST API Sandbox integration service.

Handles:
- Webhook signature verification via official PayPal API.
- Idempotent deduplication and lifecycle state recording.
- Normalization of PayPal payment events into minor units without floating-point math.
- Ingestion of verified payments as payment_transactions.
- Integration with CollectIQ's existing invoice matching engine and review queue.
- Connection verification and connectivity checks.
"""

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from django.conf import settings

from collectiq.audit import record
from collectiq.evidence.parsers.generic_csv import reference_candidates
from collectiq.integrations import service as connections
from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.platform.logging import current_correlation_id
from collectiq.platform.money import Money
from collectiq.tenancy.permissions import INTEGRATIONS_MANAGE, authorize

from .client import (
    PayPalClient,
    PayPalConfigurationError,
    PayPalError,
    redact_sensitive,
)
from .verify import get_merchant_checker, get_paypal_client, get_verifier

logger = logging.getLogger("collectiq.integrations.paypal")


@dataclass(frozen=True, slots=True)
class NormalizedPaymentEvidence:
    """Normalized representation of verified PayPal payment evidence."""

    event_id: str
    event_type: str
    capture_id: str
    order_id: str | None
    payer_id: str | None
    payer_email: str | None
    payer_name: str | None
    merchant_id: str
    amount_minor: int
    currency: str
    status: str
    value_date: date
    custom_id: str | None
    candidates: list[str]
    raw_payload: dict[str, Any]


def _system_user(workspace_id: UUID) -> UUID:
    """Returns the workspace owner user_id or a consistent workspace UUID."""
    row = fetch_one(
        "SELECT user_id FROM workspace_memberships WHERE workspace_id = %s AND role = 'OWNER' LIMIT 1",
        [workspace_id],
    )
    if row and row["user_id"]:
        return UUID(str(row["user_id"]))
    return workspace_id


def normalize_paypal_event(event: dict[str, Any]) -> NormalizedPaymentEvidence | None:
    """Normalizes a raw PayPal event into verified payment evidence.

    Uses integer minor units for amounts via Money.from_decimal_text.
    Never uses floating-point arithmetic.
    """
    event_type = str(event.get("event_type", ""))
    event_id = str(event.get("id", ""))
    resource = event.get("resource") or {}

    # Extract capture / transaction ID
    capture_id = str(resource.get("id", ""))
    if not capture_id:
        return None

    # Extract amount and currency
    amount_obj = resource.get("amount") or {}
    amount_str = amount_obj.get("value")
    currency = amount_obj.get("currency_code", "USD")
    if not amount_str:
        return None

    try:
        money = Money.from_decimal_text(str(amount_str), currency)
    except (ValueError, TypeError) as exc:
        logger.warning("Failed to parse money amount '%s %s': %s", amount_str, currency, exc)
        return None

    # Extract Order ID
    order_id = (
        resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
        or resource.get("order_id")
    )

    # Extract Payer details
    payer_obj = resource.get("payer") or {}
    payer_id = payer_obj.get("payer_id")
    payer_email = payer_obj.get("email_address")
    name_obj = payer_obj.get("name") or {}
    payer_name = f"{name_obj.get('given_name', '')} {name_obj.get('surname', '')}".strip() or None

    # Extract Payee / Merchant ID
    payee_obj = resource.get("payee") or {}
    merchant_id = payee_obj.get("merchant_id") or ""
    if not merchant_id:
        # Check purchase_units
        pu = resource.get("purchase_units") or []
        if pu and isinstance(pu, list):
            merchant_id = pu[0].get("payee", {}).get("merchant_id") or ""

    # Transaction date
    time_str = resource.get("create_time") or resource.get("update_time") or event.get("create_time")
    value_date = clock.today()
    if time_str:
        try:
            # ISO 8601 string: 2026-11-12T14:15:20Z
            cleaned = time_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            value_date = dt.date()
        except Exception:
            value_date = clock.today()

    # Custom reference / candidate matches
    custom_id = resource.get("custom_id") or resource.get("invoice_id") or resource.get("note_to_payer") or resource.get("description")
    search_text = f"{custom_id or ''} {payer_name or ''} {payer_email or ''}"
    candidates = reference_candidates(search_text)

    return NormalizedPaymentEvidence(
        event_id=event_id,
        event_type=event_type,
        capture_id=capture_id,
        order_id=order_id,
        payer_id=payer_id,
        payer_email=payer_email,
        payer_name=payer_name,
        merchant_id=merchant_id,
        amount_minor=money.amount_minor,
        currency=currency,
        status=str(resource.get("status", "")),
        value_date=value_date,
        custom_id=str(custom_id) if custom_id else None,
        candidates=candidates,
        raw_payload=event,
    )


def _get_or_create_paypal_account(workspace_id: UUID, currency: str) -> UUID:
    """Finds or creates an active receiving account for PayPal in the workspace."""
    row = fetch_one(
        "SELECT id FROM payment_accounts"
        " WHERE workspace_id = %s AND kind = 'PAYPAL' AND currency = %s AND status = 'ACTIVE' LIMIT 1",
        [workspace_id, currency],
    )
    if row:
        return UUID(str(row["id"]))

    created = fetch_one(
        "INSERT INTO payment_accounts (workspace_id, kind, label, currency, status)"
        " VALUES (%s, 'PAYPAL', %s, %s, 'ACTIVE') RETURNING id",
        [workspace_id, f"PayPal ({currency})", currency],
    )
    assert created is not None
    return UUID(str(created["id"]))


def _handle_capture_completed(
    ctx: RequestContext, evidence: NormalizedPaymentEvidence
) -> UUID | None:
    """Ingests completed PayPal capture into payment_transactions and feeds reconciliation.

    All amounts use integer minor units. The transaction is placed in the review queue;
    funds are NOT automatically allocated.
    """
    if evidence.amount_minor <= 0:
        return None

    account_id = _get_or_create_paypal_account(ctx.workspace_id, evidence.currency)
    fingerprint = hashlib.sha256(f"PAYPAL:{evidence.capture_id}".encode()).hexdigest()

    payer_descriptor = f"PayPal: {evidence.payer_email}" if evidence.payer_email else (
        f"PayPal: {evidence.payer_name}" if evidence.payer_name else (
            f"PayPal: {evidence.payer_id}" if evidence.payer_id else "PayPal"
        )
    )
    entered_by = _system_user(ctx.workspace_id)

    # Insert into payment_transactions with deduplication on (workspace_id, source_type, external_id)
    inserted = fetch_one(
        "INSERT INTO payment_transactions ("
        "    workspace_id, payment_account_id, source_type, direction,"
        "    amount_minor, currency, value_date, reference, reference_candidates,"
        "    payer_descriptor, fingerprint, occurrence_index, external_id,"
        "    evidence_type, status, entered_by"
        ") VALUES ("
        "    %s, %s, 'PAYPAL', 'CREDIT',"
        "    %s, %s, %s, %s, %s,"
        "    %s, %s, 0, %s,"
        "    'STATEMENT_ROW', 'ACTIVE', %s"
        ") ON CONFLICT (workspace_id, payment_account_id, fingerprint, occurrence_index) DO NOTHING"
        " RETURNING id",
        [
            ctx.workspace_id,
            account_id,
            evidence.amount_minor,
            evidence.currency,
            evidence.value_date,
            evidence.custom_id,
            evidence.candidates,
            payer_descriptor,
            fingerprint,
            evidence.capture_id,
            entered_by,
        ],
    )

    if not inserted:
        logger.info("PayPal capture %s already exists in payment_transactions", evidence.capture_id)
        return None

    txn_id = UUID(str(inserted["id"]))
    logger.info("Ingested PayPal payment transaction %s for capture %s", txn_id, evidence.capture_id)

    # Feed existing invoice matching engine (creates reconciliation_matches proposals)
    try:
        from collectiq.evidence import service_matching
        service_matching.reconcile(ctx, [txn_id])
    except Exception as exc:
        logger.error("Reconciliation matching error for PayPal txn %s: %s", txn_id, exc)

    return txn_id


def _handle_capture_refunded(
    ctx: RequestContext, event: dict[str, Any]
) -> None:
    """Handles PayPal refund / reversal without destroying financial history.

    If parent transaction has not been allocated, it is voided.
    If parent transaction has allocations, history is preserved and audited.
    """
    resource = event.get("resource") or {}
    refund_id = str(resource.get("id", ""))

    # Extract parent capture ID from links
    links = resource.get("links") or []
    parent_capture_id: str | None = None
    for link in links:
        if link.get("rel") == "up":
            href = link.get("href", "")
            parent_capture_id = href.rstrip("/").split("/")[-1]
            break

    if not parent_capture_id:
        parent_capture_id = resource.get("custom_id")

    if not parent_capture_id:
        logger.warning("Could not identify parent capture for refund %s", refund_id)
        return

    # Find existing parent transaction
    row = fetch_one(
        "SELECT id, amount_minor, currency FROM payment_transactions"
        " WHERE workspace_id = %s AND source_type = 'PAYPAL' AND external_id = %s",
        [ctx.workspace_id, parent_capture_id],
    )
    if not row:
        logger.info("No matching parent transaction found for refund %s (capture %s)", refund_id, parent_capture_id)
        return

    txn_id = row["id"]
    # Check if allocations exist against this transaction
    alloc_sum = fetch_one(
        "SELECT COALESCE(sum(amount_minor), 0) AS total FROM payment_allocations WHERE workspace_id = %s AND transaction_id = %s",
        [ctx.workspace_id, txn_id],
    )["total"]

    if alloc_sum == 0:
        # No allocations exist: mark transaction as VOID with reason
        execute(
            "UPDATE payment_transactions SET status = 'VOID', void_reason = %s"
            " WHERE workspace_id = %s AND id = %s",
            [f"PayPal refund: {refund_id}", ctx.workspace_id, txn_id],
        )
        record(
            ctx,
            "payment.voided",
            "payment_transaction",
            str(txn_id),
            after={"status": "VOID", "reason": f"PayPal refund: {refund_id}"},
        )
    else:
        # Allocations exist: do not destroy ledger history!
        logger.info("Parent transaction %s has allocations; preserving ledger history for refund %s", txn_id, refund_id)
        record(
            ctx,
            "payment.refund_received",
            "payment_transaction",
            str(txn_id),
            after={"refund_id": refund_id, "parent_capture_id": parent_capture_id},
        )


def receive(headers: Mapping[str, str], body: bytes) -> dict[str, Any]:
    """Ingests, verifies and processes an incoming PayPal webhook event."""
    if not settings.FEATURE_PAYPAL_WEBHOOK:
        raise ProblemError("NOT_FOUND", 404, "We could not find that.")

    if not get_verifier().verify(headers, body):
        raise ProblemError("AUTH_REQUIRED", 401, "The signature could not be verified.")

    try:
        event = json.loads(body)
        event_id = str(event["id"])
        event_type = str(event["event_type"])
        resource = event.get("resource") or {}
    except (ValueError, KeyError, TypeError):
        raise ProblemError("VALIDATION_FAILED", 422, "The event is not in the expected shape.") from None

    # Resolve merchant ID
    merchant = str(
        resource.get("payee", {}).get("merchant_id")
        or (resource.get("purchase_units") or [{}])[0].get("payee", {}).get("merchant_id")
        or ""
    )

    if not merchant:
        # Check if merchant is associated with refund links
        row = fetch_one(
            "SELECT external_account FROM integration_connections"
            " WHERE provider = 'PAYPAL' AND state IN ('CONNECTED_VERIFIED', 'SANDBOX_ONLY') LIMIT 1"
        )
        if row and row["external_account"]:
            merchant = str(row["external_account"])

    row = fetch_one("SELECT paypal_workspace_for(%s) AS ws", [merchant])
    workspace_id: UUID | None = row["ws"] if row else None

    if workspace_id is None:
        # Not ours or unknown merchant; acknowledge safely without persisting or leaking tenant info
        logger.info("PayPal webhook event %s ignored: unknown merchant %s", event_id, merchant)
        return {"received": True, "status": "IGNORED"}

    correlation = current_correlation_id() or str(uuid4())
    ctx = RequestContext(workspace_id, None, None, correlation, "SYSTEM")

    with tenant_tx(ctx):
        # 1. Deduplication check
        existing = fetch_one(
            "SELECT status FROM webhook_events WHERE workspace_id = %s AND provider = 'PAYPAL' AND event_id = %s",
            [workspace_id, event_id],
        )
        if existing:
            record(
                ctx,
                "webhook.duplicate_received",
                "webhook_event",
                event_id,
                after={"provider": "PAYPAL", "event_type": event_type, "duplicate": True},
            )
            return {"received": True, "status": "DUPLICATE"}

        # 2. Persist in webhook_events table
        execute(
            "INSERT INTO webhook_events (workspace_id, provider, event_id, event_type, status, payload)"
            " VALUES (%s, 'PAYPAL', %s, %s, 'RECEIVED', %s::jsonb)",
            [workspace_id, event_id, event_type, json.dumps(event)],
        )

        # 3. Process according to event type
        txn_id: UUID | None = None
        if event_type == "PAYMENT.CAPTURE.COMPLETED":
            normalized = normalize_paypal_event(event)
            if normalized:
                txn_id = _handle_capture_completed(ctx, normalized)
        elif event_type in ("PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED"):
            _handle_capture_refunded(ctx, event)

        # 4. Mark status as EVIDENCE_ONLY (consistent with CollectIQ core financial model)
        execute(
            "UPDATE webhook_events SET status = 'EVIDENCE_ONLY', processed_at = now()"
            " WHERE workspace_id = %s AND provider = 'PAYPAL' AND event_id = %s",
            [workspace_id, event_id],
        )

        record(
            ctx,
            "webhook.received",
            "webhook_event",
            event_id,
            after={
                "provider": "PAYPAL",
                "event_type": event_type,
                "status": "EVIDENCE_ONLY",
                "transaction_id": str(txn_id) if txn_id else None,
            },
        )

    return {"received": True, "status": "PROCESSED"}


def connect(ctx: RequestContext, merchant_id: str | None = None) -> dict[str, Any]:
    """Connects and verifies PayPal Sandbox REST application credentials and merchant ID.

    Connected only after a real API verification succeeds.
    """
    authorize(ctx, INTEGRATIONS_MANAGE)
    if not settings.FEATURE_PAYPAL_WEBHOOK:
        raise ProblemError("FEATURE_DISABLED", 409, "PayPal events are not turned on.")

    # If merchant_id not provided, check if one was previously configured
    if not merchant_id:
        existing = fetch_one(
            "SELECT external_account FROM integration_connections"
            " WHERE workspace_id = %s AND provider = 'PAYPAL'",
            [ctx.workspace_id],
        )
        if existing and existing["external_account"]:
            merchant_id = str(existing["external_account"])
        else:
            merchant_id = "PAYPAL_SANDBOX"

    checker = get_merchant_checker()
    return connections.connect(
        ctx,
        "PAYPAL",
        lambda: checker.confirm(merchant_id or ""),
        external_account=merchant_id,
    )


def verify_connection_status(ctx: RequestContext) -> dict[str, Any]:
    """Runs connectivity check against PayPal and returns detailed operational status."""
    authorize(ctx, INTEGRATIONS_MANAGE)
    client = get_paypal_client()
    return client.verify_connectivity()
