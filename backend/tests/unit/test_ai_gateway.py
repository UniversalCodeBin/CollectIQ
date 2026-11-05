"""The AI gateway: what leaves the application, what comes back, and what happens when it cannot run."""

import json

import pytest

from collectiq.ai.gateway import AIConfig, Gateway, build_provider
from collectiq.ai.providers.base import AIConfigurationError, ProviderRequest
from collectiq.ai.providers.fake import FakeProvider
from collectiq.ai.registry import TASKS, TaskSpec, register

GOOD = json.dumps({"label": "PAYMENT_CLAIM", "confidence": "HIGH", "evidence": "I paid"})


@pytest.fixture
def spec():
    task = TaskSpec(
        task_id="test.classify",
        allowed_fields=("body", "due_date", "client_name"),
        pseudonymise=("client_name",),
        max_chars=200,
        output={
            "label": ("PAYMENT_CLAIM", "OTHER"),
            "confidence": ("LOW", "MEDIUM", "HIGH"),
            "evidence": str,
        },
    )
    TASKS[task.task_id] = task
    yield task
    TASKS.pop(task.task_id, None)


def gateway(provider, **cfg):
    return Gateway(provider, AIConfig(**cfg))


def test_non_allowlisted_field_dropped(spec):
    provider = FakeProvider([GOOD])
    result = gateway(provider).run(
        "test.classify", {"body": "I paid", "internal_note": "not-for-the-model", "invoice_id": "x"}
    )
    assert result.status == "OK"
    sent = provider.requests[0].input
    assert "internal_note" not in sent and "invoice_id" not in sent
    assert "not-for-the-model" not in json.dumps(provider.requests[0].__dict__)
    assert result.dropped_fields == ("internal_note", "invoice_id")


def test_email_phone_account_become_tokens(spec):
    provider = FakeProvider([GOOD])
    body = "Mail ap@acme.example.test or call +1 (415) 555-0134, pay to account 123456789012 please"
    result = gateway(provider).run("test.classify", {"body": body, "client_name": "Acme Ltd"})
    sent = provider.requests[0].input
    for raw in ("ap@acme.example.test", "555-0134", "123456789012", "Acme Ltd"):
        assert raw not in json.dumps(sent)
    assert "[EMAIL_1]" in sent["body"] and "[PHONE_1]" in sent["body"] and "[ACCOUNT_1]" in sent["body"]
    assert sent["client_name"] == "[CLIENT_1]"
    assert result.status == "OK"
    assert "ap@acme.example.test" not in json.dumps(result.redacted_input)


def test_same_value_gets_same_token(spec):
    provider = FakeProvider([GOOD])
    gateway(provider).run(
        "test.classify", {"body": "a@x.example.test then a@x.example.test, b@x.example.test"}
    )
    assert provider.requests[0].input["body"] == "[EMAIL_1] then [EMAIL_1], [EMAIL_2]"


def test_length_is_capped(spec):
    provider = FakeProvider([GOOD])
    gateway(provider).run("test.classify", {"body": "x" * 5000})
    assert len(provider.requests[0].input["body"]) <= 200


def test_invalid_json_one_repair_then_fail_safe(spec):
    provider = FakeProvider(["not json", "still {not json"])
    result = gateway(provider).run("test.classify", {"body": "I paid"})
    assert result.status == "INVALID_OUTPUT"
    assert result.data is None
    assert len(provider.requests) == 2 and provider.requests[1].repair is True
    assert result.repaired is True


def test_invalid_json_repaired_once_succeeds(spec):
    provider = FakeProvider(["oops", GOOD])
    result = gateway(provider).run("test.classify", {"body": "I paid"})
    assert result.status == "OK" and result.repaired is True and result.data["label"] == "PAYMENT_CLAIM"


@pytest.mark.parametrize(
    "bad",
    [
        {"label": "MARK_PAID", "confidence": "HIGH", "evidence": "x"},
        {"label": "OTHER", "confidence": "0.97", "evidence": "x"},
        {"label": "OTHER", "confidence": "HIGH"},
        {"label": "OTHER", "confidence": "HIGH", "evidence": "x", "extra": 1},
        ["list"],
    ],
)
def test_schema_violation_is_never_used(spec, bad):
    provider = FakeProvider([json.dumps(bad), json.dumps(bad)])
    result = gateway(provider).run("test.classify", {"body": "I paid"})
    assert result.status == "INVALID_OUTPUT" and result.data is None


def test_kill_switch_short_circuits(spec):
    provider = FakeProvider([GOOD])
    result = gateway(provider, kill_switch=True).run("test.classify", {"body": "I paid"})
    assert result.status == "DISABLED" and provider.requests == []


def test_fake_refused_in_production():
    with pytest.raises(AIConfigurationError):
        build_provider("fake", production=True)
    assert isinstance(build_provider("fake", production=False), FakeProvider)


def test_provider_receives_no_tools(spec):
    provider = FakeProvider([GOOD])
    gateway(provider).run("test.classify", {"body": "I paid"})
    request = provider.requests[0]
    assert isinstance(request, ProviderRequest)
    assert not any("tool" in name or "function" in name for name in request.__dataclass_fields__)


def test_no_provider_returns_not_configured(spec):
    assert build_provider("none", production=False) is None
    result = gateway(None).run("test.classify", {"body": "I paid"})
    assert result.status == "AI_NOT_CONFIGURED" and result.data is None


def test_unknown_provider_name_is_refused():
    with pytest.raises(AIConfigurationError):
        build_provider("mystery", production=False)


def test_unknown_task_is_refused():
    result = gateway(FakeProvider([GOOD])).run("no.such.task", {})
    assert result.status == "UNKNOWN_TASK"


def test_provider_error_retries_are_bounded(spec):
    provider = FakeProvider([TimeoutError("slow"), TimeoutError("slow"), TimeoutError("slow"), GOOD])
    result = gateway(provider, max_retries=1).run("test.classify", {"body": "I paid"})
    assert result.status == "PROVIDER_ERROR" and len(provider.requests) == 2


def test_provider_error_then_success(spec):
    provider = FakeProvider([TimeoutError("slow"), GOOD])
    result = gateway(provider, max_retries=1).run("test.classify", {"body": "I paid"})
    assert result.status == "OK"


def test_rate_limit(spec):
    now = [1000.0]
    gw = Gateway(
        FakeProvider([GOOD] * 4), AIConfig(rate_limit=2, rate_window_seconds=60), clock=lambda: now[0]
    )
    assert gw.run("test.classify", {"body": "a"}, scope="ws1").status == "OK"
    assert gw.run("test.classify", {"body": "a"}, scope="ws1").status == "OK"
    assert gw.run("test.classify", {"body": "a"}, scope="ws1").status == "RATE_LIMITED"
    assert gw.run("test.classify", {"body": "a"}, scope="ws2").status == "OK"
    now[0] += 61
    assert gw.run("test.classify", {"body": "a"}, scope="ws1").status == "OK"


def test_result_carries_the_record_fields(spec):
    provider = FakeProvider([GOOD])
    result = gateway(provider).run("test.classify", {"body": "I paid"})
    assert result.provider == "fake" and result.model_version and len(result.input_sha256) == 64
    assert result.task_id == "test.classify"


def test_registered_tasks_declare_allowlists():
    assert register is not None
    for task in TASKS.values():
        assert task.allowed_fields, task.task_id
