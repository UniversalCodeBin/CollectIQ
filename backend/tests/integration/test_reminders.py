"""Reminders and manual handoff (E083-E089): TS-001, 011, 014, 027 and the two critical negatives."""

import json
import uuid
from datetime import timedelta
from typing import Any

import psycopg
import pytest

from collectiq.comms.domain.linter import lint_reminder
from collectiq.platform import clock
from tests.integration.test_accounts import _invoices
from tests.integration.test_allocation_db import World, allocate, line, world
from tests.support import API, add_member, drain_jobs, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")


class Env:
    def __init__(
        self, owner_db: psycopg.Connection, email: str, supported: bool = True, contact: bool = True
    ):
        self.db = owner_db
        self.client, self.ws = owner_workspace(owner_db, email)
        owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [self.ws])
        self.invoices = _invoices(self.client, self.ws, ("INV-1", "2026-10-01"), ("INV-2", "2026-10-02"))
        prepare(owner_db, self.ws, list(self.invoices.values()), supported, contact)

    def url(self, tail: str) -> str:
        return f"{API}/workspaces/{self.ws}/{tail}"

    def evaluate(self, invoice: str = "INV-1") -> Any:
        return self.client.post(self.url(f"invoices/{self.invoices[invoice]}/reminders/evaluate"), **idem())

    def draft(self, invoice: str = "INV-1") -> dict[str, Any]:
        response = self.evaluate(invoice)
        assert response.status_code == 200, response.content
        reminder = response.json()["reminder"]
        assert reminder, response.json()
        return reminder

    def approve(self, reminder_id: str) -> Any:
        return self.client.post(self.url(f"reminders/{reminder_id}/approve"), **idem())

    def mark_sent(self, reminder_id: str, **extra: Any) -> Any:
        body = {"sent_at": (clock.now() - timedelta(minutes=1)).isoformat(), "method": "EMAIL", **extra}
        return self.client.post(self.url(f"reminders/{reminder_id}/mark-sent"), body, format="json", **idem())

    def get(self, reminder_id: str) -> dict[str, Any]:
        return self.client.get(self.url(f"reminders/{reminder_id}")).json()

    def reminder_status(self, invoice: str = "INV-1") -> str:
        return self.db.execute(
            "SELECT reminder_status FROM invoice_state WHERE invoice_id = %s", [self.invoices[invoice]]
        ).fetchone()[0]


def prepare(db: psycopg.Connection, ws: str, invoice_ids: list[str], supported: bool, contact: bool) -> None:
    if supported:
        db.execute("UPDATE invoice_state SET evidence_coverage = 'SUPPORTED'")
    if contact:
        for client_id in {
            r[0]
            for r in db.execute("SELECT client_id FROM invoices WHERE id = ANY(%s)", [invoice_ids]).fetchall()
        }:
            db.execute(
                "INSERT INTO client_contacts (workspace_id, client_id, email, name) VALUES (%s, %s, %s, %s)",
                [ws, client_id, "ap@northwind.example.test", "Accounts Payable"],
            )


@pytest.fixture
def env(owner_db: psycopg.Connection) -> Env:
    return Env(owner_db, f"rem-{uuid.uuid4().hex[:8]}@example.test")


# ---- drafting ---------------------------------------------------------------------------------------


def test_evaluate_creates_a_template_draft_with_a_fact_block(env: Env) -> None:
    body = env.evaluate().json()
    assert body["outcome"] == "REQUIRE_APPROVAL" and all(g["passed"] for g in body["gate_results"])
    reminder = body["reminder"]
    assert reminder["status"] == "DRAFT" and reminder["sequence"] == 1
    assert reminder["fact_block"]["invoice_number"] == "INV-1"
    assert reminder["fact_block"]["outstanding_minor"] == 10000
    assert reminder["intended_date"] == "2026-10-23"  # due 2026-10-20 plus the first step of the cadence
    assert "INR 100.00" in reminder["body"] and "INV-1" in reminder["body"]
    assert reminder["recipient"] == "ap@northwind.example.test"
    assert env.reminder_status() == "DRAFT_READY"


def test_retried_evaluation_creates_one_record(env: Env) -> None:  # TS-014
    first = env.draft()
    second = env.draft()
    assert first["id"] == second["id"]
    assert env.db.execute("SELECT count(*) FROM reminders").fetchone()[0] == 1


