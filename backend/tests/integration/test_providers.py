"""Gated Gmail send-only and PayPal webhook adapters, on fake transports. Not verified against either."""

import json
import uuid
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import psycopg
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from collectiq.integrations.gmail import transport as gmail
from collectiq.integrations.paypal import verify as paypal
from tests.integration.test_reminders import Env as ReminderEnv
from tests.support import API, drain_jobs, idem

pytestmark = pytest.mark.usefixtures("pg")

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


@pytest.fixture
def fake() -> Iterator[gmail.FakeTransport]:
    transport = gmail.FakeTransport()
    gmail.set_transport(transport)
    yield transport
    gmail.set_transport(None)


@pytest.fixture
def flags() -> Iterator[None]:
    with override_settings(FEATURE_GMAIL_SEND=True, FEATURE_PAYPAL_WEBHOOK=True):
        yield


@pytest.fixture
def env(owner_db: psycopg.Connection) -> ReminderEnv:
    return ReminderEnv(owner_db, f"prov-{uuid.uuid4().hex[:8]}@example.test")


def connect_gmail(
    env: ReminderEnv, fake: gmail.FakeTransport, scopes: tuple[str, ...] = (SEND_SCOPE,)
) -> Any:
    start = env.client.post(env.url("integrations/gmail/connect"), **idem())
    assert start.status_code == 200, start.content
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    fake.grant_scopes = scopes
    return env.client.get(
        f"{API}/integrations/gmail/callback", {"state": state, "code": "fake-code"}
    ), start.json()


def approved(env: ReminderEnv) -> str:
    draft = env.draft()
    assert env.approve(draft["id"]).status_code == 200
    return str(draft["id"])


def send(env: ReminderEnv, reminder_id: str) -> Any:
    return env.client.post(env.url(f"reminders/{reminder_id}/send"), **idem())


def status(env: ReminderEnv, reminder_id: str) -> str:
    return str(env.db.execute("SELECT status FROM reminders WHERE id = %s", [reminder_id]).fetchone()[0])


def ready(env: ReminderEnv, fake: gmail.FakeTransport) -> str:
    done, _ = connect_gmail(env, fake)
    assert done.status_code in (200, 302), done.content
    return approved(env)


# ---- Gmail: connection ------------------------------------------------------------------------------


def test_connect_asks_only_for_the_send_scope(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None
) -> None:  # TS-025
    start = env.client.post(env.url("integrations/gmail/connect"), **idem())
    assert start.status_code == 200
    query = parse_qs(urlparse(start.json()["authorization_url"]).query)
    assert query["scope"] == [SEND_SCOPE]
    assert query["code_challenge_method"] == ["S256"] and query["code_challenge"] and query["state"]


def test_a_granted_read_scope_is_refused_and_nothing_is_connected(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None
) -> None:  # TS-025
    done, _ = connect_gmail(env, fake, (SEND_SCOPE, "https://www.googleapis.com/auth/gmail.readonly"))
    assert done.status_code == 409
    items = {i["key"]: i for i in env.client.get(env.url("integrations")).json()["items"]}
    assert items["GMAIL"]["state"] == "NEEDS_CONFIGURATION"
    assert env.db.execute("SELECT count(*) FROM oauth_credential_refs").fetchone()[0] == 0


def test_callback_checks_state_and_pkce_and_a_state_works_once(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None
) -> None:
    bad = env.client.get(f"{API}/integrations/gmail/callback", {"state": "nope", "code": "c"})
    assert bad.status_code == 400
    done, _ = connect_gmail(env, fake)
    assert done.status_code in (200, 302)
    assert fake.exchanged and fake.exchanged[0]["verifier"]
    start = env.client.post(env.url("integrations/gmail/connect"), **idem())
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    assert env.client.get(
        f"{API}/integrations/gmail/callback", {"state": state, "code": "c"}
    ).status_code in (200, 302)
    assert (
        env.client.get(f"{API}/integrations/gmail/callback", {"state": state, "code": "c"}).status_code == 400
    )


def test_tokens_are_stored_sealed(env: ReminderEnv, fake: gmail.FakeTransport, flags: None) -> None:
    connect_gmail(env, fake)
    sealed = bytes(env.db.execute("SELECT sealed FROM oauth_credential_refs").fetchone()[0])
    assert fake.refresh_token.encode() not in sealed


def test_only_the_owner_connects(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None, owner_db: psycopg.Connection
) -> None:
    from tests.support import add_member

    finance, _ = add_member(owner_db, env.ws, "fin-prov@example.test", "FINANCE_ADMIN")
    assert finance.post(env.url("integrations/gmail/connect"), **idem()).status_code == 403


def test_disconnect_revokes_and_blocks_sending(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None
) -> None:
    reminder = ready(env, fake)
    gone = env.client.delete(env.url("integrations/GMAIL"), **idem())
    assert gone.status_code == 200 and gone.json()["state"] == "DISCONNECTED"
    assert fake.revoked
    assert env.db.execute("SELECT count(*) FROM oauth_credential_refs").fetchone()[0] == 0
    assert send(env, reminder).status_code == 409
    assert "integration.disconnected" in [
        r[0] for r in env.db.execute("SELECT action FROM audit_events").fetchall()
    ]


