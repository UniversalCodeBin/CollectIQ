"""Registration, verification, login, sessions and reset through the real API (TSD M01, TS-024)."""
import hashlib
import json

import psycopg
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from collectiq.platform import email as email_port
from collectiq.platform.context import GLOBAL_WORKSPACE_ID
from tests.support import (
    API,
    OTHER_PASS,
    PASS,
    WORKSPACE_BODY,
    drain_jobs,
    idem,
    logged_in,
    login,
    mailbox,
    make_user,
    token_from,
)

ALICE = "alice@example.test"
WRONG = "not-the-right-phrase-at-all"


@pytest.fixture(autouse=True)
def _empty_outbox() -> None:
    email_port.memory_outbox.clear()


def _register(email: str = ALICE, password: str = PASS, client: APIClient | None = None):
    return (client or APIClient()).post(
        f"{API}/auth/register", {"email": email, "password": password}, format="json", **idem()
    )


def _visible_headers(response) -> dict[str, str]:
    return {k: v for k, v in response.items() if k.lower() not in ("x-correlation-id", "content-length")}


def _verified_via_email(email: str = ALICE) -> None:
    assert _register(email).status_code == 201
    drain_jobs()
    token = token_from(mailbox(email)[-1])
    assert APIClient().post(f"{API}/auth/verify-email", {"token": token}, format="json").status_code == 204


def _auth_events(owner_db: psycopg.Connection) -> list[tuple]:
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [str(GLOBAL_WORKSPACE_ID)])
    return owner_db.execute(
        "SELECT action, object_id, before_masked::text, after_masked::text FROM audit_events ORDER BY id"
    ).fetchall()


# Registration


@pytest.mark.parametrize("verified", [False, True], ids=["unverified", "verified"])
def test_registration_response_identical_for_existing_email(pg, owner_db, verified: bool) -> None:
    fresh = _register("new@example.test")
    make_user(owner_db, ALICE, verified=verified)
    existing = _register(ALICE)
    assert (fresh.status_code, fresh.content) == (existing.status_code, existing.content)
    assert fresh.status_code == 201
    assert _visible_headers(fresh) == _visible_headers(existing)
    assert "id" not in fresh.json() and "user" not in fresh.json()