def test_coverage_gap_blocks_with_expected_outcome(owner_db: psycopg.Connection) -> None:
    env = Env(owner_db, f"rem-{uuid.uuid4().hex[:8]}@example.test", supported=False)
    body = env.evaluate().json()
    assert body["outcome"] == "PAUSE_FOR_REVIEW" and "G6_EVIDENCE_NOT_SUPPORTED" in body["reasons"]
    assert body["reminder"] is None
    assert env.db.execute("SELECT count(*) FROM reminders").fetchone()[0] == 0


def test_no_active_contact_means_no_draft(owner_db: psycopg.Connection) -> None:
    env = Env(owner_db, f"rem-{uuid.uuid4().hex[:8]}@example.test", contact=False)
    body = env.evaluate().json()
    assert body["outcome"] == "PAUSE_FOR_REVIEW" and body["reminder"] is None


def test_suppressed_contact_gets_no_draft(env: Env) -> None:
    env.db.execute("UPDATE client_contacts SET status = 'SUPPRESSED', suppression_reason = 'Asked to stop'")
    body = env.evaluate().json()
    assert body["reminder"] is None and body["outcome"] == "PAUSE_FOR_REVIEW"


def test_contact_limits_defer(env: Env) -> None:
    first = env.draft()
    assert env.approve(first["id"]).status_code == 200
    assert env.mark_sent(first["id"]).status_code == 201
    env.db.execute(
        "UPDATE workspace_policies SET settings = jsonb_set(settings, '{limits}', '{\"max_contacts\": 1}')"
    )
    body = env.evaluate().json()
    assert body["outcome"] == "DEFER" and "G10_CONTACT_LIMIT" in body["reasons"] and body["reminder"] is None


def test_paused_invoice_during_a_dispute_gets_no_draft(env: Env) -> None:
    opened = env.client.post(
        env.url("cases"),
        {"invoice_id": env.invoices["INV-1"], "type": "DISPUTE", "summary": "Amount is wrong"},
        format="json",
        **idem(),
    )
    assert opened.status_code == 201
    body = env.evaluate().json()
    assert body["outcome"] == "PAUSE_FOR_REVIEW" and "G4_DISPUTE" in body["reasons"]


# ---- editing and the linter -------------------------------------------------------------------------


def test_edit_keeps_the_facts_and_refuses_legal_threats(env: Env) -> None:  # TS-027
    draft = env.draft()
    url = env.url(f"reminders/{draft['id']}")
    good = draft["body"].replace("friendly reminder", "gentle nudge")
    edited = env.client.patch(url, {"body": good}, format="json", HTTP_IF_MATCH=f'"{draft["version"]}"')
    assert edited.status_code == 200 and "gentle nudge" in edited.json()["body"]
    threat = good + "\nWe will take legal action if you do not pay."
    refused = env.client.patch(url, {"body": threat}, format="json", HTTP_IF_MATCH='"2"')
    assert refused.status_code == 422
    dropped = env.client.patch(url, {"body": "Please pay up."}, format="json", HTTP_IF_MATCH='"2"')
    assert dropped.status_code == 422
    assert env.get(draft["id"])["body"] == good


def test_edit_needs_the_current_version(env: Env) -> None:
    draft = env.draft()
    stale = env.client.patch(
        env.url(f"reminders/{draft['id']}"), {"body": draft["body"]}, format="json", HTTP_IF_MATCH='"99"'
    )
    assert stale.status_code == 409


def test_linter_findings() -> None:
    facts = {
        "invoice_number": "INV-9",
        "amount_text": "INR 6,000.00",
        "amount_plain": "6000.00",
        "due_date": "2026-10-20",
    }
    ok = "Invoice INV-9 for INR 6,000.00 was due on 2026-10-20."
    assert lint_reminder(ok, facts) == []
    codes = {f.code for f in lint_reminder("Pay now. Final notice, we will sue you.", facts)}
    assert {"MISSING_INVOICE_NUMBER", "MISSING_AMOUNT", "MISSING_DUE_DATE", "NO_LEGAL_THREATS"} <= codes
    assert lint_reminder("", facts)[0].code == "EMPTY"


# ---- approval and hand-off --------------------------------------------------------------------------


def test_approved_and_copied_is_not_reported_sent(env: Env) -> None:
    draft = env.draft()
    approved = env.approve(draft["id"])
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
    state = env.get(draft["id"])
    assert state["status"] == "APPROVED" and state["sent_at"] is None
    assert env.reminder_status() == "DRAFT_READY"  # nothing says it was sent
    assert env.db.execute("SELECT count(*) FROM reminders WHERE status = 'MARKED_SENT'").fetchone()[0] == 0


