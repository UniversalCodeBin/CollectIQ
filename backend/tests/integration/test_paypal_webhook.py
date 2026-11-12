"""Comprehensive integration tests for PayPal Sandbox webhook processing, payment normalization,
event deduplication, invoice matching, review queue integration, human confirmation, and tenant isolation.
"""

import json
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from collectiq.integrations import service
from collectiq.integrations.paypal import verify as paypal
from collectiq.platform.context import RequestContext
from tests.integration.test_import import HEADER, _import
from tests.support import API, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")

MERCHANT_A = "MERCHANTA123"
MERCHANT_B = "MERCHANTB456"


@pytest.fixture
def flags() -> Iterator[None]:
    with override_settings(FEATURE_PAYPAL_WEBHOOK=True):
        yield


class PayPalTestEnv:
    def __init__(self, owner_db: psycopg.Connection, email: str, merchant_id: str = MERCHANT_A) -> None:
        self.db = owner_db
        self.merchant_id = merchant_id
        self.client, self.ws = owner_workspace(owner_db, email)
        self.activate_tenant()
        self.user = owner_db.execute(
            "SELECT user_id FROM workspace_memberships WHERE role = 'OWNER'"
        ).fetchone()[0]
        self.ctx = RequestContext(uuid.UUID(self.ws), self.user, "OWNER", str(uuid.uuid4()), "USER")
        service.connect(self.ctx, "PAYPAL", lambda: True, external_account=merchant_id)

    def activate_tenant(self) -> None:
        self.db.execute("SELECT set_config('app.workspace_id', %s, false)", [self.ws])

    def query(self, sql: str, params: list[Any] | None = None) -> Any:
        self.activate_tenant()
        return self.db.execute(sql, params or [])

    def url(self, tail: str) -> str:
        return f"{API}/workspaces/{self.ws}/{tail}"

    def load_invoices(self, *rows: tuple[str, str, str, str]) -> dict[str, str]:
        """Loads invoices (number, client, currency, total)."""
        body = HEADER + "".join(f"{n},{c},2026-11-30,{cur},{t},2026-11-01\n" for n, c, cur, t in rows)
        _import(self.client, self.ws, body.encode())
        items = self.client.get(f"{API}/workspaces/{self.ws}/invoices?limit=200").json()["items"]
        return {i["invoice_number"]: i["id"] for i in items}


def make_paypal_payload(
    event_id: str,
    event_type: str = "PAYMENT.CAPTURE.COMPLETED",
    amount: str = "120.00",
    currency: str = "USD",
    merchant_id: str = MERCHANT_A,
    capture_id: str = "CAP-12345",
    custom_id: str | None = None,
    status: str = "COMPLETED",
    payer_email: str = "buyer-test@example.test",
) -> dict[str, Any]:
    return {
        "id": event_id,
        "event_version": "1.0",
        "create_time": "2026-11-12T14:15:20Z",
        "resource_type": "capture",
        "event_type": event_type,
        "summary": f"Payment capture {status}",
        "resource": {
            "id": capture_id,
            "status": status,
            "amount": {"value": amount, "currency_code": currency},
            "payee": {"merchant_id": merchant_id, "email_address": "merchant@example.test"},
            "payer": {
                "payer_id": "PAYER-123",
                "email_address": payer_email,
                "name": {"given_name": "Test", "surname": "Buyer"},
            },
            "custom_id": custom_id,
            "create_time": "2026-11-12T14:15:20Z",
        },
    }


def post_webhook(body: dict[str, Any], valid: bool = True) -> Any:
    headers = {"HTTP_X_FAKE_SIGNATURE": "valid" if valid else "forged"}
    return APIClient().post(f"{API}/webhooks/paypal", body, format="json", **headers)


