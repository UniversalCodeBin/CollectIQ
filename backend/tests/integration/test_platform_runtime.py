"""Idempotency, jobs, outbox and the envelope cipher, against real Postgres as the app role."""
import base64
import json
import os
import signal
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import psycopg
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import ProgrammingError, connection
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from collectiq import audit
from collectiq.audit.models import AuditEvent
from collectiq.platform import jobs, outbox
from collectiq.platform.context import RequestContext
from collectiq.platform.crypto import DecryptionError, EnvelopeCipher
from collectiq.platform.db import tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.platform.idempotency import idempotent

_seen: list[tuple] = []


@pytest.fixture(autouse=True)
def _clear_seen():
    _seen.clear()


def _ctx(workspace_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None) -> RequestContext:
    return RequestContext(
        workspace_id=workspace_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        role="OWNER",
        correlation_id="corr-test",
        actor_type="USER",
    )


def _audit_count(ctx: RequestContext) -> int:
    with tenant_tx(ctx):
        return AuditEvent.objects.count()


def _app_count(table: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT count(*) FROM {table}")
        return cursor.fetchone()[0]


def _job(owner_db: psycopg.Connection, job_id: uuid.UUID) -> dict:
    row = owner_db.execute(
        "SELECT status, attempts, last_error, run_at > now() AS backed_off"
        " FROM background_jobs WHERE id = %s",
        [job_id],
    ).fetchone()
    return dict(zip(("status", "attempts", "last_error", "backed_off"), row, strict=True))


def _enqueue(ctx: RequestContext, kind: str, **kwargs) -> uuid.UUID:
    with tenant_tx(ctx):
        return jobs.enqueue(ctx, kind, {"object_id": "obj-1"}, **kwargs)


# Idempotency


class _CreateView(APIView):
    ctx: RequestContext | None = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        request.ctx = self.ctx

    def effect(self, request) -> None:
        with tenant_tx(request.ctx):  # as a service would: it joins the transaction @idempotent opened
            audit.record(request.ctx, "thing.created", "thing", "t-1")

    @idempotent
    def post(self, request):
        self.effect(request)
        return Response(
            {"id": str(uuid.uuid4()), "zeta": 1, "alpha": [1, 2]},
            status=201,
            headers={"ETag": '"7"', "Location": "/things/1", "X-Other": "not-kept"},
        )


class _RaisingView(_CreateView):
    @idempotent
    def post(self, request):
        self.effect(request)
        raise ProblemError("STATE_TRANSITION_INVALID", 409, "Cannot do that now.")


class _ReturnedConflictView(_CreateView):
    @idempotent
    def post(self, request):
        self.effect(request)
        return Response({"code": "CONFLICT"}, status=409)


def _call(ctx, body=None, key: object = "auto", view=_CreateView, path="/api/v1/things"):
    headers = {}
    if key is not None:
        headers["HTTP_IDEMPOTENCY_KEY"] = str(uuid.uuid4()) if key == "auto" else str(key)
    request = APIRequestFactory().post(path, body or {"name": "a"}, format="json", **headers)
    return view.as_view(ctx=ctx)(request).render()


def test_replay_same_key_returns_original_response(pg) -> None:
    ctx, key = _ctx(), uuid.uuid4()
    first = _call(ctx, key=key)
    second = _call(ctx, key=key)
    assert first.status_code == second.status_code == 201
    assert first.content == second.content  # byte-identical: the key order is kept too
    assert (second["ETag"], second["Location"]) == ('"7"', "/things/1")
    assert "X-Other" not in second
    assert _audit_count(ctx) == 1


def test_same_key_different_body_is_422(pg) -> None:
    ctx, key = _ctx(), uuid.uuid4()
    _call(ctx, {"name": "a"}, key=key)
    response = _call(ctx, {"name": "b"}, key=key)
    assert response.status_code == 422
    assert response["Content-Type"].startswith("application/problem+json")
    assert json.loads(response.content)["code"] == "IDEMPOTENCY_MISMATCH"
    assert _audit_count(ctx) == 1


def test_same_key_on_another_path_is_422(pg) -> None:
    ctx, key = _ctx(), uuid.uuid4()
    _call(ctx, key=key)
    assert _call(ctx, key=key, path="/api/v1/others").status_code == 422


def test_same_key_from_another_user_is_422_not_a_replay(pg) -> None:
    workspace_id, key = uuid.uuid4(), uuid.uuid4()
    first = _call(_ctx(workspace_id), key=key)
    second = _call(_ctx(workspace_id), key=key)
    assert second.status_code == 422
    assert json.loads(first.content)["id"] not in second.content.decode()


def test_same_key_in_another_workspace_is_independent(pg) -> None:
    key, first, second = uuid.uuid4(), _ctx(), _ctx()
    assert _call(first, key=key).content != _call(second, key=key).content
    assert (_audit_count(first), _audit_count(second)) == (1, 1)


@pytest.mark.parametrize("key", [None, "not-a-uuid"], ids=["missing", "malformed"])
def test_missing_or_malformed_key_is_422(pg, key: object) -> None:
    ctx = _ctx()
    response = _call(ctx, key=key)
    assert response.status_code == 422
    body = json.loads(response.content)
    assert body["code"] == "VALIDATION_FAILED"
    assert body["errors"][0]["field"] == "Idempotency-Key"
    assert _audit_count(ctx) == 0


@pytest.mark.parametrize("view", [_RaisingView, _ReturnedConflictView], ids=["raised", "returned"])
def test_failed_request_undoes_its_work_and_releases_the_key(pg, view: type[APIView]) -> None:
    ctx, key = _ctx(), uuid.uuid4()
    assert _call(ctx, key=key, view=view).status_code == 409
    assert _audit_count(ctx) == 0
    assert _call(ctx, key=key).status_code == 201  # not a stored failure, and no mismatch
    assert _audit_count(ctx) == 1


def test_key_expires_after_24_hours(pg, owner_db: psycopg.Connection) -> None:
    ctx, key = _ctx(), uuid.uuid4()
    first = _call(ctx, key=key)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [str(ctx.workspace_id)])
    owner_db.execute("UPDATE idempotency_keys SET created_at = now() - interval '23 hours 59 minutes'")
    assert _call(ctx, key=key).content == first.content
    owner_db.execute("UPDATE idempotency_keys SET created_at = now() - interval '24 hours 1 minute'")
    assert _call(ctx, key=key).content != first.content
    assert _audit_count(ctx) == 2