def test_mark_sent_requires_approval_first(env: Env) -> None:
    draft = env.draft()
    assert env.mark_sent(draft["id"]).status_code == 409


def test_mark_sent_records_the_send_by_hand(env: Env) -> None:
    draft = env.draft()
    env.approve(draft["id"])
    response = env.mark_sent(draft["id"], method="WHATSAPP")
    assert response.status_code == 201
    done = response.json()
    assert done["status"] == "MARKED_SENT" and done["method"] == "WHATSAPP" and done["sent_at"]
    assert env.reminder_status() == "WAITING_FOR_CUSTOMER"
    assert env.mark_sent(draft["id"]).status_code == 409  # not twice


def test_mark_sent_needs_a_real_time_and_method(env: Env) -> None:
    draft = env.draft()
    env.approve(draft["id"])
    future = (clock.now() + timedelta(days=2)).isoformat()
    assert env.mark_sent(draft["id"], sent_at=future).status_code == 422
    assert env.mark_sent(draft["id"], method="CARRIER_PIGEON").status_code == 422
    missing = env.client.post(env.url(f"reminders/{draft['id']}/mark-sent"), {}, format="json", **idem())
    assert missing.status_code == 422


def test_reject_returns_the_invoice_to_not_contacted(env: Env) -> None:
    draft = env.draft()
    rejected = env.client.post(
        env.url(f"reminders/{draft['id']}/reject"), {"reason": "Not yet"}, format="json", **idem()
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
    assert env.reminder_status() == "NOT_CONTACTED"
    again = env.client.post(env.url(f"reminders/{draft['id']}/reject"), {}, format="json", **idem())
    assert again.status_code == 409


def test_second_reminder_follows_the_cadence(env: Env) -> None:
    first = env.draft()
    env.approve(first["id"])
    env.mark_sent(first["id"])
    second = env.draft()
    assert second["sequence"] == 2 and second["intended_date"] == "2026-10-30"  # due plus ten days


def test_dispute_opened_during_approval_blocks(env: Env) -> None:  # TOCTOU
    draft = env.draft()
    opened = env.client.post(
        env.url("cases"),
        {"invoice_id": env.invoices["INV-1"], "type": "DISPUTE", "summary": "Not our invoice"},
        format="json",
        **idem(),
    )
    assert opened.status_code == 201
    blocked = env.approve(draft["id"])  # the subscriber has not run yet; the gates catch it anyway
    assert blocked.status_code == 409
    assert env.get(draft["id"])["status"] == "DRAFT"
    drain_jobs()
    assert env.get(draft["id"])["status"] == "CANCELLED"


def test_dispute_after_approval_blocks_the_hand_off(env: Env) -> None:
    draft = env.draft()
    env.approve(draft["id"])
    env.client.post(
        env.url("cases"),
        {"invoice_id": env.invoices["INV-1"], "type": "DISPUTE", "summary": "Not our invoice"},
        format="json",
        **idem(),
    )
    assert env.mark_sent(draft["id"]).status_code == 409
    assert env.db.execute("SELECT count(*) FROM reminders WHERE status = 'MARKED_SENT'").fetchone()[0] == 0


def test_case_opening_ends_a_running_pause_and_cancels_drafts(env: Env) -> None:
    draft = env.draft()
    env.client.post(
        env.url("cases"),
        {"invoice_id": env.invoices["INV-1"], "type": "QUESTION", "summary": "Needs a PO number"},
        format="json",
        **idem(),
    )
    drain_jobs()
    assert env.get(draft["id"])["status"] == "CANCELLED"


def test_stale_facts_refuse_approval(env: Env) -> None:  # TS-011, TOCTOU form
    draft = env.draft()
    env.db.execute(
        "UPDATE invoice_state SET outstanding_minor = 6000 WHERE invoice_id = %s", [env.invoices["INV-1"]]
    )
    blocked = env.approve(draft["id"])
    assert blocked.status_code == 409 and "G12_DRAFT_FACTS" in blocked.json()["detail"]


def test_listing_and_detail_show_gate_results(env: Env) -> None:
    draft = env.draft()
    page = env.client.get(env.url("reminders?limit=10")).json()
    assert [item["id"] for item in page["items"]] == [draft["id"]] and page["next_cursor"] is None
    detail = env.get(draft["id"])
    assert detail["gates"]["outcome"] == "REQUIRE_APPROVAL" and len(detail["gates"]["gate_results"]) == 15


# ---- roles and isolation ----------------------------------------------------------------------------


def test_project_lead_cannot_write_or_see(env: Env, owner_db: psycopg.Connection) -> None:
    draft = env.draft()
    lead, _ = add_member(owner_db, env.ws, f"lead-{uuid.uuid4().hex[:6]}@example.test", "PROJECT_LEAD")
    assert (
        lead.post(env.url(f"invoices/{env.invoices['INV-1']}/reminders/evaluate"), **idem()).status_code
        == 403
    )
    assert lead.post(env.url(f"reminders/{draft['id']}/approve"), **idem()).status_code == 403
    assert (
        lead.post(env.url(f"reminders/{draft['id']}/mark-sent"), {}, format="json", **idem()).status_code
        == 403
    )


def test_another_workspace_cannot_reach_the_reminder(env: Env, owner_db: psycopg.Connection) -> None:
    draft = env.draft()
    other_client, other_ws = owner_workspace(owner_db, f"rem-x-{uuid.uuid4().hex[:6]}@example.test")
    url = f"{API}/workspaces/{other_ws}/reminders/{draft['id']}"
    assert other_client.get(url).status_code == 404
    assert other_client.post(f"{url}/approve", **idem()).status_code == 404


def test_there_is_no_scheduled_or_automatic_send_path() -> None:
    from collectiq.comms import service_reminders as service
    from collectiq.platform import jobs
    from collectiq.policy.domain import ActionType

    assert not {"AUTO_SEND", "MARK_PAID", "AUTO_ALLOCATE"} & {a.name for a in ActionType}
    public = {name for name in dir(service) if not name.startswith("_")}
    assert not {n for n in public if "auto" in n.lower() or "schedule" in n.lower() or n == "send"}
    kinds = set(getattr(jobs, "_handlers", {}))
    assert not {k for k in kinds if k.startswith("comms.send") or k.startswith("reminders.send")}
    source = json.dumps(sorted(public))
    assert "send_reminder" not in source


# ---- payments cancel pending drafts (TS-001, TS-011) -------------------------------------------------


def paid_world(owner_db: psycopg.Connection) -> tuple[World, str, str]:
    w = world(owner_db, f"rem-pay-{uuid.uuid4().hex[:6]}@example.test", payments=("40.00", "60.00"))
    prepare(owner_db, w.ws, list(w.invoices.values()), True, True)
    return w, w.invoices["INV-1"], w.txns[0]


def evaluate_for(w: World, invoice: str) -> dict[str, Any]:
    response = w.client.post(f"{API}/workspaces/{w.ws}/invoices/{invoice}/reminders/evaluate", **idem())
    assert response.status_code == 200, response.content
    return response.json()


def test_partial_payment_invalidates_a_stale_draft(owner_db: psycopg.Connection) -> None:  # TS-011
    w, invoice, first_txn = paid_world(owner_db)
    stale = evaluate_for(w, invoice)["reminder"]
    assert stale["fact_block"]["outstanding_minor"] == 10000
    assert allocate(w, first_txn, line(invoice, 4000)).status_code == 200
    drain_jobs()
    cancelled = w.client.get(f"{API}/workspaces/{w.ws}/reminders/{stale['id']}").json()
    assert cancelled["status"] == "CANCELLED"
    owner_db.execute(
        "UPDATE invoice_state SET evidence_coverage = 'SUPPORTED'"
    )  # coverage is recomputed by accounts
    result = evaluate_for(w, invoice)
    assert result["reminder"], result
    fresh = result["reminder"]
    assert fresh["id"] != stale["id"] and fresh["fact_block"]["outstanding_minor"] == 6000
    assert "INR 60.00" in fresh["body"]


def test_payment_cancels_pending_drafts(owner_db: psycopg.Connection) -> None:  # TS-001
    w, invoice, first_txn = paid_world(owner_db)
    draft = evaluate_for(w, invoice)["reminder"]
    assert allocate(w, first_txn, line(invoice, 4000)).status_code == 200
    assert allocate(w, w.txns[1], line(invoice, 6000)).status_code == 200
    drain_jobs()
    assert w.client.get(f"{API}/workspaces/{w.ws}/reminders/{draft['id']}").json()["status"] == "CANCELLED"
    after = evaluate_for(w, invoice)
    assert (
        after["outcome"] == "CANCEL" and "G2_ALREADY_PAID" in after["reasons"] and after["reminder"] is None
    )