def test_webhook_disabled_returns_404(owner_db: psycopg.Connection) -> None:
    env = PayPalTestEnv(owner_db, f"pp-{uuid.uuid4().hex[:8]}@example.test")
    paypal.set_verifier(paypal.FakeVerifier())
    try:
        with override_settings(FEATURE_PAYPAL_WEBHOOK=False):
            res = post_webhook(make_paypal_payload("E-OFF"))
            assert res.status_code == 404
    finally:
        paypal.set_verifier(None)


def test_webhook_unverified_signature_returns_401(owner_db: psycopg.Connection, flags: None) -> None:
    env = PayPalTestEnv(owner_db, f"pp-{uuid.uuid4().hex[:8]}@example.test")
    paypal.set_verifier(paypal.FakeVerifier())
    try:
        res = post_webhook(make_paypal_payload("E-FORGED"), valid=False)
        assert res.status_code == 401
        assert env.query("SELECT count(*) FROM webhook_events").fetchone()[0] == 0
    finally:
        paypal.set_verifier(None)


def test_webhook_unknown_merchant_safely_ignored(owner_db: psycopg.Connection, flags: None) -> None:
    env = PayPalTestEnv(owner_db, f"pp-{uuid.uuid4().hex[:8]}@example.test", merchant_id="MERCHANT-KNOWN")
    paypal.set_verifier(paypal.FakeVerifier())
    try:
        payload = make_paypal_payload("E-UNKNOWN", merchant_id="SOMEONE-ELSE")
        res = post_webhook(payload, valid=True)
        assert res.status_code == 200
        assert env.query("SELECT count(*) FROM webhook_events").fetchone()[0] == 0
    finally:
        paypal.set_verifier(None)


def test_webhook_malformed_payload_returns_422(owner_db: psycopg.Connection, flags: None) -> None:
    paypal.set_verifier(paypal.FakeVerifier())
    try:
        res = post_webhook({"broken": True}, valid=True)
        assert res.status_code == 422
    finally:
        paypal.set_verifier(None)


def test_webhook_completed_capture_ingests_and_proposes_match(
    owner_db: psycopg.Connection, flags: None
) -> None:
    env = PayPalTestEnv(owner_db, f"pp-{uuid.uuid4().hex[:8]}@example.test")
    invoices = env.load_invoices(("INV-201", "Acme Corp", "USD", "120.00"))
    inv_id = invoices["INV-201"]

    paypal.set_verifier(paypal.FakeVerifier())
    try:
        payload = make_paypal_payload(
            event_id="EVT-COMPLETED-1",
            amount="120.00",
            currency="USD",
            capture_id="CAP-10001",
            custom_id="INV-201",
        )
        res = post_webhook(payload, valid=True)
        assert res.status_code == 200

        # 1. Verified event stored in webhook_events with EVIDENCE_ONLY
        ev = env.query(
            "SELECT status FROM webhook_events WHERE event_id = 'EVT-COMPLETED-1'"
        ).fetchone()
        assert ev is not None
        assert ev[0] == "EVIDENCE_ONLY"

        # 2. Ingested into payment_transactions as CREDIT with minor units (12000)
        txn = env.query(
            "SELECT id, source_type, amount_minor, currency, external_id, status FROM payment_transactions"
            " WHERE external_id = 'CAP-10001'"
        ).fetchone()
        assert txn is not None
        txn_id = str(txn[0])
        assert txn[1] == "PAYPAL"
        assert txn[2] == 12000
        assert txn[3] == "USD"
        assert txn[4] == "CAP-10001"
        assert txn[5] == "ACTIVE"

        # 3. Existing matcher created proposal in reconciliation_matches
        proposal = env.query(
            "SELECT id, status, band, invoice_id FROM reconciliation_matches WHERE transaction_id = %s",
            [txn_id],
        ).fetchone()
        assert proposal is not None
        proposal_id = str(proposal[0])
        assert proposal[1] == "PROPOSED"
        assert str(proposal[3]) == inv_id

        # 4. Invoices moved to AWAITING_VERIFICATION (not automatically marked paid!)
        inv_state = env.query(
            "SELECT payment_status FROM invoice_state WHERE invoice_id = %s", [inv_id]
        ).fetchone()
        assert inv_state[0] == "AWAITING_VERIFICATION"

        # 5. Visible in review queue (ProposalsView)
        proposals_page = env.client.get(env.url("reconciliation/proposals")).json()
        assert any(item["id"] == proposal_id for item in proposals_page["items"])

        # 6. Human confirms proposal: creates allocation and marks invoice PAID_VERIFIED
        confirm_res = env.client.post(
            env.url(f"reconciliation/proposals/{proposal_id}/confirm"),
            {"allocations": [{"invoice_id": inv_id, "amount_minor": 12000, "overpayment_confirmed": False}]},
            format="json",
            **idem(),
        )
        assert confirm_res.status_code == 200

        # Ledger now has allocation
        alloc = env.query(
            "SELECT amount_minor, kind FROM payment_allocations WHERE transaction_id = %s", [txn_id]
        ).fetchone()
        assert alloc[0] == 12000
        assert alloc[1] == "ALLOCATION"

        # Invoice is now verified paid
        paid_state = env.query(
            "SELECT payment_status, paid_minor, outstanding_minor FROM invoice_state WHERE invoice_id = %s",
            [inv_id],
        ).fetchone()
        assert paid_state[0] == "PAID_VERIFIED"
        assert paid_state[1] == 12000
        assert paid_state[2] == 0
    finally:
        paypal.set_verifier(None)