def test_registering_an_existing_email_does_not_change_its_password(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    _register(ALICE, OTHER_PASS)
    assert login(APIClient(), ALICE, OTHER_PASS).status_code == 401
    assert login(APIClient(), ALICE, PASS).status_code == 200


def test_email_differs_only_in_the_mailbox(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    _register(ALICE)
    _register("new@example.test")
    drain_jobs()
    assert "token=" not in mailbox(ALICE)[0].body
    assert "token=" in mailbox("new@example.test")[0].body


@pytest.mark.parametrize("password", ["short", "a" * 200, ALICE], ids=["short", "long", "same-as-email"])
def test_weak_password_is_rejected(pg, password: str) -> None:
    response = _register(ALICE, password)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_email_is_case_insensitive(pg) -> None:
    _verified_via_email("Mixed.Case@Example.Test")
    assert login(APIClient(), "mixed.case@example.test").status_code == 200


def test_register_needs_a_valid_idempotency_key(pg) -> None:
    body = {"email": ALICE, "password": PASS}
    assert APIClient().post(f"{API}/auth/register", body, format="json").status_code == 422


def test_unknown_field_is_rejected(pg) -> None:
    body = {"email": ALICE, "password": PASS, "is_admin": True}
    assert APIClient().post(f"{API}/auth/register", body, format="json", **idem()).status_code == 422


# Verification


def test_verification_token_is_single_use(pg) -> None:
    _register()
    drain_jobs()
    token = token_from(mailbox(ALICE)[-1])
    url = f"{API}/auth/verify-email"
    assert APIClient().post(url, {"token": token}, format="json").status_code == 204
    assert APIClient().post(url, {"token": token}, format="json").status_code == 422


def test_expired_verification_token_is_rejected(pg, owner_db) -> None:
    _register()
    drain_jobs()
    owner_db.execute("UPDATE auth_tokens SET expires_at = now() - interval '1 second'")
    token = token_from(mailbox(ALICE)[-1])
    assert APIClient().post(f"{API}/auth/verify-email", {"token": token}, format="json").status_code == 422


def test_resend_sends_only_to_unverified_and_answers_the_same(pg, owner_db) -> None:
    make_user(owner_db, "done@example.test")
    _register()
    drain_jobs()
    email_port.memory_outbox.clear()
    url = f"{API}/auth/verify-email/resend"
    for address in (ALICE, "done@example.test", "nobody@example.test"):
        assert APIClient().post(url, {"email": address}, format="json").status_code == 204
    drain_jobs()
    assert [message.to for message in email_port.memory_outbox] == [ALICE]


def test_tokens_are_stored_hashed(pg, owner_db) -> None:
    _register()
    drain_jobs()
    token = token_from(mailbox(ALICE)[-1])
    stored = owner_db.execute("SELECT token_hash FROM auth_tokens").fetchone()[0]
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert token not in json.dumps(owner_db.execute("SELECT payload::text FROM background_jobs").fetchall())


# Login, lockout, rate limit


def test_login_returns_user_and_workspaces(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    body = login(APIClient(), ALICE).json()
    assert body["user"]["email"] == ALICE
    assert body["workspaces"] == []
    assert "password_hash" not in json.dumps(body)


def test_login_failure_identical_for_unknown_email_and_wrong_password(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    wrong, unknown = login(APIClient(), ALICE, WRONG), login(APIClient(), "nobody@example.test", WRONG)
    assert wrong.status_code == unknown.status_code == 401
    strip = lambda r: {k: v for k, v in r.json().items() if k != "correlation_id"}  # noqa: E731
    assert strip(wrong) == strip(unknown)


def test_disabled_user_cannot_log_in_or_keep_a_session(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    client = logged_in(ALICE)
    owner_db.execute("UPDATE users SET status = 'DISABLED'")
    assert client.get(f"{API}/auth/session").status_code == 401
    assert login(APIClient(), ALICE).status_code == 401


@override_settings(AUTH_LOCKOUT_THRESHOLD=3, AUTH_LOCKOUT_SECONDS=120)
@pytest.mark.parametrize("email", [ALICE, "nobody@example.test"], ids=["existing", "unknown"])
def test_lockout_returns_429_with_retry_after(pg, owner_db, email: str) -> None:
    make_user(owner_db, ALICE)
    for _ in range(3):
        assert login(APIClient(), email, WRONG).status_code == 401
    locked = login(APIClient(), email, PASS)
    assert locked.status_code == 429
    assert locked.json()["code"] == "RATE_LIMITED"
    assert 0 < int(locked["Retry-After"]) <= 120


@override_settings(AUTH_LOCKOUT_THRESHOLD=3, AUTH_LOCKOUT_SECONDS=120)
def test_lock_ends_after_the_window_and_success_resets_the_count(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    for _ in range(3):
        login(APIClient(), ALICE, WRONG)
    owner_db.execute("UPDATE auth_throttles SET locked_until = now() - interval '1 second'")
    assert login(APIClient(), ALICE).status_code == 200
    for _ in range(2):
        assert login(APIClient(), ALICE, WRONG).status_code == 401
    assert login(APIClient(), ALICE).status_code == 200


@override_settings(AUTH_IP_RATE_LIMIT=2)
def test_public_auth_posts_are_rate_limited_by_ip(pg) -> None:
    for _ in range(2):
        assert login(APIClient(), "nobody@example.test", WRONG).status_code == 401
    limited = APIClient().post(f"{API}/auth/password-reset/request", {"email": ALICE}, format="json")
    assert limited.status_code == 429
    assert int(limited["Retry-After"]) > 0


# Cookies, CSRF, origin


@override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
def test_cookie_flags(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    cookies = login(APIClient(), ALICE).cookies
    session = cookies["collectiq_session"]
    assert session["httponly"] and session["secure"]
    assert session["samesite"] == "Lax"
    assert session["max-age"] == 12 * 3600
    assert session["path"] == "/"


def test_session_token_is_stored_hashed(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    token = login(APIClient(), ALICE).cookies["collectiq_session"].value
    stored = owner_db.execute("SELECT token_hash FROM user_sessions").fetchone()[0]
    assert stored == hashlib.sha256(token.encode()).hexdigest()


def test_csrf_required_on_mutation(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    client = APIClient(enforce_csrf_checks=True)
    assert login(client, ALICE).status_code == 200
    refused = client.post(f"{API}/auth/logout")
    assert refused.status_code == 403
    assert refused.json()["code"] == "FORBIDDEN"
    token = client.get(f"{API}/auth/session").json()["csrf_token"]
    assert client.post(f"{API}/auth/logout", HTTP_X_CSRFTOKEN=token).status_code == 204


def test_login_rejects_cross_site_origin(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    body = {"email": ALICE, "password": PASS}
    forged = APIClient().post(f"{API}/auth/login", body, format="json", HTTP_ORIGIN="https://evil.example.test")
    assert forged.status_code == 403
    same = APIClient().post(f"{API}/auth/login", body, format="json", HTTP_ORIGIN="http://testserver")
    assert same.status_code == 200


# Sessions


def test_session_requires_a_cookie(pg) -> None:
    response = APIClient().get(f"{API}/auth/session")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_login_replaces_a_session_already_on_the_browser(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    client = logged_in(ALICE)
    old = client.cookies["collectiq_session"].value
    assert login(client, ALICE).status_code == 200
    assert client.cookies["collectiq_session"].value != old
    planted = APIClient()
    planted.cookies["collectiq_session"] = old
    assert planted.get(f"{API}/auth/session").status_code == 401


def test_logout_revokes_only_this_session(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    first, second = logged_in(ALICE), logged_in(ALICE)
    assert first.post(f"{API}/auth/logout").status_code == 204
    assert first.get(f"{API}/auth/session").status_code == 401
    assert second.get(f"{API}/auth/session").status_code == 200


def test_sign_out_everywhere_revokes_every_session(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    first, second = logged_in(ALICE), logged_in(ALICE)
    assert first.post(f"{API}/auth/logout?scope=all").status_code == 204
    assert second.get(f"{API}/auth/session").status_code == 401


def test_session_ends_at_the_absolute_limit(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    client = logged_in(ALICE)
    owner_db.execute("UPDATE user_sessions SET expires_at = now() - interval '1 second'")
    assert client.get(f"{API}/auth/session").status_code == 401


def test_idle_session_blocks_only_sensitive_actions(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    client = logged_in(ALICE)
    workspace = client.post(f"{API}/workspaces", WORKSPACE_BODY, format="json", **idem()).json()
    owner_db.execute("UPDATE user_sessions SET last_seen_at = now() - interval '31 minutes'")
    invite = {"email": "new@example.test", "role": "FINANCE_ADMIN"}
    url = f"{API}/workspaces/{workspace['id']}/invitations"
    assert client.post(url, invite, format="json", **idem()).status_code == 401
    assert client.get(f"{API}/workspaces/{workspace['id']}").status_code == 200
    assert client.post(url, invite, format="json", **idem()).status_code == 201


# Password reset


def _reset_token(email: str = ALICE) -> str:
    url = f"{API}/auth/password-reset/request"
    assert APIClient().post(url, {"email": email}, format="json").status_code == 204
    drain_jobs()
    return token_from(mailbox(email)[-1])


def _confirm(token: str, password: str = OTHER_PASS):
    body = {"token": token, "new_password": password}
    return APIClient().post(f"{API}/auth/password-reset/confirm", body, format="json")


def test_reset_token_single_use(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    token = _reset_token()
    assert _confirm(token).status_code == 204
    assert login(APIClient(), ALICE, OTHER_PASS).status_code == 200
    second = _confirm(token, "yet-another-long-phrase")
    assert second.status_code == 422
    assert login(APIClient(), ALICE, OTHER_PASS).status_code == 200


def test_expired_reset_token_is_rejected(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    token = _reset_token()
    owner_db.execute("UPDATE auth_tokens SET expires_at = now() - interval '1 second'")
    assert _confirm(token).status_code == 422


def test_a_newer_reset_token_replaces_the_older_one(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    first, second = _reset_token(), _reset_token()
    assert _confirm(first).status_code == 422
    assert _confirm(second).status_code == 204


def test_reset_revokes_every_session(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    client = logged_in(ALICE)
    assert _confirm(_reset_token()).status_code == 204
    assert client.get(f"{API}/auth/session").status_code == 401


def test_reset_request_is_silent_for_unknown_email(pg) -> None:
    response = APIClient().post(
        f"{API}/auth/password-reset/request", {"email": "nobody@example.test"}, format="json"
    )
    assert response.status_code == 204
    drain_jobs()
    assert email_port.memory_outbox == []


@override_settings(AUTH_EMAIL_HOURLY_LIMIT=2)
def test_reset_emails_to_one_address_are_capped(pg, owner_db) -> None:
    make_user(owner_db, ALICE)
    for _ in range(4):
        response = APIClient().post(f"{API}/auth/password-reset/request", {"email": ALICE}, format="json")
        assert response.status_code == 204
    drain_jobs()
    assert len(mailbox(ALICE)) == 2


# Audit


def test_auth_events_recorded(pg, owner_db) -> None:
    _verified_via_email()
    login(APIClient(), ALICE, WRONG)
    client = logged_in(ALICE)
    client.post(f"{API}/auth/logout")
    token = _reset_token()
    _confirm(token)
    events = _auth_events(owner_db)
    actions = [event[0] for event in events]
    for action in (
        "auth.register",
        "auth.verify_email",
        "auth.login.failure",
        "auth.login.success",
        "auth.logout",
        "auth.password_reset.requested",
        "auth.password_reset.confirmed",
    ):
        assert action in actions
    flat = json.dumps(events, default=str)
    assert ALICE not in flat and PASS not in flat and WRONG not in flat and token not in flat


# Email outage


def test_email_outage_is_retried_by_the_job(pg, owner_db, monkeypatch) -> None:
    def fail(*_args, **_kwargs) -> None:
        raise OSError("mail server down")

    _register()
    monkeypatch.setattr(email_port, "_deliver", fail)
    drain_jobs()
    assert email_port.memory_outbox == []
    row = owner_db.execute("SELECT attempts, status FROM background_jobs").fetchone()
    assert row == (1, "QUEUED")
    assert owner_db.execute("SELECT count(*) FROM auth_tokens WHERE used_at IS NULL").fetchone() == (0,)


# Correlation id


def test_problem_carries_the_correlation_id_it_was_sent(pg) -> None:
    response = APIClient().get(f"{API}/auth/session", HTTP_X_CORRELATION_ID="corr-abc-123")
    assert response.json()["correlation_id"] == "corr-abc-123"
    assert response["X-Correlation-ID"] == "corr-abc-123"


def test_unsafe_correlation_id_is_replaced(pg) -> None:
    response = APIClient().get(f"{API}/auth/session", HTTP_X_CORRELATION_ID="bad id\twith spaces")
    assert response.json()["correlation_id"] != "bad id\twith spaces"
