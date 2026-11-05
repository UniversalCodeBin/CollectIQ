"""Customer replies, claims, promises and snoozes (E062-E066, E071-E075): TS-005, 009, 010, 033, 035."""

import json
import uuid
from datetime import timedelta
from typing import Any

import psycopg
import pytest

from collectiq.platform import clock
from tests.integration.test_accounts import _invoices
from tests.support import API, add_member, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")


class Env:
    def __init__(self, owner_db: psycopg.Connection, email: str) -> None:
        self.db = owner_db
        self.client, self.ws = owner_workspace(owner_db, email)
        owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [self.ws])
        self.invoices = _invoices(self.client, self.ws, ("INV-1", "2026-10-01"), ("INV-2", "2026-10-02"))

    def url(self, tail: str) -> str:
        return f"{API}/workspaces/{self.ws}/{tail}"

    def paste(
        self,
        text: str = "We paid last week.",
        on: str | None = None,
        labels: tuple[str, ...] = (),
        **extra: Any,
    ) -> Any:
        body: dict[str, Any] = {"source": "PASTE", "text": text, **extra}
        if on:
            body["invoice_ids"] = [json.dumps({"invoice_id": self.invoices[on], "labels": list(labels)})]
        return self.client.post(self.url("messages"), body, format="multipart", **idem())

    def message(self, **kw: Any) -> dict[str, Any]:
        response = self.paste(**kw)
        assert response.status_code == 201, response.content
        return response.json()

    def label(self, message_id: str, invoice: str, *labels: str) -> Any:
        return self.client.post(
            self.url(f"messages/{message_id}/associations"),
            {"invoice_ids": [{"invoice_id": self.invoices[invoice], "labels": list(labels)}]},
            format="json",
            **idem(),
        )

    def state(self, invoice: str = "INV-1") -> dict[str, Any]:
        cur = self.db.execute(
            "SELECT payment_status, reminder_status, dispute_status, outstanding_minor, open_task_count"
            " FROM invoice_state WHERE invoice_id = %s",
            [self.invoices[invoice]],
        )
        return dict(zip([c.name for c in cur.description], cur.fetchone(), strict=True))

    def promise(self, invoice: str, strength: str, days: int | None, **extra: Any) -> Any:
        body: dict[str, Any] = {"invoice_id": self.invoices[invoice], "strength": strength, **extra}
        if days is not None:
            body["date"] = str(clock.now().date() + timedelta(days=days))
        return self.client.post(self.url("commitments"), body, format="json", **idem())

    def approve(self, approval_id: str) -> Any:
        return self.client.post(
            self.url(f"approvals/{approval_id}/decide"), {"decision": "APPROVED"}, format="json", **idem()
        )

    def start_snooze(self, invoice: str = "INV-1", days: int = 10) -> dict[str, Any]:
        made = self.promise(invoice, "EXPLICIT", days)
        assert made.status_code == 201, made.content
        proposal = made.json()["snooze"]
        assert proposal and proposal["approval_id"]
        assert self.approve(proposal["approval_id"]).status_code == 200
        return proposal

    def approve_snooze(self, proposal: dict[str, Any], invoice: str = "INV-1") -> Any:
        return self.client.post(
            self.url(f"invoices/{self.invoices[invoice]}/snooze/approve"),
            {"approval_id": proposal["approval_id"]},
            format="json",
            **idem(),
        )


@pytest.fixture
def env(owner_db: psycopg.Connection) -> Env:
    return Env(owner_db, f"conv-{uuid.uuid4().hex[:8]}@example.test")


# --- capture and storage ---


def test_pasted_text_is_captured_and_shown_in_the_timeline(env: Env) -> None:
    message = env.message(on="INV-1", subject="Re: INV-1", sender="ap@client.example.test")
    assert message["source"] == "PASTE" and message["body"] == "We paid last week."
    assert message["associations"][0]["invoice_id"] == env.invoices["INV-1"]
    timeline = env.client.get(env.url(f"invoices/{env.invoices['INV-1']}/messages")).json()
    assert any("We paid last week." in json.dumps(item) for item in timeline["items"])
    assert env.client.get(env.url(f"messages/{message['id']}")).json()["id"] == message["id"]


