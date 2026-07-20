# Custom Events, Deep Research Foundation, And Product Truth

> authority_class: informative
>
> Date: 2026-07-19 (Asia/Shanghai)
>
> Verdict: local implementation slice GREEN; hosted/licensed acceptance UNPROVED

## Scope

This slice resumed the complete M1-M6 goal without waiting on the missing licensed
Agent Server credential. Three independent audits separated external gates from local
implementation gaps and selected the canonical custom-event path as the next P1
mainline change. Two user-visible P1 defects were repaired in parallel. Task 13 also
received its first bounded framework foundation, but no Deep Research product flow was
claimed.

The global verdict remains:

```text
V2: PARTIAL
Production Ready: NO
Task 8: RED / PARTIAL
```

## Official Framework Decisions

The current official LangChain documentation and stable package metadata were checked
before implementation:

- Deep Agents is an official harness built on LangChain `create_agent` and LangGraph.
- Stable Python release is `deepagents==0.6.12`.
- Supported restrictions use `HarnessProfile.excluded_tools`,
  `GeneralPurposeSubagentProfile(enabled=False)`, explicit subagents,
  `FilesystemPermission`, and `StateBackend`.
- LangGraph custom data is emitted with `get_stream_writer()` and consumed through
  `stream_mode="custom"` or a v3 `CustomTransformer`.
- `@langchain/react` exposes named custom streams through `useChannel`/
  `custom:<name>`; a private EventSource or parser is unnecessary.

ADR 0010 records why Task 13 now satisfies ADR 0009's Deep Agents reintroduction
trigger. Market analysis keeps its existing lightweight Research path. Task 13 can use
one restricted Deep Agents selector, with an explicit LangChain fallback; the two
harnesses cannot be active in one factory call or deployment mode.

## RED Evidence

The Task 13 harness RED executed six test bodies. It failed only on named capability
gaps: no locked runtime dependency, no restricted factory module, and no typed report
contract. There was no zero-test, skip, network, or collection-only success.

```text
uv run --project backend pytest -q \
  backend/tests/contract/test_research_harness.py \
  backend/tests/contract/test_research_harness_fallback.py

6 failed
```

The canonical custom-event RED likewise executed three test bodies and failed on the
missing versioned event module:

```text
uv run --project backend pytest -q \
  backend/tests/contract/test_event_stream_contract.py

3 failed
```

The two frontend workers separately recorded RED for the waiting-human navigation and
Home source disclosure before their focused GREEN runs.

## Implementation

### Canonical Event Stream

`graph/events.py` defines a strict discriminated union for:

```text
task_progress
artifact
evidence
usage
notification
quality
```

Every event carries schema version, stable SHA-256 event ID, sequence, correlation ID,
Task ID, Product Run ID, official Thread ID, and request ID. Payloads contain only
bounded phase/status/count/usage fields. Query text, provider payloads, raw Artifact
content, credentials, Authorization values, and arbitrary event names are rejected or
never selected.

The existing canonical StateGraph calls LangGraph's official `get_stream_writer()`.
There is no second Graph, custom SSE framing, custom reconnect loop, or token/event
database. Review edit loops use iteration-aware event sequences. Agent Server
submit/fork/resume Runs request `updates+custom`; Product worker join remains
`updates`-only so `domain_events` continues to own durable business projection.

The frontend keeps one root `useStream` and adds one official `useChannel` subscription
covering the six named channels. Strict Zod parsing, Product Run filtering, stable event
ID deduplication, bounded replay, and human-readable projections prevent raw event
rendering. Durable Product stage history remains authoritative after refresh.

### Restricted Deep Research Foundation

`research_harness_selection.py` uses the official stable Deep Agents package. The main
Agent has no Product tool. Its only synchronous subagent is
`verified-source-researcher`, which receives one injected read-only verified Search
Tool. Default general-purpose delegation is disabled; filesystem and execution tools
are hidden; read/write permission is deny-all; backend is thread-scoped `StateBackend`.
Both Deep Agents and fallback paths use `ToolStrategy`, secret/PII middleware, model
call limits, and typed citation indexes. Model output has no URL or raw provider-payload
field.

This is only a factory foundation. It is not wired into Graph input, Product task type,
background continuation, subagent stream, nested HITL, persistence, or UI.

### Product Truth Repairs

- A `waiting_human` Run Detail CTA now links to the current Task without a historical
  `run` query parameter, so Work does not disable the review controls. Other statuses
  retain exact Task+Run historical navigation.
- Home now distinguishes `exchange_native`, `web_search_verified`, and
  `controlled_dependency`, preserves fetched time, and displays explicit fallback
  warnings. It no longer describes all snapshots as real exchange-native market data.

## GREEN Evidence

```text
Backend full:       935 passed, 174 skipped, 1 warning
Root tests:         exit 0
Focused framework:  57 passed
Event stream:       4 passed
Frontend unit:      32 files / 390 tests passed
Frontend typecheck: passed
Frontend lint:      passed
Frontend build:     passed
Ruff check/format:  passed
git diff --check:   passed
```

The event contract exercises both in-process `stream_mode="custom"` and
`astream_events(version="v3")` with official `CustomTransformer`/
`UpdatesTransformer`. The v3 API is marked experimental by the locked LangGraph
version; the warning is asserted rather than hidden.

All 174 backend skips remain unproved. They include live merged Protocol, licensed
restart/durability, real PostgreSQL when not explicitly enabled, and real provider/model
gates. The existing no-reload Agent/Worker processes predate these changes, so no live
browser claim is made for custom channels or the two UI repairs.

## Open Work

1. Run the custom-channel chain on current-source Agent Server and prove replay/
   reconnect on Desktop and Pixel 7; licensed restart remains a separate gate.
2. Integrate the selected Task 13 harness into one canonical Graph branch and Product
   background Task before building its UI.
3. Add canonical nested provider review, not another fixture Graph.
4. Complete real notification receipts, hosted OIDC/HTTPS multi-user states,
   LangSmith/Langfuse hosted trace correlation, production recovery/SLO/security, and
   release evidence.
5. The approved built-in Web Search capability remains RED on the current endpoint;
   local DDGS/proxy proof does not replace it.

No code was staged, committed, or pushed.

## Follow-up Correction: Run Detail Authority

The first waiting-human CTA repair was incomplete. A real resolved source Run exposed
`run.status=waiting_human` together with a historical Task projection and no active
pause, which strict frontend parsing correctly rejected. The follow-up does not weaken
that current-Task invariant. Run Detail now returns current `task`, selected
`run_projection` and `is_current_run`; the UI uses current authority for actions and
the selected projection for historical evidence/report rendering.

Fresh follow-up evidence is recorded in
`2026-07-19-run-detail-current-history-authority.md`. Backend is now `936 passed, 174
skipped`, frontend is `397 passed`, Run Detail fixture Playwright is `6 passed`, the
focused real PostgreSQL lifecycle is `1 passed`, and a separate current-source local
BFF/browser path proved the persisted old Run and latest full report. This remains
local evidence; custom-channel live replay and production gates remain open.
