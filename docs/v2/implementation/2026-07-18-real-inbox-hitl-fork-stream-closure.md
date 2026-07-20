# Real Inbox, HITL, Fork and Official Stream Closure

> Provenance correction: this historical run used DDGS `backend="auto"`
> metasearch, not a guaranteed DuckDuckGo backend. Provider-identity claims in
> this note are superseded by
> `2026-07-18-readiness-provider-integrity-and-real-regression.md`; URLs,
> citations, timings and the recorded execution sequence remain valid.

Date: 2026-07-18 (Asia/Shanghai)

Scope: local real Product chain regression for Inbox, HITL, historical fork and
official `@langchain/react` stream behavior.

Verdict: `GREEN` for the named local slices only. V2 remains `PARTIAL` and
`Production Ready: NO`.

## Runtime Boundary

The evidence used the current-source local topology:

- Next.js frontend on Node 22.
- Product API, unified Product worker and PostgreSQL.
- Official `langgraph dev --no-reload` using `langgraph-api 0.11.1` and the
  in-memory development Runtime.
- The canonical `graph_factory` and official LangChain `create_agent`,
  `ToolStrategy`, LangGraph HITL and Agent Server protocols.
- Real OKX, explicit local DuckDuckGo and the configured model endpoint for the
  official-stream profile.

The HITL and Fork profiles used independent persisted waiting-human Tasks. No
browser Product route was intercepted. The test fixtures are local acceptance
inputs, not proof of licensed checkpoint durability or hosted production.

## Retained RED Evidence

### Inbox

1. The long-page quality scan scrolled to the absolute bottom and then attempted
   to interact with a review entry that was no longer actionable.
2. Selecting by symbol could bind the wrong card when multiple Tasks shared that
   symbol.

The corrected profile restores the intended review entry to the actionable
viewport and binds it by the exact `/work?task=<id>` Product link.

### HITL

1. The countdown rendered `1:48:21` while the Product contract required the
   stable `01:48:21` form.
2. Assertions still looked for obsolete English `Evidence` and `Risk` headings
   after the UI had adopted `证据门禁` and `风险门禁`.

The implementation and profile now agree on stable `HH:MM:SS` rendering and the
current Product labels without weakening any review assertion.

### Fork

1. Node 22 produced legitimate Desktop and Pixel 7 baseline differences. The
   baselines were regenerated and visually inspected before acceptance.
2. Checkpoint GET failed while copying a compiled Graph because a private
   `_ReadRuntime` object, including its `override` member, entered the Graph's
   default config. The same class of failure remained on both the earlier and
   upgraded local Runtime versions; dependency upgrade alone was not a fix.
3. A first allowlist still merged Agent Server ambient child config, so the
   private Runtime was reintroduced after sanitization.

The final factory no longer merges the ambient child runnable config and does
not call `Pregel.with_config`. It creates root observability callbacks and
sanitized metadata/tags, then uses official
`Pregel.copy(update={"config": root_observability})`. Invocation-only
`configurable`, checkpointer, Runtime and run/thread/checkpoint coordinates do
not become compiled defaults. The regression contract explicitly installs an
ambient `_ReadRuntime` and proves it cannot leak.

No official Runtime class is monkey patched.

### Official Stream and Structured Output

1. The first profile waited for only `succeeded` or `failed`, then timed out
   after the canonical required-review Graph correctly reached `waiting_human`.
2. The next contract incorrectly required Product durable fallback during an
   active HITL pause, even though the official stream should remain mounted.
3. Reload compared complete dynamic explanatory text, which legitimately became
   richer after Product projection caught up.
4. A real model call returned invalid structured output. The profile surfaced
   `StructuredOutputValidationError`; the failure was not hidden or accepted.

The final browser contract treats `waiting_human` as the stable expected phase
for this profile, still throws on `failed`, and requires a human-readable
Artifact with Evidence, Risk and HTTPS sources when the profile reaches
`succeeded`. HITL pause requires the official stream and review controls; only a
true terminal state requires durable fallback. Reload compares stable lifecycle
identity rather than volatile explanatory copy.

Market Analysis now uses the official recovery path:

- `ToolStrategy(MarketAnalysis, handle_errors=<repair instruction>)` feeds schema
  errors back to the model.
- `ModelCallLimitMiddleware(run_limit=3, exit_behavior="error")` bounds the
  initial model call plus at most two correction calls.
- Outer `Runnable.with_retry` retries transport failures only, so structured
  output does not receive nested retry loops.

## GREEN Evidence

| Gate | Fresh result | What it proves |
|---|---:|---|
| Inbox Desktop/Pixel 7 | `2 passed (8.5s)` | persisted review discovery, exact Task navigation, scroll recovery and page quality |
| HITL approve Desktop/Pixel 7 | `2 passed (16.4s)` | real pending interrupt, readable review, approval and responsive rendering |
| Fork Desktop/Pixel 7 | `2 passed (15.4s)` | checkpoint read, Product fork command, new official Run and return to `waiting_human` |
| Official stream Desktop/Pixel 7 | `2 passed (1.5m)` | active official stream, real providers/model, reload, same Task/Run, HITL pause and browser read-only boundary |
| Framework/factory/observability contracts | `46 passed` | official Graph factory boundary and ambient Runtime non-leakage |
| Focused agent/graph contracts | `21 passed` | bounded official structured-output repair and Graph behavior |
| Ruff | passed | changed Python source and contracts satisfy the configured static gate |

The browser profiles also checked DOM semantics, axe violations, horizontal
overflow, unnamed controls, console errors and forbidden browser-side Agent
writes. The Fork baselines cover Desktop and Pixel 7 and were manually inspected
after regeneration.

## Open Production Gates

This record does not close:

- Approved built-in Web Search/Tavily and hosted egress.
- Licensed persistent Agent Server process/database restart and checkpoint
  durability.
- Hosted OIDC/HTTPS multi-user and cross-tenant browser states.
- Hosted LangSmith/Langfuse correlation and outage recovery.
- Real notification delivery receipts.
- DR/HA, load/SLO, signed SBOM, release attestation or V1 parity/removal.
- Task 13 Deep Research, Cron, retention, outcome, memory and usage scope.

No commit, stage or push was performed for this slice.
