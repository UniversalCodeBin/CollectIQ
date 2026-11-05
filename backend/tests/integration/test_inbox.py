"""Notifications (E106, E107) and the review inbox (E108): derived, scoped by role, one source of truth."""

import inspect
import uuid
from typing import Any

import psycopg
import pytest

from collectiq.notifications import review_inbox
from tests.integration.test_allocation_db import world
from tests.integration.test_reminders import Env as ReminderEnv
from tests.support import API, add_member, drain_jobs, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")


@pytest.fixture
def env(owner_db: psycopg.Connection) -> ReminderEnv:
    return ReminderEnv(owner_db, f"inbox-{uuid.uuid4().hex[:8]}@example.test")


def open_case(env: ReminderEnv, type_: str = "DISPUTE", invoice: str = "INV-1") -> dict[str, Any]:
    response = env.client.post(
        env.url("cases"),
        {"invoice_id": env.invoices[invoice], "type": type_, "summary": "Amount is wrong"},
        format="json",
        **idem(),
    )
    assert response.status_code == 201, response.content
    return response.json()


def inbox(client: Any, env: ReminderEnv) -> dict[str, Any]:
    response = client.get(env.url("review-inbox"))
    assert response.status_code == 200, response.content
    return response.json()


def kinds(body: dict[str, Any]) -> list[str]:
    return [item["kind"] for item in body["items"]]


# ---- notifications ----------------------------------------------------------------------------------


def test_opening_a_case_notifies_owner_and_finance_but_not_a_lead(
    env: ReminderEnv, owner_db: psycopg.Connection
) -> None:
    finance, _ = add_member(owner_db, env.ws, f"fin-{uuid.uuid4().hex[:6]}@example.test", "FINANCE_ADMIN")
    lead, _ = add_member(owner_db, env.ws, f"lead-{uuid.uuid4().hex[:6]}@example.test", "PROJECT_LEAD")
    case = open_case(env)
    drain_jobs()
    for who in (env.client, finance):
        items = who.get(env.url("notifications")).json()["items"]
        assert [i["type"] for i in items] == ["CASE_OPENED"] and items[0]["read_at"] is None
        assert items[0]["subject_ref"] == {"case_id": case["id"], "invoice_id": env.invoices["INV-1"]}
        assert items[0]["target_route"] == f"invoices/{env.invoices['INV-1']}/overview"
        assert items[0]["action"]
    assert lead.get(env.url("notifications")).json()["items"] == []


def test_notification_carries_ids_and_codes_not_customer_text(env: ReminderEnv) -> None:
    open_case(env)
    drain_jobs()
    raw = env.client.get(env.url("notifications")).content.decode()
    assert "Amount is wrong" not in raw


def test_marking_read_is_personal_and_repeatable(env: ReminderEnv, owner_db: psycopg.Connection) -> None:
    finance, _ = add_member(owner_db, env.ws, f"fin-{uuid.uuid4().hex[:6]}@example.test", "FINANCE_ADMIN")
    open_case(env)
    drain_jobs()
    mine = env.client.get(env.url("notifications")).json()["items"][0]
    theirs = finance.get(env.url("notifications")).json()["items"][0]
    assert finance.post(env.url(f"notifications/{mine['id']}/read"), **idem()).status_code == 404
    assert env.client.post(env.url(f"notifications/{mine['id']}/read"), **idem()).status_code == 204
    assert env.client.post(env.url(f"notifications/{mine['id']}/read"), **idem()).status_code == 204
    assert env.client.get(env.url("notifications")).json()["items"][0]["read_at"]
    assert finance.get(env.url("notifications")).json()["items"][0]["id"] == theirs["id"]
    assert finance.get(env.url("notifications")).json()["items"][0]["read_at"] is None


def test_reading_an_unknown_notification_is_not_found(env: ReminderEnv) -> None:
    assert env.client.post(env.url(f"notifications/{uuid.uuid4()}/read"), **idem()).status_code == 404


def test_a_new_draft_notifies_the_people_who_can_approve_it(env: ReminderEnv) -> None:
    env.draft()
    drain_jobs()
    items = env.client.get(env.url("notifications")).json()["items"]
    assert [i["type"] for i in items] == ["REMINDER_DRAFT_READY"]
    assert items[0]["target_route"].startswith("reminders/")


def test_notifications_are_private_to_the_workspace(env: ReminderEnv, owner_db: psycopg.Connection) -> None:
    open_case(env)
    drain_jobs()
    other, other_ws = owner_workspace(owner_db, f"inbox-x-{uuid.uuid4().hex[:6]}@example.test")
    assert other.get(f"{API}/workspaces/{other_ws}/notifications").json()["items"] == []
    assert other.get(env.url("notifications")).status_code in (403, 404)


