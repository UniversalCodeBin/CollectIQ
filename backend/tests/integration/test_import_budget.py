"""NFR-02: a 1,000-row file is validated and previewed within 30 seconds."""

import time

from tests.integration.test_import import HEADER, _commit, _prepare, _row
from tests.support import owner_workspace


def _file(rows: int) -> bytes:
    lines = (
        _row(f"INV-{n}", f"Client {n % 50}", total=f"{n + 1}.00", issued="2026-06-01") for n in range(rows)
    )
    return (HEADER + "".join(lines)).encode()


def test_a_thousand_rows_preview_within_the_budget(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    started = time.perf_counter()
    _, preview = _prepare(client, ws, _file(1_000))
    elapsed = time.perf_counter() - started

    assert preview["counts"]["total_rows"] == 1_000
    assert preview["counts"]["new"] == 1_000
    assert elapsed < 30, f"preview took {elapsed:.1f}s"


def test_the_largest_file_commits_in_one_request(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "owner@example.test")
    import_id, _ = _prepare(client, ws, _file(10_000))
    started = time.perf_counter()
    response = _commit(client, ws, import_id)
    elapsed = time.perf_counter() - started

    assert response.status_code == 200, response.content
    assert response.json()["counts"]["created"] == 10_000
    assert elapsed < 120, f"commit took {elapsed:.1f}s"