# ---- Gmail: sending ---------------------------------------------------------------------------------


def test_send_is_off_by_default(env: ReminderEnv, fake: gmail.FakeTransport) -> None:
    reminder = approved(env)
    response = send(env, reminder)
    assert response.status_code == 409 and response.json()["code"] == "FEATURE_DISABLED"
    assert not fake.sent and status(env, reminder) == "APPROVED"


def test_send_needs_a_verified_connection(env: ReminderEnv, fake: gmail.FakeTransport, flags: None) -> None:
    reminder = approved(env)
    response = send(env, reminder)
    assert response.status_code == 409 and response.json()["code"] == "NOT_CONNECTED"
    assert not fake.sent


def test_send_needs_human_approval_first(env: ReminderEnv, fake: gmail.FakeTransport, flags: None) -> None:
    connect_gmail(env, fake)
    draft = env.draft()
    assert send(env, draft["id"]).status_code == 409
    assert not fake.sent


def test_send_submits_the_approved_text_and_never_says_delivered(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None
) -> None:
    reminder = ready(env, fake)
    body = env.get(reminder)["body"]
    response = send(env, reminder)
    assert response.status_code == 202, response.content
    assert len(fake.sent) == 1
    assert fake.sent[0]["to"] == "ap@northwind.example.test" and fake.sent[0]["body"] == body
    shown = env.get(reminder)
    assert shown["status"] == "SUBMITTED" and shown["sent_at"] is None
    assert "deliver" not in json.dumps(shown).lower()
    assert env.reminder_status() == "WAITING_FOR_CUSTOMER"


def test_provider_rejection_keeps_it_approved_and_is_recorded(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None
) -> None:
    reminder = ready(env, fake)
    fake.script = ["reject"]
    response = send(env, reminder)
    assert response.status_code == 502 and response.json()["code"] == "PROVIDER_REJECTED"
    assert status(env, reminder) == "APPROVED"
    assert env.reminder_status() == "DRAFT_READY"


def test_network_drop_after_submit_is_submission_unknown_with_no_auto_retry(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None
) -> None:
    reminder = ready(env, fake)
    fake.script = ["drop"]
    response = send(env, reminder)
    assert response.status_code == 202 and response.json()["status"] == "SUBMISSION_UNKNOWN"
    assert status(env, reminder) == "SUBMISSION_UNKNOWN"
    assert len(fake.attempts) == 1
    assert send(env, reminder).status_code == 409  # a person must resolve it first
    drain_jobs()
    assert len(fake.attempts) == 1


def test_a_person_resolves_an_unknown_submission(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None
) -> None:
    reminder = ready(env, fake)
    fake.script = ["drop"]
    send(env, reminder)
    url = env.url(f"reminders/{reminder}/confirm-unknown")
    assert env.client.post(url, {"outcome": "WAS_SENT"}, format="json", **idem()).status_code == 200
    assert status(env, reminder) == "SUBMITTED"
    again = env.client.post(url, {"outcome": "WAS_SENT"}, format="json", **idem())
    assert again.status_code == 409


def test_not_sent_returns_to_approved_and_allows_a_new_send(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None
) -> None:
    reminder = ready(env, fake)
    fake.script = ["drop"]
    send(env, reminder)
    url = env.url(f"reminders/{reminder}/confirm-unknown")
    assert env.client.post(url, {"outcome": "NOT_SENT"}, format="json", **idem()).status_code == 200
    assert status(env, reminder) == "APPROVED"
    assert send(env, reminder).status_code == 202


def test_confirm_unknown_only_applies_to_an_unknown_submission(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None
) -> None:
    reminder = ready(env, fake)
    url = env.url(f"reminders/{reminder}/confirm-unknown")
    assert env.client.post(url, {"outcome": "NOT_SENT"}, format="json", **idem()).status_code == 409


def test_gates_are_checked_again_at_send_time(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None
) -> None:
    reminder = ready(env, fake)
    env.client.post(
        env.url("cases"),
        {"invoice_id": env.invoices["INV-1"], "type": "DISPUTE", "summary": "Not our invoice"},
        format="json",
        **idem(),
    )
    assert send(env, reminder).status_code == 409
    assert not fake.sent


def test_the_same_idempotency_key_sends_once(
    env: ReminderEnv, fake: gmail.FakeTransport, flags: None
) -> None:
    reminder = ready(env, fake)
    headers = idem()
    first = env.client.post(env.url(f"reminders/{reminder}/send"), **headers)
    second = env.client.post(env.url(f"reminders/{reminder}/send"), **headers)
    assert first.status_code == 202 and second.status_code == 202
    assert len(fake.sent) == 1


def test_a_send_is_audited(env: ReminderEnv, fake: gmail.FakeTransport, flags: None) -> None:
    reminder = ready(env, fake)
    send(env, reminder)
    assert "reminder.submitted" in [
        r[0] for r in env.db.execute("SELECT action FROM audit_events").fetchall()
    ]


