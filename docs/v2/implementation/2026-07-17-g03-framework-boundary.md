# G0.3 Framework Boundary Record

Date: 2026-07-17 Asia/Shanghai
Phase: G0.3
Status: convergence complete for the canonical local source boundary

## Canonical Runtime

The only Agent Server graph registered by `backend/langgraph.json` is:

```text
langgraph.json
  -> crypto_alert_v2.graph.graph:graph_factory
  -> StateGraph(AnalysisState, context_schema=AnalysisRuntime)
  -> Product Worker / AgentServerRunner
  -> Product projection and PostgreSQL
```

The module-level `graph` export is retained for contract and direct graph tests. It is
not a second Agent Server registration. `graph_factory` is the deployment boundary and
builds the compiled graph for each official Agent Server run.

## Official Agent Ownership

| Responsibility | Canonical module | Official capability | Project-owned boundary |
| --- | --- | --- | --- |
| Market decision | `agents/market_analysis.py` | LangChain `create_agent` and `ToolStrategy(MarketAnalysis)` | prompt policy, model adapter and transient retry policy |
| Cited research interpretation | `agents/research.py` | LangChain `create_agent` and `ToolStrategy(ResearchBundle)` | evidence-only prompt, URL allowlist and citation consistency |
| Graph orchestration | `graph/graph.py` | LangGraph `StateGraph`, `interrupt`, compiled graph | domain gates, Product terminal state and HITL routing |
| Provider I/O | `providers/okx.py`, `providers/search.py` | typed LangChain tool boundary where applicable | exchange DTO validation, evidence normalization and retry budget |
| Product durability | `commands/dispatcher.py`, `persistence/` | official Agent Server SDK at the remote boundary | task/run ownership, transaction projection and idempotency |
| Frontend progress | `OfficialRunStream` | `@langchain/react` stream | Product Task remains final business authority |

Only the two agent factory modules may call `create_agent` in the canonical runtime.
Canonical analysis never parses model text as JSON; structured responses are read from
the official `structured_response` field and then validated by domain models.

## Removed Legacy Path

`backend/src/crypto_alert_v2/graph/nodes/` contained an older hand-written JSON-agent
implementation. It was not imported by the canonical graph or registered in
`langgraph.json`, and it has now been deleted. The framework boundary contract fails if
the directory, a production import of it, a second `create_agent` location, or free-text
model JSON parsing is reintroduced.

The inactive `deepagents` dependency and its unused transitive dependencies were removed
from `pyproject.toml`, `uv.lock`, and the synchronized environment. This closes the local
G0.3 source and dependency convergence gate. It is not a production-release claim:
hosted Agent Server durability, external observability delivery and the remaining M1-M6
gates are separate requirements.

## Retry and State Ownership

- Provider retries belong to the provider retry policy.
- Model retries belong to the agent factory retry wrapper.
- Product command retries belong to the durable dispatcher and create immutable Runs.
- PostgreSQL transaction retries belong to the persistence transaction policy.
- Product Task/Run is the durable business authority; Agent Server Thread/Run is execution
  authority; frontend stream values are transient progress only.

No new fallback, second graph registration or second structured-output parser may be
introduced without updating this record, ADR 0009 and the framework contract test.

## Research Harness Decision

Decision: use the official LangChain `create_agent` Research Harness as the single
active research harness for this release. This is the formal Deep Agents fallback
allowed by the normative plan; it is not a custom Agent Runtime.

The current research job has one bounded responsibility: call the configured read-only
Web Search provider, pass the returned citations to a structured extraction agent, and
reject findings that cite a URL outside the returned evidence. It has no need for
planning, filesystem state, shell execution, subagent delegation, memory files or a
long-running task graph.

The locked Deep Agents package was inspected at `0.6.12`. Its official
`create_deep_agent` default harness includes todo, filesystem, execute and task tools.
`HarnessProfile` can exclude these tools, but activating that pre-1.0 harness would add
another permission and middleware surface without a product requirement. The release
therefore keeps exactly one research harness active: `create_agent` with
`ToolStrategy(ResearchBundle)`, provider-owned read-only search, redaction middleware,
and bounded model retry. Risk policy, Product persistence and notifications remain
outside the agent.

This decision forbids a dual runtime. ADR 0009 records the accepted fallback. A future Deep Agents experiment must first prove a
restricted effective tool list, disabled general-purpose subagent, deny-all filesystem
backend and a migration plan; it cannot be enabled by merely importing
`create_deep_agent`. The inactive `deepagents` release dependency and the orphan
`graph/nodes` manual JSON runtime were removed together with static regression guards.

## Verification And Compatibility Boundary

- Canonical framework/dependency guards: `9 passed`.
- Full backend suite after convergence: `616 passed, 128 skipped, 1 warning`.
- Frontend unit suite: `278 passed`; frontend typecheck passed.
- Authenticated Agent Server probe: 401/403/200 resource authorization passed and the
  `crypto_analysis` assistant was registered.

The 128 skipped backend tests remain unproved external/real scopes. The warning is the
known Starlette/httpx TestClient deprecation. In the locked official compatibility group
(`langgraph-api==0.11.0`, `langgraph==1.2.9`), both Assistant graph introspection variants
return HTTP 500 for this Runtime-context graph because official code accesses a missing
`_ReadRuntime.override` attribute. The resource-auth probe therefore verifies assistant
registration and authorization but does not claim remote graph-introspection success.
Compiled top-level topology remains enforced by local graph contracts. This upstream
compatibility defect is recorded as open; it was not hidden or presented as fixed.
