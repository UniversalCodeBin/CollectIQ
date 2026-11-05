"""CSV import end to end: upload, map, review, commit. Nothing reaches the ledger before the commit."""

import csv
import io
import json
import threading
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from rest_framework.test import APIClient

from collectiq.platform.context import RequestContext
from collectiq.platform.crypto import get_cipher
from collectiq.platform.db import tenant_tx
from tests.support import API, add_member, idem, owner_workspace

FIXTURES = Path(__file__).parent.parent / "fixtures" / "invoices"
BASIC_MAPPING = {
    "invoice_number": "Invoice No",
    "client_name": "Client",
    "due_date": "Due",
    "currency": "Currency",
    "total": "Total",
    "issue_date": "Issued",
    "client_email": "Email",
}
SHORT_MAPPING = {
    "invoice_number": "Invoice No",
    "client_name": "Client",
    "due_date": "Due",
    "currency": "Currency",
    "total": "Total",
}
HEADER = "Invoice No,Client,Due,Currency,Total,Issued\n"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _row(number: str, client: str = "Northwind", total: str = "100.00", issued: str = "2026-06-01") -> str:
    return f"{number},{client},2026-07-01,INR,{total},{issued}\n"


def _upload(client: APIClient, ws: str, data: bytes, name: str = "invoices.csv", **extra: Any) -> Any:
    file = SimpleUploadedFile(name, data, content_type="text/csv")
    return client.post(
        f"{API}/workspaces/{ws}/imports/invoices", {"file": file}, format="multipart", **{**idem(), **extra}
    )


def _map(
    client: APIClient,
    ws: str,
    import_id: str,
    mapping: dict[str, str] | None = None,
    date_format: str | None = "YYYY-MM-DD",
) -> Any:
    body: dict[str, Any] = {
        "mapping": mapping if mapping is not None else {**SHORT_MAPPING, "issue_date": "Issued"}
    }
    if date_format is not None:
        body["date_format"] = date_format
    return client.put(f"{API}/workspaces/{ws}/imports/{import_id}/mapping", body, format="json")


def _commit(client: APIClient, ws: str, import_id: str, decisions: dict[str, Any] | None = None) -> Any:
    return client.post(
        f"{API}/workspaces/{ws}/imports/{import_id}/commit",
        {"decisions": decisions or {}},
        format="json",
        **idem(),
    )


def _get(client: APIClient, ws: str, import_id: str, query: str = "") -> Any:
    return client.get(f"{API}/workspaces/{ws}/imports/{import_id}{query}")


def _prepare(client: APIClient, ws: str, data: bytes, **map_args: Any) -> tuple[str, dict[str, Any]]:
    upload = _upload(client, ws, data)
    assert upload.status_code == 201, upload.content
    mapped = _map(client, ws, upload.json()["id"], **map_args)
    assert mapped.status_code == 200, mapped.content
    return upload.json()["id"], mapped.json()


def _import(
    client: APIClient, ws: str, data: bytes, decisions: dict[str, Any] | None = None
) -> dict[str, Any]:
    import_id, _ = _prepare(client, ws, data)
    committed = _commit(client, ws, import_id, decisions)
    assert committed.status_code == 200, committed.content
    return committed.json()


def _scoped(owner_db: psycopg.Connection, ws: str) -> None:
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])


def _invoices(owner_db: psycopg.Connection, ws: str) -> list[dict[str, Any]]:
    _scoped(owner_db, ws)
    with owner_db.cursor(row_factory=psycopg.rows.dict_row) as cursor:
        return cursor.execute("SELECT * FROM invoices ORDER BY source_row, created_at").fetchall()


def _count(owner_db: psycopg.Connection, ws: str, table: str) -> int:
    _scoped(owner_db, ws)
    row = owner_db.execute(f"SELECT count(*) FROM {table}").fetchone()
    assert row
    return row[0]


def _audit(owner_db: psycopg.Connection, ws: str, action: str) -> list[dict[str, Any]]:
    _scoped(owner_db, ws)
    with owner_db.cursor(row_factory=psycopg.rows.dict_row) as cursor:
        return cursor.execute("SELECT * FROM audit_events WHERE action = %s ORDER BY id", [action]).fetchall()


