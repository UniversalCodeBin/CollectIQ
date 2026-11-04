"""Database-free adapters and formatters: log scrubbing, local storage, problem+json mapping."""
import io
import json
import logging
import uuid
from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import PermissionDenied, RequestDataTooBig
from django.http import Http404
from rest_framework import exceptions

from collectiq.platform.context import RequestContext
from collectiq.platform.errors import ProblemError
from collectiq.platform.logging import ScrubbingJsonFormatter, bind_correlation_id
from collectiq.platform.problem import problem_exception_handler
from collectiq.platform.storage import LocalFileStorage, StorageKeyError, storage_key

_EMAIL = "asha@example.test"
_TOKEN = "tok" + "9f8e7d6c" * 5


def _ctx(workspace_id: uuid.UUID | None = None) -> RequestContext:
    return RequestContext(
        workspace_id=workspace_id or uuid.uuid4(),
        user_id=None,
        role=None,
        correlation_id="corr-1",
        actor_type="SYSTEM",
    )


def _emit(log) -> dict:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ScrubbingJsonFormatter())
    logger = logging.Logger("scrub-test")
    logger.addHandler(handler)
    log(logger)
    return json.loads(stream.getvalue())


def test_log_scrubber_removes_email_token_amount() -> None:
    entry = _emit(
        lambda log: log.info(
            "reminder for %s, Bearer %s, token=%s, owed INR 1,200.50", _EMAIL, _TOKEN, _TOKEN
        )
    )
    assert "reminder for" in entry["message"]
    for leaked in (_EMAIL, _TOKEN, "1,200.50"):
        assert leaked not in json.dumps(entry)


@pytest.mark.parametrize(
    "amount",
    [
        "₹1,200.50",
        "$12.50",
        "€ 99",
        "INR 1200",
        "1200 USD",
        "amount_minor=120050",
        '"amount": 1200',
        "paid 1,20,000",
        "paid 4500.75",
    ],
)
def test_log_scrubber_removes_amount_forms(amount: str) -> None:
    entry = _emit(lambda log: log.info("settled %s today", amount))
    digits = "".join(character for character in amount if character.isdigit())
    assert digits not in "".join(character for character in entry["message"] if character.isdigit())
    assert entry["message"].startswith("settled")


def test_log_scrubber_keeps_ids_and_durations() -> None:
    identifier = str(uuid.uuid4())
    entry = _emit(lambda log: log.info("job %s took 0.25s, attempt 3", identifier))
    assert entry["message"] == f"job {identifier} took 0.25s, attempt 3"


def test_log_scrubber_covers_extra_fields() -> None:
    entry = _emit(
        lambda log: log.info(
            "sent",
            extra={
                "customer_email": _EMAIL,
                "amount_minor": 1200,
                "invoice_id": "inv-1",
                "note": f"contact {_EMAIL}",
                "detail": {"api_token": _TOKEN, "attempt": 2},
            },
        )
    )
    assert "customer_email" not in entry
    assert "amount_minor" not in entry
    assert entry["invoice_id"] == "inv-1"
    assert entry["detail"] == {"attempt": 2}
    assert _EMAIL not in json.dumps(entry)


def test_log_scrubber_covers_exception_text() -> None:
    def log(logger: logging.Logger) -> None:
        try:
            raise ValueError(f"bad address {_EMAIL}")
        except ValueError:
            logger.exception("import failed")

    entry = _emit(log)
    assert "ValueError" in entry["exception"]
    assert _EMAIL not in json.dumps(entry)


def test_log_entries_carry_the_bound_correlation_id() -> None:
    with bind_correlation_id("corr-42"):
        entry = _emit(lambda log: log.info("inside"))
    assert entry["correlation_id"] == "corr-42"
    assert _emit(lambda log: log.info("outside")).get("correlation_id") is None


def test_every_configured_log_route_goes_through_the_scrubber() -> None:
    config = settings.LOGGING
    formatter = config["formatters"][config["handlers"]["console"]["formatter"]]
    assert formatter["()"].endswith("ScrubbingJsonFormatter")
    assert set(config["handlers"]) == {"console"}
    assert config["root"]["handlers"] == ["console"]
    for name in ("django", "django.server"):  # Django's defaults attach their own handlers to these
        assert config["loggers"][name] == {"handlers": ["console"], "level": "INFO", "propagate": False}


