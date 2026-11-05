"""Truthful integration status (E093): no connected state without a real verification (TS-016 groundwork)."""

import uuid
from typing import Any

import psycopg
import pytest

from collectiq.integrations import service
from collectiq.platform.context import RequestContext
from tests.support import API, add_member, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")


class Env:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        self.client, self.ws = owner_workspace(db, f"int-{uuid.uuid4().hex[:8]}@example.test")
        db.execute("SELECT set_config('app.workspace_id', %s, false)", [self.ws])
        user = db.execute("SELECT user_id FROM workspace_memberships WHERE role = 'OWNER'").fetchone()[0]
        self.ctx = RequestContext(uuid.UUID(self.ws), user, "OWNER", str(uuid.uuid4()), "USER")

    def listing(self, client: Any = None) -> dict[str, dict[str, Any]]:
        response = (client or self.client).get(f"{API}/workspaces/{self.ws}/integrations")
        assert response.status_code == 200, response.content
        return {item["key"]: item for item in response.json()["items"]}


@pytest.fixture
def env(owner_db: psycopg.Connection) -> Env:
    return Env(owner_db)


def test_csv_and_manual_handoff_are_listed_truthfully(env: Env) -> None:
    items = env.listing()
    assert items["INVOICE_CSV"]["state"] == "FILE_BASED"
    assert items["STATEMENT_CSV"]["state"] == "FILE_BASED"
    assert items["MANUAL_PAYMENT"]["state"] == "MANUAL"
    assert items["MANUAL_REMINDER"]["state"] == "MANUAL"


def test_nothing_is_connected_by_default_and_no_accounting_connectors_exist(env: Env) -> None:
    items = env.listing()
    assert items["GMAIL"]["state"] == "NEEDS_CONFIGURATION"
    assert items["PAYPAL"]["state"] == "NEEDS_CONFIGURATION"
    assert not [k for k in items if k.upper() in ("ZOHO", "QUICKBOOKS", "XERO", "TALLY")]
    assert all(i["state"] != "CONNECTED_VERIFIED" for i in items.values())
    assert all(i["verified_at"] is None for i in items.values())


def test_no_connected_state_without_verification(env: Env) -> None:
    refused = service.connect(env.ctx, "GMAIL", lambda: False)
    assert refused["state"] == "NEEDS_CONFIGURATION"
    assert env.listing()["GMAIL"]["state"] != "CONNECTED_VERIFIED"

    def boom() -> bool:
        raise TimeoutError

    service.connect(env.ctx, "GMAIL", boom)
    assert env.listing()["GMAIL"]["state"] != "CONNECTED_VERIFIED"


def test_database_refuses_connected_without_a_verification_time(env: Env) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        env.db.execute(
            "INSERT INTO integration_connections (workspace_id, provider, state)"
            " VALUES (%s, 'GMAIL', 'CONNECTED_VERIFIED')",
            [env.ws],
        )


def test_verified_connect_and_disconnect_are_audited(env: Env) -> None:
    done = service.connect(env.ctx, "PAYPAL", lambda: True)
    assert done["state"] == "CONNECTED_VERIFIED"
    assert done["verified_at"] is not None
    assert env.listing()["PAYPAL"]["state"] == "CONNECTED_VERIFIED"
    service.disconnect(env.ctx, "PAYPAL")
    assert env.listing()["PAYPAL"]["state"] == "DISCONNECTED"
    actions = [
        r[0] for r in env.db.execute("SELECT action FROM audit_events ORDER BY occurred_at").fetchall()
    ]
    assert "integration.connected" in actions
    assert "integration.disconnected" in actions


def test_failed_verification_is_audited_too(env: Env) -> None:
    service.connect(env.ctx, "GMAIL", lambda: False)
    actions = [r[0] for r in env.db.execute("SELECT action FROM audit_events").fetchall()]
    assert "integration.verification_failed" in actions


def test_only_an_owner_manages_connections(env: Env, owner_db: psycopg.Connection) -> None:
    finance, _ = add_member(owner_db, env.ws, "fin-int@example.test", "FINANCE_ADMIN")
    assert env.listing(finance)["GMAIL"]["state"] == "NEEDS_CONFIGURATION"  # may read
    user = owner_db.execute(
        "SELECT user_id FROM workspace_memberships WHERE role = 'FINANCE_ADMIN'"
    ).fetchone()[0]
    ctx = RequestContext(uuid.UUID(env.ws), user, "FINANCE_ADMIN", str(uuid.uuid4()), "USER")
    from collectiq.platform.errors import ProblemError

    with pytest.raises(ProblemError) as caught:
        service.connect(ctx, "GMAIL", lambda: True)
    assert caught.value.status == 403
    with pytest.raises(ProblemError):
        service.disconnect(ctx, "GMAIL")


def test_unknown_provider_is_refused(env: Env) -> None:
    from collectiq.platform.errors import ProblemError

    with pytest.raises(ProblemError) as caught:
        service.connect(env.ctx, "QUICKBOOKS", lambda: True)
    assert caught.value.status == 422


def test_tenant_isolation(env: Env, owner_db: psycopg.Connection) -> None:
    service.connect(env.ctx, "PAYPAL", lambda: True)
    other = Env(owner_db)
    assert other.listing()["PAYPAL"]["state"] == "NEEDS_CONFIGURATION"