def _rows(preview: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {row["row"]: row for row in preview["rows"]}


def test_upload_returns_columns_a_suggested_mapping_and_the_scan_status(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    response = _upload(client, ws, _fixture("basic.csv"), name="march.csv")
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "PREVIEW"
    assert body["file_name"] == "march.csv"
    assert body["headers"] == ["Invoice No", "Client", "Due", "Currency", "Total", "Issued", "Email"]
    assert body["suggested_mapping"]["total"] == "Total"
    assert body["suggested_mapping"]["client_email"] == "Email"
    assert "DD/MM/YYYY" in body["date_format_options"]
    assert body["scan_status"] == "NOT_SCANNED"


def test_a_renamed_spreadsheet_is_refused_in_plain_words_and_nothing_is_stored(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    response = _upload(client, ws, b"PK\x03\x04 pretend spreadsheet", name="book.csv")
    assert response.status_code == 415
    assert "Excel" in response.json()["detail"]
    assert _count(owner_db, ws, "import_batches") == 0
    assert _count(owner_db, ws, "stored_files") == 0


def test_a_wrong_extension_is_refused(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    assert _upload(client, ws, b"a,b\n1,2\n", name="invoices.txt").status_code == 415


def test_over_5mb_or_10000_rows_rejected(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    too_big = HEADER.encode() + b"x" * (settings.MAX_UPLOAD_BYTES + 1 - len(HEADER))
    assert _upload(client, ws, too_big).status_code == 413
    line = _row("I", "C")
    assert _upload(client, ws, (HEADER + line * 10_001).encode()).status_code == 413
    assert _upload(client, ws, (HEADER + line * 10_000).encode()).status_code == 201


def test_an_oversized_request_is_refused_before_anything_parses_it(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    response = _upload(client, ws, b"a,b\n1,2\n", CONTENT_LENGTH=str(10**9))
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_a_file_with_only_headings_is_refused(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    response = _upload(client, ws, HEADER.encode())
    assert response.status_code == 422
    assert response.json()["code"] == "IMPORT_VALIDATION_FAILED"
    assert "no invoice rows" in response.json()["detail"]


@pytest.mark.parametrize("missing", ["total", "due_date", "invoice_number", "client_name", "currency"])
def test_a_mapping_without_a_required_field_cannot_proceed(pg, owner_db, missing) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id = _upload(client, ws, _fixture("basic.csv")).json()["id"]
    mapping = {key: value for key, value in BASIC_MAPPING.items() if key != missing}
    response = _map(client, ws, import_id, mapping, "DD/MM/YYYY")
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == f"mapping.{missing}"


def test_an_unknown_date_format_is_refused(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id = _upload(client, ws, _fixture("basic.csv")).json()["id"]
    response = _map(client, ws, import_id, BASIC_MAPPING, "guess")
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "date_format"


def test_a_mapping_is_remembered_for_the_next_file_with_those_columns(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    data = b"Ref,Buyer,Pay By,Cur,Sum\nINV-1,Northwind,2026-07-01,INR,10.00\n"
    mapping = {
        "invoice_number": "Ref",
        "client_name": "Buyer",
        "due_date": "Pay By",
        "currency": "Cur",
        "total": "Sum",
    }
    first = _upload(client, ws, data).json()
    assert first["suggested_mapping"].get("total") != "Sum"
    assert _map(client, ws, first["id"], mapping).status_code == 200
    assert _commit(client, ws, first["id"]).status_code == 200
    assert _upload(client, ws, data).json()["suggested_mapping"] == mapping
    other = _upload(client, ws, _fixture("basic.csv")).json()
    assert other["suggested_mapping"]["total"] == "Total"


def test_the_ledger_is_unchanged_until_the_import_is_confirmed(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, preview = _prepare(
        client, ws, _fixture("basic.csv"), mapping=BASIC_MAPPING, date_format="DD/MM/YYYY"
    )
    assert preview["counts"]["new"] == 3
    assert preview["counts"]["total_rows"] == 3
    assert _count(owner_db, ws, "invoices") == 0
    assert _count(owner_db, ws, "clients") == 0

    committed = _commit(client, ws, import_id)
    assert committed.status_code == 200, committed.content
    assert committed.json()["status"] == "COMMITTED"
    assert committed.json()["counts"]["created"] == 3
    invoices = _invoices(owner_db, ws)
    assert [invoice["gross_minor"] for invoice in invoices] == [25000000, 100050, 120000]
    assert [invoice["currency"] for invoice in invoices] == ["INR", "INR", "USD"]
    assert _count(owner_db, ws, "clients") == 2
    assert _count(owner_db, ws, "client_contacts") == 2


def test_an_ambiguous_date_is_blocked_until_a_format_is_chosen(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, preview = _prepare(
        client, ws, _fixture("ambiguous_dates.csv"), mapping=SHORT_MAPPING, date_format=None
    )
    assert preview["counts"]["invalid"] == 1
    assert _rows(preview)[2]["errors"][0]["field"] == "date_format"
    assert _commit(client, ws, import_id, {"skip_invalid": True}).status_code == 422
    assert _count(owner_db, ws, "invoices") == 0

    _map(client, ws, import_id, SHORT_MAPPING, "DD/MM/YYYY")
    assert _commit(client, ws, import_id).status_code == 200
    assert _invoices(owner_db, ws)[0]["due_date"].isoformat() == "2026-04-03"


def test_the_chosen_format_decides_the_month(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, _ = _prepare(
        client, ws, _fixture("ambiguous_dates.csv"), mapping=SHORT_MAPPING, date_format="MM/DD/YYYY"
    )
    assert _commit(client, ws, import_id).status_code == 200
    assert _invoices(owner_db, ws)[0]["due_date"].isoformat() == "2026-03-04"


def test_invalid_rows_are_skipped_only_by_explicit_choice(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, preview = _prepare(
        client, ws, _fixture("mixed_invalid.csv"), mapping=SHORT_MAPPING, date_format="YYYY-MM-DD"
    )
    assert preview["counts"]["invalid"] == 2
    assert preview["counts"]["new"] == 1
    assert {error["field"] for error in _rows(preview)[4]["errors"]} == {"client_name", "total"}
    refused = _commit(client, ws, import_id)
    assert refused.status_code == 422
    assert refused.json()["code"] == "IMPORT_VALIDATION_FAILED"
    assert _count(owner_db, ws, "invoices") == 0

    committed = _commit(client, ws, import_id, {"skip_invalid": True})
    assert committed.status_code == 200, committed.content
    assert committed.json()["counts"]["skipped_invalid"] == 2
    assert [invoice["invoice_number"] for invoice in _invoices(owner_db, ws)] == ["INV-6001"]


def test_the_error_report_downloads_and_is_safe_to_open_in_a_spreadsheet(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    data = (HEADER + "=HYPERLINK(1),Northwind,2026-07-01,XXQ,10.00,2026-06-01\n").encode()
    import_id, _ = _prepare(client, ws, data)
    response = client.get(f"{API}/workspaces/{ws}/imports/{import_id}/error-report", HTTP_ACCEPT="text/csv")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert "attachment" in response["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(response.content.decode())))
    assert rows[0] == ["row", "invoice_number", "field", "problem"]
    assert rows[1][:3] == ["2", "'=HYPERLINK(1)", "currency"]


def test_total_tolerance_0_01(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    mapping = {**SHORT_MAPPING, "subtotal": "Subtotal", "tax": "Tax"}
    import_id, preview = _prepare(client, ws, _fixture("conflict_total.csv"), mapping=mapping)
    assert preview["counts"]["new"] == 1
    assert preview["counts"]["conflict"] == 1
    conflict = _rows(preview)[3]
    assert conflict["status"] == "CONFLICT"
    assert conflict["conflict"] == {"total_minor": 11802, "sum_minor": 11800}
    refused = _commit(client, ws, import_id)
    assert refused.status_code == 422
    assert _count(owner_db, ws, "invoices") == 0

    committed = _commit(client, ws, import_id, {"rows": {"3": {"total_source": "SUM"}}})
    assert committed.status_code == 200, committed.content
    assert [invoice["gross_minor"] for invoice in _invoices(owner_db, ws)] == [11801, 11800]


def test_a_conflict_can_keep_the_stated_total_or_be_left_out(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    mapping = {**SHORT_MAPPING, "subtotal": "Subtotal", "tax": "Tax"}
    import_id, _ = _prepare(client, ws, _fixture("conflict_total.csv"), mapping=mapping)
    assert _commit(client, ws, import_id, {"rows": {"3": {"total_source": "TOTAL"}}}).status_code == 200
    assert [invoice["gross_minor"] for invoice in _invoices(owner_db, ws)] == [11801, 11802]

    other, other_ws = owner_workspace(owner_db, "other@example.test")
    import_id, _ = _prepare(other, other_ws, _fixture("conflict_total.csv"), mapping=mapping)
    assert _commit(other, other_ws, import_id, {"rows": {"3": {"action": "IGNORE"}}}).status_code == 200
    assert [invoice["gross_minor"] for invoice in _invoices(owner_db, other_ws)] == [11801]


def test_reimport_same_csv_creates_no_duplicates_and_shows_diff(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    original = (HEADER + _row("INV-1") + _row("INV-2", total="200.00", issued="2026-06-02")).encode()
    _import(client, ws, original)

    import_id, preview = _prepare(client, ws, original)
    assert preview["counts"]["new"] == 0
    assert preview["counts"]["duplicate"] == 2
    assert _commit(client, ws, import_id).json()["counts"]["created"] == 0
    assert _count(owner_db, ws, "invoices") == 2

    changed = (
        HEADER + _row("inv 1", total="150.00") + _row("INV-2", total="200.00", issued="2026-06-02")
    ).encode()
    import_id, preview = _prepare(client, ws, changed)
    assert preview["counts"]["updated"] == 1
    row = _rows(preview)[2]
    assert row["status"] == "UPDATED"
    assert row["diffs"] == [{"field": "gross_minor", "current": 10000, "incoming": 15000, "kept": False}]
    assert row["allowed_decisions"] == ["UPDATE", "IGNORE"]
    assert _commit(client, ws, import_id).status_code == 422
    assert _invoices(owner_db, ws)[0]["gross_minor"] == 10000

    assert (
        _commit(client, ws, import_id, {"rows": {"2": {"action": "IGNORE"}}}).json()["counts"]["ignored"] == 1
    )
    assert _invoices(owner_db, ws)[0]["gross_minor"] == 10000

    import_id, _ = _prepare(client, ws, changed)
    committed = _commit(client, ws, import_id, {"rows": {"2": {"action": "UPDATE"}}})
    assert committed.json()["counts"]["updated"] == 1
    updated = _invoices(owner_db, ws)[0]
    assert updated["gross_minor"] == 15000
    assert updated["version"] == 2
    assert str(updated["import_batch_id"]) == import_id
    assert len(_audit(owner_db, ws, "invoice.updated")) == 1


def test_a_blank_cell_does_not_erase_what_is_on_the_invoice(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _import(client, ws, (HEADER + _row("INV-1")).encode())
    import_id, preview = _prepare(client, ws, (HEADER + _row("INV-1", issued="")).encode())
    assert preview["counts"]["duplicate"] == 1
    assert _commit(client, ws, import_id).status_code == 200
    assert _invoices(owner_db, ws)[0]["issue_date"].isoformat() == "2026-06-01"


def test_a_field_a_person_corrected_is_never_silently_overwritten(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _import(client, ws, (HEADER + _row("INV-1")).encode())
    _scoped(owner_db, ws)
    owner_db.execute(
        "UPDATE invoices SET gross_minor = 9999,"
        ' field_provenance = field_provenance || \'{"gross_minor": "USER"}\''
    )
    only_corrected = (HEADER + _row("INV-1")).encode()
    _, preview = _prepare(client, ws, only_corrected)
    assert preview["counts"]["duplicate"] == 1

    both = (HEADER + "INV-1,Northwind,2026-08-01,INR,100.00,2026-06-01\n").encode()
    import_id, preview = _prepare(client, ws, both)
    assert {diff["field"]: diff["kept"] for diff in _rows(preview)[2]["diffs"]} == {
        "due_date": False,
        "gross_minor": True,
    }
    assert _commit(client, ws, import_id, {"rows": {"2": {"action": "UPDATE"}}}).status_code == 200
    invoice = _invoices(owner_db, ws)[0]
    assert invoice["gross_minor"] == 9999
    assert invoice["due_date"].isoformat() == "2026-08-01"
    assert invoice["diverges_from_source"] is True


def test_same_client_amount_date_different_number_is_possible_duplicate_not_merged(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _import(client, ws, (HEADER + _row("INV-1")).encode())
    existing = _invoices(owner_db, ws)[0]
    twin = (HEADER + _row("INV-99")).encode()

    import_id, preview = _prepare(client, ws, twin)
    assert preview["counts"]["possible_duplicate"] == 1
    row = _rows(preview)[2]
    assert row["allowed_decisions"] == ["KEEP_BOTH", "MERGE", "IGNORE"]
    assert row["matches"][0]["invoice_number"] == "INV-1"
    assert row["matches"][0]["invoice_id"] == str(existing["id"])
    assert _commit(client, ws, import_id).status_code == 422
    assert _count(owner_db, ws, "invoices") == 1

    assert _commit(client, ws, import_id, {"rows": {"2": {"action": "IGNORE"}}}).status_code == 200
    assert _count(owner_db, ws, "invoices") == 1

    import_id, _ = _prepare(client, ws, twin)
    assert _commit(client, ws, import_id, {"rows": {"2": {"action": "KEEP_BOTH"}}}).status_code == 200
    invoices = _invoices(owner_db, ws)
    assert len(invoices) == 2
    kept = next(invoice for invoice in invoices if invoice["invoice_number"] == "INV-99")
    assert kept["possible_duplicate_of"] == existing["id"]

    import_id, preview = _prepare(client, ws, twin)
    assert preview["counts"]["new"] == 0
    assert preview["counts"]["duplicate"] == 1


def test_a_repeated_possible_duplicate_is_one_decision(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _import(client, ws, (HEADER + _row("INV-1")).encode())

    _, preview = _prepare(client, ws, (HEADER + _row("INV-99") + _row("INV-99")).encode())

    assert preview["counts"]["possible_duplicate"] == 1
    assert preview["counts"]["duplicate"] == 1
    assert set(_rows(preview)) == {2}, "the repeat asks nothing of the reader"


def test_a_merge_keeps_the_existing_invoice_and_remembers_the_other_number(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _import(client, ws, (HEADER + _row("INV-1")).encode())
    twin = (HEADER + _row("INV-99")).encode()
    import_id, _ = _prepare(client, ws, twin)
    committed = _commit(client, ws, import_id, {"rows": {"2": {"action": "MERGE"}}})
    assert committed.status_code == 200, committed.content
    assert committed.json()["counts"]["merged"] == 1
    invoices = _invoices(owner_db, ws)
    assert len(invoices) == 1
    assert invoices[0]["invoice_number"] == "INV-1"
    assert "INV-99" in invoices[0]["payment_references"]
    assert len(_audit(owner_db, ws, "invoice.merged")) == 1

    _, preview = _prepare(client, ws, twin)
    assert preview["counts"]["duplicate"] == 1
    assert preview["counts"]["possible_duplicate"] == 0


def test_both_twins_in_one_file_are_flagged_and_neither_is_merged(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    data = (HEADER + _row("INV-1") + _row("INV-2")).encode()
    import_id, preview = _prepare(client, ws, data)
    assert preview["counts"]["possible_duplicate"] == 2
    rows = _rows(preview)
    assert rows[2]["allowed_decisions"] == ["KEEP_BOTH", "IGNORE"]
    assert rows[3]["matches"][0]["row"] == 2
    disallowed = _commit(
        client, ws, import_id, {"rows": {"2": {"action": "MERGE"}, "3": {"action": "KEEP_BOTH"}}}
    )
    assert disallowed.status_code == 422
    decisions = {"rows": {"2": {"action": "KEEP_BOTH"}, "3": {"action": "KEEP_BOTH"}}}
    assert _commit(client, ws, import_id, decisions).status_code == 200
    first, second = _invoices(owner_db, ws)
    assert first["possible_duplicate_of"] is None
    assert second["possible_duplicate_of"] == first["id"]


def test_a_row_repeated_in_one_file_is_one_invoice(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _, preview = _prepare(client, ws, (HEADER + _row("INV-1") + _row("INV-1")).encode())
    assert preview["counts"]["new"] == 1
    assert preview["counts"]["duplicate"] == 1


def test_the_same_number_with_different_figures_in_one_file_needs_a_decision(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _, preview = _prepare(client, ws, (HEADER + _row("INV-1") + _row("INV-1", total="5.00")).encode())
    assert preview["counts"]["possible_duplicate"] == 2


def test_external_ids_identify_an_invoice_across_files(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    header = "Id,Invoice No,Client,Due,Currency,Total\n"
    mapping = {**SHORT_MAPPING, "external_id": "Id"}
    first = (header + "A1,INV-1,Northwind,2026-07-01,INR,100.00\n").encode()
    import_id, _ = _prepare(client, ws, first, mapping=mapping)
    assert _commit(client, ws, import_id).status_code == 200

    renumbered = (header + "A1,INV-1-R,Northwind,2026-07-01,INR,120.00\n").encode()
    import_id, preview = _prepare(client, ws, renumbered, mapping=mapping)
    assert preview["counts"]["updated"] == 1

    stolen = (header + "A1,INV-1,Other Co,2026-07-01,INR,100.00\n").encode()
    _, preview = _prepare(client, ws, stolen, mapping=mapping)
    assert _rows(preview)[2]["errors"][0]["field"] == "external_id"

    clashing = (
        header + "B1,INV-5,Northwind,2026-07-01,INR,1.00\nB1,INV-5,Northwind,2026-07-01,INR,2.00\n"
    ).encode()
    _, preview = _prepare(client, ws, clashing, mapping=mapping)
    assert _rows(preview)[3]["errors"][0]["field"] == "external_id"


def test_a_similar_client_name_is_a_question_never_a_silent_merge(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _import(client, ws, (HEADER + _row("INV-1", "Acme Pvt Ltd")).encode())
    existing_id = str(_invoices(owner_db, ws)[0]["client_id"])
    similar = (HEADER + _row("INV-2", "ACME Private Limited", total="5.00")).encode()

    import_id, preview = _prepare(client, ws, similar)
    assert preview["counts"]["client_decisions"] == 1
    assert preview["counts"]["awaiting_client"] == 1
    match = preview["client_matches"][0]
    assert match["name"] == "acme private limited"
    assert match["candidates"] == [
        {"client_id": existing_id, "display_name": "Acme Pvt Ltd", "reason": "SIMILAR_NAME"}
    ]
    assert _commit(client, ws, import_id).status_code == 422
    assert _count(owner_db, ws, "clients") == 1

    link = {"clients": {"acme private limited": {"action": "LINK", "client_id": existing_id}}}
    assert _commit(client, ws, import_id, link).status_code == 200
    invoices = _invoices(owner_db, ws)
    assert {str(invoice["client_id"]) for invoice in invoices} == {existing_id}
    assert _count(owner_db, ws, "clients") == 1
    assert _count(owner_db, ws, "client_aliases") == 1

    again = (HEADER + _row("INV-3", "ACME Private Limited", total="6.00")).encode()
    _, preview = _prepare(client, ws, again)
    assert preview["counts"]["client_decisions"] == 0
    assert preview["counts"]["new"] == 1


def test_a_similar_name_can_stay_a_separate_client(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _import(client, ws, (HEADER + _row("INV-1", "Acme Pvt Ltd")).encode())
    import_id, _ = _prepare(
        client, ws, (HEADER + _row("INV-2", "ACME Private Limited", total="5.00")).encode()
    )
    decisions = {"clients": {"acme private limited": {"action": "NEW"}}}
    assert _commit(client, ws, import_id, decisions).status_code == 200
    assert _count(owner_db, ws, "clients") == 2


def test_similar_names_in_one_file_are_asked_about(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    data = (
        HEADER + _row("INV-1", "Acme Pvt Ltd") + _row("INV-2", "ACME Private Limited", total="5.00")
    ).encode()
    import_id, preview = _prepare(client, ws, data)
    assert preview["counts"]["client_decisions"] == 1
    assert preview["client_matches"][0]["in_file"] == ["acme pvt ltd"]
    same = {"clients": {"acme private limited": {"action": "SAME_AS", "name": "acme pvt ltd"}}}
    assert _commit(client, ws, import_id, same).status_code == 200
    assert _count(owner_db, ws, "clients") == 1
    assert _count(owner_db, ws, "client_aliases") == 1
    assert len({invoice["client_id"] for invoice in _invoices(owner_db, ws)}) == 1


def test_a_known_email_under_a_new_name_is_asked_about(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    header = "Invoice No,Client,Due,Currency,Total,Email\n"
    mapping = {**SHORT_MAPPING, "client_email": "Email"}
    first = (header + "INV-1,Northwind,2026-07-01,INR,1.00,pay@northwind.example.test\n").encode()
    import_id, _ = _prepare(client, ws, first, mapping=mapping)
    assert _commit(client, ws, import_id).status_code == 200
    second = (header + "INV-2,NW Trading,2026-07-01,INR,2.00,pay@northwind.example.test\n").encode()
    _, preview = _prepare(client, ws, second, mapping=mapping)
    assert preview["client_matches"][0]["candidates"][0]["reason"] == "SAME_EMAIL"
    assert preview["counts"]["new"] == 0


@pytest.mark.parametrize(
    "decision",
    [
        {"action": "LINK", "client_id": "00000000-0000-4000-8000-000000000000"},
        {"action": "LINK"},
        {"action": "SAME_AS", "name": "nobody"},
        {"action": "SAME_AS", "name": "acme private limited"},
    ],
)
def test_a_client_decision_that_makes_no_sense_is_refused(pg, owner_db, decision) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _import(client, ws, (HEADER + _row("INV-1", "Acme Pvt Ltd")).encode())
    import_id, _ = _prepare(
        client, ws, (HEADER + _row("INV-2", "ACME Private Limited", total="5.00")).encode()
    )
    response = _commit(client, ws, import_id, {"clients": {"acme private limited": decision}})
    assert response.status_code == 422
    assert _count(owner_db, ws, "invoices") == 1


def test_a_decision_about_an_unknown_row_or_name_is_refused(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, _ = _prepare(client, ws, (HEADER + _row("INV-1")).encode())
    assert _commit(client, ws, import_id, {"rows": {"99": {"action": "IGNORE"}}}).status_code == 422
    assert _commit(client, ws, import_id, {"rows": {"2": {"action": "UPDATE"}}}).status_code == 422
    assert _commit(client, ws, import_id, {"rows": {"two": {"action": "IGNORE"}}}).status_code == 422
    assert _commit(client, ws, import_id, {"clients": {"nobody": {"action": "NEW"}}}).status_code == 422
    assert _commit(client, ws, import_id, {"colour": "red"}).status_code == 422
    assert _count(owner_db, ws, "invoices") == 0


def test_failed_commit_leaves_no_records(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    data = (
        HEADER + _row("INV-1") + _row("INV-2", "Blue Harbor") + _row("INV-BOOM", "Kestrel", total="3.00")
    ).encode()
    import_id, _ = _prepare(client, ws, data)
    owner_db.execute(
        "CREATE FUNCTION test_fail_import() RETURNS trigger LANGUAGE plpgsql AS $$"
        " BEGIN IF NEW.invoice_number = 'INV-BOOM' THEN RAISE EXCEPTION 'injected failure'; END IF;"
        " RETURN NEW; END $$"
    )
    owner_db.execute(
        "CREATE TRIGGER test_fail_import BEFORE INSERT ON invoices"
        " FOR EACH ROW EXECUTE FUNCTION test_fail_import()"
    )
    try:
        failed = _commit(client, ws, import_id)
        assert failed.status_code == 500
        assert "Nothing was added" in failed.json()["detail"]
        assert "injected" not in failed.content.decode()
        assert _count(owner_db, ws, "invoices") == 0
        assert _count(owner_db, ws, "clients") == 0
        batch = _get(client, ws, import_id).json()
        assert batch["status"] == "IMPORT_FAILED"
        assert "Nothing was added" in batch["failure_reason"]
        assert len(_audit(owner_db, ws, "invoice.created")) == 0
        assert len(_audit(owner_db, ws, "import.failed")) == 1
    finally:
        owner_db.execute("DROP TRIGGER test_fail_import ON invoices")
        owner_db.execute("DROP FUNCTION test_fail_import()")

    retried = _commit(client, ws, import_id)
    assert retried.status_code == 200, retried.content
    assert retried.json()["counts"]["created"] == 3
    assert _count(owner_db, ws, "invoices") == 3


def test_a_failed_commit_logs_no_row_values(pg, owner_db, caplog) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, _ = _prepare(client, ws, (HEADER + _row("INV-1", "Quiet Harbor Traders")).encode())
    owner_db.execute(
        "CREATE FUNCTION test_fail_import() RETURNS trigger LANGUAGE plpgsql AS $$"
        " BEGIN RAISE EXCEPTION 'failed on %', NEW.invoice_number; END $$"
    )
    owner_db.execute(
        "CREATE TRIGGER test_fail_import BEFORE INSERT ON invoices"
        " FOR EACH ROW EXECUTE FUNCTION test_fail_import()"
    )
    try:
        with caplog.at_level("DEBUG"):
            assert _commit(client, ws, import_id).status_code == 500
    finally:
        owner_db.execute("DROP TRIGGER test_fail_import ON invoices")
        owner_db.execute("DROP FUNCTION test_fail_import()")

    assert import_id in caplog.text
    assert "INV-1" not in caplog.text
    assert "Quiet Harbor" not in caplog.text


def test_import_writes_summary_audit_event(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, _ = _prepare(
        client, ws, _fixture("basic.csv"), mapping=BASIC_MAPPING, date_format="DD/MM/YYYY"
    )
    assert len(_audit(owner_db, ws, "import.previewed")) == 1
    assert _commit(client, ws, import_id).status_code == 200
    summary = _audit(owner_db, ws, "import.committed")
    assert len(summary) == 1
    assert summary[0]["object_id"] == import_id
    assert summary[0]["after_masked"]["counts"]["created"] == 3
    serialized = json.dumps(summary[0]["after_masked"])
    assert "Northwind" not in serialized
    assert "northwind.example.test" not in serialized
    assert len(_audit(owner_db, ws, "invoice.created")) == 3
    assert len(_audit(owner_db, ws, "client.created")) == 2


def test_discard_deletes_the_file_and_closes_the_batch(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, _ = _prepare(client, ws, (HEADER + _row("INV-1")).encode())
    _scoped(owner_db, ws)
    row = owner_db.execute("SELECT storage_key FROM stored_files").fetchone()
    assert row
    stored = settings.COLLECTIQ_STORAGE_DIR / row[0]
    assert stored.exists()

    assert client.delete(f"{API}/workspaces/{ws}/imports/{import_id}").status_code == 204
    assert not stored.exists()
    assert _get(client, ws, import_id).json()["status"] == "DISCARDED"
    assert len(_audit(owner_db, ws, "import.discarded")) == 1
    assert _commit(client, ws, import_id).status_code == 409
    assert _map(client, ws, import_id).status_code == 409
    assert client.get(f"{API}/workspaces/{ws}/imports/{import_id}/error-report").status_code == 409
    assert client.delete(f"{API}/workspaces/{ws}/imports/{import_id}").status_code == 409


def test_a_committed_batch_cannot_be_committed_again_or_discarded(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, _ = _prepare(client, ws, (HEADER + _row("INV-1")).encode())
    assert _commit(client, ws, import_id).status_code == 200
    second = _commit(client, ws, import_id)
    assert second.status_code == 409
    assert second.json()["code"] == "STATE_TRANSITION_INVALID"
    assert client.delete(f"{API}/workspaces/{ws}/imports/{import_id}").status_code == 409
    assert _map(client, ws, import_id).status_code == 409
    assert _count(owner_db, ws, "invoices") == 1


def test_a_commit_without_a_mapping_is_refused(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id = _upload(client, ws, (HEADER + _row("INV-1")).encode()).json()["id"]
    assert _commit(client, ws, import_id).status_code == 422


def test_the_original_row_and_file_are_encrypted_and_recoverable(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, _ = _prepare(
        client, ws, _fixture("basic.csv"), mapping=BASIC_MAPPING, date_format="DD/MM/YYYY"
    )
    assert _commit(client, ws, import_id).status_code == 200
    invoice = _invoices(owner_db, ws)[0]
    ciphertext = bytes(invoice["raw_row_ciphertext"])
    assert b"Northwind" not in ciphertext
    _scoped(owner_db, ws)
    row = owner_db.execute("SELECT storage_key FROM stored_files").fetchone()
    assert row
    assert b"Northwind" not in (settings.COLLECTIQ_STORAGE_DIR / row[0]).read_bytes()

    ctx = RequestContext(uuid.UUID(ws), None, "OWNER", "test", "system")
    with tenant_tx(ctx):
        plain = get_cipher().decrypt(ctx, ciphertext, str(invoice["id"]).encode())
    raw = json.loads(plain)
    assert raw["Invoice No"] == "INV-1001"
    assert raw["Total"] == "2,50,000.00"


def test_every_invoice_records_where_it_came_from(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, _ = _prepare(
        client, ws, _fixture("basic.csv"), mapping=BASIC_MAPPING, date_format="DD/MM/YYYY"
    )
    assert _commit(client, ws, import_id).status_code == 200
    invoices = _invoices(owner_db, ws)
    assert [invoice["source_row"] for invoice in invoices] == [2, 3, 4]
    assert all(str(invoice["import_batch_id"]) == import_id for invoice in invoices)
    assert invoices[0]["source_system"] == "CSV"
    assert invoices[0]["status"] == "ACTIVE"
    assert invoices[0]["field_provenance"]["gross_minor"] == "IMPORT"
    assert invoices[0]["normalized_number"] == "inv1001"


def test_an_address_someone_opted_out_of_stays_suppressed(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    header = "Invoice No,Client,Due,Currency,Total,Email\n"
    mapping = {**SHORT_MAPPING, "client_email": "Email"}
    first = (header + "INV-1,Northwind,2026-07-01,INR,1.00,pay@northwind.example.test\n").encode()
    import_id, _ = _prepare(client, ws, first, mapping=mapping)
    assert _commit(client, ws, import_id).status_code == 200
    _scoped(owner_db, ws)
    owner_db.execute("UPDATE client_contacts SET status = 'SUPPRESSED', suppression_reason = 'OPT_OUT'")
    second = (header + "INV-2,Northwind,2026-07-02,INR,2.00,pay@northwind.example.test\n").encode()
    import_id, _ = _prepare(client, ws, second, mapping=mapping)
    assert _commit(client, ws, import_id).status_code == 200
    row = owner_db.execute("SELECT count(*), min(status) FROM client_contacts").fetchone()
    assert row == (1, "SUPPRESSED")


@pytest.mark.parametrize("fixture", ["semicolon.csv", "bom.csv"])
def test_semicolons_and_byte_order_marks_import_end_to_end(pg, owner_db, fixture) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    upload = _upload(client, ws, _fixture(fixture))
    assert upload.status_code == 201, upload.content
    assert upload.json()["headers"][0] == "Invoice No"
    mapped = _map(client, ws, upload.json()["id"], SHORT_MAPPING, "YYYY-MM-DD")
    assert mapped.json()["counts"]["new"] == 1, mapped.content
    assert _commit(client, ws, upload.json()["id"]).status_code == 200


def test_another_workspace_cannot_see_or_touch_a_batch(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, _ = _prepare(client, ws, (HEADER + _row("INV-1")).encode())
    other, other_ws = owner_workspace(owner_db, "other@example.test")
    assert _get(other, other_ws, import_id).status_code == 404
    assert _map(other, other_ws, import_id).status_code == 404
    assert _commit(other, other_ws, import_id).status_code == 404
    assert other.delete(f"{API}/workspaces/{other_ws}/imports/{import_id}").status_code == 404
    assert other.get(f"{API}/workspaces/{other_ws}/imports/{import_id}/error-report").status_code == 404


def test_only_finance_roles_can_import_but_team_leads_cannot(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, _ = _prepare(client, ws, (HEADER + _row("INV-1")).encode())
    lead, _ = add_member(owner_db, ws, "lead@example.test", "PROJECT_LEAD")
    assert _upload(lead, ws, (HEADER + _row("INV-2")).encode()).status_code == 403
    assert _get(lead, ws, import_id).status_code == 403
    assert _commit(lead, ws, import_id).status_code == 403
    finance, _ = add_member(owner_db, ws, "finance@example.test", "FINANCE_ADMIN")
    assert _get(finance, ws, import_id).status_code == 200
    assert _commit(finance, ws, import_id).status_code == 200


def test_a_real_multipart_upload_passes_csrf_and_a_retry_replays(pg, owner_db) -> None:
    logged, ws = owner_workspace(owner_db, "owner@example.test")
    strict = APIClient(enforce_csrf_checks=True)
    strict.cookies = logged.cookies
    token = logged.cookies["collectiq_csrf"].value
    key = idem()
    headers = {"HTTP_X_CSRFTOKEN": token, **key}
    data = (HEADER + _row("INV-1")).encode()

    first = _upload(strict, ws, data, **headers)
    assert first.status_code == 201, first.content
    replay = _upload(strict, ws, data, **headers)
    assert replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]
    assert _count(owner_db, ws, "import_batches") == 1

    different = _upload(strict, ws, (HEADER + _row("INV-2")).encode(), **headers)
    assert different.status_code == 422
    assert different.json()["code"] == "IDEMPOTENCY_MISMATCH"


def test_the_preview_pages_through_rows_needing_attention(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    lines = "".join(f"INV-{n},Northwind,2026-07-01,XXQ,10.00,2026-06-01\n" for n in range(5))
    import_id, _ = _prepare(client, ws, (HEADER + lines).encode())
    first = _get(client, ws, import_id, "?limit=2").json()
    assert [row["row"] for row in first["rows"]] == [2, 3]
    assert first["next_row"] == 3
    second = _get(client, ws, import_id, f"?limit=2&after_row={first['next_row']}").json()
    assert [row["row"] for row in second["rows"]] == [4, 5]
    assert _get(client, ws, import_id, "?limit=0").status_code == 422
    assert _get(client, ws, import_id, "?after_row=x").status_code == 422


def test_two_rows_cannot_rewrite_one_invoice_in_different_ways(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _import(client, ws, (HEADER + _row("INV-1")).encode())
    data = (
        HEADER + _row("INV-1", total="150.00") + _row("inv 1", total="150.00") + _row("INV 1", total="175.00")
    )
    _, preview = _prepare(client, ws, data.encode())
    rows = _rows(preview)
    assert rows[2]["status"] == "UPDATED"
    assert preview["counts"]["duplicate"] == 1
    assert rows[4]["status"] == "INVALID"
    assert rows[4]["errors"][0]["field"] == "invoice_number"


def test_commit_is_offered_only_when_nothing_is_left_to_decide(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, preview = _prepare(client, ws, _fixture("mixed_invalid.csv"), mapping=SHORT_MAPPING)
    actions = {action["action"]: action for action in preview["allowed_actions"]}
    assert actions["COMMIT"]["allowed"] is False
    assert actions["COMMIT"]["reason"]
    assert actions["DISCARD"]["allowed"] is True

    assert _commit(client, ws, import_id, {"skip_invalid": True}).status_code == 200
    done = _get(client, ws, import_id).json()
    assert {action["action"]: action["allowed"] for action in done["allowed_actions"]} == {
        "COMMIT": False,
        "DISCARD": False,
    }
    assert done["rows"] == []


@pytest.mark.concurrency
def test_two_commits_of_the_same_file_cannot_both_create_invoices(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    data = (HEADER + _row("INV-1") + _row("INV-2", total="5.00")).encode()
    first, _ = _prepare(client, ws, data)
    second, _ = _prepare(client, ws, data)
    barrier = threading.Barrier(2)
    statuses: list[int] = []

    def commit(import_id: str) -> None:
        try:
            barrier.wait(timeout=10)
            statuses.append(_commit(client, ws, import_id).status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=commit, args=(batch,)) for batch in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert statuses == [200, 200]
    assert _count(owner_db, ws, "invoices") == 2
