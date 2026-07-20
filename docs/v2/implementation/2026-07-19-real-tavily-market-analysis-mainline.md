# 2026-07-19 Real Tavily Market Analysis Mainline

```yaml
slice_id: real-tavily-market-analysis-mainline
phase: g0.2-local-real-provider-closure
owner_role: current_codex_implementer
owner_agent_id: current-thread-019f3c9c-9a47-78e1-a3b7-a82ff06effcb
normative_sha: unavailable-task-0-not-attested
base_sha: e9def238edbf1e04ef809d75a1eb293a4a81e310
candidate_sha: null
requirement_ids:
  - g0.2-zero-mock-market-analysis-mainline
  - task-4-real-okx-and-web-search
  - task-12-real-product-browser-evidence
status: partial
```

This note records current dirty-worktree implementation evidence. It is not a release
attestation. The user requested no stage, commit or push, so no immutable candidate SHA
exists.

## 1. Mainline Under Test

The tested Product path was:

```text
Product admission
  -> PostgreSQL TaskCommand
  -> unified Worker / CommandDispatcher
  -> official development Agent Server Run
  -> one canonical StateGraph
  -> real OKX public market data
  -> real Tavily Web Search
  -> gpt-5.5 structured research extraction
  -> gpt-5.5 market-analysis-v2 structured result
  -> Evidence and risk gates
  -> committed analysis_report ArtifactVersion
  -> trading Decision
  -> Product API/BFF readable frontend projection
```

The Tavily credential was injected only into the isolated Agent/Worker process
environment. It was not written to an env file, repository file, evidence receipt or
documentation, and no process environment was scraped or printed.

## 2. Honest RED and Root Cause

The first Desktop/Pixel 7 run is retained at:

```text
/tmp/crypto-alert-real-market-tavily-20260719-100000
```

Both Product Tasks failed before any provider result was committed. PostgreSQL correctly
recorded terminal `failed/error` Runs, one terminal event per Task and zero market
snapshots, Evidence, Artifacts or Decisions. The root exception was:

```text
ValueError: Unknown scheme for proxy URL URL('')
```

The public configuration contract documents both proxy settings as optional and permits
blank values, but `Settings` preserved an environment value of `""`. `OkxProvider` then
passed `proxy=""` to `httpx.Client`, which rejects it as an invalid URL. This was a
configuration normalization defect, not an OKX, Tavily, model or frontend failure.

## 3. Repair

`backend/src/crypto_alert_v2/config.py` now normalizes blank optional strings and
optional secrets to `None` before runtime assembly. This covers the model base URL,
market/search proxies, readiness URLs, observability host, optional compatibility paths
and optional credentials. Selecting `SEARCH_PROVIDER=tavily` also requires a nonblank
`TAVILY_API_KEY` during Settings validation, so the process fails at startup instead of
inside a Product Run.

`backend/tests/contract/test_search_runtime_readiness.py` proves blank proxy/config
normalization and blank Tavily credential rejection. The rerun deliberately retained:

```text
MARKET_DATA_HTTP_PROXY=
SEARCH_HTTP_PROXY=
```

This makes the GREEN evidence a direct regression proof for the original failure.

## 4. Real Browser GREEN

The current-source rerun is retained at:

```text
/tmp/crypto-alert-real-market-tavily-rerun-20260719-100400
```

It used isolated Product PostgreSQL
`crypto_alert_v2_market_tavily_20260719095531`, official LangGraph development Agent
Server, the unified Worker and frontend `http://127.0.0.1:3001`. Playwright results:

```text
real-provider-desktop: passed in 39.6s
real-provider-pixel-7: passed in 41.4s
2 passed in 1.4m
0 skipped
0 unexpected
```

The browser asserted a committed actionable result, matched citations, zero unmatched
sources, Evidence/risk gates, real provider provenance, both model audit prompt versions,
Chinese rationale, public HTTPS links and no failed Product/Agent response. DOM/visual
quality gates found no `<pre>` raw JSON, horizontal overflow, clipped or unnamed control,
axe violation, console/page error or unexpected HTTP failure.

Retained screenshots:

```text
frontend/artifacts/playwright-real/real-product-success-real-provider-desktop.png
frontend/artifacts/playwright-real/real-product-success-real-provider-pixel-7.png
```

Both were also manually inspected. They contain real market data, eight readable Web Evidence
cards, Chinese analysis/risk sections, data provenance, model audit and the next-analysis
control. The long Pixel 7 page remains single-column and readable without horizontal
overflow or overlap.

## 5. PostgreSQL Receipt

The two successful Tasks are:

```text
8ccffa67-a4d8-4640-99c2-44245bafaaec
27f73d6d-9d0d-42b4-912d-a35121d9a9ff
```

Each has exactly:

- one `succeeded/success` Product Run;
- one real OKX market snapshot;
- eight Tavily Evidence rows, eight unique source URLs and eight unique content hashes;
- one `analysis_report` Artifact and one committed ArtifactVersion;
- one `no_trade` Decision with `manual_execution_required=true`;
- seven ordered domain events:
  `market.snapshot.committed -> research.evidence.committed -> agent.output.committed ->
  evidence.verdict.committed -> risk.verdict.committed -> artifact.committed ->
  run.terminal`;
- zero notification outbox rows because this test intentionally submitted `notify=false`.

Artifact provenance is `market_provider=okx`, `search_provider=tavily`,
`model_provider=openai-compatible`, `model_name=gpt-5.5`, with eight source references.
The `no_trade` outcome is expected because the test prompt requires no trade when macro
evidence is incomplete; both Evidence and risk gates reported allowed/sufficient.

## 6. Fresh Regression

- Focused backend provider/runtime/Graph regression: `198 passed`, `0 skipped`, one
  existing Starlette/httpx deprecation warning.
- Ruff: all checks passed.
- Root docs/routes/Playwright discovery and runner contracts: `74 passed`.
- Frontend: TypeScript and ESLint passed; all `34` Vitest files / `416` tests passed;
  Playwright discovery/profile contracts passed `35` tests. Prettier is not configured
  or installed, so no formatting pass is claimed.
- `git diff --check`: passed.
- Secret scan excluding every `.env*`, generated artifact, dependency and Git directory:
  no `tvly-dev-` credential occurrence.

## 7. Evidence Boundary and Next Mainline

This closes the local real Tavily Market Analysis Product slice. It does not prove the
default built-in Search provider, hosted egress, licensed persistent Agent Server,
hosted OIDC/HTTPS, real notification delivery, hosted LangSmith/Langfuse traces,
backup/recovery, SLO, security/release attestation or the complete M1-M6 scope.

The next business-mainline gap is Scheduled Monitor/Cron. Current code has no Monitor
tables, Product API, official Cron adapter, `monitor_ingress` branch or frontend product
surface. Implementation must use the locked official LangGraph SDK
`client.crons.create/search/update/delete`, keep one canonical Graph and preserve
`task_commands`/`CommandDispatcher` as the only Product analysis admission path. Local
development Cron evidence cannot be promoted to licensed/hosted production proof.

V2 remains `PARTIAL`; `Production Ready: NO`. No code was staged, committed or pushed.
