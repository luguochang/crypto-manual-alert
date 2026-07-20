# Readiness, Provider Integrity and Real Regression

Date: 2026-07-18

Phase: `G0.2/M1/M5-M6` local production-auth proof; hosted acceptance open

## Scope and Verdict

This iteration closed a set of false-green readiness paths, provider-integrity
gaps and unbounded remote waits found while re-running the current Product
mainline. It also corrected the persisted identity of the local Web provider and
re-ran the current source through PostgreSQL, the unified Worker, the official
LangGraph development Runtime, real providers, the model and the rendered UI.

The truthful verdict remains:

```text
V2: PARTIAL
Production Ready: NO
```

The local production-auth mainline is GREEN under the explicitly recorded HTTP
proxy and `SEARCH_PROVIDER=ddgs_metasearch` conditions. The approved
`builtin_web_search` path, licensed persistent Agent Server, hosted identity and
release gates remain open.

## Retained REDs

The following failures were retained before their corresponding corrections:

1. `ddgs==9.14.3` uses `backend="auto"` when no backend is supplied, while the
   old implementation persisted every automatic metasearch result as
   `source=duckduckgo`. The citations were real, but the provider identity was
   not supportable.
2. The OKX adapter accepted mixed-instrument rows when an otherwise successful
   response contained an `instId` different from the requested instrument. It
   also accepted negative candle volume.
3. Product readiness used a one-shot Agent probe. It had no long-running
   first-success barrier, stale-success protection or consecutive-failure
   policy, so a previously healthy dependency could remain falsely green.
4. Worker readiness could report green before every required loop had succeeded
   and while an active iteration was hung. A health-listener bind failure could
   also leave ambiguous process state.
5. Command reconciliation and selected remote Run operations did not all share
   a bounded network deadline, leaving long waits in failure paths.
6. Stopping the whole Agent process also stopped its mounted Product custom
   application. The browser-facing Product BFF request then had no server-owned
   upstream deadline and could wait indefinitely.
7. Running integration tests against the shared production-proof database
   caused legitimate historical-count and Worker-contention failures. Those
   failures were environmental isolation defects, not assertions to weaken.
8. The old one-shot healthcheck subprocess contract hung after the healthcheck
   became a long-running monitor and had to be replaced with lifecycle tests.
9. The Langfuse OTLP recovery test exposed a full-suite-only asynchronous error
   logging race. The security requirement to log a redacted 503 and deliver the
   next trace after recovery was retained.

## Implemented Corrections

### Agent and Product Readiness

`AgentReadinessMonitor` now owns a long-running semantic probe with:

- independent `/livez`, `/readyz` and `/healthz` behavior;
- a first-success barrier;
- a bounded semantic-probe timeout;
- a configurable consecutive-failure threshold;
- monotonic stale-success protection; and
- recovery after the Agent dependency becomes healthy again.

The Product readiness endpoint now requires Product PostgreSQL, the Agent
readiness monitor and the Worker readiness endpoint. The monitor also validates
the exact configured `SEARCH_PROVIDER`, preventing a healthy response from a
runtime using a different provider selection.

Compose runs the monitor as a restartable, healthchecked sidecar. Product
readiness queries the sidecar at runtime; Worker and frontend startup wait for
the sidecar's healthy state rather than a one-shot startup probe.

### Worker Readiness

`WorkerRuntime` now tracks first success and failure state for every required
loop. Readiness falls when a loop crosses the consecutive-failure threshold or
when an active iteration exceeds the configured stale interval. Normal polling
sleep does not count as a stale iteration, and recovery restores readiness after
the affected loop succeeds.

The runtime also refuses to report live when its health listener cannot bind and
limits the health request buffer to 8 KiB. The thresholds are configurable with
`WORKER_READINESS_FAILURE_THRESHOLD` and
`WORKER_READINESS_STALE_AFTER_SECONDS`.

### Bounded Remote Operations

The command dispatcher now applies the same bounded remote deadline to resume
with heartbeat, submit/resume/fork reconciliation `find` calls and normal remote
Run `get` calls. A timeout preserves the existing typed indeterminate or
reconciliation state. It does not introduce a second retry loop or create a
duplicate remote operation.

The Product BFF now applies a server-owned eight-second upstream deadline that
is combined with request cancellation. A hung Product upstream returns a
bounded, redacted 502 response:

```text
Product API is temporarily unavailable.
```

This corrects the browser-facing wait. Task 8 deliberately mounts Product as the
Agent Server `/app` custom application, so the shared process failure domain is
an approved topology property; whole-process outage is expected to surface as a
bounded BFF transport failure rather than an independently served Product 503.

### OKX and Retry Integrity

Ticker, mark price, index price, funding and open-interest parsing now reject
any response row whose `instId` does not match the requested instrument. Index
price keeps its required spot-style instrument mapping. Candle parsing rejects
negative volume while preserving zero as a valid value.

`RetryPolicy` now rejects zero or negative attempts, zero or negative total
budget, an empty backoff sequence and negative backoff values at construction
time.

### DDGS Provenance

The local diagnostic provider is now named `ddgs_metasearch` throughout config,
runtime state, persisted Evidence and UI labels. DDGS `text()` and `news()` are
called with explicit `backend="auto"`; the obsolete `SEARCH_PROVIDER=duckduckgo`
value fails closed. New records use:

```text
source=ddgs_metasearch
parser_version=ddgs-metasearch-v1
```