def test_message_body_is_encrypted_at_rest(env: Env) -> None:
    phrase = "Our remittance note mentions ZX-91827364"
    env.message(text=phrase)
    raw = bytes(env.db.execute("SELECT body_enc FROM messages").fetchone()[0])
    assert phrase.encode() not in raw


def test_eml_html_is_sanitised_and_stored_as_text(env: Env) -> None:
    eml = (
        b"From: AP <ap@client.example.test>\r\nSubject: Re: invoice\r\n"
        b"Date: Mon, 02 Nov 2026 10:00:00 +0000\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n\r\n"
        b"<html><body><script>alert(1)</script><p>We will pay <b>soon</b></p></body></html>"
    )
    from django.core.files.uploadedfile import SimpleUploadedFile

    response = env.client.post(
        env.url("messages"),
        {"source": "EML", "file": SimpleUploadedFile("reply.eml", eml)},
        format="multipart",
        **idem(),
    )
    assert response.status_code == 201, response.content
    body = response.json()["body"]
    assert "<script" not in body and "alert" not in body and "We will pay soon" in body
    assert response.json()["sender"] == "ap@client.example.test"


def test_paste_needs_text(env: Env) -> None:
    response = env.client.post(
        env.url("messages"), {"source": "PASTE", "text": ""}, format="multipart", **idem()
    )
    assert response.status_code == 422


# --- claims never move money (critical negative 1; TS-005, TS-033) ---


def test_claim_never_changes_balance_or_marks_paid(env: Env) -> None:
    before = env.state()
    message = env.message(on="INV-1")
    assert env.label(message["id"], "INV-1", "PAYMENT_CLAIM").status_code == 200
    after = env.state()
    assert after["payment_status"] == "AWAITING_VERIFICATION"
    assert after["outstanding_minor"] == before["outstanding_minor"]
    assert after["reminder_status"] == "SUPPRESSED" and after["open_task_count"] == 1
    assert env.db.execute("SELECT count(*) FROM commitments").fetchone()[0] == 0
    assert env.db.execute("SELECT count(*) FROM snoozes").fetchone()[0] == 0
    assert env.db.execute("SELECT count(*) FROM verification_tasks WHERE status = 'OPEN'").fetchone()[0] == 1


def test_claim_on_a_verified_paid_invoice_is_a_note_only(env: Env) -> None:
    env.db.execute(
        "UPDATE invoice_state SET payment_status = 'PAID_VERIFIED' WHERE invoice_id = %s",
        [env.invoices["INV-1"]],
    )
    message = env.message(on="INV-1")
    assert env.label(message["id"], "INV-1", "PAYMENT_CLAIM").status_code == 200
    state = env.state()
    assert state["payment_status"] == "PAID_VERIFIED" and state["open_task_count"] == 0


def test_unassociated_message_changes_nothing(env: Env) -> None:
    before = env.state()
    env.message()
    assert env.state() == before


def test_opt_out_suppresses_the_matching_contact(env: Env) -> None:
    client_id = env.db.execute(
        "SELECT client_id FROM invoices WHERE id = %s", [env.invoices["INV-1"]]
    ).fetchone()[0]
    env.db.execute(
        "INSERT INTO client_contacts (workspace_id, client_id, email) VALUES (%s, %s, %s)",
        [env.ws, client_id, "stop@client.example.test"],
    )
    message = env.message(on="INV-1", sender="stop@client.example.test")
    assert env.label(message["id"], "INV-1", "WRONG_RECIPIENT_OR_OPT_OUT").status_code == 200
    status = env.db.execute(
        "SELECT status FROM client_contacts WHERE email = 'stop@client.example.test'"
    ).fetchone()[0]
    assert status == "SUPPRESSED" and env.state()["reminder_status"] == "SUPPRESSED"


def test_dispute_label_opens_a_case_linked_to_the_message(env: Env) -> None:
    message = env.message(on="INV-1")
    assert env.label(message["id"], "INV-1", "DISPUTE").status_code == 200
    row = env.db.execute("SELECT source_message_id FROM cases").fetchone()
    assert str(row[0]) == message["id"] and env.state()["dispute_status"] == "OPEN"


# --- promises and snoozes (TS-009, TS-010) ---


