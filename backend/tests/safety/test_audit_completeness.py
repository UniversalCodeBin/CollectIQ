"""TS-023 / critical negative 12: every audited write leaves an audit event with its required fields.

The probe in `audit_probe.py` watches every API call in the whole test run. These tests prove the probe
catches a missing event, then check what the run has seen so far.
"""

import uuid

import pytest
from django.test import RequestFactory
from django.urls import resolve

from collectiq.api import registry, urls  # noqa: F401  (importing urls binds the views)
from tests.safety.audit_probe import PROBE, ProbeMiddleware
from tests.support import API, idem, owner_workspace

# Audited mutating endpoints that no test reaches with a 2xx, each with the reason.
NOT_DRIVEN_TO_SUCCESS: dict[str, str] = {
    "E096": "Gmail monitoring is always refused with NOT_AVAILABLE, so it never succeeds.",
}

FULL_RUN_ENDPOINTS = 40  # below this the run was a subset and coverage is not judged


def _response(status: int = 200):
    from django.http import HttpResponse

    return HttpResponse(status=status)


def test_the_probe_catches_an_audited_write_with_no_event() -> None:
    PROBE.violations.clear()
    path = f"{API}/workspaces/{uuid.uuid4()}/automation/pause"
    request = RequestFactory().post(path)
    request.resolver_match = resolve(path)
    ProbeMiddleware(lambda _request: _response())(request)
    assert any("E019" in line and "no audit event" in line for line in PROBE.violations)
    PROBE.violations.clear()


def test_a_failed_call_is_not_expected_to_audit() -> None:
    PROBE.violations.clear()
    path = f"{API}/workspaces/{uuid.uuid4()}/automation/pause"
    request = RequestFactory().post(path)
    request.resolver_match = resolve(path)
    ProbeMiddleware(lambda _request: _response(409))(request)
    assert PROBE.violations == []


def test_pausing_writes_one_event_with_every_required_field(pg, owner_db) -> None:
    client, ws = owner_workspace(owner_db, "audit-probe@example.test")
    PROBE.violations.clear()
    before = sum(len(rows) for rows in PROBE.audits.values())
    assert (
        client.post(f"{API}/workspaces/{ws}/automation/pause", {}, format="json", **idem()).status_code == 200
    )
    assert sum(len(rows) for rows in PROBE.audits.values()) == before + 1
    assert "E019" in PROBE.seen_ok
    assert PROBE.violations == []


def test_every_mutating_audited_endpoint_is_flagged_audited_in_the_registry() -> None:
    quiet = sorted(
        spec.id
        for spec in registry.ENDPOINTS.values()
        if spec.mutates and not spec.audited and spec.id in registry.BOUND
    )
    # E107 only marks a notification read; it changes no money, message or setting.
    assert quiet == ["E107"]


def test_no_audited_write_so_far_lacked_its_event() -> None:
    assert sorted(set(PROBE.violations)) == []


def test_every_audited_endpoint_was_driven_to_success_by_some_test() -> None:
    if len(PROBE.seen_ok) < FULL_RUN_ENDPOINTS:
        pytest.skip("only part of the suite has run; run the whole suite to judge coverage")
    wanted = {
        spec.id
        for spec in registry.ENDPOINTS.values()
        if spec.mutates and spec.audited and spec.id in registry.BOUND
    }
    missing = sorted(wanted - PROBE.seen_ok - set(NOT_DRIVEN_TO_SUCCESS))
    assert missing == []