@pytest.mark.concurrency
def test_concurrent_same_key_runs_once(pg) -> None:
    ctx, key = _ctx(), uuid.uuid4()
    callers = 8
    barrier = threading.Barrier(callers)
    bodies: list[bytes] = []
    failures: list[BaseException] = []

    def caller() -> None:
        try:
            barrier.wait(timeout=30)
            bodies.append(_call(ctx, key=key).content)
        except BaseException as exc:  # reported on the main thread below
            failures.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=caller) for _ in range(callers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert failures == []
    assert len(bodies) == callers
    assert len(set(bodies)) == 1
    assert _audit_count(ctx) == 1


# Jobs


@jobs.job_handler("test.record")
def _record_handler(ctx: RequestContext, payload: dict) -> None:
    with tenant_tx(ctx):  # handlers call services, and services open tenant_tx
        audit.record(ctx, "job.ran", "job", payload["object_id"])
    _seen.append((ctx.workspace_id, ctx.actor_type, ctx.correlation_id, payload))


@jobs.job_handler("test.peek")
def _peek_handler(ctx: RequestContext, payload: dict) -> None:
    _seen.append((ctx.workspace_id, AuditEvent.objects.count(), _app_count("background_jobs")))


@jobs.job_handler("test.fail")
def _failing_handler(ctx: RequestContext, payload: dict) -> None:
    audit.record(ctx, "job.ran", "job", "never-committed")
    raise ValueError("customer asha@example.test is wrong")


def test_handler_without_context_sees_no_rows(pg) -> None:
    ctx, other = _ctx(), _ctx()
    with tenant_tx(ctx):
        audit.record(ctx, "a.b", "x", "1")
        jobs.enqueue(ctx, "test.peek", {"object_id": "obj-1"})
    with tenant_tx(other):
        audit.record(other, "a.b", "x", "2")
        jobs.enqueue(other, "test.peek", {"object_id": "obj-2"}, dedupe_key="later")

    job = jobs.claim()
    assert job is not None
    # The claim hands over a row, not a tenant context: outside tenant_tx nothing is visible.
    assert _app_count("audit_events") == 0
    assert _app_count("background_jobs") == 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.workspace_id', true)")
        assert cursor.fetchone()[0] in ("", None)

    jobs.run_job(job)
    assert _seen == [(job.workspace_id, 1, 1)]  # its own audit row and job only, in its own context
    assert _app_count("background_jobs") == 0


def test_handler_runs_with_a_system_context_and_the_enqueuers_correlation(pg, owner_db) -> None:
    ctx = _ctx()
    job_id = _enqueue(ctx, "test.record")
    assert jobs.run_once() is True
    assert _seen == [(ctx.workspace_id, "SYSTEM", "corr-test", {"object_id": "obj-1"})]
    assert _job(owner_db, job_id)["status"] == "DONE"
    assert _audit_count(ctx) == 1
    assert jobs.run_once() is False


KILLED_WORKER = """
import os, signal, django
django.setup()
from collectiq import audit
from collectiq.platform import jobs

@jobs.job_handler("test.record")
def die(ctx, payload):
    audit.record(ctx, "job.ran", "job", "uncommitted")
    os.kill(os.getpid(), signal.SIGKILL)

jobs.run_once(lease_seconds=300)
"""


def test_killed_worker_job_requeues_after_lease(pg, owner_db: psycopg.Connection) -> None:
    ctx = _ctx()
    job_id = _enqueue(ctx, "test.record")
    worker = subprocess.run(
        [sys.executable, "-c", KILLED_WORKER],
        cwd=Path(__file__).parents[2],
        env=os.environ | {"DJANGO_SETTINGS_MODULE": "collectiq.settings.test"},
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert worker.returncode == -signal.SIGKILL, worker.stderr.decode()[-500:]
    assert _job(owner_db, job_id) == {
        "status": "RUNNING",
        "attempts": 1,
        "last_error": None,
        "backed_off": False,
    }
    assert _audit_count(ctx) == 0  # the handler's transaction died with the worker
    assert jobs.claim() is None  # the lease still holds

    owner_db.execute("UPDATE background_jobs SET lease_until = now() - interval '1 second'")
    assert jobs.run_once() is True
    assert _job(owner_db, job_id)["status"] == "DONE"
    assert _job(owner_db, job_id)["attempts"] == 2
    assert _audit_count(ctx) == 1


def test_dead_letter_after_max_attempts(pg, owner_db: psycopg.Connection) -> None:
    ctx = _ctx()
    job_id = _enqueue(ctx, "test.fail", max_attempts=2)

    assert jobs.run_once() is True
    state = _job(owner_db, job_id)
    assert (state["status"], state["attempts"], state["backed_off"]) == ("QUEUED", 1, True)
    assert jobs.claim() is None  # backing off
    assert _audit_count(ctx) == 0  # the failed attempt rolled back

    owner_db.execute("UPDATE background_jobs SET run_at = now()")
    assert jobs.run_once() is True
    assert _job(owner_db, job_id)["status"] == "DEAD_LETTER"
    assert _job(owner_db, job_id)["attempts"] == 2
    owner_db.execute("UPDATE background_jobs SET run_at = now()")
    assert jobs.claim() is None


def test_failure_records_the_error_type_without_its_message(pg, owner_db: psycopg.Connection) -> None:
    job_id = _enqueue(_ctx(), "test.fail")
    jobs.run_once()
    assert _job(owner_db, job_id)["last_error"] == "ValueError"


def test_problem_error_records_its_code(pg, owner_db: psycopg.Connection) -> None:
    @jobs.job_handler("test.problem")
    def handler(ctx: RequestContext, payload: dict) -> None:
        raise ProblemError("INTEGRATION_UNAVAILABLE", 503, "Provider said no to asha@example.test.")

    job_id = _enqueue(_ctx(), "test.problem")
    jobs.run_once()
    assert _job(owner_db, job_id)["last_error"] == "INTEGRATION_UNAVAILABLE"


def test_lease_expiry_on_the_last_attempt_dead_letters(pg, owner_db: psycopg.Connection) -> None:
    job_id = _enqueue(_ctx(), "test.record", max_attempts=1)
    assert jobs.claim() is not None
    owner_db.execute("UPDATE background_jobs SET lease_until = now() - interval '1 second'")
    assert jobs.claim() is None
    state = _job(owner_db, job_id)
    assert (state["status"], state["last_error"]) == ("DEAD_LETTER", "LEASE_EXPIRED")


def test_unknown_kind_fails_like_any_handler(pg, owner_db: psycopg.Connection) -> None:
    job_id = _enqueue(_ctx(), "test.unregistered")
    assert jobs.run_once() is True
    state = _job(owner_db, job_id)
    assert (state["status"], state["last_error"]) == ("QUEUED", "UnknownJobKind")


def test_worker_that_lost_its_lease_cannot_commit(pg, owner_db: psycopg.Connection) -> None:
    ctx = _ctx()
    job_id = _enqueue(ctx, "test.record")
    job = jobs.claim()
    owner_db.execute("UPDATE background_jobs SET lease_token = gen_random_uuid()")  # another worker took it
    jobs.run_job(job)
    assert _job(owner_db, job_id)["status"] == "RUNNING"
    assert _audit_count(ctx) == 0  # fenced: the stale worker's effects rolled back


def test_worker_that_lost_its_lease_cannot_record_a_failure(pg, owner_db: psycopg.Connection) -> None:
    job_id = _enqueue(_ctx(), "test.fail")
    job = jobs.claim()
    owner_db.execute("UPDATE background_jobs SET lease_token = gen_random_uuid()")
    jobs.run_job(job)
    assert _job(owner_db, job_id)["status"] == "RUNNING"


def _set_lock_timeout(value: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('lock_timeout', %s, false)", [value])


@pytest.mark.concurrency
def test_claim_skips_a_row_another_worker_has_locked(pg, owner_db: psycopg.Connection) -> None:
    locked = _enqueue(_ctx(), "test.record", dedupe_key="locked")
    free = _enqueue(_ctx(), "test.record", dedupe_key="free")
    _set_lock_timeout("2s")  # waiting on the lock fails the test here rather than hanging it
    with owner_db.transaction():
        owner_db.execute("SELECT 1 FROM background_jobs WHERE id = %s FOR UPDATE", [locked])
        job = jobs.claim()
    assert job is not None
    assert job.id == free


@pytest.mark.concurrency
def test_dead_letter_sweep_skips_a_row_another_worker_has_locked(pg, owner_db: psycopg.Connection) -> None:
    job_id = _enqueue(_ctx(), "test.record")
    owner_db.execute(
        "UPDATE background_jobs SET status = 'RUNNING', attempts = max_attempts,"
        " lease_until = now() - interval '1 hour' WHERE id = %s",
        [job_id],
    )
    _set_lock_timeout("2s")
    with owner_db.transaction():
        owner_db.execute("SELECT 1 FROM background_jobs WHERE id = %s FOR UPDATE", [job_id])
        assert jobs.claim() is None
    assert _job(owner_db, job_id)["status"] == "RUNNING"


@pytest.mark.concurrency
def test_concurrent_claims_never_share_a_job(pg) -> None:
    total, workers = 30, 6
    for number in range(total):
        _enqueue(_ctx(), "test.record", dedupe_key=str(number))
    barrier = threading.Barrier(workers)
    claimed: list[uuid.UUID] = []
    failures: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=30)
            while (job := jobs.claim()) is not None:
                claimed.append(job.id)
        except BaseException as exc:  # reported on the main thread below
            failures.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert failures == []
    assert len(claimed) == total
    assert len(set(claimed)) == total


def test_claim_function_is_definer_with_pinned_search_path_and_no_public_grant(owner_db) -> None:
    secdef, config, acl = owner_db.execute(
        "SELECT prosecdef, proconfig, proacl::text FROM pg_proc WHERE proname = 'claim_background_job'"
    ).fetchone()
    assert secdef is True
    assert config == ["search_path=pg_catalog, pg_temp"]
    assert "collectiq_app=X/" in acl
    assert not acl.startswith("{=X/") and ",=X/" not in acl


def test_app_role_cannot_delete_or_truncate_jobs_or_outbox(pg) -> None:
    for statement in (
        "DELETE FROM background_jobs",
        "TRUNCATE background_jobs",
        "DELETE FROM outbox_events",
        "TRUNCATE outbox_events",
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), connection.cursor() as cursor:
            cursor.execute(statement)


def test_enqueue_refuses_to_run_outside_a_transaction(pg) -> None:
    with pytest.raises(RuntimeError, match="transaction"):
        jobs.enqueue(_ctx(), "test.record", {"object_id": "obj-1"})


def test_enqueue_rolls_back_with_the_caller(pg) -> None:
    ctx = _ctx()
    with pytest.raises(ValueError, match="boom"), tenant_tx(ctx):
        jobs.enqueue(ctx, "test.record", {"object_id": "obj-1"})
        raise ValueError("boom")
    assert jobs.claim() is None


def test_dedupe_key_enqueues_once_per_workspace(pg, owner_db: psycopg.Connection) -> None:
    ctx, other = _ctx(), _ctx()
    first = _enqueue(ctx, "test.record", dedupe_key="same")
    assert _enqueue(ctx, "test.record", dedupe_key="same") == first
    assert _enqueue(other, "test.record", dedupe_key="same") != first
    assert owner_db.execute("SELECT count(*) FROM background_jobs").fetchone() == (2,)


@pytest.mark.parametrize(
    "payload",
    [{"body": {"nested": "text"}}, {"body": "x" * 129}, {"amount": 12.5}, {"ids": [{"a": 1}]}],
    ids=["nested", "long-string", "float", "list-of-maps"],
)
def test_job_payload_carries_ids_only(payload: dict) -> None:
    with pytest.raises(ValueError, match="IDs"):
        jobs.require_ids_only(payload)


def test_job_payload_accepts_ids() -> None:
    jobs.require_ids_only(
        {"invoice_id": uuid.uuid4(), "line": 3, "force": True, "ids": ["a", "b"], "x": None}
    )


def test_backoff_grows_with_jitter_up_to_a_cap() -> None:
    samples = {attempt: [jobs.backoff_seconds(attempt) for _ in range(50)] for attempt in (1, 2, 3, 30)}
    assert all(15 <= value <= 30 for value in samples[1])
    assert all(30 <= value <= 60 for value in samples[2])
    assert all(60 <= value <= 120 for value in samples[3])
    assert all(value <= 3600 for value in samples[30])
    assert len(set(samples[1])) > 1


def test_duplicate_handler_registration_is_refused() -> None:
    with pytest.raises(ValueError, match="test.record"):
        jobs.job_handler("test.record")(lambda ctx, payload: None)


def test_run_worker_drains_due_jobs_and_exits(pg, owner_db: psycopg.Connection) -> None:
    first, second = _enqueue(_ctx(), "test.record"), _enqueue(_ctx(), "test.record")
    call_command("run_worker", "--drain")
    assert _job(owner_db, first)["status"] == _job(owner_db, second)["status"] == "DONE"


# Outbox


@outbox.subscriber("test.happened")
def _on_happened(ctx: RequestContext, payload: dict) -> None:
    _seen.append((ctx.workspace_id, payload))


def test_outbox_event_reaches_subscriber_in_tenant_context(pg, owner_db: psycopg.Connection) -> None:
    ctx = _ctx()
    with tenant_tx(ctx):
        event_id = outbox.publish(ctx, "test.happened", {"object_id": "obj-1"})
    assert jobs.run_once() is True
    assert _seen == [(ctx.workspace_id, {"object_id": "obj-1"})]
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [str(ctx.workspace_id)])
    assert owner_db.execute(
        "SELECT published_at IS NOT NULL FROM outbox_events WHERE id = %s", [event_id]
    ).fetchone() == (True,)


def test_outbox_event_rolls_back_with_the_caller(pg) -> None:
    ctx = _ctx()
    with pytest.raises(ValueError, match="boom"), tenant_tx(ctx):
        outbox.publish(ctx, "test.happened", {"object_id": "obj-1"})
        raise ValueError("boom")
    assert jobs.claim() is None
    with tenant_tx(ctx):
        assert _app_count("outbox_events") == 0


def test_outbox_event_without_a_subscriber_is_still_published(pg, owner_db: psycopg.Connection) -> None:
    ctx = _ctx()
    with tenant_tx(ctx):
        event_id = outbox.publish(ctx, "test.nobody_listens", {"object_id": "obj-1"})
    assert jobs.run_once() is True
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [str(ctx.workspace_id)])
    assert owner_db.execute(
        "SELECT published_at IS NOT NULL FROM outbox_events WHERE id = %s", [event_id]
    ).fetchone() == (True,)