# ---- PayPal webhook ---------------------------------------------------------------------------------

MERCHANT = "MERCHANT-1"


def paypal_event(event_id: str, merchant: str = MERCHANT) -> dict[str, Any]:
    return {
        "id": event_id,
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "amount": {"value": "120.00", "currency_code": "USD"},
            "payee": {"merchant_id": merchant},
        },
    }


@pytest.fixture
def pp_env(env: ReminderEnv, flags: None) -> Iterator[ReminderEnv]:
    from collectiq.integrations import service
    from collectiq.platform.context import RequestContext

    user = env.db.execute("SELECT user_id FROM workspace_memberships WHERE role = 'OWNER'").fetchone()[0]
    ctx = RequestContext(uuid.UUID(env.ws), user, "OWNER", str(uuid.uuid4()), "USER")
    service.connect(ctx, "PAYPAL", lambda: True, external_account=MERCHANT)
    paypal.set_verifier(paypal.FakeVerifier())
    yield env
    paypal.set_verifier(None)


def post_event(body: dict[str, Any], valid: bool = True) -> Any:
    headers = {"HTTP_X_FAKE_SIGNATURE": "valid" if valid else "forged"}
    return APIClient().post(f"{API}/webhooks/paypal", body, format="json", **headers)


def test_webhook_is_off_by_default(env: ReminderEnv) -> None:
    assert post_event(paypal_event("E-1")).status_code == 404


def test_a_forged_signature_stores_nothing(pp_env: ReminderEnv) -> None:
    assert post_event(paypal_event("E-1"), valid=False).status_code == 401
    assert pp_env.db.execute("SELECT count(*) FROM webhook_events").fetchone()[0] == 0


def test_valid_event_is_evidence_not_allocation(pp_env: ReminderEnv) -> None:
    before = pp_env.db.execute("SELECT count(*) FROM payment_allocations").fetchone()[0]
    paid_before = pp_env.db.execute(
        "SELECT count(*) FROM invoice_state WHERE payment_status <> 'OUTSTANDING'"
    ).fetchone()[0]
    assert post_event(paypal_event("E-1")).status_code == 200
    row = pp_env.db.execute("SELECT status FROM webhook_events").fetchone()
    assert row[0] == "EVIDENCE_ONLY"
    assert pp_env.db.execute("SELECT count(*) FROM payment_allocations").fetchone()[0] == before
    assert (
        pp_env.db.execute(
            "SELECT count(*) FROM invoice_state WHERE payment_status <> 'OUTSTANDING'"
        ).fetchone()[0]
        == paid_before
    )


def test_a_redelivered_event_is_stored_once(pp_env: ReminderEnv) -> None:  # TS-014
    assert post_event(paypal_event("E-1")).status_code == 200
    assert post_event(paypal_event("E-1")).status_code == 200
    assert pp_env.db.execute("SELECT count(*) FROM webhook_events").fetchone()[0] == 1


def test_an_unknown_merchant_is_ignored_without_a_trace_of_another_tenant(pp_env: ReminderEnv) -> None:
    response = post_event(paypal_event("E-9", merchant="SOMEONE-ELSE"))
    assert response.status_code == 200
    assert pp_env.db.execute("SELECT count(*) FROM webhook_events").fetchone()[0] == 0


# ---- PayPal connect and Gmail monitoring --------------------------------------------------------------


def test_paypal_connect_is_verified_only_when_paypal_confirms(env: ReminderEnv, flags: None) -> None:
    body = {"merchant_id": "FAKEMERCHANT1"}
    refused = env.client.post(env.url("integrations/paypal/connect"), body, format="json", **idem())
    assert refused.status_code == 200 and refused.json()["state"] == "NEEDS_CONFIGURATION"
    paypal.set_merchant_checker(paypal.FakeMerchantChecker())
    try:
        ok = env.client.post(env.url("integrations/paypal/connect"), body, format="json", **idem())
        assert ok.json()["state"] == "CONNECTED_VERIFIED"
        wrong = env.client.post(
            env.url("integrations/paypal/connect"), {"merchant_id": "OTHERMERCH1"}, format="json", **idem()
        )
        assert wrong.json()["state"] == "NEEDS_REAUTH"
    finally:
        paypal.set_merchant_checker(None)


def test_paypal_connect_is_off_by_default_and_validates_the_id(env: ReminderEnv) -> None:
    off = env.client.post(
        env.url("integrations/paypal/connect"), {"merchant_id": "FAKEMERCHANT1"}, format="json", **idem()
    )
    assert off.status_code == 409
    with override_settings(FEATURE_PAYPAL_WEBHOOK=True):
        bad = env.client.post(
            env.url("integrations/paypal/connect"), {"merchant_id": "x y"}, format="json", **idem()
        )
        assert bad.status_code == 422


def test_gmail_monitoring_is_refused_rather_than_faked(env: ReminderEnv) -> None:
    res = env.client.post(env.url("integrations/gmail/monitoring"), **idem())
    assert res.status_code == 409 and res.json()["code"] == "NOT_AVAILABLE"