def test_webhook_duplicate_delivery_is_idempotent(
    owner_db: psycopg.Connection, flags: None
) -> None:
    env = PayPalTestEnv(owner_db, f"pp-{uuid.uuid4().hex[:8]}@example.test")
    env.load_invoices(("INV-301", "Acme Corp", "USD", "50.00"))

    paypal.set_verifier(paypal.FakeVerifier())
    try:
        payload = make_paypal_payload(
            event_id="EVT-DUP-1",
            amount="50.00",
            currency="USD",
            capture_id="CAP-DUP-1",
            custom_id="INV-301",
        )
        # First delivery
        res1 = post_webhook(payload, valid=True)
        assert res1.status_code == 200

        # Second duplicate delivery
        res2 = post_webhook(payload, valid=True)
        assert res2.status_code == 200

        # Exactly 1 webhook event and 1 payment transaction
        assert env.query("SELECT count(*) FROM webhook_events WHERE event_id = 'EVT-DUP-1'").fetchone()[0] == 1
        assert (
            env.query("SELECT count(*) FROM payment_transactions WHERE external_id = 'CAP-DUP-1'").fetchone()[0]
            == 1
        )
    finally:
        paypal.set_verifier(None)


def test_webhook_pending_capture_does_not_create_active_transaction(
    owner_db: psycopg.Connection, flags: None
) -> None:
    env = PayPalTestEnv(owner_db, f"pp-{uuid.uuid4().hex[:8]}@example.test")
    paypal.set_verifier(paypal.FakeVerifier())
    try:
        payload = make_paypal_payload(
            event_id="EVT-PENDING-1",
            event_type="PAYMENT.CAPTURE.PENDING",
            amount="75.00",
            currency="USD",
            capture_id="CAP-PENDING-1",
            status="PENDING",
        )
        res = post_webhook(payload, valid=True)
        assert res.status_code == 200

        # Stored in webhook_events as evidence
        assert env.query("SELECT count(*) FROM webhook_events WHERE event_id = 'EVT-PENDING-1'").fetchone()[0] == 1
        # No payment transaction created
        assert (
            env.query("SELECT count(*) FROM payment_transactions WHERE external_id = 'CAP-PENDING-1'").fetchone()[0]
            == 0
        )
    finally:
        paypal.set_verifier(None)