# Cipher


_PLAINTEXT = b"synthetic message for asha@example.test"


def _cipher() -> EnvelopeCipher:
    return EnvelopeCipher(base64.b64encode(bytes(range(32))).decode())


def test_cipher_round_trip_uses_a_fresh_nonce(pg) -> None:
    ctx, cipher = _ctx(), _cipher()
    with tenant_tx(ctx):
        first, second = cipher.encrypt(ctx, _PLAINTEXT), cipher.encrypt(ctx, _PLAINTEXT)
        assert first != second
        assert _PLAINTEXT not in first
        assert cipher.decrypt(ctx, first) == cipher.decrypt(ctx, second) == _PLAINTEXT


def test_cipher_refuses_another_workspaces_ciphertext(pg) -> None:
    ctx, other, cipher = _ctx(), _ctx(), _cipher()
    with tenant_tx(ctx):
        sealed = cipher.encrypt(ctx, _PLAINTEXT)
    with tenant_tx(other), pytest.raises(DecryptionError):
        cipher.decrypt(other, sealed)


def test_cipher_refuses_tampering_and_a_different_aad(pg) -> None:
    ctx, cipher = _ctx(), _cipher()
    with tenant_tx(ctx):
        sealed = cipher.encrypt(ctx, _PLAINTEXT, aad=b"message:1")
        assert cipher.decrypt(ctx, sealed, aad=b"message:1") == _PLAINTEXT
        for bad, aad in (
            (sealed[:-1] + bytes([sealed[-1] ^ 1]), b"message:1"),
            (sealed, b"message:2"),
            (sealed[:5], b"message:1"),
            (b"\x09" + sealed[1:], b"message:1"),
        ):
            with pytest.raises(DecryptionError):
                cipher.decrypt(ctx, bad, aad=aad)