def test_storage_rejects_other_workspace_key(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    mine, other = _ctx(), _ctx()
    key = storage_key(other, "imports", "a.csv")
    storage.put(other, key, b"theirs")
    for operation in (
        lambda: storage.get(mine, key),
        lambda: storage.put(mine, key, b"mine"),
        lambda: storage.delete(mine, key),
    ):
        with pytest.raises(StorageKeyError):
            operation()
    assert storage.get(other, key) == b"theirs"


def test_storage_round_trip_and_delete(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    ctx = _ctx()
    key = storage_key(ctx, "imports", "a.csv")
    assert key == f"ws/{ctx.workspace_id}/imports/a.csv"
    storage.put(ctx, key, b"first")
    storage.put(ctx, key, b"second")
    assert storage.get(ctx, key) == b"second"
    storage.delete(ctx, key)
    storage.delete(ctx, key)  # deleting twice is not an error: deletion jobs retry
    with pytest.raises(FileNotFoundError):
        storage.get(ctx, key)
    assert [path.name for path in tmp_path.rglob("*") if path.is_file()] == []


@pytest.mark.parametrize(
    "suffix",
    ["../other/a.csv", "a/../../other/a.csv", "./a.csv", "a//b.csv", "a\\b.csv", "a\x00.csv", "", "a/"],
)
def test_storage_rejects_malformed_keys(tmp_path: Path, suffix: str) -> None:
    ctx = _ctx()
    with pytest.raises(StorageKeyError):
        LocalFileStorage(tmp_path).put(ctx, f"ws/{ctx.workspace_id}/{suffix}", b"x")


def test_storage_refuses_a_symlink_out_of_the_root(tmp_path: Path) -> None:
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    ctx = _ctx()
    (root / "ws").mkdir()
    (root / "ws" / str(ctx.workspace_id)).symlink_to(outside)
    with pytest.raises(StorageKeyError):
        LocalFileStorage(root).put(ctx, storage_key(ctx, "a.csv"), b"x")
    assert list(outside.iterdir()) == []


def _handled(exc: Exception):
    return problem_exception_handler(exc, {"request": None})


def test_problem_error_renders_the_documented_fields() -> None:
    error = ProblemError("POLICY_BLOCKED", 409, "Status changed.", {"gate_results": [{"gate": "G7"}]})
    with bind_correlation_id("corr-9"):
        response = _handled(error)
    assert response.status_code == 409
    assert response.content_type == "application/problem+json"
    assert response.data == {
        "type": "/problems/policy-blocked",
        "title": "Policy blocked",
        "status": 409,
        "code": "POLICY_BLOCKED",
        "detail": "Status changed.",
        "correlation_id": "corr-9",
        "gate_results": [{"gate": "G7"}],
    }


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (exceptions.NotAuthenticated(), 401, "AUTH_REQUIRED"),
        (exceptions.AuthenticationFailed(), 401, "AUTH_REQUIRED"),
        (exceptions.PermissionDenied(), 403, "FORBIDDEN"),
        (exceptions.NotFound(), 404, "NOT_FOUND"),
        (exceptions.ParseError(), 422, "VALIDATION_FAILED"),
        (exceptions.UnsupportedMediaType("text/plain"), 415, "UNSUPPORTED_MEDIA_TYPE"),
        (exceptions.Throttled(), 429, "RATE_LIMITED"),
        (exceptions.MethodNotAllowed("PUT"), 405, "METHOD_NOT_ALLOWED"),
        (Http404(), 404, "NOT_FOUND"),
        (PermissionDenied(), 403, "FORBIDDEN"),
        (RequestDataTooBig(), 413, "PAYLOAD_TOO_LARGE"),
    ],
)
def test_drf_exceptions_map_to_the_code_catalogue(exc: Exception, status: int, code: str) -> None:
    response = _handled(exc)
    assert (response.status_code, response.data["code"]) == (status, code)
    assert response.content_type == "application/problem+json"


def test_throttled_keeps_its_retry_after_header() -> None:
    assert _handled(exceptions.Throttled(wait=30))["Retry-After"] == "30"


def test_auth_failure_stays_401_when_drf_downgraded_it() -> None:
    exc = exceptions.NotAuthenticated()
    exc.status_code = 403  # DRF does this when no authenticator offers a WWW-Authenticate header
    response = _handled(exc)
    assert (response.status_code, response.data["code"]) == (401, "AUTH_REQUIRED")


def test_validation_errors_list_fields() -> None:
    response = _handled(exceptions.ValidationError({"name": ["Required."]}))
    assert response.status_code == 422
    assert response.data["code"] == "VALIDATION_FAILED"
    assert response.data["errors"] == [{"field": "name", "message": "Required."}]


def test_unexpected_exception_is_a_500_without_its_message() -> None:
    response = _handled(RuntimeError(f"row for {_EMAIL}"))
    assert (response.status_code, response.data["code"]) == (500, "INTERNAL_ERROR")
    assert _EMAIL not in json.dumps(response.data)
    assert response.data["correlation_id"]


def test_settings_use_the_problem_handler() -> None:
    assert settings.REST_FRAMEWORK["EXCEPTION_HANDLER"].endswith("problem_exception_handler")