def test_webhook_denied_capture_does_not_create_active_transaction(
    owner_db: psycopg.Connection, flags: None
) -> None:
    env = PayPalTestEnv(owner_db, f"pp-{uuid.uuid4().hex[:8]}@example.test")
    paypal.set_verifier(paypal.FakeVerifier())
    try:
        payload = make_paypal_payload(
            event_id="EVT-DENIED-1",
            event_type="PAYMENT.CAPTURE.DENIED",
            amount="75.00",
            currency="USD",
            capture_id="CAP-DENIED-1",
            status="DENIED",
        )
        res = post_webhook(payload, valid=True)
        assert res.status_code == 200

        # Stored in webhook_events as evidence
        assert env.query("SELECT count(*) FROM webhook_events WHERE event_id = 'EVT-DENIED-1'").fetchone()[0] == 1
        # No payment transaction created
        assert (
            env.query("SELECT count(*) FROM payment_transactions WHERE external_id = 'CAP-DENIED-1'").fetchone()[0]
            == 0
        )
    finally:
        paypal.set_verifier(None)


def test_webhook_refund_voids_unallocated_transaction(
    owner_db: psycopg.Connection, flags: None
) -> None:
    env = PayPalTestEnv(owner_db, f"pp-{uuid.uuid4().hex[:8]}@example.test")
    paypal.set_verifier(paypal.FakeVerifier())
    try:
        # 1. Ingest original capture
        capture_payload = make_paypal_payload(
            event_id="EVT-ORIG-CAP",
            amount="200.00",
            currency="USD",
            capture_id="CAP-REFUNDABLE-1",
        )
        post_webhook(capture_payload, valid=True)

        txn = env.query(
            "SELECT id, status FROM payment_transactions WHERE external_id = 'CAP-REFUNDABLE-1'"
        ).fetchone()
        assert txn[1] == "ACTIVE"

        # 2. Refund event arrives
        refund_payload = {
            "id": "EVT-REFUND-1",
            "event_type": "PAYMENT.CAPTURE.REFUNDED",
            "resource": {
                "id": "REF-9999",
                "status": "COMPLETED",
                "amount": {"value": "200.00", "currency_code": "USD"},
                "payee": {"merchant_id": env.merchant_id},
                "links": [{"rel": "up", "href": "https://api.sandbox.paypal.com/v1/payments/captures/CAP-REFUNDABLE-1"}],
            },
        }
        res = post_webhook(refund_payload, valid=True)
        assert res.status_code == 200

        # 3. Transaction is marked VOID with reason
        voided = env.query(
            "SELECT status, void_reason FROM payment_transactions WHERE external_id = 'CAP-REFUNDABLE-1'"
        ).fetchone()
        assert voided[0] == "VOID"
        assert "REF-9999" in voided[1]
    finally:
        paypal.set_verifier(None)


def test_tenant_isolation_cross_tenant_denied(
    owner_db: psycopg.Connection, flags: None
) -> None:
    env_a = PayPalTestEnv(owner_db, f"pp-a-{uuid.uuid4().hex[:8]}@example.test", merchant_id=MERCHANT_A)
    env_b = PayPalTestEnv(owner_db, f"pp-b-{uuid.uuid4().hex[:8]}@example.test", merchant_id=MERCHANT_B)

    paypal.set_verifier(paypal.FakeVerifier())
    try:
        # Event for Merchant A
        payload_a = make_paypal_payload(
            event_id="EVT-TENANT-A",
            merchant_id=MERCHANT_A,
            capture_id="CAP-TENANT-A",
        )
        res = post_webhook(payload_a, valid=True)
        assert res.status_code == 200

        # Workspace A received it
        assert env_a.query(
            "SELECT count(*) FROM webhook_events WHERE workspace_id = %s AND event_id = 'EVT-TENANT-A'",
            [env_a.ws],
        ).fetchone()[0] == 1

        # Workspace B has NO trace of it
        assert env_b.query(
            "SELECT count(*) FROM webhook_events WHERE workspace_id = %s AND event_id = 'EVT-TENANT-A'",
            [env_b.ws],
        ).fetchone()[0] == 0
    finally:
        paypal.set_verifier(None)
