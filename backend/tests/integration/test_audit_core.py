"""The audit write path: same-transaction inserts, append-only by privilege and trigger, hash-chained."""
import json
import threading
import uuid

import psycopg
import pytest
from django.db import ProgrammingError, connection

from collectiq import audit
from collectiq.audit.models import AuditEvent
from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx

_SENSITIVE = "must-not-reach-storage"


def _ctx(workspace_id: uuid.UUID | None = None) -> RequestContext:
    return RequestContext(
        workspace_id=workspace_id or uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="OWNER",
        correlation_id="corr-test",
        actor_type="USER",
    )


def _write(ctx: RequestContext, count: int = 1) -> None:
    with tenant_tx(ctx):
        for number in range(count):
            audit.record(ctx, "invoice.updated", "invoice", f"inv-{number}")


def _chain(ctx: RequestContext) -> list[AuditEvent]:
    with tenant_tx(ctx):
        return list(AuditEvent.objects.order_by("id"))


def _assert_linear(rows: list[AuditEvent]) -> None:
    assert rows[0].prev_hash is None
    for previous, current in zip(rows, rows[1:], strict=False):
        assert bytes(current.prev_hash) == bytes(previous.hash)
    assert len({bytes(row.hash) for row in rows}) == len(rows)


@pytest.mark.parametrize(
    "statement",
    ["UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events", "TRUNCATE audit_events"],
    ids=["update", "delete", "truncate"],
)
def test_app_role_cannot_update_delete_truncate(pg, statement: str) -> None:
    ctx = _ctx()
    _write(ctx)
    with pytest.raises(ProgrammingError, match="permission denied"), tenant_tx(ctx):
        with connection.cursor() as cursor:
            cursor.execute(statement)
    assert len(_chain(ctx)) == 1


@pytest.mark.parametrize(
    "statement",
    ["UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events"],
    ids=["update", "delete"],
)
def test_trigger_blocks_changes_even_for_the_owner(pg, owner_db: psycopg.Connection, statement: str) -> None:
    ctx = _ctx()
    _write(ctx)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [str(ctx.workspace_id)])
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        owner_db.execute(statement)


def test_hash_links_per_workspace(pg) -> None:
    first, second = _ctx(), _ctx()
    for _ in range(3):  # interleaved, so a chain shared across workspaces would be caught
        _write(first)
        _write(second)
    first_rows, second_rows = _chain(first), _chain(second)
    assert len(first_rows) == len(second_rows) == 3
    _assert_linear(first_rows)
    _assert_linear(second_rows)
    assert not {bytes(row.hash) for row in first_rows} & {bytes(row.hash) for row in second_rows}


def test_hash_detects_an_edit(pg, owner_db: psycopg.Connection) -> None:
    ctx = _ctx()
    _write(ctx, count=2)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [str(ctx.workspace_id)])
    recompute = "SELECT count(*) FROM audit_events e WHERE e.hash <> audit_event_hash(e)"
    assert owner_db.execute(recompute).fetchone() == (0,)

    owner_db.execute("ALTER TABLE audit_events DISABLE TRIGGER USER")
    try:
        owner_db.execute("UPDATE audit_events SET after_masked = '{\"edited\": true}'")
    finally:
        owner_db.execute("ALTER TABLE audit_events ENABLE TRIGGER USER")
    assert owner_db.execute(recompute).fetchone() == (2,)


def test_caller_cannot_supply_the_hash_or_the_link(pg) -> None:
    ctx = _ctx()
    _write(ctx)
    with tenant_tx(ctx), connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO audit_events (workspace_id, actor_type, action, object_type, object_id,"
            " correlation_id, prev_hash, hash) VALUES (%s, 'USER', 'a.b', 'x', '1', 'c', %s, %s)",
            [str(ctx.workspace_id), b"forged-link", b"forged-hash"],
        )
    rows = _chain(ctx)
    _assert_linear(rows)
    assert bytes(rows[-1].hash) != b"forged-hash"


@pytest.mark.concurrency
def test_concurrent_writers_keep_chain_linear(pg) -> None:
    ctx = _ctx()
    writers, writes_each = 8, 20
    barrier = threading.Barrier(writers)
    failures: list[BaseException] = []

    def writer() -> None:
        try:
            barrier.wait(timeout=30)
            for _ in range(writes_each):
                _write(ctx)
        except BaseException as exc:  # reported on the main thread below
            failures.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=writer) for _ in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert failures == []
    rows = _chain(ctx)
    assert len(rows) == writers * writes_each
    _assert_linear(rows)