def test_notifications_page(env: ReminderEnv) -> None:
    open_case(env)
    open_case(env, "QUESTION", "INV-2")
    drain_jobs()
    first = env.client.get(env.url("notifications?limit=1")).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = env.client.get(env.url(f"notifications?limit=1&cursor={first['next_cursor']}")).json()
    assert len(second["items"]) == 1 and second["items"][0]["id"] != first["items"][0]["id"]


# ---- review inbox -----------------------------------------------------------------------------------


def test_every_item_carries_a_route_and_the_action_that_resolves_it(env: ReminderEnv) -> None:
    env.draft("INV-2")
    open_case(env)
    items = inbox(env.client, env)["items"]
    assert set(kinds({"items": items})) == {"REMINDER_DRAFT", "CASE"}
    for item in items:
        assert item["target_route"] and item["action"] and item["subject_ref"] and item["created_at"]
        assert item["kind"] in review_inbox.KINDS


def test_match_proposals_and_payment_claims_appear(owner_db: psycopg.Connection) -> None:
    w = world(owner_db, f"inbox-m-{uuid.uuid4().hex[:6]}@example.test")
    body = w.client.get(f"{API}/workspaces/{w.ws}/review-inbox").json()
    assert kinds(body) == ["MATCH_PROPOSAL"]
    assert body["items"][0]["target_route"].startswith("reconciliation/")


def test_resolving_at_source_clears_inbox_item(env: ReminderEnv) -> None:
    draft = env.draft("INV-2")
    case = open_case(env)
    assert set(kinds(inbox(env.client, env))) == {"REMINDER_DRAFT", "CASE"}
    resolved = env.client.post(
        env.url(f"cases/{case['id']}/resolve"), {"outcome": "NO_CHANGE"}, format="json", **idem()
    )
    assert resolved.status_code == 200
    assert kinds(inbox(env.client, env)) == ["REMINDER_DRAFT"]
    rejected = env.client.post(env.url(f"reminders/{draft['id']}/reject"), {}, format="json", **idem())
    assert rejected.status_code == 200
    assert inbox(env.client, env)["items"] == []


def test_approved_but_unsent_draft_stays_until_marked_sent(env: ReminderEnv) -> None:
    draft = env.draft()
    env.approve(draft["id"])
    item = inbox(env.client, env)["items"][0]
    assert item["kind"] == "REMINDER_DRAFT" and item["action"] == "Mark as sent"
    env.mark_sent(draft["id"])
    assert inbox(env.client, env)["items"] == []


def test_project_lead_sees_only_assigned_cases(env: ReminderEnv, owner_db: psycopg.Connection) -> None:
    lead, lead_member = add_member(
        owner_db, env.ws, f"lead-{uuid.uuid4().hex[:6]}@example.test", "PROJECT_LEAD"
    )
    env.draft()
    mine = open_case(env, "QUESTION", "INV-1")
    open_case(env, "QUESTION", "INV-2")
    assert inbox(lead, env)["items"] == []
    owner_db.execute(
        "UPDATE cases SET assignee_id = (SELECT user_id FROM workspace_memberships WHERE id = %s)"
        " WHERE id = %s",
        [lead_member, mine["id"]],
    )
    items = inbox(lead, env)["items"]
    assert kinds({"items": items}) == ["CASE"] and items[0]["subject_ref"]["case_id"] == mine["id"]


def test_inbox_is_scoped_to_the_workspace(env: ReminderEnv, owner_db: psycopg.Connection) -> None:
    open_case(env)
    other, other_ws = owner_workspace(owner_db, f"inbox-x-{uuid.uuid4().hex[:6]}@example.test")
    assert other.get(f"{API}/workspaces/{other_ws}/review-inbox").json()["items"] == []


def test_inbox_needs_login(env: ReminderEnv) -> None:
    from rest_framework.test import APIClient

    assert APIClient().get(env.url("review-inbox")).status_code == 401


def test_inbox_adds_no_source_of_truth(env: ReminderEnv) -> None:
    open_case(env)
    before = env.db.execute("SELECT count(*) FROM notifications").fetchone()[0]
    inbox(env.client, env)
    inbox(env.client, env)
    assert env.db.execute("SELECT count(*) FROM notifications").fetchone()[0] == before
    source = inspect.getsource(review_inbox).upper()
    assert "INSERT " not in source and "UPDATE " not in source and "DELETE " not in source
