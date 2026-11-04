"""The registry against the TSD's endpoint table, then real requests for every bound endpoint and role."""

import re
import uuid
from pathlib import Path

import psycopg
import pytest
import yaml
from django.urls import resolve
from rest_framework.test import APIClient

from collectiq.api import registry, urls  # noqa: F401  (importing urls binds the views)
from collectiq.tenancy.permissions import allowed_roles
from tests.support import API, add_member, idem, logged_in, make_user, owner_workspace

_ROOT = Path(__file__).resolve().parents[3]
_TSD = _ROOT / "CollectIQ_Technical_Specification_v1.0.md"
_CONTRACT = _ROOT / "CollectIQ_API_Contracts.yaml"
_ROLE_LETTERS = {"O": "OWNER", "F": "FINANCE_ADMIN", "L": "PROJECT_LEAD"}
_MODES = {"Public": "public", "Session": "session", "Self": "self", "Infra": "infra", "Webhook": "webhook"}
_ROLES = ("OWNER", "FINANCE_ADMIN", "PROJECT_LEAD")


def _tsd_rows() -> dict[str, list[str]]:
    rows = {}
    for line in _TSD.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip().strip("`") for cell in line.split("|")]
        if len(cells) > 8 and re.fullmatch(r"E\d{3}", cells[1]):
            rows[cells[1]] = cells
    return rows


def test_tsd_table_is_complete() -> None:
    assert len(_tsd_rows()) == 112


@pytest.mark.parametrize("endpoint_id", sorted(_tsd_rows()))
def test_registry_matches_tsd(endpoint_id: str) -> None:
    _, _, method, path, _, roles, flags, priority, *_ = _tsd_rows()[endpoint_id]
    spec = registry.ENDPOINTS[endpoint_id]
    assert (spec.method, spec.path) == (method, path)
    assert spec.priority == priority.replace(" cond.", "")
    assert spec.audited == ("A" in flags.split(","))
    assert spec.idempotent == ("I" in flags.split(","))
    assert spec.versioned == ("V" in flags.split(","))
    assert spec.mutates == (method != "GET")
    if roles in _MODES:
        assert spec.permission == _MODES[roles]
    else:
        assert allowed_roles(spec.permission) == {_ROLE_LETTERS[letter] for letter in roles.split(",")}


def test_every_registry_endpoint_is_in_the_contract() -> None:
    contract = yaml.safe_load(_CONTRACT.read_text(encoding="utf-8"))
    found = {
        operation["x-endpoint-id"]: (method.upper(), path)
        for path, operations in contract["paths"].items()
        for method, operation in operations.items()
        if method != "parameters"
    }
    assert {key: (spec.method, spec.path) for key, spec in registry.ENDPOINTS.items()} == found


def _url(path: str, workspace_id: str) -> str:
    return API + re.sub(
        r"\{\w+\}", lambda m: workspace_id if m.group() == "{ws}" else str(uuid.uuid4()), path
    )


def _call(client: APIClient, spec: registry.EndpointSpec, workspace_id: str):
    headers = {"HTTP_IF_MATCH": '"1"', **idem()}
    url = _url(spec.path, workspace_id)
    if spec.method == "GET":
        return client.get(url, **headers)
    return getattr(client, spec.method.lower())(url, {}, format="json", **headers)


def test_every_route_is_bound_to_its_registry_entry() -> None:
    assert registry.BOUND, "no view is bound yet"
    for endpoint_id, spec in registry.ENDPOINTS.items():
        if endpoint_id in registry.BOUND:
            match = resolve(_url(spec.path, str(uuid.uuid4())))
            handler = getattr(match.func.view_class, spec.method.lower())
            assert handler.endpoint_id == endpoint_id


def test_authz_matrix_every_endpoint_every_role(pg, owner_db: psycopg.Connection) -> None:
    owner, workspace_id = owner_workspace(owner_db, "owner@example.test")
    clients = {
        "OWNER": owner,
        "FINANCE_ADMIN": add_member(owner_db, workspace_id, "finance@example.test", "FINANCE_ADMIN")[0],
        "PROJECT_LEAD": add_member(owner_db, workspace_id, "lead@example.test", "PROJECT_LEAD")[0],
    }
    make_user(owner_db, "outsider@example.test")
    outsider = logged_in("outsider@example.test")
    wrong: list[tuple] = []

    def expect(endpoint_id: str, who: str, ok: bool, status: int) -> None:
        if not ok:
            wrong.append((endpoint_id, who, status))

    for endpoint_id in sorted(registry.BOUND):
        spec = registry.ENDPOINTS[endpoint_id]
        if spec.permission in ("public", "infra", "webhook"):
            status = _call(APIClient(), spec, workspace_id).status_code
            expect(endpoint_id, "anonymous", status not in (401, 403), status)
            continue
        status = _call(APIClient(), spec, workspace_id).status_code
        expect(endpoint_id, "anonymous", status == 401, status)
        if "{ws}" not in spec.path:
            continue
        status = _call(outsider, spec, workspace_id).status_code
        expect(endpoint_id, "outsider", status == 404, status)
        allowed = set(_ROLES) if spec.permission == "self" else allowed_roles(spec.permission)
        for role in _ROLES:
            status = _call(clients[role], spec, workspace_id).status_code
            expect(endpoint_id, role, (status != 403) if role in allowed else (status == 403), status)
    assert wrong == []
