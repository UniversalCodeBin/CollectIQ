"""Queue, dashboard and invoice detail (E042-E048). Read-only views over `invoice_state`."""

import json
import uuid
import zlib
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import pytest
from rest_framework.test import APIClient

from collectiq.invoices import read_models
from tests.integration.test_import import HEADER, _import
from tests.support import API, add_member, idem, owner_workspace

pytestmark = pytest.mark.usefixtures("pg")
NOW = datetime(2026, 7, 15, 6, 0, tzinfo=UTC)
FORBIDDEN = {"workspace_id", "raw_row_ciphertext", "normalized_number", "field_provenance", "import_batch_id"}


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(read_models, "_now", lambda: NOW)


def _line(
    number: str,
    client: str = "Northwind",
    due: str = "2026-07-01",
    currency: str = "INR",
    total: str = "100.00",
) -> str:
    # A different issue date for each number, or rows alike in client and amount read as possible duplicates.
    issued = date(2018, 1, 1) + timedelta(days=zlib.crc32(number.encode()) % 2500)
    return f"{number},{client},{due},{currency},{total},{issued.isoformat()}\n"


def _seed(client: APIClient, ws: str, *lines: str) -> dict[str, str]:
    _import(client, ws, (HEADER + "".join(lines)).encode())
    page = client.get(f"{API}/workspaces/{ws}/invoices?limit=200").json()
    return {item["invoice_number"]: item["id"] for item in page["items"]}


def _state(owner_db: Any, ws: str, invoice_id: str, **changes: Any) -> None:
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    sets = ", ".join(f"{name} = %s" for name in changes)
    owner_db.execute(
        f"UPDATE invoice_state SET {sets} WHERE invoice_id = %s",  # noqa: S608
        [*changes.values(), invoice_id],
    )


def _fresh(owner_db: Any, ws: str, *ids: str) -> None:
    for invoice_id in ids:
        _state(owner_db, ws, invoice_id, coverage_as_of=NOW - timedelta(days=1))


def _queue(client: APIClient, ws: str, query: str = "") -> Any:
    return client.get(f"{API}/workspaces/{ws}/queue{query}")


def _list(client: APIClient, ws: str, query: str = "") -> Any:
    return client.get(f"{API}/workspaces/{ws}/invoices{query}")


def _numbers(response: Any) -> list[str]:
    assert response.status_code == 200, response.content
    return [item["invoice_number"] for item in response.json()["items"]]


def _audit(owner_db: Any, ws: str, action: str) -> list[dict[str, Any]]:
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    cursor = owner_db.execute(
        "SELECT object_id, before_masked, after_masked, reason_codes FROM audit_events"
        " WHERE action = %s ORDER BY id",
        [action],
    )
    return [
        {"object_id": row[0], "before": row[1], "after": row[2], "reason_codes": row[3]}
        for row in cursor.fetchall()
    ]


# ---------- the named tests from the brief ----------


