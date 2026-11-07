"""Nightly scheduling (Task 40): one set of maintenance jobs per workspace per day, IDs only."""

import pytest
from django.core.management import call_command

from tests.support import owner_workspace

pytestmark = pytest.mark.usefixtures("pg")

KINDS = {"audit.verify_chain", "evidence.integrity_check", "privacy.retention", "conversations.snooze_expiry"}


def _jobs(owner_db, ws: str) -> list[tuple]:
    return owner_db.execute(
        "SELECT kind, dedupe_key, payload::text FROM background_jobs WHERE workspace_id = %s ORDER BY kind",
        [ws],
    ).fetchall()


def test_schedules_the_nightly_jobs_for_every_workspace(owner_db) -> None:
    _, a = owner_workspace(owner_db, "sched-a@example.test")
    _, b = owner_workspace(owner_db, "sched-b@example.test")
    call_command("schedule_nightly")
    for ws in (a, b):
        rows = _jobs(owner_db, ws)
        assert {r[0] for r in rows} == KINDS
        assert all(r[2] == "{}" for r in rows)


def test_running_twice_on_one_day_adds_nothing(owner_db) -> None:
    _, ws = owner_workspace(owner_db, "sched-c@example.test")
    call_command("schedule_nightly")
    call_command("schedule_nightly")
    assert len(_jobs(owner_db, ws)) == 4


def test_the_jobs_run_and_finish(owner_db) -> None:
    _, ws = owner_workspace(owner_db, "sched-d@example.test")
    call_command("schedule_nightly")
    call_command("run_worker", "--drain")
    statuses = owner_db.execute("SELECT status FROM background_jobs WHERE workspace_id = %s", [ws]).fetchall()
    assert statuses and {s[0] for s in statuses} == {"DONE"}


def test_listing_function_returns_ids_only_and_is_not_public(owner_db) -> None:
    secdef, config, acl = owner_db.execute(
        "SELECT prosecdef, proconfig, proacl::text FROM pg_proc WHERE proname = 'workspace_ids_for_schedule'"
    ).fetchone()
    assert secdef is True
    assert config == ["search_path=pg_catalog, pg_temp"]
    assert "collectiq_app=X/" in acl
    assert not acl.startswith("{=X/") and ",=X/" not in acl
