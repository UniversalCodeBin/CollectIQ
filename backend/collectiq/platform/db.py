"""Transactions that carry the tenant context. Services open them; views never do.

Opening at the service boundary means an exception rolls back before DRF handles it. The two callers above
a service, @idempotent and the job runner, open the same scope first; the service then joins as a savepoint.
"""
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from uuid import UUID

from django.db import connection, transaction

from .context import RequestContext

_Scope = tuple[UUID | None, UUID | None]
_active_scope: ContextVar[_Scope | None] = ContextVar("collectiq_tenant_scope", default=None)


@contextmanager
def _scoped_tx(workspace_id: UUID | None, user_id: UUID | None) -> Iterator[None]:
    scope = (workspace_id, user_id)
    if connection.in_atomic_block:
        # SET LOCAL lasts until the outermost commit, so a nested scope would leak into its parent.
        if _active_scope.get() != scope:
            raise RuntimeError("a transaction is already open; tenant context must start it")
        with transaction.atomic():
            yield
        return
    token = _active_scope.set(scope)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.workspace_id', %s, true), set_config('app.user_id', %s, true)",
                    [str(workspace_id) if workspace_id else "", str(user_id) if user_id else ""],
                )
            yield
    finally:
        _active_scope.reset(token)


def tenant_tx(ctx: RequestContext) -> AbstractContextManager[None]:
    return _scoped_tx(ctx.workspace_id, ctx.user_id)


def user_tx(user_id: UUID) -> AbstractContextManager[None]:
    """For the few reads before a workspace is known: a user's own memberships and profile."""
    return _scoped_tx(None, user_id)
