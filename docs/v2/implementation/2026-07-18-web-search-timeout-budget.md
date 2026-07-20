# Web Search Timeout Budget and Structured Evidence Binding

> Provenance correction: this historical run used DDGS `backend="auto"`
> metasearch, not a guaranteed DuckDuckGo backend. Provider-identity claims in
> this note are superseded by
> `2026-07-18-readiness-provider-integrity-and-real-regression.md`; URLs,
> citations, timings and the recorded execution sequence remain valid.

Date: 2026-07-18 Asia/Shanghai
Phase: G0.2 mainline recovery / M1 provider and structured-output reliability
Status: local explicit search path green; approved built-in/Tavily production gate open

## Problem

The first fresh zero-mock Product run exposed two separate failures:

1. The search policy advertised three attempts in a 30-second total budget, but
   passed the complete remaining budget to the first transport call. A real
   timeout consumed the whole budget, so Product persisted `attempt=1` and never
   started the advertised retries.
2. After an explicit DuckDuckGo search returned real evidence, the Research
   `ToolStrategy(ResearchBundle)` asked the model to copy provider URLs and
   timestamps. A model URL variation was rejected by the evidence allowlist as a
   `ValueError`, even though the provider evidence itself was valid. Pixel 7 also
   exposed that Market Analysis had no bounded structured-output repair.

These failures were kept visible in the Product API and browser. No model text,
credential, authorization value or raw provider response was added to the
Product projection.

## Implementation

- `SearchRetryPolicy` now allocates a bounded transport slice per attempt while
  preserving the formal three-attempt/30-second total budget. Backoff is reserved
  before each slice; fast failures release unused time to later attempts.
- `SearchAttempt.remaining_budget_seconds` retains its original meaning: the
  total budget available when an attempt starts. It is deliberately distinct
  from the timeout passed to the transport. Tests assert both values.
- Research now uses the official LangChain `create_agent` and `ToolStrategy`,
  but its typed output contains only findings and a bounded `source_index`.
  Application code deterministically maps that index to the verified
  `WebEvidence` row and fills URL/fetched/published timestamps. Unknown indexes
  fail closed.
- Market Analysis, Web Market extraction and Research share one official
  `Runnable.with_retry` tuple containing transient transport errors and
  `StructuredOutputError`, with `stop_after_attempt=2`. This is one total retry
  budget, not nested retry loops.
- The local mainline was started with an explicit
  `SEARCH_PROVIDER=duckduckgo` decision to isolate downstream Product behavior.
  This is not a silent production fallback and does not amend ADR 0002, which
  still requires built-in Web Search or configured Tavily for the production
  selection.

## Verification

```text
Retry/search/parser focused contracts:        71 passed
Agent/graph/search focused contracts:          104 passed, then 43 passed after retry change
Backend hermetic current worktree:             837 passed, 164 skipped, 1 warning
Backend Ruff:                                  passed
Frontend unit/typecheck/lint/build:            335 passed / passed / passed / passed
Root structure + Playwright discovery:         passed
Fresh isolated PostgreSQL integration:         191 passed after migrations 0001 -> 0018
Real Product Playwright Desktop, explicit DDG: 1 passed (1.0m)
Real Product Playwright Pixel 7, explicit DDG: 1 passed (56.5s)
```

The two successful Product Tasks persisted eight typed `duckduckgo` evidence
rows, a committed Artifact, a succeeded Run, and ordered stages:

```text
market_snapshot -> web_evidence -> analysis -> evidence_verdict
-> risk_verdict -> artifact -> run
```

Both browser runs executed Product API, PostgreSQL, worker, canonical Graph,
official local Agent Server and the actual frontend. The Playwright body checked
human-readable result content, cited HTTPS links, no `<pre>`, no failed Product
or Agent responses, no console/page errors, no horizontal overflow, no clipped
controls, no unnamed controls and zero axe violations. Screenshots are retained
as execution artifacts, not approved visual baselines.

The approved built-in path remains an explicit open failure: the latest real
Desktop run reached `attempt=3` with three `APITimeoutError` attempts, persisted
`research_unavailable`, zero Web Evidence and no Artifact. Direct Tavily proof
remains unavailable because no `TAVILY_API_KEY` is configured. This is the
correct failure boundary; the local DDG run must not be used to close that gate.

## Remaining Boundary

V2 remains `PARTIAL`; `Production Ready: NO`. The next mainline gates are the
approved search-provider decision in a hosted egress environment, official
running-stage reload, licensed persistent Agent Server restart durability,
hosted OIDC/HTTPS multi-user browser states, and the remaining M5/M6 release
evidence. No commit or push was performed.
