"""AI settings and flagged PDF extraction (E038-E041, E109-E110): TS-003, AIR-01..AIR-04."""

import json
import re
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from collectiq.ai.gateway import AIConfig, Gateway
from collectiq.ai.providers.fake import FakeProvider
from collectiq.ai.runtime import use_gateway
from tests.support import API, add_member, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")

TEXT = "Invoice INV-900 for Northwind Traders issued 2026-10-01 due 2026-10-31 total INR 1500.50"


def make_pdf(text: str = TEXT) -> bytes:
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 900 200] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    return out


GOOD = {
    "invoice_number": "INV-900",
    "client_name": "Northwind Traders",
    "issue_date": "2026-10-01",
    "due_date": "2026-10-31",
    "currency": "INR",
    "total": "1500.50",
}


@pytest.fixture
def script() -> Iterator[Any]:
    def install(*responses: str | Exception) -> FakeProvider:
        provider = FakeProvider(list(responses))
        use_gateway(Gateway(provider, AIConfig()))
        return provider

    yield install
    use_gateway(None)


class Env:
    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        self.client, self.ws = owner_workspace(db, f"ext-{uuid.uuid4().hex[:8]}@example.test")

    def url(self, tail: str) -> str:
        return f"{API}/workspaces/{self.ws}/{tail}"

    def settings(self, **flags: bool) -> Any:
        return self.client.put(self.url("ai/settings"), flags, format="json", **idem())

    def upload(self, data: bytes | None = None, client: APIClient | None = None) -> Any:
        file = SimpleUploadedFile("inv.pdf", data if data is not None else make_pdf(), "application/pdf")
        return (client or self.client).post(
            self.url("invoices/pdf"), {"file": file}, format="multipart", **idem()
        )

    def confirm(self, extraction_id: str, body: dict[str, Any] | None = None) -> Any:
        return self.client.post(
            self.url(f"extractions/{extraction_id}/confirm"),
            body if body is not None else {"decisions": {"create_client": True}},
            format="json",
            **idem(),
        )

    def count(self, table: str) -> int:
        self.db.execute("SELECT set_config('app.workspace_id', %s, false)", [self.ws])
        return int(self.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # noqa: S608


@pytest.fixture
def env(owner_db: psycopg.Connection) -> Env:
    return Env(owner_db)


@pytest.fixture
def on(env: Env, script: Any) -> Env:
    assert env.settings(pdf_extraction_enabled=True).status_code == 200
    return env


# --- settings ---


def test_ai_is_off_by_default(env: Env) -> None:
    body = env.client.get(env.url("ai/settings")).json()
    assert body["pdf_extraction_enabled"] is False
    assert body["reply_interpretation_enabled"] is False
    assert body["kill_switch"] is False
    assert body["provider_configured"] is False


def test_only_an_owner_changes_settings_and_it_is_audited(env: Env, owner_db: psycopg.Connection) -> None:
    finance, _ = add_member(owner_db, env.ws, "fin-ai@example.test", "FINANCE_ADMIN")
    denied = finance.put(env.url("ai/settings"), {"kill_switch": True}, format="json", **idem())
    assert denied.status_code == 403
    assert env.settings(pdf_extraction_enabled=True).json()["pdf_extraction_enabled"] is True
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [env.ws])
    actions = [r[0] for r in owner_db.execute("SELECT action FROM audit_events").fetchall()]
    assert "ai_settings.updated" in actions


def test_settings_reject_empty_and_unknown_changes(env: Env) -> None:
    assert env.settings().status_code == 422
    assert env.settings(unknown=True).status_code == 422


# --- gating ---


def test_flag_off_refuses_and_calls_no_model(env: Env, script: Any) -> None:
    provider = script(json.dumps(GOOD))
    response = env.upload()
    assert response.status_code == 409
    assert response.json()["code"] == "AI_DISABLED"
    assert provider.requests == []
    assert env.count("invoice_extractions") == 0


def test_kill_switch_beats_the_opt_in(on: Env, script: Any) -> None:
    provider = script(json.dumps(GOOD))
    assert on.settings(kill_switch=True).status_code == 200
    assert on.upload().json()["code"] == "AI_DISABLED"
    assert provider.requests == []