Alembic revision `0019_ddgs_provenance` recursively rewrites only structured
`source`, `provider` and `search_provider` keys in Web Evidence, Run output,
Artifact version and Domain Event JSON. Downgrade reverses the same scoped
transformation. Free text and unrelated keys are not rewritten.

This note supersedes provider-identity claims in earlier 2026-07-18 records that
called the DDGS automatic metasearch result "DuckDuckGo". It does not erase the
historical test sequence or invalidate the real URLs and citations.

### Langfuse Recovery Contract

The official OTLP transport test now waits for the asynchronous 503 error log
before changing the mock transport to 200. The original requirements remain
unchanged: observability failure is fail-open for business execution, the 503 is
logged at error level without response-body credentials, and the next trace is
delivered after recovery.

## Fresh Verification

The source, configuration and test bodies below are current-worktree evidence.
The exact pass counts, timings, database counts and fault-transition timings are
local-session evidence recorded during this iteration. They are not yet bound
to a clean candidate Git SHA, image digest and retained JUnit/Playwright
manifest, so they must not be treated as release attestation.

### Static, Unit and Integration Gates

```text
Backend:
887 passed, 166 skipped, 1 warning

Fresh isolated PostgreSQL, Alembic 0001 -> 0019:
198 passed

Command dispatcher against real PostgreSQL:
73 passed

Focused OKX/search/retry provider verification:
55 passed

Frontend:
374 passed in 30 files
typecheck passed
ESLint passed
production build passed

Root structure/deployment suite:
exit 0
docker compose config --quiet passed with a test-only credential

Ruff:
check passed
183 files format-checked

Repository whitespace gate:
git diff --check passed
```

The 166 skips are unproved requirements, not passes. The historical
`alembic/versions/0001_initial.py` was not mechanically reformatted because that
would create migration-history churn; new revision 0019 was independently
format-checked.

### Migration Rehearsal

Before revision 0019, a local PostgreSQL backup was created at:

```text
/tmp/crypto-alert-v2-before-0019-20260718235814.dump
```

The real database migration reported:

```text
upgrade to 0019:
legacy_rows=0
corrected_rows=274

0019 -> 0018:
legacy Evidence=178
ddgs Evidence=0

0018 -> 0019:
legacy Evidence=0
ddgs Evidence=178
```

This proves local reversible data transformation. It is not a production
zero-downtime migration, failover or operator attestation.

### Readiness Fault and Recovery

The running production-auth local stack initially reported Agent monitor,
Worker and Product readiness as HTTP 200.

Pausing only the Agent readiness monitor caused Product readiness to return 503
after approximately two seconds with `Agent Server is not ready.`. Resuming the
monitor restored both endpoints to 200.

Pausing the whole Agent process caused the monitor to return 503 after its
failure threshold. Because Product shares that process, the Product BFF returned
the bounded redacted 502 after eight seconds. Resuming the process restored
Agent, monitor, Worker and Product readiness to 200.

### Zero-Mock Product Mainline

The current production-auth local proof passed:

```text
Desktop: 1 passed (1.4m)
Pixel 7: 1 passed (1.1m)
Combined: 2 passed (2.5m)
```

The observed local session, corroborated by the inspected screenshots and
follow-up PostgreSQL queries, exercised:

```text
Frontend
-> same-origin BFF with production JWT
-> Product API
-> PostgreSQL
-> unified durable Worker
-> official LangGraph development Runtime
-> real proxied OKX
-> real proxied DDGS automatic metasearch
-> model Structured Output
-> persisted Artifact/Evidence/model audit
-> rendered UI
```

The follow-up local PostgreSQL query for the two Product tasks found four Runs
in `succeeded` or `waiting_human` states, two committed Artifacts, sixteen
Evidence rows with `source=ddgs_metasearch` and
`parser=ddgs-metasearch-v1`, and four model audit entries. Those exact counts
are local-session evidence; the Playwright test contract itself requires a
committed actionable result, matched citations and visible model audits rather
than those database totals.

The real Library/Artifact detail profile also passed Desktop and Pixel 7:

```text
2 passed (12.7s)
```

The four inspected screenshots are:

- `frontend/artifacts/playwright-real/real-product-success-real-provider-desktop.png`
- `frontend/artifacts/playwright-real/real-product-success-real-provider-pixel-7.png`
- `frontend/artifacts/playwright-real/real-library-artifact-detail-fixture-desktop.png`
- `frontend/artifacts/playwright-real/real-library-artifact-detail-fixture-pixel-7.png`

The test gates include raw JSON absence, DOM overflow, clipped or unnamed
controls, axe findings, browser console/page errors and failed Product/Agent
responses. The screenshots are local QA evidence, not approved hosted visual
baselines.

## Open Production Boundaries

This iteration does not prove or complete:

- approved `builtin_web_search` on the user's endpoint;
- a real Tavily run with a verified credential;
- licensed persistent Agent Server restart and checkpoint durability;
- hosted OIDC, trusted HTTPS and real multi-user browser storage states;
- a fresh hosted LangSmith and Langfuse trace linked through the Product flow;
- a real notification delivery receipt;
- production HA, PITR, failover and measured Product SLOs;
- signed SBOM, release candidate review or release attestation; or
- Task 13 Deep Research and lifecycle implementation.

The local mainline also depends on host HTTP proxy `127.0.0.1:7890`. The active
official Agent Server is the in-memory development Runtime, not a licensed
persistent production deployment.

No commit, stage or push was performed.
