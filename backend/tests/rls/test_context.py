"""Forced RLS and the transaction context, against real Postgres as the app role."""
import uuid

import pytest
from django.db import ProgrammingError, connection, transaction

from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx, user_tx


def _ctx(workspace_id: uuid.UUID) -> RequestContext:
    return RequestContext(
        workspace_id=workspace_id, user_id=uuid.uuid4(), role="OWNER",
        correlation_id="test", actor_type="USER",
    )


def _insert(workspace_id: uuid.UUID) -> None:
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO rls_probe (workspace_id) VALUES (%s)", [workspace_id])


def _count() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM rls_probe")
        return cursor.fetchone()[0]


def _setting(name: str) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [name])
        return cursor.fetchone()[0]


def _backend_pid() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        return cursor.fetchone()[0]


def test_no_context_returns_zero_rows(pg):
    workspace = uuid.uuid4()
    with tenant_tx(_ctx(workspace)):
        _insert(workspace)
    assert _count() == 0


def test_context_resets_after_commit_on_reused_connection(pg):
    workspace = uuid.uuid4()
    pid = _backend_pid()
    with tenant_tx(_ctx(workspace)):
        _insert(workspace)
        assert _count() == 1
    assert _backend_pid() == pid
    assert not _setting("app.workspace_id")
    assert _count() == 0


def test_other_workspace_row_invisible(pg):
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    with tenant_tx(_ctx(theirs)):
        _insert(theirs)
    with tenant_tx(_ctx(mine)):
        assert _count() == 0


def test_app_role_is_not_owner_and_cannot_disable_rls(pg):
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        assert cursor.fetchone() == ("collectiq_app", False, False)
        cursor.execute("SELECT tableowner FROM pg_tables WHERE tablename = 'rls_probe'")
        assert cursor.fetchone()[0] == "collectiq_owner"
        cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'rls_probe'")
        assert cursor.fetchone() == (True, True)
    with pytest.raises(ProgrammingError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("ALTER TABLE rls_probe DISABLE ROW LEVEL SECURITY")


def test_insert_for_other_workspace_is_rejected(pg):
    with pytest.raises(ProgrammingError), tenant_tx(_ctx(uuid.uuid4())):
        _insert(uuid.uuid4())


def test_insert_without_context_is_rejected(pg):
    with pytest.raises(ProgrammingError), transaction.atomic():
        _insert(uuid.uuid4())


def test_exception_rolls_back_and_clears_context(pg):
    workspace = uuid.uuid4()
    with pytest.raises(RuntimeError, match="boom"), tenant_tx(_ctx(workspace)):
        _insert(workspace)
        raise RuntimeError("boom")
    assert not _setting("app.workspace_id")
    with tenant_tx(_ctx(workspace)):
        assert _count() == 0


def test_nested_tenant_tx_is_refused(pg):
    # SET LOCAL would otherwise outlive the inner block, carrying the wrong workspace onward.
    with tenant_tx(_ctx(uuid.uuid4())), pytest.raises(RuntimeError, match="already"):
        with tenant_tx(_ctx(uuid.uuid4())):
            pass


def test_tenant_tx_inside_open_transaction_is_refused(pg):
    with transaction.atomic(), pytest.raises(RuntimeError, match="already"), tenant_tx(_ctx(uuid.uuid4())):
        pass


def test_user_tx_sets_user_without_workspace(pg):
    user = uuid.uuid4()
    with user_tx(user):
        assert _setting("app.user_id") == str(user)
        assert not _setting("app.workspace_id")
        assert _count() == 0
    assert not _setting("app.user_id")


def test_tenant_tx_sets_user_for_audit_and_policy(pg):
    ctx = _ctx(uuid.uuid4())
    with tenant_tx(ctx):
        assert _setting("app.workspace_id") == str(ctx.workspace_id)
        assert _setting("app.user_id") == str(ctx.user_id)


def test_same_scope_joins_the_open_tenant_tx(pg):
    ctx = _ctx(uuid.uuid4())
    with tenant_tx(ctx):
        _insert(ctx.workspace_id)
        with pytest.raises(ValueError, match="inner"), tenant_tx(ctx):  # a savepoint: only this part undoes
            _insert(ctx.workspace_id)
            raise ValueError("inner")
        with tenant_tx(ctx):
            _insert(ctx.workspace_id)
    with tenant_tx(ctx):
        assert _count() == 2


def test_same_workspace_other_user_is_refused_inside_tenant_tx(pg):
    workspace_id = uuid.uuid4()
    with tenant_tx(_ctx(workspace_id)), pytest.raises(RuntimeError, match="already"):
        with tenant_tx(_ctx(workspace_id)):
            pass