def test_no_provider_is_a_clear_state(on: Env) -> None:
    use_gateway(None)
    response = on.upload()
    assert response.status_code == 409
    assert response.json()["code"] == "AI_NOT_CONFIGURED"


# --- TS-003 ---


def test_extraction_is_a_reviewable_draft_not_an_invoice(on: Env, script: Any) -> None:
    script(json.dumps(GOOD))
    response = on.upload()
    assert response.status_code == 202, response.content
    body = response.json()
    assert body["status"] == "READY"
    assert body["fields"]["invoice_number"] == "INV-900"
    assert body["ai_derived"] is True
    assert body["verified"] is False
    assert not re.search(r"\d\s*%|confidence|score", json.dumps(body), re.I)
    assert on.count("invoices") == 0
    assert on.count("ai_processing_records") == 1


def test_confirm_creates_the_invoice_in_minor_units(on: Env, script: Any) -> None:
    script(json.dumps(GOOD))
    ext = on.upload().json()
    confirmed = on.confirm(ext["id"])
    assert confirmed.status_code == 201, confirmed.content
    assert confirmed.json()["status"] == "CONFIRMED"
    invoice = on.client.get(on.url(f"invoices/{confirmed.json()['invoice_id']}")).json()
    assert invoice["facts"]["invoice_number"] == "INV-900"
    assert invoice["facts"]["gross_minor"] == 150050
    assert invoice["derived"]["outstanding_minor"] == 150050


def test_duplicate_invoice_is_refused(on: Env, script: Any) -> None:
    script(json.dumps(GOOD), json.dumps(GOOD))
    first = on.confirm(on.upload().json()["id"])
    assert first.status_code == 201
    client_id = on.client.get(on.url(f"invoices/{first.json()['invoice_id']}")).json()["facts"]["client_id"]
    second = on.upload().json()
    again = on.confirm(second["id"], {"decisions": {"client_id": client_id}})
    assert again.status_code == 409
    assert again.json()["code"] == "DUPLICATE_INVOICE"


def test_values_the_document_does_not_support_are_dropped(on: Env, script: Any) -> None:
    script(json.dumps({**GOOD, "total": "999999.00", "client_name": "Invented Corp"}))
    body = on.upload().json()
    assert body["fields"]["total"] == ""
    assert body["fields"]["client_name"] == ""
    assert set(body["dropped_fields"]) == {"total", "client_name"}
    assert on.confirm(body["id"]).status_code == 422


def test_a_person_can_fill_gaps_then_confirm(on: Env, script: Any) -> None:
    script(json.dumps({**GOOD, "total": "999999.00"}))
    ext = on.upload()
    patched = on.client.patch(
        on.url(f"extractions/{ext.json()['id']}"),
        {"fields": {"total": "1500.50"}},
        format="json",
        HTTP_IF_MATCH=ext["ETag"],
    )
    assert patched.status_code == 200, patched.content
    assert on.confirm(ext.json()["id"]).status_code == 201


def test_stale_version_conflicts(on: Env, script: Any) -> None:
    script(json.dumps(GOOD))
    ext = on.upload().json()
    response = on.client.patch(
        on.url(f"extractions/{ext['id']}"),
        {"fields": {"currency": "USD"}},
        format="json",
        HTTP_IF_MATCH='"99"',
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT_VERSION"


def test_bad_pdf_goes_to_manual_review_without_a_model_call(on: Env, script: Any) -> None:
    provider = script(json.dumps(GOOD))
    response = on.upload(b"not a pdf at all")
    assert response.status_code == 415
    assert provider.requests == []
    assert on.count("invoice_extractions") == 0


def test_model_failure_becomes_manual_review(on: Env, script: Any) -> None:
    script(RuntimeError("down"), RuntimeError("down"))
    body = on.upload().json()
    assert body["status"] == "NEEDS_MANUAL_REVIEW"
    assert body["failure_code"]
    assert on.count("invoices") == 0


def test_tenant_isolation(on: Env, script: Any, owner_db: psycopg.Connection) -> None:
    script(json.dumps(GOOD))
    ext = on.upload().json()
    other = Env(owner_db)
    assert other.client.get(other.url(f"extractions/{ext['id']}")).status_code == 404
    assert other.client.get(on.url(f"extractions/{ext['id']}")).status_code in (403, 404)