def test_explicit_promise_proposes_a_snooze_that_needs_approval(env: Env) -> None:
    made = env.promise("INV-1", "EXPLICIT", 10)
    assert made.status_code == 201 and made["ETag"]
    proposal = made.json()["snooze"]
    assert proposal["outcome"] == "REQUIRE_APPROVAL" and proposal["approval_id"]
    assert env.state()["reminder_status"] != "SNOOZED"
    assert env.approve(proposal["approval_id"]).status_code == 200
    assert env.state()["reminder_status"] != "SNOOZED"
    started = env.approve_snooze(proposal)
    assert started.status_code == 200 and started.json()["reminder_status"] == "SNOOZED"
    assert env.state()["reminder_status"] == "SNOOZED"
    assert env.approve_snooze(proposal).status_code in (404, 409, 422)


def test_snooze_cannot_start_without_the_approval_being_decided(env: Env) -> None:
    proposal = env.promise("INV-1", "EXPLICIT", 10).json()["snooze"]
    assert env.approve_snooze(proposal).status_code >= 400
    assert env.state()["reminder_status"] != "SNOOZED"


def test_undo_restores_the_prior_reminder_status(env: Env) -> None:
    prior = env.state()["reminder_status"]
    env.approve_snooze(env.start_snooze())
    undone = env.client.post(
        env.url(f"invoices/{env.invoices['INV-1']}/snooze/undo"), {}, format="json", **idem()
    )
    assert undone.status_code == 200 and env.state()["reminder_status"] == prior


@pytest.mark.parametrize(
    ("setup", "strength", "days"),
    [
        ("dispute", "EXPLICIT", 10),
        ("claim", "EXPLICIT", 10),
        (None, "TENTATIVE", 10),
        (None, "EXPLICIT", 90),
        (None, "EXPLICIT", -3),
    ],
)
def test_snooze_negatives_never_start_pausing(env: Env, setup: str | None, strength: str, days: int) -> None:
    message = env.message(on="INV-1")
    if setup == "dispute":
        env.label(message["id"], "INV-1", "DISPUTE")
    if setup == "claim":
        env.label(message["id"], "INV-1", "PAYMENT_CLAIM")
    made = env.promise("INV-1", strength, days)
    assert made.status_code == 201, made.content
    body = made.json()
    proposal = body["snooze"]
    if proposal is not None:
        assert proposal["outcome"] != "ALLOW_AUTOMATIC"
        assert proposal["approval_id"] is None or setup is None
    assert env.state()["reminder_status"] != "SNOOZED"
    if proposal is None:
        assert body["snooze_note"]


def test_withdrawing_a_promise_ends_the_snooze(env: Env) -> None:
    proposal = env.start_snooze()
    env.approve_snooze(proposal)
    listing = env.client.get(env.url(f"invoices/{env.invoices['INV-1']}/commitments")).json()
    commitment = listing["items"][0]
    stale = env.client.patch(
        env.url(f"commitments/{commitment['id']}"),
        {"status": "WITHDRAWN"},
        format="json",
        HTTP_IF_MATCH='"99"',
    )
    assert stale.status_code == 409
    ok = env.client.patch(
        env.url(f"commitments/{commitment['id']}"),
        {"status": "WITHDRAWN"},
        format="json",
        HTTP_IF_MATCH=f'"{commitment["version"]}"',
    )
    assert ok.status_code == 200 and ok.json()["status"] == "WITHDRAWN"
    assert env.state()["reminder_status"] != "SNOOZED"


# --- access ---


def test_project_lead_cannot_add_a_message_or_promise(env: Env, owner_db: psycopg.Connection) -> None:
    lead, _ = add_member(owner_db, env.ws, f"v-{uuid.uuid4().hex[:6]}@example.test", "PROJECT_LEAD")
    response = lead.post(env.url("messages"), {"source": "PASTE", "text": "hi"}, format="multipart", **idem())
    assert response.status_code == 403
    made = lead.post(
        env.url("commitments"),
        {"invoice_id": env.invoices["INV-1"], "strength": "TENTATIVE"},
        format="json",
        **idem(),
    )
    assert made.status_code == 403


def test_other_workspace_cannot_read_a_message(env: Env, owner_db: psycopg.Connection) -> None:
    message = env.message()
    other = Env(owner_db, f"conv-{uuid.uuid4().hex[:8]}@example.test")
    assert other.client.get(other.url(f"messages/{message['id']}")).status_code == 404