def test_rollback_leaves_no_audit_row(pg) -> None:
    ctx = _ctx()
    with pytest.raises(RuntimeError, match="boom"), tenant_tx(ctx):
        audit.record(ctx, "invoice.updated", "invoice", "inv-1")
        raise RuntimeError("boom")
    assert _chain(ctx) == []

    _write(ctx)  # the rolled-back row must not have moved the chain head either
    assert _chain(ctx)[0].prev_hash is None


def test_masking_removes_sensitive_fields(pg) -> None:
    ctx = _ctx()
    before = {
        "status": "OPEN",
        "password": _SENSITIVE,
        "nested": {"api_key": _SENSITIVE, "Access_Token": _SENSITIVE, "kept": 1},
        "contacts": [{"name": "Asha", "account_number": _SENSITIVE}],
    }
    after = {"status": "PAID", "password_hash": _SENSITIVE, "amount_minor": 1200}
    evidence = {"message_id": "m-1", "email_body": _SENSITIVE}
    with tenant_tx(ctx):
        audit.record(
            ctx, "invoice.updated", "invoice", "inv-1", before=before, after=after, evidence_refs=evidence
        )

    row = _chain(ctx)[0]
    assert row.evidence_refs == {"message_id": "m-1"}
    assert row.before_masked == {
        "status": "OPEN",
        "nested": {"kept": 1},
        "contacts": [{"name": "Asha"}],
    }
    assert row.after_masked == {"status": "PAID", "amount_minor": 1200}
    assert _SENSITIVE not in json.dumps([row.before_masked, row.after_masked, row.evidence_refs])


def test_record_stores_context_and_decision_fields(pg) -> None:
    ctx = _ctx()
    decision = uuid.uuid4()
    with tenant_tx(ctx):
        audit.record(
            ctx,
            "policy.decision",
            "reminder",
            "rem-1",
            reason_codes=("DISPUTE_OPEN", "SNOOZED"),
            evidence_refs={"message_id": "m-1"},
            policy_decision_id=decision,
        )
    row = _chain(ctx)[0]
    assert (row.workspace_id, row.actor_id, row.actor_type) == (ctx.workspace_id, ctx.user_id, "USER")
    assert (row.action, row.object_type, row.object_id) == ("policy.decision", "reminder", "rem-1")
    assert row.correlation_id == "corr-test"
    assert row.reason_codes == ["DISPUTE_OPEN", "SNOOZED"]
    assert row.evidence_refs == {"message_id": "m-1"}
    assert row.policy_decision_id == decision


def test_other_workspace_events_are_invisible(pg) -> None:
    first, second = _ctx(), _ctx()
    _write(first)
    assert _chain(second) == []


def test_record_refuses_to_run_outside_a_transaction(pg) -> None:
    with pytest.raises(RuntimeError, match="transaction"):
        audit.record(_ctx(), "invoice.updated", "invoice", "inv-1")


def test_record_refuses_another_workspaces_context(pg) -> None:
    current, other = _ctx(), _ctx()
    with pytest.raises(ProgrammingError, match="row-level security"), tenant_tx(current):
        audit.record(other, "invoice.updated", "invoice", "inv-1")


def test_stored_anchor_catches_a_rehashed_rewrite(pg, owner_db: psycopg.Connection, tmp_path) -> None:
    """The chain alone misses a rewrite that also fixes the hashes; an off-host anchor catches it."""
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    ctx = _ctx()
    _write(ctx, count=2)
    from collectiq.platform.management.commands.audit_anchor import _head

    anchor = tmp_path / "anchor.jsonl"
    anchor.write_text(json.dumps(_head(ctx.workspace_id)) + "\n")
    call_command("audit_anchor", check=str(anchor), stdout=StringIO())  # untouched: passes

    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [str(ctx.workspace_id)])
    owner_db.execute("ALTER TABLE audit_events DISABLE TRIGGER USER")
    try:
        owner_db.execute("UPDATE audit_events SET after_masked = '{\"edited\": true}'")
        owner_db.execute("UPDATE audit_events e SET hash = audit_event_hash(e)")
    finally:
        owner_db.execute("ALTER TABLE audit_events ENABLE TRIGGER USER")
    with pytest.raises(CommandError, match="no longer match"):
        call_command("audit_anchor", check=str(anchor), stdout=StringIO())
