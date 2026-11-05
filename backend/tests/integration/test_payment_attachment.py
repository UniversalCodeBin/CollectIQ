"""FR-032: a manual payment may carry one proof file. Content decides the type, never the file name."""

from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.integration.test_allocation_db import manual, scalar, world
from tests.support import API, add_member, idem

pytestmark = pytest.mark.usefixtures("pg")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"0" * 64


def _upload(w: Any, payment: str, name: str, data: bytes, client: Any = None) -> Any:
    return (client or w.client).post(
        f"{API}/workspaces/{w.ws}/payments/{payment}/attachment",
        {"file": SimpleUploadedFile(name, data)},
        format="multipart",
        **idem(),
    )


def _payment(w: Any) -> str:
    response = manual(w, 5_000, payer="Acme")
    assert response.status_code == 201, response.content
    return response.json()["payment"]["id"]


def test_attach_download_and_detail(owner_db: Any) -> None:
    w = world(owner_db, "att1@example.test", payments=())
    payment = _payment(w)
    response = _upload(w, payment, "receipt.png", PNG)
    assert response.status_code == 201, response.content
    expected = {"file_name": "receipt.png", "size_bytes": len(PNG), "content_type": "image/png"}
    assert response.json() == expected
    detail = w.client.get(f"{API}/workspaces/{w.ws}/payments/{payment}").json()
    assert detail["attachment"] == {
        "file_name": "receipt.png",
        "size_bytes": len(PNG),
        "content_type": "image/png",
    }
    download = w.client.get(f"{API}/workspaces/{w.ws}/payments/{payment}/attachment")
    assert download.status_code == 200 and download.content == PNG
    assert download["Content-Type"] == "image/png"
    assert "attachment" in download["Content-Disposition"]
    assert download["X-Content-Type-Options"] == "nosniff"
    assert scalar(w, "SELECT count(*) FROM audit_events WHERE action = 'payment.attachment_added'") == 1


def test_a_payment_without_proof_has_none(owner_db: Any) -> None:
    w = world(owner_db, "att2@example.test", payments=())
    payment = _payment(w)
    detail = w.client.get(f"{API}/workspaces/{w.ws}/payments/{payment}").json()
    assert detail["attachment"] is None
    assert w.client.get(f"{API}/workspaces/{w.ws}/payments/{payment}/attachment").status_code == 404


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("proof.png", b"<html><script>alert(1)</script></html>"),  # name lies about the content
        ("run.exe", b"MZ" + b"\x00" * 64),
        ("empty.pdf", b""),
        ("big.pdf", PDF + b"0" * (5 * 1024 * 1024)),
    ],
)
def test_content_is_checked_not_the_name(owner_db: Any, name: str, data: bytes) -> None:
    w = world(owner_db, "att3@example.test", payments=())
    payment = _payment(w)
    response = _upload(w, payment, name, data)
    assert response.status_code == 422, response.content
    assert scalar(w, "SELECT count(*) FROM payment_attachments") == 0


def test_one_attachment_only_and_statement_rows_refuse_it(owner_db: Any) -> None:
    w = world(owner_db, "att4@example.test")  # one imported statement row
    assert _upload(w, w.txns[0], "a.pdf", PDF).status_code == 422
    payment = _payment(w)
    assert _upload(w, payment, "a.pdf", PDF).status_code == 201
    assert _upload(w, payment, "b.pdf", PDF).status_code == 409


def test_a_project_lead_cannot_attach_and_another_workspace_cannot_see(owner_db: Any) -> None:
    w = world(owner_db, "att5@example.test", payments=())
    payment = _payment(w)
    assert _upload(w, payment, "a.pdf", PDF).status_code == 201
    other = world(owner_db, "att6@example.test", payments=())
    foreign = other.client.get(f"{API}/workspaces/{other.ws}/payments/{payment}/attachment")
    assert foreign.status_code == 404
    lead, _ = add_member(owner_db, w.ws, "att5p@example.test", "PROJECT_LEAD")
    assert _upload(w, payment, "c.pdf", PDF, client=lead).status_code == 403
