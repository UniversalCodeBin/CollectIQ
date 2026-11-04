"""Deny by default, and the human-only actions stay human (TSD M03, INV-03, INV-06)."""

import uuid

import pytest

from collectiq.platform.context import RequestContext
from collectiq.platform.errors import ProblemError
from collectiq.tenancy.permissions import (
    AI_SETTINGS_WRITE,
    CASE_OPEN,
    DRAFT_APPROVE,
    LEDGER_WRITE,
    authorize,
    is_allowed,
)


def _ctx(role: str | None, actor_type: str = "USER") -> RequestContext:
    return RequestContext(uuid.uuid4(), uuid.uuid4(), role, "corr", actor_type)


def test_unknown_permission_is_denied() -> None:
    assert not is_allowed("OWNER", "USER", "no.such.permission")


@pytest.mark.parametrize("role", [None, "", "SUPERADMIN", "owner"])
def test_unknown_role_is_denied(role: str | None) -> None:
    assert not is_allowed(role, "USER", LEDGER_WRITE)


@pytest.mark.parametrize("permission", [LEDGER_WRITE, DRAFT_APPROVE, AI_SETTINGS_WRITE])
@pytest.mark.parametrize("actor_type", ["AI", "SYSTEM"])
def test_non_human_actors_are_denied_human_only_actions(actor_type: str, permission: str) -> None:
    assert not is_allowed("OWNER", actor_type, permission)


@pytest.mark.parametrize("actor_type", ["AI", "SYSTEM"])
def test_non_human_actors_may_open_a_case(actor_type: str) -> None:
    assert is_allowed(None, actor_type, CASE_OPEN)


def test_finance_cannot_write_ai_settings() -> None:
    assert not is_allowed("FINANCE_ADMIN", "USER", AI_SETTINGS_WRITE)
    assert is_allowed("OWNER", "USER", AI_SETTINGS_WRITE)


def test_authorize_raises_forbidden() -> None:
    with pytest.raises(ProblemError) as caught:
        authorize(_ctx("PROJECT_LEAD"), LEDGER_WRITE)
    assert (caught.value.code, caught.value.status) == ("FORBIDDEN", 403)


def test_authorize_returns_silently_when_allowed() -> None:
    authorize(_ctx("FINANCE_ADMIN"), LEDGER_WRITE)
