"""The agent loop: tools, permissions, proposals, budgets, provider failure and untrusted data."""

import json
from dataclasses import replace

from collectiq.ai.agents import AgentRunner, AgentSpec, Tool
from collectiq.ai.gateway import AIConfig
from collectiq.ai.providers.base import FailoverProvider
from collectiq.ai.providers.fake import FakeProvider

CALLS: list[dict] = []


def lookup(args: dict) -> dict:
    CALLS.append(args)
    note = "never leaves"
    return {
        "status": "OPEN",
        "contact": "ap@acme.example.test",
        "secret_note": note,  # pragma: allowlist secret
    }

READ = Tool("lookup", "Read invoice facts", {"invoice": str}, lookup, "invoices:read", ("status", "contact"))
SEND = Tool("send", "Draft a send", {"body": str}, lookup, "messages:write", ("status",), effect="PROPOSE")
SPEC = AgentSpec(
    agent_id="test",
    instructions="Summarise.",
    tools=(READ, SEND),
    final={"summary": str},
    max_steps=4,
    max_tool_calls=3,
    max_context_chars=400,
)
FINAL = json.dumps({"final": {"summary": "ok"}})
USE = json.dumps({"tool": "lookup", "args": {"invoice": "INV-1"}})
ALLOWED = {"invoices:read", "messages:write"}


def runner(script, **cfg):
    provider = FakeProvider(script)
    return AgentRunner(provider, AIConfig(**cfg)), provider


def setup_function() -> None:
    CALLS.clear()


def test_tool_then_final_completes_and_minimises_results() -> None:
    agent, provider = runner([USE, FINAL])
    result = agent.run(SPEC, {"note": "mail ap@acme.example.test"}, permissions=ALLOWED)
    assert result.status == "COMPLETED" and result.final == {"summary": "ok"}
    assert CALLS == [{"invoice": "INV-1"}]
    second = json.dumps(provider.requests[1].input)
    assert "secret_note" not in second and "ap@acme.example.test" not in second
    assert "untrusted_data" in second and "[EMAIL_" in second
    assert "ap@acme.example.test" not in json.dumps(provider.requests[0].input)


def test_missing_permission_denies_without_running() -> None:
    agent, _ = runner([USE, FINAL])
    result = agent.run(SPEC, {}, permissions=set())
    assert CALLS == [] and result.trace[0]["event"] == "denied"
    assert result.status == "COMPLETED"


def test_propose_tool_is_recorded_never_executed() -> None:
    send = json.dumps({"tool": "send", "args": {"body": "Hi"}})
    agent, _ = runner([send, FINAL])
    result = agent.run(SPEC, {}, permissions=ALLOWED)
    assert CALLS == [] and result.status == "AWAITING_APPROVAL"
    assert result.proposals == [{"tool": "send", "args": {"body": "Hi"}}]


def test_unknown_tool_and_bad_args_are_not_run() -> None:
    bad = [
        json.dumps({"tool": "drop_tables", "args": {}}),
        json.dumps({"tool": "lookup", "args": {"invoice": 5}}),
        json.dumps({"tool": "lookup", "args": {"invoice": "x", "extra": 1}}),
    ]
    agent, _ = runner([*bad, FINAL])
    result = agent.run(SPEC, {}, permissions=ALLOWED)
    assert CALLS == [] and [t["event"] for t in result.trace[:3]] == ["invalid_call"] * 3


def test_tool_call_budget_ends_the_run() -> None:
    agent, _ = runner([USE] * 6)
    result = agent.run(SPEC, {}, permissions=ALLOWED)
    assert result.status == "BUDGET_EXCEEDED" and len(CALLS) == 3


def test_step_budget_ends_a_run_that_never_finishes() -> None:
    agent, _ = runner(["not json"] * 8)
    result = agent.run(SPEC, {}, permissions=ALLOWED)
    assert result.status == "INVALID_OUTPUT"


def test_one_repair_then_success() -> None:
    agent, provider = runner(["oops", FINAL])
    result = agent.run(SPEC, {}, permissions=ALLOWED)
    assert result.status == "COMPLETED" and provider.requests[1].repair is True


def test_bad_final_shape_fails_safe() -> None:
    agent, _ = runner([json.dumps({"final": {"summary": "x", "paid": True}})])
    assert agent.run(SPEC, {}, permissions=ALLOWED).status == "INVALID_OUTPUT"


def test_context_budget_drops_oldest_results() -> None:
    agent, provider = runner([USE, USE, USE, FINAL])
    agent.run(replace(SPEC, max_context_chars=150), {}, permissions=ALLOWED)
    assert len(provider.requests[3].input["observations"]) == 1


def test_provider_failure_is_a_status_not_an_exception() -> None:
    agent, _ = runner([TimeoutError("down")])
    assert agent.run(SPEC, {}, permissions=ALLOWED).status == "PROVIDER_ERROR"


def test_failover_uses_the_next_provider() -> None:
    primary, backup = FakeProvider([TimeoutError("down")]), FakeProvider([FINAL])
    agent = AgentRunner(FailoverProvider([primary, backup]))
    result = agent.run(SPEC, {}, permissions=ALLOWED)
    assert result.status == "COMPLETED" and len(backup.requests) == 1


def test_kill_switch_and_unconfigured() -> None:
    assert runner([FINAL], kill_switch=True)[0].run(SPEC, {}, permissions=ALLOWED).status == "DISABLED"
    assert AgentRunner(None).run(SPEC, {}, permissions=ALLOWED).status == "AI_NOT_CONFIGURED"


def test_a_tool_that_raises_is_an_observation() -> None:
    boom = Tool("lookup", "x", {"invoice": str}, lambda a: 1 / 0, "invoices:read", ("status",))
    spec = AgentSpec("t", "x", (boom,), {"summary": str})
    agent, _ = runner([USE, FINAL])
    result = agent.run(spec, {}, permissions=ALLOWED)
    assert result.status == "COMPLETED" and result.trace[0]["event"] == "tool_error"