def test_every_queue_row_has_reason(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(
        client,
        ws,
        _line("A-1"),
        _line("A-2", due="2026-08-30"),
        _line("A-3"),
        _line("A-4"),
        _line("A-5"),
    )
    _state(owner_db, ws, ids["A-2"], payment_status="AWAITING_VERIFICATION")
    _state(owner_db, ws, ids["A-3"], dispute_status="OPEN")
    _state(owner_db, ws, ids["A-4"], reminder_status="DRAFT_READY", coverage_as_of=NOW)
    _state(owner_db, ws, ids["A-5"], coverage_as_of=NOW)
    items = _queue(client, ws).json()["items"]
    assert {item["invoice_number"] for item in items} == {"A-1", "A-2", "A-3", "A-4", "A-5"}
    for item in items:
        assert item["reasons"], item
        assert all(reason["code"] and reason["label"] and reason["link"] for reason in item["reasons"])
        assert item["recommended_action"]["code"]
        assert item["tier"] in (1, 2, 3, 4, 5)


def test_overdue_uses_workspace_timezone_across_utc_boundary(
    pg: None, owner_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    owner_db.execute("UPDATE workspaces SET timezone = 'Asia/Kolkata' WHERE id = %s", [ws])
    ids = _seed(client, ws, _line("TZ-1", due="2026-07-15"))
    _fresh(owner_db, ws, ids["TZ-1"])
    # 20:00 UTC on the 15th is already 01:30 on the 16th in Kolkata, and only then is the 15th past.
    monkeypatch.setattr(read_models, "_now", lambda: datetime(2026, 7, 15, 20, 0, tzinfo=UTC))
    row = _list(client, ws).json()["items"][0]
    assert (row["days_overdue"], row["due_bucket"]) == (1, "OVERDUE")
    owner_db.execute("UPDATE workspaces SET timezone = 'UTC' WHERE id = %s", [ws])
    row = _list(client, ws).json()["items"][0]
    assert (row["days_overdue"], row["due_bucket"]) == (0, "DUE_TODAY")


def test_dashboard_totals_are_per_currency(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _seed(
        client,
        ws,
        _line("D-1", total="100.00"),
        _line("D-2", total="50.00"),
        _line("D-3", currency="USD", total="70.00"),
    )
    body = client.get(f"{API}/workspaces/{ws}/dashboard").json()
    by_currency = {block["currency"]: block for block in body["currencies"]}
    assert set(by_currency) == {"INR", "USD"}
    tiles = {tile["key"]: tile for tile in by_currency["INR"]["tiles"]}
    assert (tiles["outstanding"]["count"], tiles["outstanding"]["amount_minor"]) == (2, 15000)
    tiles = {tile["key"]: tile for tile in by_currency["USD"]["tiles"]}
    assert (tiles["outstanding"]["count"], tiles["outstanding"]["amount_minor"]) == (1, 7000)
    assert "amount_minor" not in body
    assert "total_minor" not in body


@pytest.mark.parametrize("path", ["invoices", "queue", "dashboard"])
def test_unknown_query_param_is_422(pg: None, owner_db: Any, path: str) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    response = client.get(f"{API}/workspaces/{ws}/{path}?paymentstatus=OUTSTANDING")
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"
    assert response.json()["errors"][0]["field"] == "paymentstatus"


def test_search_q_is_tenant_scoped(pg: None, owner_db: Any) -> None:
    first, ws_a = owner_workspace(owner_db, "a@example.test")
    second, ws_b = owner_workspace(owner_db, "b@example.test")
    _seed(first, ws_a, _line("SHARED-1", client="Alpha"))
    _seed(second, ws_b, _line("SHARED-2", client="Beta"))
    assert _numbers(_list(first, ws_a, "?q=shared")) == ["SHARED-1"]
    assert _numbers(_list(second, ws_b, "?q=shared")) == ["SHARED-2"]
    assert _numbers(_list(first, ws_a, "?q=beta")) == []


def test_dto_exposes_allowed_actions_and_no_internal_fields(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("X-1"))
    summary = _list(client, ws).json()["items"][0]
    detail = client.get(f"{API}/workspaces/{ws}/invoices/{ids['X-1']}").json()
    queued = _queue(client, ws).json()["items"][0]
    for dto in (summary, queued, detail):
        text = json.dumps(dto)
        assert not FORBIDDEN & _all_keys(dto), text
        assert not any(word in key for key in _all_keys(dto) for word in ("risk", "score", "probab"))
        actions = {entry["action"]: entry for entry in dto["allowed_actions"]}
        assert set(actions) == {"CORRECT", "CANCEL", "ARCHIVE"}
        assert all(entry["allowed"] is True or entry["reason"] for entry in dto["allowed_actions"])


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for inner in value.values() for key in _all_keys(inner)}
    if isinstance(value, list):
        return {key for inner in value for key in _all_keys(inner)}
    return set()


# ---------- queue ----------


def test_queue_is_in_exception_order_and_reset_restores_it(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(
        client,
        ws,
        _line("O-small", due="2026-07-01", total="10.00"),
        _line("O-big", due="2026-07-01", total="90.00"),
        _line("O-old", due="2026-06-01", total="10.00"),
        _line("O-draft", due="2026-07-01"),
        _line("O-dispute", due="2026-08-30"),
    )
    _fresh(owner_db, ws, *ids.values())
    _state(owner_db, ws, ids["O-draft"], reminder_status="DRAFT_READY")
    _state(owner_db, ws, ids["O-dispute"], dispute_status="OPEN")
    expected = ["O-dispute", "O-draft", "O-old", "O-big", "O-small"]
    assert _numbers(_queue(client, ws)) == expected
    assert _numbers(_queue(client, ws, "?sort=invoice_number"))[0] == "O-big"
    assert _numbers(_queue(client, ws, "?sort=-invoice_number"))[0] == "O-small"
    assert _numbers(_queue(client, ws, "?sort=exception")) == expected


def test_paid_verified_is_absent_from_queue_and_found_by_search(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("P-1"), _line("P-2"))
    _state(owner_db, ws, ids["P-1"], payment_status="PAID_VERIFIED", paid_minor=10000, outstanding_minor=0)
    assert _numbers(_queue(client, ws)) == ["P-2"]
    assert _numbers(_list(client, ws, "?q=P-1")) == ["P-1"]


def test_queue_row_says_who_can_act_and_hides_the_button_for_a_role_that_cannot(
    pg: None, owner_db: Any
) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    lead, lead_member = add_member(owner_db, ws, "lead@example.test", "PROJECT_LEAD")
    ids = _seed(client, ws, _line("R-1"))
    owner_row = _queue(client, ws).json()["items"][0]
    assert owner_row["recommended_action"]["can_act"] is True
    assert owner_row["recommended_action"]["performed_by"] == ["Owner", "Finance admin"]
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    owner_db.execute(
        "UPDATE invoices SET assignee_id ="
        " (SELECT user_id FROM workspace_memberships WHERE id = %s) WHERE id = %s",
        [lead_member, ids["R-1"]],
    )
    lead_row = _queue(lead, ws).json()["items"][0]
    assert lead_row["recommended_action"]["can_act"] is False
    assert lead_row["recommended_action"]["reason"]
    actions = {entry["action"]: entry for entry in lead_row["allowed_actions"]}
    assert actions["CANCEL"]["allowed"] is False and actions["CANCEL"]["reason"]


def test_a_project_lead_sees_only_assigned_invoices(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    lead, lead_member = add_member(owner_db, ws, "lead@example.test", "PROJECT_LEAD")
    ids = _seed(client, ws, _line("L-1"), _line("L-2"))
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    owner_db.execute(
        "UPDATE invoices SET assignee_id ="
        " (SELECT user_id FROM workspace_memberships WHERE id = %s) WHERE id = %s",
        [lead_member, ids["L-1"]],
    )
    assert _numbers(_queue(lead, ws)) == ["L-1"]
    assert _numbers(_list(lead, ws)) == ["L-1"]
    assert lead.get(f"{API}/workspaces/{ws}/invoices/{ids['L-2']}").status_code == 404
    assert lead.get(f"{API}/workspaces/{ws}/invoices/{ids['L-1']}").status_code == 200


def test_reads_do_not_write_an_audit_event_or_change_state(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _seed(client, ws, _line("N-1"))
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    before = owner_db.execute("SELECT count(*) FROM audit_events").fetchone()[0]
    state = owner_db.execute("SELECT version FROM invoice_state").fetchone()[0]
    _queue(client, ws)
    _list(client, ws)
    client.get(f"{API}/workspaces/{ws}/dashboard")
    assert owner_db.execute("SELECT count(*) FROM audit_events").fetchone()[0] == before
    assert owner_db.execute("SELECT version FROM invoice_state").fetchone()[0] == state


# ---------- list: filters, sort, cursor ----------


def test_two_filters_are_the_intersection(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(
        client,
        ws,
        _line("F-1", currency="INR"),
        _line("F-2", currency="USD"),
        _line("F-3", currency="USD"),
    )
    _state(owner_db, ws, ids["F-3"], dispute_status="OPEN")
    assert _numbers(_list(client, ws, "?currency=USD&dispute_status=OPEN")) == ["F-3"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("?payment_status=OUTSTANDING", {"G-1", "G-2", "G-3"}),
        ("?reminder_status=NOT_CONTACTED", {"G-1", "G-2", "G-3"}),
        ("?due_from=2026-07-02", {"G-2", "G-3"}),
        ("?due_to=2026-07-02", {"G-1"}),
        ("?amount_min=20", {"G-2", "G-3"}),
        ("?amount_max=20", {"G-1"}),
        ("?amount_min=20.50&amount_max=20.50", {"G-3"}),
        ("?q=INV-REF", set()),
        ("?q=g-2", {"G-2"}),
        ("?q=Northwind", {"G-1", "G-2"}),
        ("?q=20.50", {"G-3"}),
        ("?q=20.5", {"G-3"}),
        ("?q=%25", set()),
    ],
)
def test_each_filter_narrows_the_list(pg: None, owner_db: Any, query: str, expected: set[str]) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _seed(
        client,
        ws,
        _line("G-1", due="2026-07-01", total="10.00"),
        _line("G-2", due="2026-08-01", total="30.00"),
        _line("G-3", client="Globex", due="2026-08-01", total="20.50"),
    )
    assert set(_numbers(_list(client, ws, query))) == expected


def test_client_assignee_and_batch_filters(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _lead, lead_member = add_member(owner_db, ws, "lead@example.test", "PROJECT_LEAD")
    ids = _seed(client, ws, _line("H-1"), _line("H-2", client="Globex"))
    detail = client.get(f"{API}/workspaces/{ws}/invoices/{ids['H-1']}").json()
    assert _numbers(_list(client, ws, f"?client_id={detail['facts']['client_id']}")) == ["H-1"]
    batch = detail["provenance"]["import_id"]
    assert len(_numbers(_list(client, ws, f"?import_batch={batch}"))) == 2
    assert _numbers(_list(client, ws, f"?import_batch={uuid.uuid4()}")) == []
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    user = owner_db.execute(
        "SELECT user_id FROM workspace_memberships WHERE id = %s", [lead_member]
    ).fetchone()[0]
    owner_db.execute("UPDATE invoices SET assignee_id = %s WHERE id = %s", [user, ids["H-2"]])
    assert _numbers(_list(client, ws, f"?assignee={user}")) == ["H-2"]


def test_a_bad_filter_value_is_422(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    for query in (
        "?payment_status=PAID",
        "?due_from=soon",
        "?amount_min=-1",
        "?client_id=nope",
        "?sort=password",
        "?sort=due_date,amount",
        "?limit=0",
        "?cursor=garbage",
        "?currency=ZZZ",
    ):
        assert _list(client, ws, query).status_code == 422, query


def test_a_repeated_parameter_is_refused(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    assert _list(client, ws, "?currency=INR&currency=USD").status_code == 422


def test_paging_visits_every_row_once_in_any_sort(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _seed(client, ws, *[_line(f"S-{n}", total=f"{10 + n % 2}.00") for n in range(7)])
    for sort in ("", "&sort=amount", "&sort=-amount", "&sort=invoice_number", "&sort=-evidence_as_of"):
        seen: list[str] = []
        cursor = ""
        for _ in range(10):
            page = _list(client, ws, f"?limit=3{sort}{cursor}").json()
            seen += [item["invoice_number"] for item in page["items"]]
            if page["next_cursor"] is None:
                break
            cursor = f"&cursor={page['next_cursor']}"
        assert sorted(seen) == sorted(f"S-{n}" for n in range(7)), sort


def test_a_cursor_from_another_sort_is_refused(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _seed(client, ws, _line("C-1"), _line("C-2"))
    cursor = _list(client, ws, "?limit=1&sort=amount").json()["next_cursor"]
    assert _list(client, ws, f"?limit=1&sort=due_date&cursor={cursor}").status_code == 422


# ---------- dashboard ----------


def test_each_tile_and_bucket_count_equals_the_list_it_opens(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(
        client,
        ws,
        _line("T-1", due="2026-07-14"),
        _line("T-2", due="2026-06-10"),
        _line("T-3", due="2026-05-10"),
        _line("T-4", due="2026-03-01"),
        _line("T-5", due="2026-07-20"),
        _line("T-6", due="2026-08-30"),
        _line("T-7", due="2026-07-01"),
        _line("T-8", due="2026-07-01"),
        _line("T-9", due="2026-07-01"),
        _line("T-10", due="2026-07-01"),
        _line("T-11", due="2026-07-01", currency="USD"),
        _line("T-12", due="2026-07-01"),
    )
    _state(owner_db, ws, ids["T-7"], payment_status="PARTIALLY_PAID", paid_minor=2000, outstanding_minor=8000)
    _state(owner_db, ws, ids["T-8"], payment_status="AWAITING_VERIFICATION")
    _state(owner_db, ws, ids["T-9"], dispute_status="OPEN")
    _state(owner_db, ws, ids["T-10"], reminder_status="SNOOZED", snooze_until=date(2026, 7, 30))
    _state(owner_db, ws, ids["T-12"], payment_status="PAID_VERIFIED", paid_minor=10000, outstanding_minor=0)
    body = client.get(f"{API}/workspaces/{ws}/dashboard").json()
    keys = set()
    for block in body["currencies"]:
        keys |= {tile["key"] for tile in block["tiles"]}
        for entry in (*block["tiles"], *block["aging"]):
            listed = _list(client, ws, "?limit=200&" + urlencode(entry["filter"]))
            assert listed.status_code == 200, entry
            items = listed.json()["items"]
            assert len(items) == entry["count"], entry
            assert all(item["currency"] == block["currency"] for item in items)
            assert sum(item["outstanding_minor"] for item in items) == entry["amount_minor"], entry
    assert keys == {
        "outstanding",
        "overdue",
        "due_soon",
        "partially_paid",
        "needs_verification",
        "disputed",
        "snoozed",
    }
    inr = next(block for block in body["currencies"] if block["currency"] == "INR")
    tiles = {tile["key"]: tile["count"] for tile in inr["tiles"]}
    aging = {bucket["bucket"]: bucket["count"] for bucket in inr["aging"]}
    assert tiles["outstanding"] == 10
    assert tiles["due_soon"] == 1
    assert (tiles["partially_paid"], tiles["needs_verification"], tiles["disputed"], tiles["snoozed"]) == (
        1,
        1,
        1,
        1,
    )
    assert list(aging) == ["not_due", "1-30", "31-60", "61-90", "90+"]
    assert aging == {"not_due": 2, "1-30": 5, "31-60": 1, "61-90": 1, "90+": 1}


def test_an_empty_workspace_has_an_empty_dashboard(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    body = client.get(f"{API}/workspaces/{ws}/dashboard").json()
    assert body["currencies"] == []
    assert body["has_sample_data"] is False
    assert body["as_of_date"] == "2026-07-15"


# ---------- invoice state follows the invoice ----------


def test_an_import_creates_state_in_the_same_commit_and_a_reimport_moves_outstanding(
    pg: None, owner_db: Any
) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("I-1", total="100.00"))
    row = _list(client, ws).json()["items"][0]
    assert (row["payment_status"], row["outstanding_minor"], row["paid_minor"]) == ("OUTSTANDING", 10000, 0)
    assert (row["evidence_coverage"], row["evidence_as_of"]) == ("MISSING", None)
    _import(
        client,
        ws,
        (HEADER + _line("I-1", total="120.00")).encode(),
        decisions={"rows": {"2": {"action": "UPDATE"}}},
    )
    row = client.get(f"{API}/workspaces/{ws}/invoices/{ids['I-1']}").json()
    assert (row["facts"]["gross_minor"], row["derived"]["outstanding_minor"]) == (12000, 12000)


def test_every_invoice_has_exactly_one_state_row_protected_by_rls(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    _seed(client, ws, _line("I-1"), _line("I-2"))
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    assert owner_db.execute("SELECT count(*) FROM invoice_state").fetchone()[0] == 2
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [str(uuid.uuid4())])
    assert owner_db.execute("SELECT count(*) FROM invoice_state").fetchone()[0] == 0


# ---------- detail ----------


def test_detail_has_three_separate_layers_and_where_it_came_from(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("Y-1"))
    response = client.get(f"{API}/workspaces/{ws}/invoices/{ids['Y-1']}")
    assert response.status_code == 200
    assert response["ETag"] == '"1"'
    body = response.json()
    assert body["facts"]["invoice_number"] == "Y-1"
    assert "payment_status" not in body["facts"]
    assert "invoice_number" not in body["derived"]
    assert body["derived"]["payment_status"] == "OUTSTANDING"
    assert body["ai_claims"] == []
    assert body["provenance"]["file_name"] == "invoices.csv"
    assert body["provenance"]["source_row"] == 2
    assert body["recommended_action"]["code"] == "VERIFY_PAYMENT"
    assert body["reasons"][0]["code"] == "EVIDENCE_MISSING"


def test_detail_of_a_paid_invoice_explains_why_nothing_is_recommended(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("Y-2"))
    _state(owner_db, ws, ids["Y-2"], payment_status="PAID_VERIFIED", paid_minor=10000, outstanding_minor=0)
    body = client.get(f"{API}/workspaces/{ws}/invoices/{ids['Y-2']}").json()
    assert body["recommended_action"] is None
    assert body["why_not"][0]["code"] == "PAID_VERIFIED"


def test_another_workspace_cannot_read_an_invoice(pg: None, owner_db: Any) -> None:
    first, ws_a = owner_workspace(owner_db, "a@example.test")
    second, ws_b = owner_workspace(owner_db, "b@example.test")
    ids = _seed(first, ws_a, _line("Z-1"))
    assert second.get(f"{API}/workspaces/{ws_b}/invoices/{ids['Z-1']}").status_code == 404


# ---------- correct, cancel, archive ----------


def _patch(client: APIClient, ws: str, invoice_id: str, body: dict[str, Any], version: int = 1) -> Any:
    return client.patch(
        f"{API}/workspaces/{ws}/invoices/{invoice_id}", body, format="json", HTTP_IF_MATCH=f'"{version}"'
    )


def test_a_correction_without_a_reason_is_refused(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("E-1"))
    response = _patch(client, ws, ids["E-1"], {"due_date": "2026-09-01"})
    assert response.status_code == 422
    assert {error["field"] for error in response.json()["errors"]} == {"reason"}
    blank = _patch(client, ws, ids["E-1"], {"due_date": "2026-09-01", "reason": "   "})
    assert blank.status_code == 422


def test_a_correction_versions_audits_and_flags_divergence(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("E-2", total="100.00"))
    response = _patch(client, ws, ids["E-2"], {"gross_minor": 15000, "reason": "Credit note reversed"})
    assert response.status_code == 200, response.content
    assert response["ETag"] == '"2"'
    body = response.json()
    assert body["facts"]["gross_minor"] == 15000
    assert body["facts"]["diverges_from_source"] is True
    assert body["facts"]["corrected_fields"] == ["gross_minor"]
    assert body["derived"]["outstanding_minor"] == 15000
    events = _audit(owner_db, ws, "invoice.corrected")
    assert events[0]["object_id"] == ids["E-2"]
    assert events[0]["before"] == {"gross_minor": 10000}
    assert events[0]["after"]["gross_minor"] == 15000
    assert events[0]["after"]["reason"] == "Credit note reversed"


def test_a_correction_survives_a_reimport(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("E-3", total="100.00"))
    assert _patch(client, ws, ids["E-3"], {"gross_minor": 15000, "reason": "Agreed"}).status_code == 200
    # The corrected total is kept, so a file that only disagrees about it changes nothing.
    _import(client, ws, (HEADER + _line("E-3", total="120.00")).encode())
    # A file that also moves the due date updates that, and still leaves the corrected total alone.
    _import(
        client,
        ws,
        (HEADER + _line("E-3", total="120.00", due="2026-08-01")).encode(),
        decisions={"rows": {"2": {"action": "UPDATE"}}},
    )
    body = client.get(f"{API}/workspaces/{ws}/invoices/{ids['E-3']}").json()
    assert body["facts"]["gross_minor"] == 15000
    assert body["facts"]["due_date"] == "2026-08-01"
    assert body["derived"]["outstanding_minor"] == 15000


def test_a_stale_version_conflicts_and_changes_nothing(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("E-4"))
    response = _patch(client, ws, ids["E-4"], {"due_date": "2026-09-01", "reason": "Agreed"}, version=9)
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT_VERSION"
    assert _audit(owner_db, ws, "invoice.corrected") == []


def test_a_correction_below_what_was_paid_flags_overpayment_and_keeps_paid(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("E-5", total="100.00"))
    _state(owner_db, ws, ids["E-5"], payment_status="PARTIALLY_PAID", paid_minor=6000, outstanding_minor=4000)
    body = _patch(client, ws, ids["E-5"], {"gross_minor": 5000, "reason": "Wrong total"}).json()
    assert body["derived"]["paid_minor"] == 6000
    assert body["derived"]["outstanding_minor"] == 0
    assert body["derived"]["overpayment_flag"] is True


@pytest.mark.parametrize(
    "body",
    [
        {"gross_minor": -1, "reason": "x"},
        {"gross_minor": 1.5, "reason": "x"},
        {"status": "CANCELLED", "reason": "x"},
        {"payment_status": "PAID_VERIFIED", "reason": "x"},
        {"paid_minor": 5, "reason": "x"},
        {"reason": "nothing to change"},
        {"invoice_number": "  ", "reason": "x"},
    ],
)
def test_a_correction_cannot_set_derived_fields_or_bad_values(
    pg: None, owner_db: Any, body: dict[str, Any]
) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("E-6"))
    assert _patch(client, ws, ids["E-6"], body).status_code == 422


def test_a_correction_to_a_cancelled_invoice_is_refused(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("E-7"))
    assert _act(client, ws, ids["E-7"], "cancel").status_code == 200
    response = _patch(client, ws, ids["E-7"], {"due_date": "2026-09-01", "reason": "x"}, version=2)
    assert response.status_code == 409
    assert response.json()["code"] == "STATE_TRANSITION_INVALID"


def _act(
    client: APIClient, ws: str, invoice_id: str, action: str, reason: str = "Client asked", **extra: Any
) -> Any:
    return client.post(
        f"{API}/workspaces/{ws}/invoices/{invoice_id}/{action}",
        {"reason": reason},
        format="json",
        **{**idem(), **extra},
    )


def test_cancel_then_archive_follow_the_lifecycle_and_are_audited(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("V-1"))
    cancelled = _act(client, ws, ids["V-1"], "cancel")
    assert cancelled.status_code == 200, cancelled.content
    assert cancelled.json()["facts"]["status"] == "CANCELLED"
    assert _numbers(_queue(client, ws)) == []
    assert _numbers(_list(client, ws, "?q=V-1")) == ["V-1"]
    assert _act(client, ws, ids["V-1"], "cancel").status_code == 409
    archived = _act(client, ws, ids["V-1"], "archive")
    assert archived.json()["facts"]["status"] == "ARCHIVED"
    assert _act(client, ws, ids["V-1"], "archive").status_code == 409
    assert _act(client, ws, ids["V-1"], "cancel").status_code == 409
    assert [event["after"]["status"] for event in _audit(owner_db, ws, "invoice.cancelled")] == ["CANCELLED"]
    assert [event["after"]["status"] for event in _audit(owner_db, ws, "invoice.archived")] == ["ARCHIVED"]


def test_a_cancel_needs_a_reason_and_is_refused_when_money_was_received(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("V-2"))
    assert _act(client, ws, ids["V-2"], "cancel", reason="").status_code == 422
    _state(owner_db, ws, ids["V-2"], payment_status="PARTIALLY_PAID", paid_minor=100, outstanding_minor=9900)
    response = _act(client, ws, ids["V-2"], "cancel")
    assert response.status_code == 409
    actions = {
        entry["action"]: entry
        for entry in client.get(f"{API}/workspaces/{ws}/invoices/{ids['V-2']}").json()["allowed_actions"]
    }
    assert actions["CANCEL"]["allowed"] is False
    assert "received" in actions["CANCEL"]["reason"]


def test_a_retried_cancel_returns_the_first_result(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("V-3"))
    key = idem()
    first = client.post(
        f"{API}/workspaces/{ws}/invoices/{ids['V-3']}/cancel", {"reason": "x"}, format="json", **key
    )
    again = client.post(
        f"{API}/workspaces/{ws}/invoices/{ids['V-3']}/cancel", {"reason": "x"}, format="json", **key
    )
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    assert len(_audit(owner_db, ws, "invoice.cancelled")) == 1


# ---------- sample data ----------


def test_sample_seed_is_labelled_and_refused_in_production(pg: None, owner_db: Any, settings: Any) -> None:
    from django.core.management import CommandError, call_command

    client, ws = owner_workspace(owner_db, "owner@example.test")
    settings.DJANGO_ENV = "production"
    with pytest.raises(CommandError, match="production"):
        call_command("seed_sample", workspace=ws, invoices=5)
    settings.DJANGO_ENV = "local"
    call_command("seed_sample", workspace=ws, invoices=20)
    body = client.get(f"{API}/workspaces/{ws}/dashboard").json()
    assert body["has_sample_data"] is True
    items = _queue(client, ws, "?limit=200").json()["items"]
    assert items
    assert all(item["sample"] is True and item["reasons"] for item in items)
    owner_db.execute("SELECT set_config('app.workspace_id', %s, false)", [ws])
    emails = [row[0] for row in owner_db.execute("SELECT email FROM client_contacts").fetchall()]
    assert emails and all(str(email).endswith("@example.test") for email in emails)


def test_an_open_invoice_cannot_be_archived_but_a_fully_paid_one_can(pg: None, owner_db: Any) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    ids = _seed(client, ws, _line("V-4"), _line("V-5"))
    refused = _act(client, ws, ids["V-4"], "archive")
    assert refused.status_code == 409
    assert client.get(f"{API}/workspaces/{ws}/invoices/{ids['V-4']}").json()["facts"]["status"] == "ACTIVE"
    _state(owner_db, ws, ids["V-5"], payment_status="PAID_VERIFIED", paid_minor=10000, outstanding_minor=0)
    assert _act(client, ws, ids["V-5"], "archive").json()["facts"]["status"] == "ARCHIVED"
