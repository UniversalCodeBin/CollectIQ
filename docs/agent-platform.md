# Agent platform: what exists and what does not

Classification of the AI layer (`backend/collectiq/ai/`). "Verified" means a test in this repository exercises it.

| Capability | Status | Evidence / note |
|---|---|---|
| Provider-independent gateway, kill switch, rate limit, JSON shape validation with one repair | Implemented and verified | `tests/unit/test_ai_gateway.py` |
| Bounded agent loop: step, tool-call and context budgets; unknown tools and bad arguments not run | Implemented and verified | `tests/unit/test_ai_agents.py` |
| Read-only tools run; PROPOSE tools are recorded, never executed | Implemented and verified | same file |
| Per-tool permission check against the caller's permissions | Implemented and verified | same file |
| Tenant isolation: the ai package has no database handle; tools come from the domain layer inside the caller's context | Implemented and verified | import-linter contract; RLS tests |
| Tool results minimised, redacted, truncated, wrapped as untrusted data | Implemented and verified | agents tests; `tests/safety/test_injection_corpus.py` |
| Final answers are AI-derived and never shown as verified; no AI path marks paid, allocates or sends | Implemented and verified | safety and financial-integrity tests; `make check` gates |
| Eval gate: nothing acts on an AI reading without a person until a non-synthetic eval passes | Implemented and verified (gate); the real evaluation is **not run** | `eval_gate.py`; needs a live model and real data |
| Failover across providers | Implemented and verified with fake providers | agents tests |
| Real model provider adapter (Gemini, Anthropic, other) | **Blocked on OD-05** (provider terms, key, data-handling) | `build_provider` accepts `none` and `fake` only; `fake` is refused in production |
| Provider routing by task or cost, usage metering and budgets per workspace | Not implemented | no real provider to meter; design after OD-05 |
| Long-term agent memory | Deliberately not implemented | each run sees only its minimised inputs |
| Code or shell sandbox for agents | Deliberately not implemented | tools are typed Python callables, no execution surface |
| Live-model evaluation and prompt-injection testing against a real model | Not run | the corpus runs against the fake provider; a live run needs OD-05 |

Task 32 (live AI features that depend on a provider) stays deferred under OD-05.