def test_cipher_stores_one_wrapped_key_per_workspace(pg, owner_db: psycopg.Connection) -> None:
    ctx, cipher = _ctx(), _cipher()
    with tenant_tx(ctx):
        sealed = cipher.encrypt(ctx, _PLAINTEXT)
        cipher.encrypt(ctx, _PLAINTEXT)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [str(ctx.workspace_id)])
    rows = owner_db.execute("SELECT wrapped_key FROM workspace_keys").fetchall()
    assert len(rows) == 1
    assert len(rows[0][0]) > 32  # wrapped: a nonce and a tag around the 32-byte data key

    other_master = EnvelopeCipher(base64.b64encode(bytes(32)).decode())
    with tenant_tx(ctx), pytest.raises(DecryptionError):
        other_master.decrypt(ctx, sealed)


def test_cipher_refuses_to_run_outside_a_transaction(pg) -> None:
    with pytest.raises(RuntimeError, match="transaction"):
        _cipher().encrypt(_ctx(), _PLAINTEXT)


@pytest.mark.parametrize("key", ["", "not base64!", base64.b64encode(bytes(16)).decode()])
def test_cipher_rejects_a_bad_master_key(key: str) -> None:
    with pytest.raises(ImproperlyConfigured):
        EnvelopeCipher(key)


def test_app_role_cannot_change_or_remove_wrapped_keys(pg) -> None:
    ctx = _ctx()
    with tenant_tx(ctx):
        _cipher().encrypt(ctx, _PLAINTEXT)
    for statement in ("UPDATE workspace_keys SET wrapped_key = ''", "DELETE FROM workspace_keys"):
        with pytest.raises(ProgrammingError, match="permission denied"), tenant_tx(ctx):
            with connection.cursor() as cursor:
                cursor.execute(statement)
