"""State maintenance (SAD 6.7, F-7): recompute, follow-on events, the integrity net."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from collectiq.evidence import service_state as state
from collectiq.evidence.domain.derive import Facts
from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx
from tests.integration.test_accounts import _invoices
from tests.support import API, drain_jobs, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")
NOW = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


def _ctx(owner_db: Any, ws: str) -> RequestContext:
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    user = owner_db.execute("SELECT user_id FROM workspace_memberships WHERE role = 'OWNER'").fetchone()[0]
    return RequestContext(uuid.UUID(ws), user, "OWNER", str(uuid.uuid4()), "USER")


def _row(owner_db: Any, invoice_id: str) -> dict[str, Any]:
    cur = owner_db.execute(
        "SELECT payment_status, paid_minor, outstanding_minor, overpayment_flag, version"
        " FROM invoice_state WHERE invoice_id = %s",
        [invoice_id],
    )
    return dict(zip([c.name for c in cur.description], cur.fetchone(), strict=True))


@pytest.fixture
def setup(owner_db: Any) -> tuple[RequestContext, str, Any]:
    client, ws = owner_workspace(owner_db, "state@example.test")
    ids = _invoices(client, ws, ("INV-1", "2026-10-01"))
    return _ctx(owner_db, ws), ids["INV-1"], client


def test_recompute_applies_facts_and_bumps_version(setup: Any, owner_db: Any) -> None:
    ctx, invoice, _ = setup
    before = _row(owner_db, invoice)
    assert before["payment_status"] == "OUTSTANDING"
    gross = before["outstanding_minor"]
    with tenant_tx(ctx):
        assert state.recompute(ctx, invoice, Facts(gross, (gross // 2,))) is True
    mid = _row(owner_db, invoice)
    assert (mid["payment_status"], mid["paid_minor"]) == ("PARTIALLY_PAID", gross // 2)
    assert mid["version"] == before["version"] + 1
    with tenant_tx(ctx):
        assert state.recompute(ctx, invoice, Facts(gross, (gross // 2,))) is False
    assert _row(owner_db, invoice)["version"] == mid["version"]
    with tenant_tx(ctx):
        state.recompute(ctx, invoice, Facts(gross, (gross // 2, gross - gross // 2)))
    assert _row(owner_db, invoice)["payment_status"] == "PAID_VERIFIED"


def test_open_task_count_holds_reminders_back(setup: Any, owner_db: Any) -> None:
    ctx, invoice, _ = setup
    owner_db.execute("UPDATE invoice_state SET open_task_count = 1 WHERE invoice_id = %s", [invoice])
    with tenant_tx(ctx):
        state.recompute(ctx, invoice)
    assert _row(owner_db, invoice)["payment_status"] == "AWAITING_VERIFICATION"
    owner_db.execute("UPDATE invoice_state SET open_task_count = 0 WHERE invoice_id = %s", [invoice])
    with tenant_tx(ctx):
        state.recompute(ctx, invoice)
    assert _row(owner_db, invoice)["payment_status"] == "OUTSTANDING"


def test_total_change_follows_through_outbox(setup: Any, owner_db: Any) -> None:
    ctx, invoice, client = setup
    detail = client.get(f"{API}/workspaces/{ctx.workspace_id}/invoices/{invoice}").json()
    from tests.support import idem

    response = client.patch(
        f"{API}/workspaces/{ctx.workspace_id}/invoices/{invoice}",
        {"gross_minor": 25_000, "reason": "typo"},
        format="json",
        HTTP_IF_MATCH=f'"{detail["version"]}"',
        **idem(),
    )
    assert response.status_code == 200, response.content
    drain_jobs()
    row = _row(owner_db, invoice)
    assert row["outstanding_minor"] == 25_000 and row["payment_status"] == "OUTSTANDING"


def test_integrity_check_detects_and_repairs_seeded_drift(
    setup: Any, owner_db: Any, caplog: pytest.LogCaptureFixture
) -> None:
    ctx, invoice, _ = setup
    owner_db.execute(
        "UPDATE invoice_state SET payment_status = 'PAID_VERIFIED', paid_minor = 1, outstanding_minor = 0"
        " WHERE invoice_id = %s",
        [invoice],
    )
    with caplog.at_level(logging.ERROR), tenant_tx(ctx):
        assert state.check_integrity(ctx, repair=False) == [invoice]
    assert any("drift" in r.message for r in caplog.records)
    assert _row(owner_db, invoice)["payment_status"] == "PAID_VERIFIED"
    with tenant_tx(ctx):
        assert state.check_integrity(ctx) == [invoice]
    assert _row(owner_db, invoice)["payment_status"] == "OUTSTANDING"
    audited = owner_db.execute(
        "SELECT count(*) FROM audit_events WHERE action = 'invoice_state.drift_repaired'"
    ).fetchone()[0]
    assert audited == 1
    with tenant_tx(ctx):
        assert state.check_integrity(ctx) == []
