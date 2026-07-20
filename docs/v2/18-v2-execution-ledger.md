# V2 Execution Ledger

> authority_class: informative
>
> status: m5_m6_production_closure_in_progress
>
> purpose: 记录 V2 的实际执行状态、证据边界、架构决策和下一步，避免执行状态只存在于对话上下文中。
>
> this document does not replace `13-v2-final-rebuild-spec.md`, `14-v2-final-implementation-plan.md` or any accepted ADR.

## 1. Current Decision

The original M1-M6 production-delivery scope is active. The user approved a replacement
execution objective on 2026-07-16 that preserves the complete M1-M6 scope and inserts G0
as mandatory recovery gates before peripheral product and release work resumes.

The final delivery goal remains valid:

> Deliver a maintainable, observable, multi-user production crypto analysis product whose main path is real, typed, recoverable, and verifiable on desktop and mobile.

The active goal must be executed mainline-first. Peripheral infrastructure work must not
proceed while the main user-visible path is still not closed.

Current execution target:

> **G0 Mainline Recovery and Framework Convergence**: audit the canonical code path, prove one zero-mock main vertical slice, remove or quarantine duplicate runtime implementations, and only then continue product features and release gates.

The active thread goal is the complete production-delivery objective. G0.1 is complete,
G0.3 is complete for canonical source/dependency convergence, and G0.2 now has both a
GREEN controlled/local zero-mock slice and a GREEN transient Tavily local real-provider
slice. The default configured `builtin_web_search` capability remains
`RED / EXTERNAL DEPENDENCY`; the Tavily proof used a caller-injected credential for one
isolated runner and did not change repository or deployment configuration. Execution
therefore remains in G0.2 provider closure plus the remaining M5-M6 product and
production gates. Hosted and licensed-runtime gates remain open.

Task 8 is also explicitly `RED / PARTIAL`, not GREEN. The development matrix is
`langgraph-api 0.11.1` / `langgraph 1.2.9` / Protocol `0.0.18`; the licensed
image verifier remains `langgraph-api 0.11.0`. The root `checkpoints` Protocol
channel is RED, `state.fork` returns `unknown_command`, both proposed exception
records are unaccepted, and licensed restart plus server-effective
`durability="exit"` remain UNPROVED.

G0 is not the final delivery goal and does not reduce the M1-M6 scope. It is a controlled recovery phase inside the original goal. After G0.1, G0.2 and G0.3 pass, execution must continue through the remaining M1-M6 product and production gates.

The intended relationship is:

```text
Original Final Goal: Production Deliverable V2
  |
  +-- G0.1 Canonical Path Audit
  +-- G0.2 Real Main Vertical Slice
  +-- G0.3 Framework Convergence
  |
  +-- M1-M4: providers, domain, graph, HITL, identity and core product
  +-- M5: observability, notification, security and operational reliability
  +-- M6: product completion, deployment, recovery, SLO, security and release proof
  |
  +-- Final zero-mock desktop/mobile and production acceptance
```

Passing G0 only permits the project to resume the remaining scope. It is not a release candidate and cannot be reported as production ready.

## 2. Authority Order

When documents disagree, use this order:

1. `13-v2-final-rebuild-spec.md` and the approved normative regions defined by Task 0.
2. `02-official-framework-constraints.md` and accepted ADRs.
3. `14-v2-final-implementation-plan.md` for intended implementation order.
4. This ledger for actual current status and observed evidence.
5. `15-v2-implementation-status.md` and evidence files, after they are refreshed to include the latest work.
6. `docs/refrence/agent/` as learning material, not project-specific normative requirements.

The reference notes are useful for framework selection, but they include confirmed facts, teaching analogies, user-specific experience, and items marked as inference or pending verification. They must not be copied into the product as requirements without an explicit decision.

## 3. Product Success Definition

The first acceptance gate is one real vertical slice, not a large feature count:

```text
server-owned local actor
  -> Product admission
  -> Task/Run persistence
  -> official LangGraph graph
  -> real OKX snapshot
  -> real verified web evidence
  -> LangChain structured analysis
  -> deterministic evidence and risk gates
  -> optional official interrupt/resume
  -> Product Artifact/Decision transaction
  -> readable frontend projection
  -> refresh/reload recovery
```

The slice is successful only when all of the following are true:

- The backend receives a real request and returns a server-owned Task ID.
- A real model result or an explicit typed provider failure is persisted.
- Real market data and verified evidence are persisted when providers are available.
- The frontend shows human-readable analysis, evidence, risk and failure content.
- The primary UI does not expose raw Graph state or JSON dumps.
- Refreshing the page reloads authoritative Product state.
- No generic success is returned after a provider/model failure.
- The result can be located through one correlation ID.
- Desktop and Pixel 7 browser paths cover both success and failure.

Fixture, intercepted, skipped, or development-only checks may support diagnosis but cannot be reported as completion of this gate.

## 3.1 Final Delivery Definition

The final delivery remains the complete production chain from the original M1-M6 objective:

```text
multi-user identity and authorization
  -> Product Task admission and idempotency
  -> real market data and verified web research
  -> official LangChain/LangGraph Agent execution
  -> constrained Research/Deep Agents decision where approved
  -> structured Artifact, Evidence and Risk projection
  -> official HITL interrupt/resume and aggregate review
  -> Product PostgreSQL transaction and lineage
  -> reliable command/notification workers and recovery
  -> readable Work/Runs/Inbox/Library/Settings/Feedback UI
  -> LangSmith/Langfuse correlation, masking and operational traces
  -> cancel/retry/fork/refresh/reconnect behavior
  -> hosted OIDC/HTTPS and production deployment
  -> backup/restore, migration rollback, key rotation and DR
  -> load/SLO/security/SBOM/release attestation
  -> desktop/mobile zero-mock Playwright and visual/accessibility gates
```

The final acceptance criteria are:

- Every user-visible primary workflow is backed by a real Product API and persisted state.
- The main workflow shows real successful model/provider results and honest typed failures.
- Multi-user read/write/resource isolation is proven with real identities, not only local bootstrap actors.
- Long-running, interrupted, cancelled, retried and forked runs have durable, observable outcomes.
- LangChain/LangGraph/official SDK capabilities are used at their ownership boundaries; custom code is limited to product-specific behavior.
- The frontend presents human-readable projections rather than raw Graph/Protocol JSON.
- LangSmith and Langfuse can locate the same execution without exposing secrets or sensitive payloads.
- Deployment, restart, recovery, backup, restore, security and release evidence is reproducible from an immutable source candidate.
- All required desktop/mobile zero-mock paths pass, including success, provider failure, HITL, reload, reconnect and responsive layout states.

Until this entire list is satisfied, the project remains `partial` and is not production deliverable.

## 4. Framework Boundary

### 4.1 Required official capabilities

The Agent path must use the locked official APIs:

- LangChain `create_agent` for a standard model/tool agent.
- LangChain structured output and Pydantic schemas.
- LangChain middleware for Agent-level cross-cutting behavior.
- LangGraph `StateGraph` for the non-standard product topology.
- LangGraph `interrupt()` and official resume semantics for HITL.
- LangGraph checkpointer/Store or the official Agent Server runtime for execution state.
- Official Agent Server protocol and SDK for Thread/Run/stream access when the deployment profile requires it.
- `@langchain/react` `useStream` for the browser live Runtime.
- Central LangSmith/Langfuse callback assembly for observability.

### 4.2 Allowed product code

Custom code is expected for:

- Market-domain models and evidence/risk rules.
- OKX and search provider adapters and provider-specific citation validation.
- Product Task, Run, Artifact and Decision persistence.
- Multi-user identity, membership and resource authorization.
- Transactional command admission and external notification Outbox.
- Product API DTOs, view models, BFF boundaries and visual components.
- Operational audit, retention, backup, security and release gates.

### 4.3 Explicitly prohibited duplication

The product must not maintain a second implementation of:

- ReAct or Agent while-loops.
- Tool envelope or tool registry protocols.
- Structured-output JSON extraction with regex/string parsing.
- LangGraph checkpoint or interrupt state machines.
- Private SSE framing, reconnection and message deduplication protocols.
- A second generic Agent Runtime outside the canonical graph/Agent Server boundary.
- A second production graph that is not the canonical graph.

## 5. Current Reality Snapshot

### 5.1 Confirmed existing implementation

- Canonical top-level `StateGraph` exists in `backend/src/crypto_alert_v2/graph/graph.py`.
- Market and research factories call LangChain `create_agent`.
- `ToolStrategy` structured output is present for `MarketAnalysis` and `ResearchBundle`.
- Official `interrupt()` is used for the root review path.
- Official Agent Server graph export is configured in `backend/langgraph.json`.
- Official LangGraph SDK calls are used for Thread/Run/state operations.
- Frontend `@langchain/react` `useStream` is present behind a same-origin BFF.
- LangSmith/Langfuse callback assembly and redaction code exist.
- Multi-user Product persistence, HITL, fork lineage, command worker and notification Outbox slices have substantial tests.

### 5.2 Confirmed gaps

- `create_deep_agent` has no production call site. The dependency is locked, but Deep Agents is not implemented in the runtime path.
- The current research collector calls the search provider imperatively and then uses `create_agent(tools=[])` for extraction. It is not a model-driven Web Search Tool loop.
- Market analysis also uses `create_agent(tools=[])`; this may be an unnecessary Agent wrapper around structured model invocation.
- `backend/src/crypto_alert_v2/graph/nodes/` contains a duplicate manual JSON-parsing implementation and is not imported by the canonical production graph.
- Middleware coverage is currently narrower than the reference notes: secret/PII redaction exists, but the full planned middleware profiles, budgets, ordering proofs and canary coverage are not closed.
- The current Agent Server/Product dispatcher boundary is functionally substantial but too large and difficult to audit as a single surface.
- The current status document is stale: it describes M4 as current and does not record the latest 0010/0011 notification destination work.
- The final implementation plan has many unchecked boxes and is not an observed execution ledger.
- Deep Research, canonical nested provider review, Library, Feedback, hosted OIDC/HTTPS, licensed persistent restart proof and final release gates remain open.

### 5.3 G0.1 Audit Evidence: 2026-07-16

The first current-worktree audit found the following concrete runtime facts:

| Area | Observed fact | Classification |
|---|---|---|
| Canonical graph | With `APP_ENVIRONMENT=test`, importing `crypto_alert_v2.graph.graph` returns `CompiledStateGraph` with the expected validate/market/research/analyze/evidence/risk/artifact/review/complete nodes. | canonical, but import boundary is contaminated by `crypto_alert_v2.api.__init__` importing the FastAPI app as a package side effect. A clean Graph import must not require Product API startup settings. |
| Product admission | `POST /api/v2/analysis` resolves the server-owned actor, writes Thread/Task/submit `TaskCommand`, and returns a typed Task projection. | canonical Product boundary |
| Command execution | `CommandDispatcher` claims the durable command, creates or resumes/forks the official Agent Server Run through `AgentServerRunner`, renews leases, reconciles indeterminate operations, and projects terminal state. | canonical execution adapter, currently oversized and must be decomposed after mainline proof |
| Graph runtime | `graph/runtime.py` assembles OKX, search collector and `create_market_analysis_agent`; `graph.py` invokes them as Graph nodes. | canonical framework boundary |
| Research input | `research_events` creates a generic `asset + macro market news + horizon` query and does not include `AnalysisRequest.query_text`. | mainline correctness gap; user intent is persisted but not used by Web Search |
| Market horizon | `OkxProvider.fetch_snapshot` always requests `bar=1H`; the Graph does not pass the requested horizon to the provider. | mainline correctness gap; `horizon` is accepted by the API but not fully honored by market data |
| Agent factory | `create_agent` is used for market/research structured extraction, but both factories use `tools=[]`; search is called imperatively before research extraction. | valid deterministic design candidate, but not a ReAct/Web Tool loop; requires an explicit G0.3 decision |
| Deep Agents | No production `create_deep_agent` or `deepagents` import exists. | open decision; implement a narrow read-only Research Subgraph or record and enforce a formal fallback |
| Duplicate runtime | `graph/nodes/analyze_market.py` contains a second `create_agent` and manual JSON extraction, but no production import reaches `graph/nodes`. | orphan/duplicate; quarantine or remove after protected-file review |
| Streaming | Product Task polling is authoritative for business state; official `useStream` is attached only to an active non-terminal Task and projects named live fields. The BFF forwards official SSE. | intended canonical split; requires real runtime proof |
| Legacy routes | `/` and `/manual-run` redirect to `/work`; `/runs/[traceId]` currently redirects to `/work` rather than rendering a Run detail page. | legacy/unfinished product surface |
| Worker entry | Docker/Compose use `python -m crypto_alert_v2.workers`; the old `commands.worker` module remains as an authorization/helper and test import, not the Compose entrypoint. | transitional compatibility surface |

The first direct Graph import without `APP_ENVIRONMENT` failed because `crypto_alert_v2.api.request_identity` caused Python to load `crypto_alert_v2.api.__init__`, which imports `api.app` and eagerly constructs the default FastAPI app. The same import with `APP_ENVIRONMENT=test` succeeded and exposed the canonical node list. This is an observed import-boundary bug, not a provider or model failure.

The current worktree has many uncommitted changes from prior slices. G0.1 must classify them before any deletion or broad refactor; no file is assumed removable solely because it is untracked.

### 5.4 Current Git and Evidence Anchor

| Fact | Current observation |
|---|---|
| Audit time | 2026-07-16 Asia/Shanghai |
| Branch | `codex/v2-production-completion` |
| HEAD | `e9def23` (`feat: secure multi-user checkpoint forks`) |
| Upstream | `origin/codex/v2-production-completion` at `2cf676a`; local branch ahead by one commit |
| Dirty worktree | 46 modified tracked files and 75 untracked files when expanded with `--untracked-files=all` |
| Release status | no clean candidate, no current review/attestation, not production ready |
| Current execution | G0.1 audit complete; G0.2 startup/mainline repair and zero-mock proof in progress |

The pass counts in `15-v2-implementation-status.md` and `17-m4-identity-fork-security-evidence.md` are historical evidence for their recorded M4 snapshots. They do not prove the current dirty worktree. This includes the recorded backend, PostgreSQL, frontend unit, fixture Playwright and Desktop/Pixel 7 totals.

Current uncommitted implementation slices that exist but are not yet accepted as delivered include:

- Alembic 0010 notification Outbox and 0011 owner-scoped notification destinations.
- Notification adapters, credential encryption, resolver, worker, API and frontend status/settings surfaces.
- Observability policy, redaction, logging, outage/cardinality tests and LangSmith release-gate helpers.
- Evaluation dataset/experiment/release-gate modules.
- Unified command/notification worker entry and lifecycle tests.

These items must be described as `implementation slice exists; fresh verification/review/production proof pending`, not as missing and not as done.

Confirmed code or evidence still absent includes:

- Library page and Artifact/Decision library API closure.
- Feedback persistence, API and UI.
- A dedicated projection reconciler and complete progressive stage persistence.
- Real LangSmith/Langfuse external proof suites.
- Production deployment/alerting files and CI release workflow.
- Normative baseline manifest, requirement registry and final independent attestation.
- Hosted OIDC/HTTPS and licensed persistent Agent Server restart proof.

`02`, `13`, `14` and accepted ADRs remain normative and must not be weakened to match the dirty worktree. `15` and `17` remain historical snapshots; current-state corrections belong in this ledger or a new evidence file tied to a fresh source SHA.

### 5.5 Backend Canonical Runtime Map

Current-worktree reachability establishes one V2 backend production chain:

```text
POST /api/v2/analysis
  -> api.app.create_analysis
  -> ProductAnalysisService.create_analysis
  -> Product PostgreSQL Thread + Task + submit TaskCommand
  -> python -m crypto_alert_v2.workers
  -> WorkerRuntime -> CommandDispatcher
  -> AgentServerRunner
  -> official langgraph-sdk threads/runs API
  -> langgraph.json crypto_analysis export
  -> graph_factory -> create_graph -> canonical StateGraph
  -> AnalysisRuntime -> OKX/search/LangChain agents
  -> official terminal Graph state
  -> TerminalGraphOutput validation
  -> CommandDispatcher._finalize
  -> Product Run + provider records + ArtifactVersion + Decision
  -> ProductAnalysisService._task_view
  -> Product API Task projection
```

| Backend responsibility | Canonical implementation | Authority |
|---|---|---|
| HTTP composition | `backend/src/crypto_alert_v2/http/app.py:create_app` mounts the Product app under `/app`. | deployment composition only |
| Product admission | `backend/src/crypto_alert_v2/api/app.py:create_analysis` and `api/service.py:ProductAnalysisService.create_analysis` | identity, authorization, idempotency and Product Task admission |
| Durable command queue | `persistence/models.py:TaskCommand` | Product PostgreSQL command order, lease and attempt fence |
| Worker process | `workers/__main__.py`, `workers/runtime.py`; Docker/Compose use `python -m crypto_alert_v2.workers` | deployed command/notification process lifecycle |
| Product/Agent adapter | `commands/dispatcher.py:CommandDispatcher` and `api/agent_server.py:AgentServerRunner` | dispatch and projection adapter; not Graph execution authority |
| Agent transport/runtime | official `langgraph-sdk` and Agent Server | Thread, Run, checkpoint, interrupt and raw execution status |
| Production Graph export | `backend/langgraph.json` maps `crypto_analysis` to `graph/__init__.py:graph_factory` | unique deployed Graph mapping |
| Graph construction | `graph/graph.py:graph_factory`, `create_graph` and module-level `StateGraph` builder | unique V2 analysis topology |
| Runtime assembly | `graph/runtime.py` | model, search collector, market provider and Agent factory assembly |
| Market facts | `providers/okx.py:OkxProvider.fetch_snapshot` | external market-data adapter and typed validation |
| Research extraction | `agents/research.py:CitedResearchCollector` | verified search evidence and `ResearchBundle` structured output |
| Market analysis | `agents/market_analysis.py:create_market_analysis_agent` | `MarketAnalysis` structured model output |
| Domain gates | `domain/evidence_policy.py`, `domain/risk_policy.py`, `domain/models.py` | product-specific deterministic evidence/risk contracts |
| Terminal ingress contract | `api/schemas.py:TerminalGraphOutput` | validation before Agent output enters Product persistence |
| Durable business result | `commands/dispatcher.py:_finalize` plus Product persistence models | user-visible Run, provider evidence, ArtifactVersion and Decision |
| Refresh projection | `api/service.py:_task_view` | authoritative Product state after reload |

### 5.6 Backend File Classification And Breaks

| Path or surface | Classification | Current decision / required action |
|---|---|---|
| `backend/src/crypto_alert_v2/graph/graph.py`, `graph/runtime.py`, `agents/`, `providers/`, `domain/` | canonical framework/domain path | keep; repair intent/horizon propagation and import boundaries |
| `api/app.py`, `api/service.py`, Product persistence models | canonical Product boundary | keep; reduce oversized responsibilities only after real mainline proof |
| `workers/`, `commands/dispatcher.py`, `api/agent_server.py` | canonical execution adapter | keep official SDK boundary; later split generic coordination from Product projection |
| `backend/src/crypto_alert_v2/graph/nodes/` | duplicate/orphan | not imported by the production builder; imports nonexistent `config.settings`; contains a second Agent and manual JSON extraction. Quarantine/remove in G0.3 after protected-path review. |
| `persistence/repositories.py:ArtifactRepository.commit_version_and_decision` and `unit_of_work.py` | parallel currently-unreached persistence path | evaluate as the replacement for `_finalize`'s duplicate fixed-version write; converge to one persistence implementation |
| `commands/worker.py` | transitional compatibility entry | not the Compose entrypoint; retain only if an explicit supported operational use remains |
| `testing/multi_interrupt_fixture.py` and fixture graph configuration | test fixture | never use as zero-mock production evidence |
| root `src/crypto_manual_alert/` runtime and old manual-run tooling | legacy parallel product | not part of `/api/v2/analysis`; quarantine/document removal so open-source users cannot start the wrong product |
| notifications, evaluation and Settings slices | peripheral implementation present | freeze acceptance work until G0.2/G0.3 pass; do not classify as production delivered |

Observed backend breaks that must remain visible until fixed and freshly verified:

1. `tools/v2/verify_agent_image.sh` still requires the old `:graph` mapping while
   `backend/langgraph.json` exports `:graph_factory`. The integration-stack verifier can
   reject the intended production image.
2. A succeeded Task may be forked, but terminal projection creates a second Artifact with
   fixed version `1` despite the one-Artifact-per-Task constraint. A real successful
   fork can fail at persistence; existing fork tests do not seed the first Artifact.
3. Importing `api.request_identity` or `api.agent_server` loads `api/__init__.py`, which
   eagerly imports and constructs the Product FastAPI app. Graph and worker imports are
   therefore coupled to Product API settings and `.env` loading side effects.
4. `AnalysisRequest.query_text` is persisted but `research_events` replaces it with a
   generic asset/macro query. User intent does not currently reach Web Search.
5. Requested `horizon` is not passed into `OkxProvider`; candle collection is fixed to
   `1H`. The API accepts a horizon that the market-data window does not honor.
6. Successful Artifacts use Product `ArtifactVersion`/`Decision` rows, while blocked
   Artifacts are retained only in `Run.output_payload`. This split persistence contract
   is intentional only if explicitly accepted; it is currently undocumented behavior.
7. A complete legacy runtime remains startable from the repository root even though it
   is not part of the V2 Docker/Compose production path.

These are current-worktree findings, not historical plan assumptions. G0.1 classifies
them; G0.2 must fix any item that prevents the real vertical slice, and G0.3 must remove
the duplicate runtime and persistence ownership.

### 5.7 Frontend Canonical Map And Runtime Boundaries

The frontend has one durable Product path and one auxiliary official runtime observation
path:

```text
/work
  -> WorkSurface
  -> product-client
  -> same-origin Product BFF
  -> Product API TaskView/ProductTask
  -> one-second polling and URL recovery
  -> human-readable Analysis/Evidence/Risk projection

ProductTask.agent_stream
  -> @langchain/react useStream
  -> same-origin Agent BFF
  -> official Thread state/history/SSE
  -> transient execution-progress projection
```

| Frontend responsibility | Canonical implementation | Authority |
|---|---|---|
| Primary route | `frontend/src/app/work/page.tsx:WorkPage` | user-facing product entry |
| Submit/recover/cancel/review | `features/work/work-surface.tsx:WorkSurface` | UI orchestration only |
| Product API contract | `lib/api/product-client.ts` + `lib/schemas/product-api.ts` | typed BFF contract boundary |
| Product BFF | `app/api/product/[...path]/route.ts` -> `lib/api/product-proxy.ts` | same-origin auth/route allowlist |
| Durable task status | backend `ProductTask` projection | final business authority |
| Refresh recovery | URL `task/run` pointer -> Product GET | Product persistence, not browser memory |
| Live progress | `features/agent-runtime/official-run-stream.tsx` | official Thread events, transient only |
| Human-readable result | `analysis-view-model.ts` -> `AnalysisResult`/`ResearchEvidence` | ProductTask projection |

The canonical frontend boundary is therefore not a choice between polling and streaming:
Product polling remains the final state authority, while official `useStream` supplies
progressive execution detail and must be allowed to disappear or reconnect without
changing the final Product result.

Frontend issues recorded for implementation gates:

1. `createAnalysis` generates an idempotency key but `WorkSurface` does not persist the
   key across an unknown response. A timeout after server admission can create a second
   Task on resubmission.
2. `OfficialRunStream` receives `assistant_id` and `thread_id`; `run_id` is only compared
   locally and is not passed as a stream selector. The UI cannot independently prove that
   a Thread event belongs to the declared Product Run.
3. `NotificationStatus` stops polling when the first response has no active item. A
   delayed Outbox delivery can therefore remain invisible until a full refresh.
4. Product and Agent streams both carry lifecycle/market/evidence/analysis-shaped data;
   the code conventionally treats Product as authoritative, but has no explicit
   consistency assertion when live values disagree.
5. The Product schema accepts a non-empty Agent `thread_id`, while the Agent BFF route
   matcher requires UUID shape. The binding contract is stricter in the proxy than in
   the upstream response schema.
6. Blocked draft Artifacts currently render only a summary of blocked/missing reasons;
   structured confidence caps and other gate details are not fully exposed.
7. `/runs/[traceId]` redirects to `/work`, Library is only a disabled navigation entry,
   and the mock-only browser suites are not zero-mock evidence. Settings and notification
   slices exist in the dirty tree but lack a clean baseline and real browser proof.

G0.2 must prove the `/work` success and honest failure path with the Product projection
and confirm that raw JSON is not the primary UI. G0.3 must make stream ownership,
idempotent admission and duplicate runtime boundaries explicit.

### 5.8 Official Capability Overlap Decisions

| Current surface | Official capability | Decision | Reason / next action |
|---|---|---|---|
| `graph/graph.py` topology | LangGraph `StateGraph` | keep | product topology is non-standard and already uses the official owner |
| Human review state | LangGraph `interrupt()` and resume | keep | do not introduce a Product-side checkpoint or interrupt machine |
| `agents/market_analysis.py` with `tools=[]` | LangChain structured model output / `create_agent` | decide in G0.3 | prefer the smallest official structured-output primitive unless Agent middleware/tool behavior is actually required |
| `agents/research.py` imperative search followed by `create_agent(tools=[])` | LangChain tool Agent or restricted Deep Agents research graph | replace/converge in G0.3 | user query and verified read-only Web Search must be first-class; keep product citation validation outside generic Agent runtime |
| `graph/nodes/analyze_market.py` manual JSON parsing and second Agent | official structured output | quarantine/remove | duplicate unreachable implementation and prohibited regex/string JSON ownership |
| `AgentServerRunner` | official `langgraph-sdk` | keep as thin adapter | retain auth, Product correlation and typed conversion; remove any behavior that duplicates official Run/checkpoint semantics |
| `CommandDispatcher` | official Agent Server plus Product durable command queue | keep Product ownership, decompose | Product queue, lease, idempotency and projection are legitimate; generic Run coordination must stay delegated to SDK/Server |
| Product Task polling | Product persistence | keep | final business state is not an Agent Runtime responsibility |
| `OfficialRunStream` | `@langchain/react useStream` | keep | official live runtime; make Thread/Run binding and reconciliation explicit |
| Product/Agent BFF proxies | official protocol plus server-owned identity | keep narrowly | BFF is an auth and allowlist boundary, not a custom SSE/runtime implementation |
| provider retry policy | transport retries and LangChain model retry middleware | keep with single-owner matrix | assign each failure to provider transport, Agent middleware or Product command retry; prohibit multiplied retries |
| observability callback assembly | LangSmith/Langfuse callbacks | keep Product policy wrapper | redaction, tenant sampling and correlation are product/security responsibilities |
| `ArtifactRepository.commit_version_and_decision` versus dispatcher writes | Product persistence | converge | select one versioning transaction and remove the fixed-version duplicate projection path |
| root legacy `crypto_manual_alert` runtime | none in V2 | quarantine/remove | a second runnable product path makes deployment and maintenance ambiguous |

### 5.9 G0.1 Exit Decision

G0.1 is complete for the current dirty worktree. A reviewer can now identify:

- one production Graph: `graph/graph.py` exported by `langgraph.json:crypto_analysis`;
- one runtime assembly path: `graph/runtime.py`, with the research and market Agent roles;
- one Product admission path: `POST /api/v2/analysis` -> `ProductAnalysisService`;
- one deployed command path: `crypto_alert_v2.workers` -> `CommandDispatcher`;
- one execution-state authority: official Agent Server Thread/Run/checkpoint state;
- one product-state authority: Product PostgreSQL and `TaskView/ProductTask`;
- one streaming path: `@langchain/react useStream` through the same-origin Agent BFF;
- all currently observed duplicate/orphan candidates: `graph/nodes`, parallel Artifact
  persistence, legacy worker entry, fixture graph/test routes, root legacy runtime and
  unfinished/redirected frontend routes.

G0.1 produced an audit result, not runtime proof. The current tree remains `PARTIAL` and
not production ready. G0.2 starts with the actual stack stopped except for Product
PostgreSQL and must fix startup/mainline blockers before collecting zero-mock evidence.

### 5.10 G0.2 Local Stack Readiness Map

The current Compose topology is:

```text
product-postgres + agent-postgres + langgraph-redis
  -> migrate -> internal-jwt-keys -> development-bootstrap
  -> langgraph-api (official Agent Server + mounted Product app)
  -> langgraph-api-readiness
  -> command-worker
  -> frontend (Next.js Product BFF and /work)
```

Host ports are loopback-only: Agent Server `8123` and frontend `3001` by default.
The Product API is mounted inside the Agent Server custom HTTP app, so the frontend
Product base URL is `/app` and the browser-facing BFF remains the only browser entry.

The current start script builds the backend/frontend images, builds the official Agent
Server image from `backend/langgraph.json`, verifies the locked base image, then runs
`docker compose up --detach --wait`. The readiness map is technically complete, but the
following gaps remain before it can be called a real proof:

- `verify_agent_image.sh` previously required `:graph` while the source export is
  `:graph_factory`; this has now been corrected to the canonical export.
- Compose health checks prove process/readiness only; they do not prove OKX, Web Search,
  model output, worker liveness after startup or Product Artifact persistence.
- The worker has no Compose healthcheck and frontend only waits for `service_started`;
  a worker crash must be captured by the real request evidence, not inferred from frontend
  health.
- The existing mock/fixture Playwright suites and Agent-only probe are diagnostic only.
  G0.2 requires the external-server real Product suites with no route interception.

Only environment variable names were inspected for this map. Values remain secret and
are not recorded in this ledger.

## 6. G0 Execution Phases

### G0.1 Canonical Path Audit

Status: `completed` on 2026-07-16.

Deliverables:

- One import/runtime map from Product admission to Graph to UI.
- A file classification table: canonical, product boundary, test fixture, duplicate, or orphan.
- A list of every custom abstraction that overlaps an official capability.
- A decision for each overlap: keep with reason, replace with official API, or remove/quarantine.
- No feature expansion during this phase.

Exit gate:

- A reviewer can identify the one production Graph, one Agent factory path, one streaming path, one Product admission path and one persistence authority without reading the whole repository.

### G0.2 Main Vertical Slice

Status: `completed_local` on 2026-07-17. This is not hosted production proof.

Deliverables:

- Start the actual local stack.
- Submit one BTC/ETH/SOL analysis through Product API and the frontend.
- Verify real model/provider/evidence behavior, including typed failure behavior.
- Persist the model output, evidence, Artifact and Decision.
- Render readable content in `/work` and verify refresh recovery.
- Capture command, environment profile, correlation ID, screenshots and database assertions.

Exit gate:

- The main success path and one provider failure path pass on Desktop and Pixel 7 without route interception or raw JSON UI.

### G0.3 Framework Convergence

Status: `completed` on 2026-07-17 for the canonical source/dependency boundary.

Deliverables:

- Remove the orphan manual JSON Agent path.
- Decide whether market analysis should use `create_agent` or direct official structured model output.
- Decide whether restricted research needs Deep Agents. If yes, implement one narrow read-only research subgraph with explicit tools and permissions. If no, record a formal fallback decision to `create_agent`/LangGraph and remove the unused Deep Agents dependency.
- Make retry ownership explicit: graph/node, model middleware, or provider transport, with no accidental multiplication.
- Reduce Agent Server/Product coordination to a thin adapter and split oversized dispatcher/service responsibilities.

Exit gate:

- No custom code duplicates an official Agent Runtime capability.
- The framework choice is visible in a small number of obvious factory/graph files.
- Every remaining custom wrapper has an ADR or a direct product-boundary reason.

### G0.4 Product Completion

Only after G0.2 and G0.3 pass:

- Settings and encrypted notification destination integration/acceptance.
- Library and Artifact/Decision lineage.
- Retry and cancellation UX.
- Feedback persistence and UI.
- Run detail and historical recovery.
- Notification delivery and manual resend UI.

### G0.5 Production Gates

Only after the product path is stable:

- Hosted OIDC and trusted HTTPS.
- Persistent Agent Server restart/recovery.
- LangSmith/Langfuse real trace and secret canary proof.
- Desktop/mobile Playwright, DOM, accessibility and visual regression.
- Backup/restore, migration rollback, key rotation, load/SLO, security scan, SBOM/signing and release attestation.

## 7. Execution Rules

- Work on one phase at a time; no parallel peripheral feature work while G0.2 is red.
- Every execution turn updates this ledger with date, phase, files, tests, evidence and residual risks.
- A test marked skip is recorded as unproved, never as passed.
- A local development proof is not a hosted production proof.
- A fixture or intercepted browser test is not a zero-mock real-flow proof.
- No code commit or push until the user explicitly permits it.
- Do not modify protected user-owned files without an explicit decision.
- Do not read or print secrets. Evidence records only names, hashes, statuses and redacted identifiers.
- If three consecutive execution turns do not move the current phase's exit gate, stop and report the blocker instead of expanding scope.

## 8. Execution Entry Format

Every future update must use this compact record:

```text
Date:
Phase:
Objective:
Files changed:
Tests run:
Evidence produced:
Current result: RED / GREEN / PARTIAL / BLOCKED
Remaining risk:
Next single action:
```

## 9. Decision Log

### 2026-07-16: Pause and recalibrate

- User paused the global M1-M6 goal because execution appeared to drift into deep infrastructure work.
- Review found that the normative plan and actual status ledger were not synchronized.
- Review found that the latest notification destination work was not represented in `15-v2-implementation-status.md`.
- Decision proposed: retain the final normative goal, add G0 mainline recovery, and require user confirmation before resuming.

### 2026-07-16: Final delivery goal activated

- User approved replacing the paused goal with the complete production-delivery goal.
- The active goal preserves the original M1-M6 scope and makes G0.1, G0.2 and G0.3
  mandatory mainline recovery gates.
- G0 completion does not complete the active goal; execution continues through product,
  deployment, security, recovery and zero-mock desktop/mobile release gates.
- Current phase: G0.1 Canonical Path Audit.
- Commit and push remain prohibited until the user explicitly authorizes them.

## 10. User Confirmation

Approved decision:

> Execute G0.1 -> G0.2 -> G0.3 inside the complete production-delivery goal. Do not resume peripheral M5/M6 work until the mainline and framework convergence exit gates pass.

Execution resumed with G0.1. Every subsequent phase transition and implementation slice
must update this ledger with current-worktree evidence.

## 11. Execution Updates

### 2026-07-16: G0.1 complete, G0.2 startup/mainline repair started

Date: 2026-07-16 Asia/Shanghai  
Phase: G0.2  
Objective: Remove immediate mainline blockers and prepare the real local stack.  
Files changed: `api/__init__.py`, `graph/graph.py`, `graph/runtime.py`,
`providers/okx.py`, `tools/v2/verify_agent_image.sh`, and focused contract/integration
tests.  
Tests run: `APP_ENVIRONMENT=test uv run --project backend pytest
backend/tests/integration/test_okx_provider.py backend/tests/contract/test_analysis_graph.py
backend/tests/integration/test_interrupt_resume.py -q` -> `29 passed`; sanitized Graph
factory import without `APP_ENVIRONMENT` -> `graph_factory`.  
Evidence produced: G0.1 backend/frontend canonical maps, file classification, official
capability decisions and local Compose readiness map in this ledger.  
Current result: PARTIAL.  
Remaining risk: the real Compose stack has not yet been started; no real OKX/Search/model
request, Product Artifact persistence assertion or browser screenshot exists. The fork
Artifact uniqueness bug, production observability proof, external LangSmith/Langfuse proof
and remaining product/release work are still open.  
Next single action: run the corrected integration-stack startup and capture the first
honest readiness failure or success without calling a fixture result production proof.

### 2026-07-16: G0.2 real local slice exercised

Date: 2026-07-16 Asia/Shanghai  
Phase: G0.2  
Objective: Exercise the current source through the Product API, official local Agent
Server, durable worker and browser UI with a real model/provider configuration.  
Files changed: `Dockerfile` (uv cache/retry build hardening),
`graph/runtime.py` (honor `Settings.okx_base_url`), and the associated focused tests.  
Environment: isolated temporary PostgreSQL on loopback port `55435`, migrations through
`0011`, development bootstrap actor `dev-user`, current-source `langgraph dev` on
`8123`, current-source Next.js on `3001`, current-source Product worker. This is a local
development proof, not a hosted or production Agent Server proof.  
Tests run:

- `47 passed, 1 warning` for runtime readiness, Graph, and OKX contract suites;
- real model structured-output and capability tests: `2 passed`;
- real OKX provider tests for BTC/ETH/SOL: `3 failed` at the first ticker connection
  (`ConnectTimeout`/`Host is down`); Tavily test: `1 skipped` because the current process
  had no exposed `TAVILY_API_KEY`;
- one short real built-in Web Search request returned one verified HTTPS citation; a
  broader market-data search timed out and was recorded as failure;
- real Product `POST /app/api/v2/analysis` returned `202`, then Product GET reached
  `failed` with `provider_unavailable`, `provider=okx`, `web_evidence=[]`, and no Artifact;
- database assertions confirmed the submitted Chinese `query_text`, terminal failed Task,
  one failed Run, official run ID, and persisted typed provider error in `output_payload`;
- Playwright through the in-app browser observed the queued state, final readable failure
  state, refresh recovery, no raw JSON primary UI, no console errors, desktop full-page
  rendering, and `412x915` layout with `scrollWidth == clientWidth == 412`.

Evidence produced: real correlation IDs and task/run IDs are available in local command
output and the isolated database; values are not treated as release evidence until tied
to an immutable candidate. No secret values were printed.  
Current result: PARTIAL / RED for the success gate, GREEN for the honest provider-failure
path.  
Remaining risk: direct OKX, Binance and Bybit public endpoints are unreachable from this
machine without a configured proxy; the full Compose build is also currently blocked by
unstable Docker large-file downloads (`alembic` extraction `unexpected BufError`, then
an unresolved `uv`/BuildKit download). The current local Agent Server explicitly reports
it is in-memory development runtime and cannot be called production proof. The main
success Artifact, persisted Web Evidence, visual success path, fork projection fix and
production restart/deployment gates remain open.  
Next single action: make provider connectivity configurable and re-run the same real
vertical slice with a reachable exchange endpoint/proxy, or preserve the typed failure
and move provider fallback/hosted connectivity into the next implementation gate without
claiming G0.2 success.

### 2026-07-17: G0.2 zero-mock local success path completed

Date: 2026-07-17 Asia/Shanghai  
Phase: G0.2  
Objective: Re-run the canonical Product path with reachable real market and Web Search
providers, then prove model output, persistence, readable frontend projection and refresh
recovery in real browser viewports.  
Files changed: `backend/src/crypto_alert_v2/providers/search.py`,
`backend/tests/unit/test_search_parser.py`,
`frontend/tests/e2e-v2/real-product-flow.spec.ts`.  
Runtime: current source `langgraph dev` on `8123`, current source Product worker,
current source Next.js on `3001`, isolated PostgreSQL on `55435`, real OKX through the
configured local HTTP proxy, and explicitly selected `SEARCH_PROVIDER=duckduckgo` through
the configured local HTTP proxy. This is a local development proof, not hosted production
Agent Server proof.  
Tests run:

- `APP_ENVIRONMENT=test uv run --project backend pytest backend/tests/unit/test_search_parser.py backend/tests/contract/test_analysis_graph.py -q` -> `42 passed`;
- direct real DuckDuckGo provider smoke -> `8` verified public HTTPS results;
- direct real built-in `web_search` short probe -> `1` verified HTTPS citation;
- full real Product task `db5460ca-64d8-405a-ba1a-43ae1425d83e` -> `succeeded`;
- real Playwright `REAL_PRODUCT_E2E=1 PLAYWRIGHT_EXTERNAL_SERVER=1 PLAYWRIGHT_FRONTEND_BASE_URL=http://127.0.0.1:3001 npx playwright test tests/e2e-v2/real-product-flow.spec.ts --project=fixture-desktop --project=fixture-pixel-7` -> `2 passed (2.4m)`.

Evidence produced:

- Product Task `db5460ca-64d8-405a-ba1a-43ae1425d83e` and Run
  `7b12304e-8380-4aa0-9906-6edc4b853f86` are both `succeeded`;
- one exchange-native `market_snapshots` record was persisted for `BTC-USDT-SWAP`;
- two `web_evidence` records were persisted with `source=duckduckgo` and
  `parser_version=langchain-ddgs-v1`;
- one committed `analysis_report` Artifact, version `1`, and one Decision were persisted;
  the decision is `no_trade`, evidence sufficiency is `true`, and risk is allowed;
- Product GET returned the committed artifact and readable analysis projection;
- Desktop and Pixel 7 rendered `分析完成`, `暂不操作`, Evidence, Risk and two HTTPS source
  links; after reload both remained `分析完成`;
- both viewports had zero horizontal overflow, zero `<pre>` raw JSON blocks, no console
  errors and no HTTP 5xx responses. Generated screenshots are under
  `frontend/artifacts/playwright-real/`.

Implementation note: the original user query remains in `WebEvidence.query`; only the
outbound DuckDuckGo transport query is compacted to bounded English asset/context terms.
This fixes the observed DDG news endpoint `403` for long CJK URLs without fabricating or
discarding evidence. The first built-in Web Search timeout and first DDG failure remain
recorded as typed failed Tasks and were not overwritten by this success sample.  
Current result: GREEN for the zero-mock local success path; PARTIAL for the overall G0.2
release gate.  
Remaining risk: local `langgraph dev` is explicitly in-memory and cannot prove hosted
production Agent Server; the full Compose production topology, strict startup search
readiness, LangSmith/Langfuse external delivery, failure/restart recovery and G0.3
official-framework convergence remain open. Tavily was not configured. The broader
real-provider matrix and hosted deployment evidence remain open.  
Next single action: begin G0.3 framework-boundary audit from the successful canonical path,
starting with the duplicate hand-written Agent path and official `create_agent` /
structured-output ownership decision, while keeping the successful lineage as the fixed
regression baseline.

### 2026-07-17: G0.2 official built-in Web Search success gate completed

Date: 2026-07-17 Asia/Shanghai  
Phase: G0.2  
Objective: Replace the diagnostic DuckDuckGo run with the formally selected built-in
Web Search provider and prove the same real Product path under the approved provider
selection policy.  
Files changed: `backend/src/crypto_alert_v2/providers/search.py`,
`backend/tests/unit/test_search_parser.py`,
`frontend/tests/e2e-v2/real-product-flow.spec.ts`.  
Runtime: `APP_ENVIRONMENT=development`, explicit `SEARCH_PROVIDER=builtin_web_search`,
current-source `langgraph dev` on `8123`, Product worker, Next.js on `3001`, isolated
PostgreSQL on `55435`, real OKX through the configured local HTTP proxy and the configured
OpenAI-compatible model endpoint.  
Tests run:

- real full-query built-in Web Search smoke after transport-query compaction -> `4`
  verified HTTPS citations;
- `APP_ENVIRONMENT=staging` capability/readiness probe -> `ready`, selected provider
  `builtin_web_search`, citations `1`, tool calling/structured output/streaming/usage
  reporting all `true`;
- `APP_ENVIRONMENT=test uv run --project backend pytest backend/tests/unit/test_search_parser.py backend/tests/contract/test_analysis_graph.py -q` -> `43 passed`;
- `npm run typecheck` -> passed;
- `npm run lint` -> passed;
- real Product Playwright with `REAL_PRODUCT_E2E=1`, external server,
  `fixture-desktop` and `fixture-pixel-7` -> `2 passed (2.5m)`.

Evidence produced:

- latest real Desktop task `7ee09271-d533-4d5c-bd00-ad8eedb383a0` and latest real Pixel 7
  task `a9dd0599-a5c3-4799-b5c7-a9618437a107` both have `Task.status=succeeded` and
  `Run.status=succeeded`;
- each latest task has `4` persisted `WebEvidence` rows with
  `source=openai_builtin_web_search`, one committed Artifact and one Decision;
- Product GET and the frontend show the committed analysis, natural-language `no_trade`,
  Evidence, Risk and the persisted HTTPS sources;
- both viewports passed final status, cited-source, no-raw-JSON, no-5xx, no-console-error,
  no-horizontal-overflow and refresh-recovery assertions. Visual artifacts are under
  `frontend/artifacts/playwright-real/` and were inspected for desktop and Pixel 7.

Implementation note: the outbound search request is compacted to a bounded query such as
`current BTC cryptocurrency market macro news` when the original request is long or CJK;
the original user query remains in the Research Agent prompt and `WebEvidence.query`.
This keeps the official built-in provider, avoids a silent provider fallback, and fixes the
observed gateway timeout caused by sending a broad multi-intent query to the search call.
The earlier typed built-in timeout and DDG diagnostic failures remain immutable failed
Task samples; they were not overwritten.  
Current result: GREEN for the G0.2 zero-mock local success gate and approved built-in
provider readiness; PARTIAL for the complete production-delivery objective.  
Remaining risk: the running Agent Server is still `langgraph dev` in-memory and therefore
not hosted production proof; Compose production topology, persistent Agent Server
checkpoint/restart evidence, LangSmith/Langfuse external delivery, G0.3 duplicate-runtime
convergence, HITL/retry/fork and the remaining M1-M6 product/release gates remain open.  
Next single action: execute G0.3 against the now-fixed success baseline, starting with a
read-only inventory of every graph/agent entry point and an explicit official-framework
ownership map before changing peripheral product scope.

### 2026-07-17: G0.3 framework boundary inventory and research decision

Date: 2026-07-17 Asia/Shanghai  
Phase: G0.3  
Objective: Freeze the canonical Graph/Agent boundary after the real success baseline and
prevent a second hand-written runtime from becoming reachable again.  
Files changed: `docs/v2/implementation/2026-07-17-g03-framework-boundary.md`,
`backend/tests/contract/test_canonical_framework_boundary.py`. No protected legacy node
files were modified or deleted.  
Evidence produced:

- `backend/langgraph.json` registers exactly one Agent Server graph:
  `crypto_alert_v2.graph.graph:graph_factory`;
- canonical orchestration is one LangGraph `StateGraph`; only
  `agents/market_analysis.py` and `agents/research.py` import official LangChain
  `create_agent`;
- canonical agents use `ToolStrategy(MarketAnalysis/ResearchBundle)` and do not parse
  model JSON text;
- no canonical production module imports `crypto_alert_v2.graph.nodes`;
- local installed `deepagents==0.6.12` inspection confirms the default official harness
  includes filesystem, `execute` and `task`; the formal release decision is one narrow
  official LangChain `create_agent` Research Harness, with no dual Deep Agents runtime;
- legacy `backend/src/crypto_alert_v2/graph/nodes/` remains quarantined and protected;
  it contains an old manual JSON parser path and is not a production entry point.

Tests run: `APP_ENVIRONMENT=test uv run --project backend pytest
backend/tests/contract/test_canonical_framework_boundary.py -q` -> `5 passed`; the
previous G0.2 real built-in success and readiness evidence remains the regression baseline.  
Current result: PARTIAL for G0.3.  
Remaining risk: the protected legacy directory still exists in the open-source worktree,
the locked but inactive Deep Agents dependency still needs a coordinated lockfile cleanup
or an approved restricted harness implementation, and hosted Agent Server/production
deployment proof is not done.  
Next single action: audit the remaining M1-M6 implementation against the canonical
ownership map, starting with missing product surfaces and real command/recovery paths;
do not add another Agent runtime while doing so.

### 2026-07-17: M5 core product surfaces, Artifact lineage and Retry vertical slice

Date: 2026-07-17 Asia/Shanghai  
Phase: M5 core product path  
Objective: Close the first real product-history slice after the G0.2 success baseline,
then remove two backend correctness blockers that would make Library/Retry/Fork unsafe:
owner-scoped Run/Artifact reads, versioned Artifact writes, and durable retry lineage.

Files changed in this slice:

- Backend API/schema/service: `backend/src/crypto_alert_v2/api/app.py`,
  `backend/src/crypto_alert_v2/api/schemas.py`,
  `backend/src/crypto_alert_v2/api/service.py`;
- Persistence/dispatcher: `backend/src/crypto_alert_v2/persistence/models.py`,
  `backend/src/crypto_alert_v2/persistence/repositories.py`,
  `backend/src/crypto_alert_v2/commands/dispatcher.py`,
  `backend/alembic/versions/0012_run_retry_lineage.py`;
- Frontend API/BFF/UI: `frontend/src/lib/api/product-client.ts`,
  `frontend/src/lib/api/product-proxy.ts`,
  `frontend/src/lib/schemas/product-api.ts`,
  `frontend/src/components/primary-navigation.tsx`,
  `frontend/src/app/library/page.tsx`,
  `frontend/src/features/library/artifact-library-surface.tsx`,
  `frontend/src/app/runs/[runId]/page.tsx`,
  `frontend/src/features/runs/run-detail-surface.tsx`,
  `frontend/src/features/work/work-surface.tsx`;
- Tests: Product API/persistence/dispatcher contracts and integration tests,
  `frontend/tests/e2e-v2/real-library-run-detail.spec.ts` and the related frontend
  client/proxy tests.

Implemented behavior:

- `GET /api/v2/runs/{run_id}` returns an owner-scoped `RunDetailView` containing the
  selected Run summary and the same typed Task projection used by Work;
- `GET /api/v2/artifacts` returns persisted ArtifactVersion summaries with Task/Run
  lineage, symbol, horizon, action, schema and status; the Library navigation is no
  longer disabled;
- Run Detail uses the current Next dynamic-route Promise contract and renders actual
  market snapshot, Web Evidence, Risk, Action and HTTPS source links without raw JSON;
- successful retries/forks reuse the unique Task Artifact and append ArtifactVersion
  and Decision versions atomically; a real PostgreSQL test proved versions `1,2` for
  two successful Runs and one Artifact row;
- `POST /api/v2/tasks/{task_id}/retry` admits only failed/blocked Tasks, creates a
  durable retry command and immutable Run with `retry_of_run_id`, and replays by the
  same idempotency key without creating another Run;
- the Work failure action calls Product Retry for the existing Task instead of creating
  a disconnected new analysis Task;
- old `/runs/[traceId]` was removed because Next rejects two dynamic slugs for the same
  path; the canonical route is `/runs/[runId]`.

Evidence:

- Backend Product API and persistence contracts: `137 passed`;
- real PostgreSQL Artifact/dispatcher slice before and after the retry addition:
  Artifact/fork version regression `1 passed`, Retry lineage regression `1 passed`,
  and the existing real dispatcher slice `54 passed`;
- frontend client/proxy/unit slice: `272 passed`; `npm run typecheck` and `npm run lint`
  passed;
- real API reads through the running Product BFF returned 200 for `/runs`,
  `/artifacts` and `/runs/{run_id}`;
- real Retry Task `021f37cb-462d-4e85-bc24-109a67bbca7c` was admitted with a real
  idempotency key and executed by the current Worker and official development Agent
  Server. The original Run `e216d75f-e31d-4db1-91ea-da88b116d2e5` is `failed`; the
  retry Run `b7d48d09-4454-4b28-84e6-d23818ca54cb` is `blocked` with
  `retry_of_run_id` pointing to the original Run, a persisted Artifact and 3 Web
  Evidence rows. The terminal block is an honest `risk_gate_blocked` result, not a
  success substitution. Replaying the same idempotency key returned the same Task
  and did not create a third Run;
- real Playwright `REAL_LIBRARY_E2E=1` against the running local Product/Agent/
  PostgreSQL stack: `2 passed` on Desktop `1440x1000` and Pixel 7 `412x915`. The test
  asserts Library -> Run Detail continuity, actual Evidence/Risk content, no `<pre>`
  raw JSON, axe violations `[]`, no horizontal overflow, no unnamed controls, no
  console errors and no 5xx responses. Screenshots are under
  `frontend/artifacts/playwright-real/real-library-run-detail-fixture-desktop.png`
  and `real-library-run-detail-fixture-pixel-7.png` and were visually inspected.

Failure discovered and fixed during the gate:

- Next 16 requires `params` to be awaited for dynamic routes; the first browser run
  exposed `/runs/undefined` and failed loudly. `frontend/src/app/runs/[runId]/page.tsx`
  now awaits the route params. The second Desktop/Pixel 7 run passed.
- Deleting stale `.next` while Turbopack was running corrupted its development cache;
  the V2 service group was restarted without deleting PostgreSQL data. This is local
  development process state, not a production success claim.

Current result: GREEN for this local product-history and retry vertical slice; PARTIAL
for the full V2 production objective.  
Remaining gaps: Artifact detail/version detail, Home/Watchlist, Feedback, `cancel_run`,
notification empty-first polling, real hosted OIDC/HTTPS, licensed persistent Agent
Server restart durability, LangSmith/Langfuse external traces, backup/restore,
security/SLO/SBOM/release gates and the remaining M1-M6 scope remain open. The current
development Agent Server is explicitly in-memory and is not production proof.

Next single action: finish the notification empty-first polling regression proof, then
continue the remaining M5/M6 product and operational gates without weakening the G0.3
framework boundary or treating local development Agent Server evidence as production
durability.

### 2026-07-17: Artifact detail lineage, migration round-trip and notification polling fix

Date: 2026-07-17 Asia/Shanghai  
Phase: M5 product history and async UX hardening  
Objective: Make persisted Artifact versions directly inspectable through an owner-scoped
Product API and readable frontend route, prove the retry migration is reversible, and
prevent a first empty notification response from permanently stopping observation.

Implementation:

- Added `GET /api/v2/artifacts/{artifact_id}?version_number=N` with tenant/workspace/
  owner/task/run-scoped reads for Artifact metadata, version history, typed content,
  Decision, market snapshots and Web Evidence.
- Added the frontend `/artifacts/[artifactId]` route, strict Zod schema/client path,
  Library deep links, version navigation and human-readable report/evidence/risk/
  decision rendering. The page does not expose raw JSON.
- Added the `0012_run_retry_lineage` PostgreSQL SQL contract and real
  `upgrade -> downgrade -> upgrade` migration test.
- Fixed notification observation so a requested notification with an empty first
  response continues polling after the Task reaches `succeeded`, with a bounded
  20-attempt window and an explicit unavailable state after the bound. Active delivery
  and manual-resend states continue to use the existing polling policy.

Files changed:

- Backend API and persistence contracts: `backend/src/crypto_alert_v2/api/app.py`,
  `backend/src/crypto_alert_v2/api/schemas.py`, `backend/src/crypto_alert_v2/api/service.py`,
  `backend/tests/contract/test_product_api.py`,
  `backend/tests/contract/test_persistence_schema.py`,
  `backend/tests/integration/test_product_analysis_service.py`,
  `backend/tests/integration/test_interrupt_pause_migration.py`.
- Frontend route and product surface: `frontend/src/app/artifacts/[artifactId]/page.tsx`,
  `frontend/src/features/artifacts/artifact-detail-surface.tsx`,
  `frontend/src/lib/api/product-client.ts`, `frontend/src/lib/api/product-proxy.ts`,
  `frontend/src/lib/schemas/product-api.ts`,
  `frontend/src/features/library/artifact-library-surface.tsx`,
  `frontend/src/features/notifications/notification-status.tsx`,
  `frontend/src/features/work/work-surface.tsx`, `frontend/src/app/globals.css`.
- Browser/unit gates: `frontend/tests/e2e-v2/real-library-run-detail.spec.ts`,
  `frontend/tests/unit/notification-status.test.ts`.

Evidence:

- Real PostgreSQL Artifact service test passed and proved one owner-scoped detail with
  one version, one Decision, one market snapshot and one Web Evidence row; a second
  user received no Artifact detail.
- Real PostgreSQL migration test passed: `0012` upgraded, downgraded to `0011`, and
  upgraded again; the retry column and scoped foreign key were present after the final
  upgrade.
- Product API contracts and targeted integration tests passed. The complete prior
  real PostgreSQL dispatcher/product slice passed `88 passed`; the previously observed
  concurrent-registration test was rerun 12 times and the complete slice passed again.
- Frontend `npm run typecheck`, `npm run lint`, and unit tests passed with `272 passed`.
- Real Playwright against the running local Product/Agent/PostgreSQL stack passed on
  Desktop `1440x1000` and Pixel 7 `412x915`: `2 passed`. The gate covered Library ->
  Artifact version detail, readable Evidence/Risk/Decision content, no raw `<pre>`,
  axe violations `[]`, no horizontal overflow, no unnamed controls, no console errors
  and no 5xx responses. Screenshots are under
  `frontend/artifacts/playwright-real/real-library-artifact-detail-fixture-desktop.png`
  and `frontend/artifacts/playwright-real/real-library-artifact-detail-fixture-pixel-7.png`;
  both were visually inspected.

Current result: GREEN for this local Artifact history and notification state slice;
PARTIAL for the complete V2 production objective.

Remaining gaps are intentionally open: Home/Watchlist, Feedback,
notification worker delivery/real receipt and empty-first real outbox E2E, hosted OIDC/
HTTPS, licensed persistent Agent Server restart/recovery, real LangSmith/Langfuse traces,
backup/restore, migration rollback in the deployment profile, DB roles, security/SLO/
load gates, key rotation, SBOM/signing, release attestation and the remaining M1-M6
scope. Local development Agent Server and fixture/diagnostic evidence must not be used
to close those gates.

### 2026-07-17: Durable cancel_run and retry-after-cancel vertical slice

Date: 2026-07-17 Asia/Shanghai  
Phase: M5 command lifecycle  
Objective: Implement the specified Product `cancel_run` contract so a selected Run can
be cancelled through durable Product admission and the official Runs cancel adapter
without conflating it with `cancel_task`.

Implemented behavior:

- Added owner-scoped `POST /api/v2/runs/{run_id}/cancel` with a required idempotency
  key; the Next BFF and typed Product client forward only this Product command route.
- Added durable `cancel_run` admission with target Run payload, lock ordering, command
  sequence, cancellation timestamp and replay by the same idempotency key.
- Dispatcher validates target Run lineage, uses the existing official
  `RemoteRunner.cancel` path, and terminalizes only the selected Run. Cancelling the
  latest Run makes the Task `cancelled`; historical Task/Run lineage remains queryable.
  `cancel_task` keeps its prior composite semantics, including queued Tasks with no
  remote Run.
- Retry admission permits a Task whose latest Run was cancelled by a dispatched
  `cancel_run`, creates a new immutable queued Run and records `retry_of_run_id`.
- Run Detail exposes the cancel control only for queued/running/waiting Runs and reloads
  authoritative Product state after the command response.

Evidence:

- Real PostgreSQL `test_cancel_run_preserves_task_history_and_allows_retry` passed. It
  proves cross-owner non-disclosure, running Run cancellation, command persistence,
  terminal Run projection, same-key idempotent replay, and a subsequent retry Run linked
  by `retry_of_run_id`.
- Complete real PostgreSQL Artifact/dispatcher/Product integration after the change:
  `89 passed`, including queued `cancel_task`, live cancellation, HITL, retry, fork and
  dispatcher lease/recovery coverage.
- Focused Product API/persistence contracts passed `139`; frontend Product client/BFF
  route tests, typecheck and lint passed; frontend unit suite passed `274 passed`.

Current result: GREEN for the local durable cancel/run-retry slice; PARTIAL for the
complete production objective. The local development Agent Server remains in-memory and
is not restart durability evidence. Remaining gaps include Home/Watchlist, Feedback,
real notification outbox delay/receipt E2E, hosted OIDC/HTTPS, licensed persistent
Agent Server restart/recovery, real LangSmith/Langfuse traces, backup/restore,
security/SLO/load, key rotation, SBOM/signing, release attestation and the remaining
M1-M6 gates.

### 2026-07-17: Owner-scoped Feedback persistence and real Run Detail loop

Date: 2026-07-17 Asia/Shanghai  
Phase: M5 product learning loop  
Objective: Close the normative Feedback path from a persisted Run/Artifact version to a
readable user interaction without introducing cross-owner writes or duplicate records.

Implemented behavior:

- Added Product PostgreSQL `feedback` entity and Alembic `0013_feedback` with rating
  constraints, owner/run uniqueness, workspace idempotency and Artifact Version linkage.
- Added `POST /api/v2/runs/{run_id}/feedback` with actor scope, idempotency replay and
  conflict protection for a second feedback on the same owner Run; Run Detail reads the
  persisted feedback together with the selected Run.
- Added strict frontend feedback schemas, Product client/BFF route, and Run Detail
  positive/negative controls with optional comment. After submission, the UI displays
  the recorded state and does not expose a second write control.

Evidence:

- Real PostgreSQL service test proves cross-owner non-disclosure, same-key replay,
  different-key conflict, Artifact Version linkage and Run Detail feedback projection.
- Migration test proves `0013_feedback` upgrade, downgrade to `0012`, and re-upgrade;
  the owner/run uniqueness constraint is present after re-upgrade.
- Combined real PostgreSQL Product/dispatcher/migration regression: `101 passed`.
- Frontend typecheck/lint passed and unit suite passed `276 passed`.
- Real Playwright against the running local Product/Agent/PostgreSQL stack passed on
  Desktop `1440x1000` and Pixel 7 `412x915`: `2 passed`. The test used the real Library
  -> Artifact -> Run Detail path, submitted feedback once through the real BFF/API and
  database, then verified the second viewport rendered the persisted `已记录` state.
  The page retained zero axe violations, no raw `<pre>` JSON, no horizontal overflow,
  no unnamed controls, no console errors and no 5xx responses.

Current result: GREEN for the local Feedback persistence and UI loop; PARTIAL for the
complete V2 production objective. Home/Watchlist, hosted identity/runtime durability,
real LangSmith/Langfuse traces, notification delivery receipts, backup/restore,
security/SLO/load, key rotation, SBOM/signing, release attestation and other M1-M6
production gates remain open.

### 2026-07-17: Home/Watchlist Product aggregation and responsive browser proof

Date: 2026-07-17 Asia/Shanghai  
Phase: M5 product surface closure  
Objective: Close the owner-scoped Home/Watchlist slice through the real Product
database and browser without inventing market prices or exposing internal state.

Implemented behavior:

- Added owner/tenant/workspace-scoped `watchlist_items` persistence with the
  `0014_watchlist` Alembic migration, symbol uniqueness and lookup index.
- `provision_actor()` creates the supported BTC/ETH/SOL watchlist rows for a newly
  provisioned local actor; existing actors can add/remove symbols through the same
  Product service.
- Added typed `GET /api/v2/home`, `PUT /api/v2/watchlist/{symbol}` and
  `DELETE /api/v2/watchlist/{symbol}` projections. Home aggregates only persisted
  watchlist rows, latest persisted MarketSnapshot values, active Tasks, Inbox count
  and recent Artifact reports. Missing snapshots render an explicit empty state.
- Added the frontend `/home` surface, navigation entry, strict Zod Home schema,
  Product client and same-origin BFF routes. The UI renders readable market/task/
  report projections and never renders raw Graph JSON.
- Found and fixed a real browser-only `405` during the first mutation attempt: the
  BFF allowlist accepted `PUT/DELETE`, but the Next catch-all route exported only
  `GET/PATCH/POST`. The route now exports the two mutation handlers as well.

Files changed in this slice:

- Backend: `backend/src/crypto_alert_v2/api/app.py`,
  `backend/src/crypto_alert_v2/api/service.py`,
  `backend/src/crypto_alert_v2/api/schemas.py`,
  `backend/src/crypto_alert_v2/persistence/models.py`,
  `backend/alembic/versions/0014_watchlist.py`.
- Frontend: `frontend/src/app/home/page.tsx`,
  `frontend/src/features/home/home-surface.tsx`,
  `frontend/src/components/primary-navigation.tsx`,
  `frontend/src/app/api/product/[...path]/route.ts`,
  `frontend/src/lib/api/product-client.ts`,
  `frontend/src/lib/api/product-proxy.ts`,
  `frontend/src/lib/schemas/product-api.ts`, `frontend/src/app/globals.css`.
- Contracts/tests: Product API and persistence schema contracts, migration SQL
  contract, Product client/BFF tests.

Evidence:

- Real local Product PostgreSQL was upgraded from `0013_feedback` to
  `0014_watchlist`; `alembic current` reports `0014_watchlist (head)`. Migration SQL
  contract and Product API/persistence contracts passed: `144 passed`.
- Frontend `npm run typecheck`, `npm run lint`, and the full unit suite passed:
  `278 passed`.
- Real browser against the running local Next/Product/PostgreSQL stack rendered seven
  persisted reports and the real BTC snapshot (`64,108.5`) on Desktop `1280x720`.
  DOM checks found no `<pre>` raw JSON, no horizontal overflow, zero unnamed buttons,
  four Home regions and no console errors.
- Real mutation proof removed BTC from the owner watchlist (`3 / 3 -> 2 / 3`),
  rendered the `关注 BTC` recovery state, then re-added it and verified
  `3 / 3` without a failure alert. This restored the local actor state after the
  test.
- Real Pixel 7 viewport `412x915` rendered Home, Watchlist and Recent Reports with
  `body.scrollWidth == innerWidth`, zero unnamed buttons, zero `<pre>` blocks and no
  console errors. The responsive navigation contains six bounded items.

Current result: GREEN for the local Home/Watchlist Product and responsive UI slice;
PARTIAL for the complete V2 production objective. This does not prove hosted OIDC/
HTTPS, production Agent Server durability, real LangSmith/Langfuse traces, real
notification receipts, or the remaining M1-M6 release gates.

Next single action: return to G0.2 mainline proof and close the remaining real
provider/model input correctness gaps (`query_text` and requested `horizon`) before
adding further peripheral surfaces.

### 2026-07-17: Final production-delivery goal reset

This entry replaces the previous broad, pause-prone execution framing with the
following operational goal:

> 完成 crypto-manual-alert-v2 的最终生产可交付版本。以真实用户从前端发起一次分析任务为起点，打通 Product API、PostgreSQL、Worker、官方 LangGraph Agent Server、真实 OKX、Web Search、模型结构化输出、Evidence/Risk/Action/Artifact 持久化、HITL/取消/失败恢复，并在前端以可读的业务内容完成展示；随后补齐多用户租户隔离、任务生命周期、通知、观测、恢复、部署和发布安全门禁，最终以真实环境零 Mock 自动化证据验收。任何未通过的链路必须显式记录为未完成，不能用 fixture、skip、local-only 或 raw JSON 页面替代生产交付证明。

Execution gates:

- `G0.1` Baseline freeze: identify the canonical path, runtime topology,
  unfinished requirements and evidence boundary. Every execution stage updates
  this ledger and `15-v2-implementation-status.md` when the status matrix changes.
- `G0.2` Mainline hard gate: prove fresh success and failure paths from the real
  frontend through Product admission, durable task/run state, Worker and the
  official Agent Server, including the requested `query_text` and `horizon` in
  the actual Search/OKX requests. Persist and render readable analysis,
  evidence, risk, action and artifact data. Include refresh recovery, cancel and
  at least one real HITL branch. No peripheral expansion is accepted before this
  gate is green.
- `G0.3` Framework boundary gate: maintain one canonical LangGraph StateGraph
  and use official LangChain agent, structured-output, HITL, streaming and
  Agent Server boundaries. Deep Agents/Research and existing private runtimes
  require an explicit ADR decision to retain, replace or quarantine; no new
  duplicate runtime abstraction may be added.
- `M1-M6` Production closure: complete multi-user authorization and tenant
  isolation, task lifecycle controls, retry/fork/library/settings/feedback/
  watchlist, notification Outbox and delivery receipts, LangSmith/Langfuse
  traces, durable Agent Server and Worker recovery, backup/restore, migration
  rollback, key rotation and deployment configuration.
- `Release` Final gate: pass real PostgreSQL and external provider/model tests,
  zero-mock Desktop and Pixel 7 Playwright flows, DOM/a11y/visual regression,
  failure injection, load/SLO, security, SBOM, signing and release-attestation
  checks. Only then may the project be called production ready; until then no
  commit or push is performed without explicit user authorization.

Current target status: `active`, G0.1/G0.2-local/G0.3 complete, M5-M6 and
hosted release gates in progress, overall delivery status `PARTIAL`. The target
is not complete until every gate above has reviewable evidence.

### 2026-07-17: G0.2 fresh zero-mock mainline proof and HITL projection repair

Phase: `G0.2` local real-mainline hard gate

Fresh evidence collected against the running local stack:

- `REAL_PRODUCT_E2E=1` Product success flow passed in both Playwright projects:
  Desktop `1440x1000` and Pixel 7 `412x915`; result `2 passed (3.2m)`. Each test
  created a new Product task through the frontend, waited for the official
  Agent stream and Worker projection, reloaded the persisted task, and verified
  readable committed analysis, Evidence, Risk, a cited HTTPS source, no raw
  `<pre>` JSON, no horizontal overflow, no unnamed controls, no console errors
  and no 5xx responses.
- PostgreSQL confirmed the two fresh tasks as `succeeded`, with request payloads
  containing the full user query and `horizon=4h`, Run output Artifact status
  `committed`, and four persisted `web_evidence` rows per Run. The stored
  Evidence query includes the original user query, `Asset: BTC`, and
  `Analysis horizon: 4h`; this proves the query is not discarded before Search.
- Real durable cancellation passed in Desktop and Pixel 7: `2 passed (9.0s)`.
  Each flow used exactly one Product task cancel write, no browser-side official
  Run write, and reached the persisted `cancelled` projection without 5xx.
- A real Search timeout produced a persisted `research_unavailable` failure.
  Opening that task directly in `/work?task=...` rendered `分析失败` with one
  readable failure panel, zero raw JSON blocks, zero horizontal overflow and no
  console errors. The timeout is recorded as a failure, not converted to fake
  success.
- Real OKX typed provider proof passed with the same explicit local proxy used by
  the running stack: `3 passed in 6.14s` for BTC/ETH/SOL. The independent direct
  run without the proxy failed with connect timeout/host-down errors; this is
  recorded as an environment boundary, not hidden. Contract coverage still
  verifies `horizon=4h -> bar=4H` and the graph passes the requested horizon to
  the provider.
- HITL required-policy proof initially found a real API boundary defect: the
  database stored canonical approve responses without `edits`, but FastAPI's
  response model reintroduced `edits: null`. Added `PublicReviewResponse` at the
  Product API response boundary, preserving request/Worker payloads while
  omitting absent optional response fields. Focused backend contract and Ruff
  checks passed (`23 passed`; all checks passed).
- After the fix, fresh real HITL approval passed independently on Desktop and
  Pixel 7 (`1 passed` each). Both tasks entered `waiting_human`, were approved
  through the Product API, rendered the responding state without `edits:null`,
  and finished with a persisted committed Artifact. The temporary local
  workspace review policy was restored from `required` to `bypass` afterward.

G0.2 local hard-gate result: `GREEN` for fresh success, failure projection,
refresh recovery, cancel, root HITL, real PostgreSQL persistence, real OKX/search/
model execution and responsive browser evidence. This is not a final production
release result: the stack still uses the local development Agent Server, local
proxy network exit and development identity. Hosted OIDC/HTTPS, licensed durable
Agent Server restart/recovery, direct/hosted provider availability, LangSmith/
Langfuse fresh traces and the remaining M1-M6 release gates remain open.

Next phase: `G0.3` official framework-boundary audit and ADR closure. Do not add
new product surfaces until the canonical LangGraph/LangChain/Agent Server
boundary, private runtime quarantine decisions and Deep Research fallback are
documented and verified.

### 2026-07-17: G0.3 canonical framework convergence completed

Phase: `G0.3` official framework boundary

Architecture decision and source convergence:

- Accepted ADR 0009. The release has one Agent Server registration,
  `crypto_alert_v2.graph.graph:graph_factory`, backed by one canonical LangGraph
  `StateGraph`.
- Market analysis and Research are the only two official LangChain agent
  factories. Both use `create_agent` with typed `ToolStrategy` structured output;
  canonical code does not parse model text as JSON.
- Research remains a bounded citation-extraction Agent over provider-owned
  evidence. `create_deep_agent` is not activated because the current product has
  no subagent, filesystem, execution or long-context requirement that justifies
  its broader middleware and permission surface.
- Removed inactive `deepagents` from `backend/pyproject.toml` and `backend/uv.lock`,
  synchronized the environment, and removed the unused transitive packages.
- Deleted the complete orphan `backend/src/crypto_alert_v2/graph/nodes/` manual
  runtime. Framework contracts now fail if that directory, its imports, a second
  Agent factory, free-text model JSON parsing, active `create_deep_agent`, or the
  inactive release dependency returns.

Probe and regression evidence:

- Canonical framework/dependency guards: `9 passed`; Ruff passed.
- Authenticated official Agent Server probe passed 401/403/200 resource access
  checks and verified registration of the `crypto_analysis` assistant. The probe
  now uses a process-local notification encryption key, a unique temporary config
  directory, bounded assistant readiness polling and file-based JSON parsing.
- Full backend suite: `616 passed, 128 skipped, 1 warning in 10.27s`.
- Frontend typecheck passed; frontend unit suite: `278 passed`.
- `bash -n tools/v2/probe_agent_server.sh` and `git diff --check` passed.

Compatibility defect kept open:

- With the locked official compatibility group `langgraph-api==0.11.0` and
  `langgraph==1.2.9`, both Assistant graph-introspection endpoint variants return
  HTTP 500 for the Runtime-context graph with `AttributeError: '_ReadRuntime'
  object has no attribute 'override'`.
- The resource-auth probe no longer treats that broken official endpoint as a
  topology gate. Assistant registration/resource authorization remain real probe
  assertions, while compiled top-level graph topology is enforced by local graph
  contracts. This is an unresolved upstream compatibility issue, not a fixed or
  hidden product error.

G0.3 result: `GREEN` for the canonical local source, dependency and official
framework ownership gate. The full V2 remains `PARTIAL`: the 128 skipped backend
tests are unproved, the Agent Server used for local product proof is still the
development runtime, and hosted OIDC/HTTPS, licensed restart durability, real
LangSmith/Langfuse traces, notification delivery receipts, recovery, SLO,
security supply-chain and release-attestation gates remain open.

Next phase: execute the remaining M5-M6 blockers in production-value order:
observability correlation and external delivery, notification/reconciliation and
process recovery, then backup/restore, deployment, security and release proof.

### 2026-07-17: Stable zero-mock mainline, observability boundary repair, and local release gates

Phase: `G0.2` real-mainline regression closure and M5/M6 local gates

Root cause found during a fresh real Desktop/Pixel 7 run:

- The Product API admitted the Task and the official Agent Server created a Run,
  but the canonical Graph failed before the first node with
  `TypeError: ProxyUser.model_dump() got an unexpected keyword argument 'mode'`.
- The failure was in the shared observability redaction boundary, not in OKX,
  Search, or the model. A second failure after the first compatibility fix showed
  that unrestricted `dataclasses.asdict()` attempted to deep-copy the official
  Runtime Store `PersistentDict`, which requires an internal filename.
- `langgraph dev` also hot-reloaded while tests changed backend files. The official
  CLI `--no-reload` option was used for the acceptance stack so a fresh Run could
  not be invalidated by test-file reloads.

Implemented repairs:

- Observability redaction now accepts model objects whose `model_dump` does not
  accept `mode="json"`, and dataclass conversion reads fields without recursive
  deep-copy.
- Root trace identity extraction now filters `configurable` through the existing
  correlation allowlist. Official Runtime/Store objects and other high-cardinality
  internals never enter trace metadata.
- Added regression coverage for legacy `model_dump` signatures and an intentionally
  non-serializable Runtime object. Focused observability/security matrix: `27 passed`.
- Projection reconciler now records official Run absence and backs off instead of
  returning a hot-loop success. Isolated real PostgreSQL reconciler/integration
  coverage: `5 passed` focused and `160 passed` full integration; the test fixture
  registration defect in `test_outbox_manual_resend.py` was also corrected.
- Supply-chain lock convergence completed: frontend PostCSS is `8.5.18`; Python
  DDGS is `9.14.3`, and archived `socksio` is absent from the lock graph.

Fresh evidence:

- Stable stack: official `langgraph dev --no-reload` on `8123`, current Product
  Worker, Next.js on `3001`, and PostgreSQL on `55435`; all health checks returned
  200. Product PostgreSQL was preserved.
- Strict real Product Playwright with `REAL_PRODUCT_E2E=1`, no route/mock injection,
  Desktop `1440x1000` and Pixel 7 `412x915`: `2 passed (2.6m)`.
- Both fresh Tasks are `succeeded`; each has one persisted market snapshot, four
  persisted Web Evidence rows, and a committed Artifact. The evidence excerpts
  have distinct lengths and hashes, and the UI proof checked distinct source
  summaries, Chinese rationale, HTTPS citations, no raw JSON, no 5xx responses,
  no console errors, zero axe violations, zero horizontal overflow and zero
  unnamed controls.
- The Artifact stores and the UI renders the model-produced analysis fields,
  including root-cause chain, why-not-opposite and invalidation. Explicit model
  name/provider-version fields are still absent from the Product audit schema and
  remain an observability/release gap; this is not claimed as complete provider
  identity proof.
- Backend hermetic suite: `654 passed, 136 skipped, 1 warning`. Skips remain
  unproved external/hosted gates and are not counted as green.
- Frontend typecheck, lint, unit and production build passed; frontend unit total
  is `282 passed`.
- Local supply-chain gate passed with `4/4` scans, `0` Python vulnerabilities,
  `0` Python adverse statuses, `0` frontend vulnerabilities, Python SBOM `119`
  components and frontend SBOM `574` unique components. Evidence directory:
  `/tmp/crypto-alert-v2-supply-final.1VVPhO`.

Evidence boundary and remaining work:

- The complete fixture Playwright command was not used as production proof. Its
  route-injected fixture suite contains stale Work expectations against the current
  Product UI and is explicitly fixture-only; the strict real Product gate above is
  the authoritative mainline result.
- The local stack remains the official in-memory development Runtime and local
  proxy network exit. Hosted OIDC/HTTPS, licensed persistent Agent Server restart,
  real LangSmith/Langfuse traces, notification receipts, production DB recovery,
  load/SLO, key rotation, signing and release attestation remain open.

Result: `G0.2 GREEN` for the fresh local zero-mock Product mainline and `PARTIAL`
for the overall V2 production objective. No commit or push was performed.

### 2026-07-17: Artifact provenance persistence and visual audit

Phase: `G0.2` auditability and browser regression follow-up

Implemented and verified:

- Added nullable `ArtifactProvenance` to the canonical domain Artifact and kept it
  inside the existing Artifact JSON content, so no migration is needed and old
  Artifacts without provenance remain readable.
- The Graph records safe provider identity fields for OKX, built-in Web Search,
  citation parser, model provider, model name and endpoint host. Secrets, query
  strings and complete URLs are excluded from the persisted value.
- The frontend schema/view model/result surface now renders a `数据溯源` section;
  the provenance field remains optional for historical Artifacts.
- Direct PostgreSQL inspection of the current `app.artifact_versions` rows shows
  fresh committed Artifacts with `model_name`, `model_provider`, `market_provider`,
  `search_provider`, `search_parser_version` and a sanitized endpoint host.
- A real Desktop Playwright run passed with the explicit `数据溯源` heading
  assertion, and the saved full-page screenshot visibly contains the section.

Regression boundary:

- Backend `ruff check`, frontend typecheck, lint, 282 frontend unit tests and
  production build passed after the compatibility change; the full backend suite
  remains `654 passed, 136 skipped, 1 warning`.
- The strict real Pixel 7 run was retried three times after the new assertion was
  added and failed before rendering a result because the real
  `builtin_web_search` provider returned `MissingProviderCitation`/`APITimeoutError`.
  The UI correctly showed `research_unavailable` and produced no report. This is
  recorded as an external provider-stability gap, not a green browser result.

Result: provenance is locally persisted and Desktop-rendered; G0.2 remains
`PARTIAL` for the new cross-viewport evidence until the real Pixel 7 provider
success is reproduced. The overall V2 remains `PARTIAL`; no commit or push was
performed.

### 2026-07-17: Real PostgreSQL and provider-gated regression follow-up

Phase: `M5` local external-boundary proof

- With `REAL_DATABASE_TESTS=1` and the running Product PostgreSQL, the complete
  backend integration suite passed: `160 passed in 27.85s`. This removes the
  database-only skips for notification/outbox, task projection, HITL, tenant
  isolation, fork lineage and reconciliation in this local topology.
- With `REAL_PROVIDER_TESTS=1 REAL_MODEL_TESTS=1` and the configured local HTTP
  proxy, `tests/real` passed `5 passed, 1 skipped in 88.50s`. The passed cases
  exercised real OKX, built-in Web Search and model behavior. The only skip was
  the explicit Tavily proof requiring an absent `TAVILY_API_KEY`.
- Frontend lint, backend Ruff for the touched runtime files and `git diff --check`
  passed after the provenance E2E assertion and documentation changes.

Boundary kept explicit:

- LangSmith and Langfuse credential status is safely reported as disabled and
  unconfigured in this environment. The official callback/tracer assembly is
  covered by contracts, but no external trace is claimed as passed.
- The real Pixel 7 Product E2E remains provider-flaky after three retries in the
  updated assertion run. Each failure was an actual built-in Web Search timeout
  and the Product correctly returned `research_unavailable`; no fixture or test
  retry was introduced.

Additional UI evidence:

- Using a real succeeded Run already persisted by the Product stack, a direct
  Pixel 7 historical Run-detail scan rendered the committed Artifact and
  `数据溯源` section with `overflow=0`, `unnamedControls=0`, zero axe violations,
  zero console errors and zero 5xx responses. Its screenshot is saved under
  `frontend/artifacts/playwright-real/real-run-detail-pixel-7.png`.
- This proves mobile rendering of a real committed result, but is intentionally
  not counted as a fresh Pixel 7 provider-success mainline run.

### 2026-07-17: Production Compose startup gate and fail-fast repair

Phase: `M6` local packaging/deployment boundary

- The pinned backend/frontend images and official `langgraph build` completed
  successfully. The image verifier ran against the locked
  `langchain/langgraph-api` base and the production frontend build completed.
- The first Compose startup exposed a real configuration defect:
  `NOTIFICATION_CREDENTIAL_KEY` was required by the production Product app but
  was absent from the Agent API/Worker environment. Compose now requires and
  passes that key and its version to both services. The local integration start
  script generates an ephemeral process-only key only when no key is supplied.
- The next diagnostic startup reached the official Postgres Runtime and real
  migration/Redis/Postgres initialization, then failed on the official license
  check because neither `LANGGRAPH_CLOUD_LICENSE_KEY` nor an authorized
  `LANGSMITH_API_KEY` is available. The start script now checks this before
  image/build work and exits `78` with a non-secret explanation.
- Deployment topology contracts passed `5 passed`; Compose config without the
  notification key fails as intended, and config with test-only injected key and
  license placeholder validates.

Result: local packaging and configuration fail-fast are improved and the failure
is now actionable. Licensed persistent Agent Server startup, restart durability,
hosted OIDC/HTTPS and external observability remain unproved until the required
LangGraph entitlement/credential is injected. No bypass was added.

### 2026-07-17: Model endpoint identity check

Phase: provider configuration audit

- The active local settings safely report model `gpt-5.5`, an OpenAI key present,
  and endpoint host `xixiapi.cc`; the configured key was not printed.
- A process-only probe against the user-supplied `https://codexai.club/v1`
  endpoint returned the real provider response `401 INVALID_API_KEY` for both
  structured model output and capability probing. The existing key and endpoint
  therefore cannot be swapped independently, and no configuration was changed.
- The existing endpoint remains the only locally verified model route. The
  `codexai.club` route requires its corresponding credential to be injected
  before it can be treated as a real provider candidate.

### 2026-07-17: Model execution audit persisted through the canonical path

Phase: `G0.2/G0.3` auditability completion slice

- Added a typed `ModelExecutionAudit` domain model and optional
  `ArtifactProvenance.model_audits`. The field is backward-compatible: old
  Artifacts without it remain readable and new artifacts default to an empty
  list when no audit metadata is available.
- The research collector and market analysis node now measure only the official
  `create_agent` invocation and read only LangChain's returned
  `messages[*].usage_metadata` and `messages[*].response_metadata.id`. The
  persisted fields are prompt version, observed AI-message count, nullable
  input/output/total tokens, monotonic latency and deduplicated observation IDs.
  Prompt text, structured content, request payloads, Authorization, cookies and
  credentials are not persisted or displayed by this audit helper.
- The canonical state path appends research first and market analysis second;
  the committed Artifact stores the same order in `provenance.model_audits`.
  The Product API Zod boundary, analysis view model and `数据溯源` UI render the
  audit as a readable summary rather than exposing raw JSON.
- Verification passed: backend Ruff; execution-audit unit tests; graph/agent
  contracts `17 passed`; frontend typecheck and lint; frontend full unit suite
  `284 passed`; production frontend build completed.
- The backend full suite was rerun and ended with `11 failed, 654 passed,
  136 skipped, 1 warning`. The failures are existing worktree baseline drift,
  not model-audit assertions: Compose tests still expect the retired
  `crypto_alert_v2.commands.worker` command, the startup contract expects a
  Compose run without the now-required LangGraph license gate, browser/docs
  structure tests expect older file/document sets, and a pre-existing root
  `run_full_e2e_test.sh` violates the current layout assertion. These failures
  remain open and are not marked as production green.

Result: model execution identity is now auditable across the canonical graph,
database JSON artifact and frontend display. V2 remains `PARTIAL`; licensed
Agent Server, hosted identity/HTTPS, external LangSmith/Langfuse traces,
provider-stable Pixel 7 success and the pre-existing full-suite baseline drift
remain open. No commit or push was performed.

### 2026-07-17: Fresh Desktop and Pixel 7 audit-rendering proof

Phase: `G0.2` real browser regression

- After restarting the no-reload local stack so it loaded the audit code, the
  real Product Playwright mainline passed on Desktop Chrome:
  `1 passed (1.5m)`. The test exercised Product API, PostgreSQL, worker, the
  official local Agent Server, OKX, built-in Web Search and the configured model.
- The same zero-mock mainline passed on Pixel 7:
  `1 passed (1.4m)`. This is fresh provider-success evidence, not the earlier
  historical Artifact scan. Both browser runs asserted visible `数据溯源`,
  `research-extraction-v1`, `market-analysis-v1`, Chinese rationale, cited HTTPS
  sources, no raw `<pre>`, no 5xx responses, no console errors, zero unnamed
  controls, zero axe violations and no horizontal overflow.
- Screenshots were generated at:
  `frontend/artifacts/playwright-real/real-product-success-fixture-desktop.png`
  and
  `frontend/artifacts/playwright-real/real-product-success-fixture-pixel-7.png`.
  Manual image inspection confirmed the long evidence list and audit section
  remain readable at both viewport sizes.
- PostgreSQL direct verification of the two latest `app.artifact_versions`
  rows returned `audit_count=2` for each, with prompt versions in the expected
  order and real token totals (`2109/11942` and `2062/12524`). No credential or
  request payload was queried.

Result: fresh Desktop and Pixel 7 zero-mock rendering now prove the model audit
is visible and persisted in the local development topology. This does not close
the licensed persistent Agent Server, hosted OIDC/HTTPS, external LangSmith/
Langfuse, production DB/DR or release-attestation gates.

### 2026-07-17: Root and V2 local gate baseline restored

Phase: local release-gate hygiene

- The earlier `11 failed` result was the repository-root contract suite, not the
  V2 backend suite. Its failures were resolved without weakening production
  requirements: Compose tests inject process-only license/notification
  placeholders, the worker contract now matches `crypto_alert_v2.workers`, BFF
  and status-document assertions match current structured routing, and the
  browser suite check requires the canonical files while allowing newly added
  real security/recovery coverage.
- Removed the obsolete untracked root `run_full_e2e_test.sh`. It hard-coded a
  retired `/sessions/...` workspace, installed floating dependencies and used
  global `pkill` calls; the maintained entry points remain under `tools/v2` and
  frontend `package.json` scripts.
- Replaced four product-surface `JSON.stringify` equality/fingerprint calls
  with one deterministic JSON-like `stableFingerprint` helper. Existing Work,
  HITL and fork identity tests passed, and the raw-JSON structure gate remains
  strict.
- Fresh exact results:
  - repository-root contracts: `1154 passed`;
  - V2 backend hermetic: `658 passed, 136 skipped, 1 warning`;
  - V2 real PostgreSQL integration: `160 passed`;
  - frontend unit: `284 passed`, plus typecheck/lint/build;
  - current-code zero-mock Product E2E: Desktop `1 passed (1.5m)` and Pixel 7
    `1 passed (1.4m)`.
- V2-targeted Ruff (`backend/src`, `backend/tests`) and `git diff --check`
  passed. A broader Ruff invocation over the separate legacy root test project
  still reports pre-existing Python 3.11 parser/style findings and is not
  misreported as a V2 failure or silently rewritten in this slice.

Result: all current local V2 and repository contract gates used by this branch
are green, with explicit real database and browser evidence. The overall V2
remains `PARTIAL` because production-only external gates remain unavailable or
unfinished. No commit or push was performed.

### 2026-07-17: Task 0B requirement-registry tooling hardening

Phase: `Task 0B` structured registry and pre-RED evidence bootstrap

The first Task 0B implementation attempt exposed a fail-open defect: the
registry builder could assign every extracted requirement to Task 1 with a
generic owner/proof mapping when no reviewed mapping existed. That behavior was
removed. The builder now requires a complete explicit reviewed mapping and fails
on missing, added, changed or removed requirement mappings; it does not infer
task ownership or proof targets from prose or source classification.

The registry source snapshot now carries and validates stable `logical_id`,
version, source-region anchor, source-statement anchor, statement hash and both
source file hash fields. Each mapping must also declare an implementation-note
path and the complete specification/code-quality/final-attestation disposition
shape. Informative, verified-evidence and superseded sources remain excluded;
proposed gates remain non-normative until the ordered governance transition.

The pre-RED verifier now:

- creates receipts with exclusive file creation, mode `0600`, flush and `fsync`,
  and never overwrites an existing receipt;
- binds the receipt to the complete registry hash, `NORMATIVE_SHA`, owner
  assignments, exact intended RED mappings and strict timestamp ordering;
- rejects a top-level RED command that differs from the task's frozen intended
  command;
- freezes one `git write-tree` snapshot for the candidate, reads registry,
  receipt and implementation notes from that tree, requires the manifest to
  equal the immutable `HEAD` baseline, and reads normative source files from the
  manifest-bound real `NORMATIVE_SHA` commit rather than trusting mutable
  working-tree files;
- requires the candidate registry, pre-RED receipt and all mapped implementation
  notes to be staged, rejects symlink redirection and index mutation, and
  structurally validates a JSON-compatible note block containing the owner,
  base SHA, exact requirement IDs, RED/GREEN commands, exit codes, test count,
  log hashes and RED timestamp.
- makes the documented proposed-gate transition CLI executable end to end: the
  candidate SHA must resolve to a real repository commit, review entries must
  bind evidence path/SHA, the builder transitions the existing registry, and
  governance verification reuses the complete ordered review-chain validator.

TDD evidence:

- Initial RED: importing the not-yet-created registry tool failed with
  `ModuleNotFoundError: No module named 'tools.v2.build_requirement_registry'`.
- Intermediate GREEN: `6 tests OK` after the first bounded implementation and
  explicit-marker tightening.
- Current GREEN: `python3.12 tools/v2/tests/test_requirement_registry.py` ->
  `16 tests OK`, including real temporary-Git CLI transition, immutable HEAD
  manifest, symlink, malformed-note and source deletion negative cases.
- Current GREEN: `python3.12 -m unittest discover -s tools/v2/tests -p
  'test_*.py' -v` -> `16 passed`.
- Current GREEN: targeted Ruff check, Ruff format check and Python 3.12
  compilation for all three Task 0B tools plus the test module.
- Current GREEN: `git diff --check`.

Evidence boundary:

- No `docs/v2/normative-baseline.json`,
  `docs/v2/requirements-registry.yaml`, `artifacts/v2-final/` receipt or formal
  Task 0B implementation note has been generated. The current worktree is dirty
  and there is no reviewed immutable candidate SHA, so creating those files now
  would be false governance evidence.
- The structured note now binds RED start time and RED/GREEN log hashes, but the
  verifier does not execute the RED command itself or cryptographically attest
  reviewer identity. Final release evidence must still verify the referenced
  logs and external reviewer/CI attestations; local metadata validation alone is
  not production attestation.
- No commit, push, reset or cleanup was performed. The formal Task 0B bootstrap
  remains `tooling GREEN / formal bootstrap NOT COMPLETE` until the reviewed
  normative candidate and explicit mappings exist.

### 2026-07-17: Real Product failure-path browser QA closure

Phase: `M6` local browser failure/success evidence quality

- The real Product Playwright test previously threw immediately after a typed
  Product failure, before running the shared DOM, axe, horizontal-overflow,
  console and network assertions. The failure branch now records the visible
  typed failure, completes the same quality scan as success, saves the screenshot
  and only then fails the test with the real business error.
- Browser observation now includes `pageerror` and `requestfailed`. Only an
  explicit aborted POST to the official Agent stream endpoint is treated as the
  expected terminal `useStream` disconnect; all other request failures remain
  test failures. Recorded failed-response evidence stores pathname rather than
  query strings.
- The first fresh Desktop run correctly retained a real
  `research_unavailable` result caused by built-in Web Search
  `APITimeoutError`. It also exposed two expected official-stream aborts, which
  were classified narrowly instead of disabling the request-failure gate.
- Fresh reruns after that classification passed against the running zero-mock
  local stack: Desktop `1 passed (1.1m)` and Pixel 7 `1 passed (51.0s)`.
- Frontend targeted ESLint and full TypeScript typecheck passed. No provider
  failure was rewritten as success and no browser route interception was added.

### 2026-07-17: Task 12 failure-injection control and first real browser slice

Phase: `Task 12` partial local failure-path implementation

- Added an explicit non-production failure-injection profile around the
  canonical `AnalysisRuntime`; it wraps the existing OKX, research, model and
  Bark adapter boundaries and does not create another graph, agent loop or tool
  protocol. The test-only Product control route is absent unless the controller
  is explicitly configured, hidden from OpenAPI, restricted to
  development/local/test, protected by `failure_injection:write`, an ephemeral
  control token and compare-and-swap scenario generations.
- The first real stack startup failed because LangGraph CLI loaded the existing
  `backend/.env` value `APP_ENVIRONMENT=development` after the script requested
  `test`. The profile now explicitly permits the local development environment
  while continuing to reject staging and production. The next run exposed that
  the browser guard requires the canonical `FAILURE_INJECTION_ENABLED=1`; the
  launcher now exports that exact value.
- The next real request returned `403` because the Product BFF correctly drops
  browser authority headers but had no exact exception for the test-only
  control token. The BFF now forwards the token only for the exact failure
  control route while the explicit profile is active. DELETE additionally
  forwards only the CAS generation header; ordinary Product routes continue to
  drop both headers. A Product proxy unit contract covers this boundary.
- The first successful PUT then returned `500` because LangGraph's blocking-call
  detector caught synchronous `mkdir`/file I/O in the ASGI event loop. Product
  control endpoints now execute the atomic file controller through
  `asyncio.to_thread`; no `--allow-blocking` bypass was added. A subsequent
  DELETE exposed the missing generation-header forwarding as `422`, and the
  bounded proxy fix above closed it.
- A real `search_unavailable` browser attempt was pre-empted by a genuine OKX
  `provider_unavailable` result because the canonical graph correctly executes
  market collection before research. That run is retained as evidence of the
  external dependency ordering and is not counted as Search-injection proof.
  The first deterministic browser slice therefore uses `okx_unavailable`,
  verifies the configured scenario before and after the Product run, requires
  the visible `provider_unavailable / okx` failure, requires no analysis result
  and no raw JSON, then resets the scenario through CAS in `finally`.
- The first deterministic slice exposed one false unnamed-control result in the
  failure spec because its custom scan ignored native `<label>` and
  `aria-labelledby` names. The accessibility snapshot and axe tree showed named
  controls. The failure spec now uses the same label resolution as the existing
  real Product test rather than adding redundant UI attributes or weakening the
  axe assertion.

Fresh exact evidence:

- failure-injection backend contract: `9 passed`;
- touched backend Ruff: passed;
- frontend unit suite after the BFF contract: `285 passed`;
- frontend targeted ESLint and full TypeScript typecheck: passed;
- exact Playwright collection: `4 tests in 2 files`, covering real-provider and
  failure-injection Desktop/Pixel 7 projects;
- real failure-injection Product E2E: Desktop and Pixel 7 `2 passed (9.5s)`.
  Both runs used the real Product API, PostgreSQL dispatcher/worker, official
  local Agent Server and rendered Work UI. They asserted zero horizontal
  overflow, zero unnamed controls and zero axe violations. No `page.route`,
  fixture provider or skipped test satisfied this result.

Boundary kept explicit:

- This is one Task 12 slice, not Task 12 completion. OKX transport-level 500 and
  timeout behavior, Search failure after a healthy market stage, malformed
  model structured output, database rollback, real notification delivery and
  failure receipts, LangSmith/Langfuse outages, process kill/restart recovery
  and the complete failure/recovery visual matrix remain open.
- `database_rollback`, `langsmith_unavailable` and `langfuse_unavailable` are
  intentionally not exposed as selectable scenarios because no real injection
  and evidence path exists yet. The current OKX timeout wrapper is also not
  transport-level retry proof and is not claimed as such.
- The official local Agent Server remains the in-memory development runtime.
  Licensed persistent deployment, hosted OIDC/HTTPS, external traces and hosted
  operational evidence remain separate open production gates. No commit or push
  was performed.

### 2026-07-17: Task 12 OKX transport failure matrix

Phase: `Task 12` partial provider transport/retry proof

- Replaced the failure profile's outer `okx_timeout` short circuit with a
  profile-only `httpx.BaseTransport` decorator around the real OKX transport.
  `okx_timeout` now raises `httpx.ReadTimeout` at the HTTP seam and the new
  `okx_http_500` scenario returns an HTTP 500 response at the same seam. The
  canonical `OkxProvider` remains the only adapter and its existing retry owner,
  total budget, timeout allocation and `ProviderUnavailable` normalization run
  unchanged. `okx_unavailable` remains the intentional immediate/no-egress
  scenario.
- The healthy `none` scenario delegates through the decorated transport. The
  failure-profile runtime creates the underlying `HTTPTransport` with native
  retries disabled and preserves the explicit market proxy at that transport
  boundary. No second provider or retry loop was introduced.
- Backend contracts prove HTTP 500 and timeout each consume all three provider
  attempts, produce exactly two configured backoffs, never call the network
  delegate, preserve provider `okx`, endpoint `ticker`, retryability and the
  original correlation ID. The combined failure-profile and existing OKX
  provider run passed `21 passed`; targeted Ruff passed.
- The real Product browser spec now executes `okx_unavailable`,
  `okx_http_500` and `okx_timeout` independently on Desktop and Pixel 7. Every
  case sets and re-reads the scenario through the protected Product API, submits
  a persisted Product Task, requires visible `provider_unavailable / okx`, no
  Artifact result and no raw JSON, then resets through generation CAS in
  `finally`. HTTP 500 and timeout require the retry action; immediate
  unavailable requires it to be absent.
- All six browser cases also assert zero unexpected console errors, page errors,
  browser 5xx responses and failed requests outside the narrowly classified
  official stream disconnect, plus zero overflow, unnamed controls and axe
  violations. Fresh exact result: `6 passed (35.0s)`. Screenshots are separated
  by scenario and viewport under `frontend/artifacts/playwright-real/`.

Boundary kept explicit:

- This upgrades the controlled transport/retry proof; it is not evidence that a
  live OKX internet endpoint actually emitted a 500 or timed out during this
  run, and it does not establish an external provider SLA.
- Search and model failure E2E still require the preceding market/research stages
  to complete or a separately approved deterministic upstream replay boundary.
  Database rollback, notification receipts/failure recovery, observability
  outages, process restart recovery and hosted gates remain open. Task 12 and V2
  remain `PARTIAL`; no commit or push was performed.

### 2026-07-17: Task 12 downstream failure-attribution RED

Phase: `Task 12` controlled-dependency design RED

- A temporary browser-matrix expansion added `search_unavailable` and
  `model_invalid_output` beside the three stable OKX scenarios on Desktop and
  Pixel 7. The exact run collected `10 tests`; the six OKX cases passed and all
  four downstream Search/Model cases failed after `2.1m`.
- Each of the four failures terminated first with the genuine canonical
  `provider_unavailable / okx` projection. The graph orders market collection
  before Web Search and model analysis, so none of those runs reached the
  intended downstream injection point. They are therefore evidence that the
  test attribution was invalid, not evidence of Search or model failure
  handling.
- No assertion was broadened, no retry or conditional pass was added, and no
  fixture, route interception or skip was used to turn the upstream failure into
  a downstream success. The two unproven scenarios were removed from the stable
  browser matrix until a test-only controlled upstream boundary can be made
  explicit and independently verified.
- After restoring the three OKX scenarios, fresh gates passed: combined failure
  profile and OKX provider tests `21 passed`; targeted Ruff, ESLint and
  TypeScript typecheck passed; Playwright collected exactly six failure tests;
  and the complete Product stack passed Desktop and Pixel 7 `6 passed (33.9s)`.

Boundary kept explicit:

- A deterministic typed market/research input used to reach a downstream node
  must be labelled `controlled-dependency Product E2E`. It cannot be described
  as zero-mock, real-provider or external-outage proof, and its contracts must
  prove that the real provider delegates were not called.
- The existing outer `InjectingAnalysisAgent` exception cannot prove malformed
  structured model output because it fails before the canonical LangChain
  agent runs. `model_invalid_output` remains RED until an injected response goes
  through the unique `create_agent` factory and official `ToolStrategy`
  validation, produces a typed non-retryable projection, and proves no Artifact,
  Decision or notification Outbox was committed.
- Task 12 and V2 remain `PARTIAL`; production readiness remains `NO`. No commit
  or push was performed.

### 2026-07-17: Task 12 official structured-output failure closure

Phase: `Task 12` controlled-dependency Product E2E

- The locked runtime was verified as LangChain `1.3.13`. A direct middleware
  experiment exposed an important false path: returning an `AIMessage` from
  `wrap_model_call` bypassed the internal structured-output parser and ended in
  `GraphRecursionError`. The accepted implementation instead uses the official
  `ModelRequest.override(model=...)` API and calls the provided handler, so the
  replacement test-only chat model is bound to the canonical structured-output
  tool and its empty `MarketAnalysis` arguments are parsed by the real
  `ToolStrategy`.
- The initial RED contracts failed during collection because the required
  `FailureInjectionModelMiddleware` did not exist. The GREEN path now keeps the
  unique `create_market_analysis_agent` factory and unique production
  `StateGraph`, accepts additional official middleware at that factory, and
  configures `ToolStrategy(MarketAnalysis, handle_errors=False)`. The malformed
  call therefore raises the official
  `langchain.agents.structured_output.StructuredOutputValidationError`; no
  project JSON parser, second agent loop or structured-output retry was added.
- The old outer `InjectingAnalysisAgent` and project-defined model-output
  exception were removed. The failure profile now supplies typed, no-delegate
  market and research inputs before the model node. Both are visibly marked as
  controlled dependencies (`source_level=controlled_dependency`, parser
  `controlled-dependency-v1`, source `controlled_dependency_test`) so persisted
  records cannot be mistaken for real OKX or Web Search evidence.
- The canonical graph maps official `StructuredOutputError` to the stable,
  non-retryable `model_invalid_output` code and allowlisted exception type.
  Transient OpenAI connection/timeout/server/rate-limit errors remain
  `model_unavailable` and retryable; unknown model failures now fail closed as
  non-retryable. Product projection adds a fixed Chinese message and never
  exposes validation input, tool arguments, model response or exception text.
- `TerminalGraphOutput` now rejects an Artifact on failed output. The dispatcher
  production branch remains unchanged: failed terminal output may persist
  preceding market/evidence records, while Artifact, Decision and notification
  planning remain success-only.
- During the combined contract run, two existing authentication tests exposed
  that development bootstrap had been widened to `local` and `test`, returning
  `202` without JWT where the security contract requires `401`. Actor
  resolution is again restricted to the explicit `development` environment;
  the failure-injection launcher already runs that environment, so the real
  browser profile remains functional.

Fresh exact evidence:

- first official-boundary RED: collection error for missing
  `FailureInjectionModelMiddleware`;
- new official factory/ToolStrategy/graph/Product/invariant contracts:
  `6 passed`;
- combined affected backend, authentication and OKX tests: `172 passed`;
- targeted backend Ruff, frontend ESLint and TypeScript typecheck: passed;
- exact failure Playwright collection: eight tests, four scenarios across
  Desktop and Pixel 7;
- full Product failure stack: `8 passed (42.7s)`. Both model cases asserted the
  typed Product Task, non-retryable UI, refresh recovery, no analysis result,
  no raw JSON, no Artifact Library entry, controlled source markers, scenario
  CAS cleanup, zero unexpected console/page/network failures, zero horizontal
  overflow, zero unnamed controls and zero axe violations;
- original PostgreSQL invocation honestly skipped because no database URL was
  present. Re-running with the same public local test DSN used by the launcher
  first exposed two test-shape REDs (Pydantic object access and normalized
  timestamp payload comparison), then passed `1 passed (3.29s)` after asserting
  the actual service and normalized persistence contracts. The persisted task
  has one controlled market snapshot and one controlled Web Evidence row, with
  zero Artifact, ArtifactVersion, Decision, NotificationOutbox and
  NotificationAttempt rows even though `notify=true`.
- Desktop and Pixel 7 model-failure screenshots were inspected manually. The
  error panel, long exception type, controlled context, form and navigation fit
  without clipping or incoherent overlap.

Boundary kept explicit:

- This is `controlled-dependency Product E2E`, not zero-mock real-provider or
  external model-outage evidence. The browser/Product/PostgreSQL/worker/official
  local Agent Server/canonical graph/framework parser chain is real; the market,
  research and malformed model response are deterministic test-only inputs and
  are labelled as such.
- The official local Agent Server is still the in-memory development runtime.
  Licensed persistent deployment and hosted gates remain open. Search failure,
  database rollback, notification failure/recovery, LangSmith/Langfuse outage,
  process kill/restart and the remaining production matrix are not closed by
  this slice. Task 12 and V2 remain `PARTIAL`; production readiness remains
  `NO`. No commit or push was performed.

### 2026-07-17: Task 12 Search and notification failure closure

Phase: `Task 12` controlled-dependency Product E2E

- Search failure now reaches the canonical research node through a typed,
  no-delegate controlled market snapshot. The Product result is the stable
  `research_unavailable / failure_injection / InjectedSearchUnavailable`
  failure, with no Web Evidence, Artifact or Library entry. Model invalid output
  continues to use controlled market and research inputs before the official
  `ToolStrategy` boundary. The complete Search/Model/OKX matrix passed ten
  Desktop/Pixel 7 cases in `51.4s`; this is controlled-dependency attribution,
  not real OKX, Search or model outage evidence.
- `notification_failure` uses controlled typed market and research inputs plus
  an official LangChain model middleware that calls the existing handler with
  `request.override(model=...)`. The unique production `create_agent`,
  `ToolStrategy` and canonical `StateGraph` therefore produce the committed
  `no_trade` Artifact. The dispatcher commits ArtifactVersion and Decision and
  plans one PostgreSQL Outbox row; the independent worker resolves the encrypted
  Bark destination and the existing Bark adapter returns
  `injected_notification_failure` before HTTP egress.
- Product Task completion is now explicit rather than conflating analysis and
  delivery. The succeeded Task projects `completion_scope.analysis=complete`,
  `completion_scope.notification=retrying` and the stable
  `notification_delivery_retrying` warning. The Work surface renders
  `分析完成`, `交付未完成` and `等待重试`, while continuing to show the committed
  report and never showing `Provider 已接收` or raw JSON.
- The failure launcher creates a process-only notification credential key and
  key version without printing or persisting either value. The Playwright case
  creates/enables its dummy Bark destination through the real Settings API,
  resets the failure scenario through generation CAS and disables the
  destination in `finally`.
- The first notification browser run was retained as RED: the native checkbox
  behind the custom switch was not directly actionable, so Playwright waited at
  `check()` until the test timeout and no analysis POST occurred. The screenshot
  proved the switch remained off. The fixed test clicks the visible label,
  verifies the named checkbox is checked and gives actions bounded timeouts;
  it does not use `force`, `page.route`, retry, skip or a fixture Task.
- Audit found that Artifact provenance always claimed `market_provider=okx`,
  including controlled inputs. `build_artifact` now derives the controlled
  boundary from the typed market `source_level` and records
  `controlled_dependency` for market and model, model name
  `controlled-dependency-test`, no model endpoint host, and the existing
  controlled Search source/parser. A graph contract prevents future false
  provider attribution.
- A real PostgreSQL integration test now executes dispatcher terminal
  persistence, encrypted destination resolution, pre-egress Bark failure and
  the Outbox worker. It requires exactly one Task, Run, command, MarketSnapshot,
  WebEvidence, Artifact, ArtifactVersion, Decision, NotificationOutbox and
  NotificationAttempt for the tested Task. It also requires destination, run,
  Artifact, version and Decision lineage to match; the attempt is automatic,
  `failed_retryable`, has one attempt, a 30-second delay, no provider receipt
  and the exact injected error code.
- The expanded real-database run exposed an old isolation assumption in the
  unknown-delivery test: it asserted the entire shared Outbox was empty after
  one Task became unknown. The test now verifies that any next global lease is
  not the unknown notification and releases a different test lease, directly
  proving the notification under test is never automatically retried.

Fresh exact evidence:

- targeted Ruff, frontend ESLint and TypeScript typecheck: passed;
- canonical graph and failure-injection contracts: `29 passed`;
- affected official framework, notification adapter and Product projection
  contracts: `48 passed`;
- frontend unit suite: `27 files / 286 tests passed`;
- real PostgreSQL dispatcher, notification worker and destination integration:
  `69 passed (11.70s)`;
- complete failure-injection Product browser matrix: `12 passed (1.1m)` across
  Desktop and Pixel 7. Every case kept scenario CAS cleanup, zero unexpected
  console/page/5xx/request failures, zero horizontal overflow, zero unnamed
  controls and zero axe violations;
- both notification full-page screenshots were manually inspected. The report,
  controlled evidence/provenance, completion warning, retryable notification,
  form and navigation remain readable without clipping or overlap on both
  viewports.

Boundary kept explicit:

- This closes the local controlled Search and notification-failure slices. It
  does not prove a live Search/model outage, a real Bark provider receipt,
  hosted notification delivery, Web Push or Email acceptance.
- The official local Agent Server remains the in-memory development runtime.
  `database_rollback`, LangSmith-only and Langfuse-only outage handling, worker
  and Agent Server kill/restart recovery, hosted/licensed deployment and the
  remaining M1-M6 release gates remain open.
- Task 12 and V2 remain `PARTIAL`; production readiness remains `NO`. No commit
  or push was performed.

### 2026-07-17: Task 12 terminal database rollback and Product recovery closure

Phase: `Task 12` controlled-dependency Product E2E

- Added the explicit non-production `database_rollback` scenario without adding
  another graph, agent, parser or retry framework. It reuses the typed
  controlled market/research inputs and official successful model middleware,
  then executes the unique LangChain `create_agent`, `ToolStrategy` and canonical
  `StateGraph` through the official local Agent Server.
- The SQL injection is installed only on the Product worker engine and matches
  only `INSERT INTO app.notification_outbox`. It raises SQLAlchemy
  `OperationalError` after Artifact, ArtifactVersion and Decision have been
  flushed but before the terminal transaction commits. The API engine and every
  other INSERT remain unaffected; the listener has an idempotent removal
  callback and staging/production failure-injection rejection was not relaxed.
- The first terminal projection attempt was retained as RED: a database exception
  escaped `_finalize()` and left the command worker unable to converge the
  Product Task. The dispatcher now rolls back that transaction and starts a new
  session. Before the retry budget is exhausted it requeues the same Task, Run
  and command with `terminal_projection_unavailable`; at the budget boundary it
  fails all three consistently with typed `DatabaseOperationalError` diagnostics.
- Recovery handles commit-outcome uncertainty as well as a definite rollback.
  A new session compares the projection fence and terminal output hash; an
  already committed identical result converges to `dispatched` instead of being
  overwritten as a failure. A later successful projection clears stale failure
  fields.
- Real PostgreSQL tests prove both branches. A one-shot rollback leaves zero
  MarketSnapshot, WebEvidence, Artifact, ArtifactVersion, Decision,
  NotificationOutbox and NotificationAttempt rows, then the same Run is
  automatically reprojected with exactly one row of each business output. A
  persistent rollback reaches the retry budget with no partial business rows;
  Product retry creates a new Run, preserves `retry_of_run_id`, and only that
  recovery Run produces the single Artifact, Decision and Outbox lineage.
- Product browser coverage now submits the real notify-enabled Task, waits for
  the typed failure, proves the Library and notification collection are empty,
  changes the scenario by generation CAS, invokes the real Product retry action,
  and verifies the recovered committed Artifact plus retryable notification.
  Reload retains both states. The test never uses `page.route`, a fixture Task,
  force click, skip or test retry.
- Failure diagnostics were separated from the user message after visual review.
  `terminal_projection_unavailable` now renders an actionable Chinese rollback
  explanation; raw code, error type, attempt and correlation ID remain available
  under semantic `details/summary` diagnostics and remain strictly asserted at
  the Product API boundary. The screenshot is captured with diagnostics returned
  to the default collapsed state. Next development indicators are disabled so
  local tooling no longer occludes Pixel 7 visual evidence.
- The complete backend contract run initially found a real application-factory
  compatibility regression: a lightweight Settings substitute did not have the
  newly optional failure-injection control-token attribute. The factory now
  reads that optional setting compatibly. The retained RED was `490 passed, 1
  failed`; the fresh GREEN is `491 passed`.

Fresh exact evidence:

- real PostgreSQL dispatcher, notification worker and destination integration:
  `71 passed (12.16s)`;
- complete backend contract suite after the application-factory repair:
  `491 passed (21.80s)`;
- backend Ruff check passed. The repository-wide Ruff format check still reports
  59 pre-existing files that would be reformatted; they were not bulk-rewritten
  as part of this slice;
- frontend unit suite: `27 files / 288 tests passed`; TypeScript typecheck and
  ESLint passed; `git diff --check` passed;
- final complete failure-injection Product browser matrix: `14 passed (1.5m)`
  across Desktop and Pixel 7. Database rollback is two of those cases; each
  performs failure, recovery, reload, DOM naming, axe, horizontal-overflow,
  console and network gates;
- all four database rollback full-page screenshots were manually inspected:
  failure and recovery on Desktop and Pixel 7 contain no incoherent overlap,
  clipping, raw JSON or development-indicator occlusion.

Boundary kept explicit:

- This is `controlled-dependency Product E2E`, not real OKX/Search/model outage
  evidence. PostgreSQL, Product API, command worker, official local Agent Server,
  canonical graph, persistence, Product retry and browser rendering are real;
  the market, research and model inputs are deterministic and persist visibly as
  controlled dependencies.
- The official local Agent Server remains the in-memory development runtime.
  LangSmith-only and Langfuse-only transport outages, real Bark acceptance,
  Web Push or Email acceptance, actual worker and Agent Server kill/restart,
  hosted/licensed deployment and the remaining M1-M6 gates are still open.
  Task 12 and V2 remain `PARTIAL`; production readiness remains `NO`. No commit
  or push was performed.

### 2026-07-17: Task 12 real worker SIGKILL recovery foundation

Phase: `Task 12` real Product worker process and PostgreSQL recovery proof

- Added a process-level harness that launches the production worker entry with
  `subprocess.Popen([python, -m, crypto_alert_v2.workers, ...])` from an empty
  temporary working directory. It uses a minimal process environment, the real
  SQLAlchemy/asyncpg path and independently committed Product seed rows.
- A loopback-only `ThreadingHTTPServer` implements the minimum locked
  LangGraph SDK HTTP surface over real TCP. Its Run-create handler persists the
  accepted Run and raises a barrier before returning the HTTP body. At that
  barrier PostgreSQL proves the first real worker has claimed the command,
  incremented attempt `1`, durably written `agent_submit_create_intent`, and has
  not registered any official Run ID.
- The harness sends real `SIGKILL` to that worker PID and requires return code
  `-SIGKILL`. After a separately committed lease-expiry transition, it launches
  a second real worker PID. The successor uses `GET /threads/{id}/runs` metadata
  discovery, registers the same accepted Run, reads status/state, joins the
  terminal result and completes the Product projection.
- The TCP server counts normalized endpoints. Across both worker PIDs the
  remote `POST /threads/{id}/runs` count remains exactly `1`; successor `find`,
  status, state and join calls are all observed. Tenant-scoped test data is
  deleted in `finally`, and child stdout/stderr are discarded to avoid secret
  output or pipe backpressure.
- A second process test releases the create response, waits until Product
  Thread/Run/Command official IDs are committed, then blocks the first worker's
  Run-status GET and kills that PID. After lease expiry the successor reuses the
  persisted remote handle: Thread create, Run create and pre-create discovery
  counts do not increase, while status and join complete the same Product Run.

Fresh exact evidence:

- standalone real process recovery: `2 passed (5.52s)`;
- combined real PostgreSQL dispatcher plus process recovery: `65 passed
  (16.36s)`;
- complete hermetic/local backend suite after this slice: `689 passed, 146
  skipped, 1 dependency deprecation warning (54.23s)`; the skipped process and
  external gates are not counted as production proof;
- process harness collect-only: exactly `2 tests`; without both
  `REAL_DATABASE_TESTS=1` and `PRODUCT_DATABASE_URL`, it is explicitly skipped
  and cannot be counted as passing;
- focused Ruff and `git diff --check`: passed.

Boundary kept explicit:

- The Product worker processes, PostgreSQL, SDK client and TCP transport are
  real. The loopback Agent Server is a controlled protocol dependency, not the
  official licensed persistent Runtime; this test does not prove Agent Server
  restart or checkpoint durability.
- The process proof covers remote acceptance before Product registration and
  committed Product registration before terminal status projection.
  Claim-before-send and notification `sending` process-kill cases remain open.
  The lease is explicitly expired by a committed
  test transaction after proving the old owner; the test does not spend 30 wall
  clock seconds proving the default lease duration. Task 12 and V2 remain
  `PARTIAL`; production readiness remains `NO`. No commit or push was performed.

### 2026-07-17: Task 9 canonical graph callback binding contract

Phase: `Task 9` local canonical graph assembly proof, not hosted trace closure

- Confirmed the production Agent Server export remains the unique
  `graph_factory`; Product API, worker and individual graph nodes do not create
  duplicate LangSmith/Langfuse callback stacks.
- Added a contract that replaces only the root observability factory with a
  synthetic `CallbackManager`, invokes the official `graph_factory`, and proves
  the resulting compiled Pregel config contains that handler plus the original
  correlation metadata. This closes the gap between isolated Runnable assembly
  tests and the canonical Agent Server graph export.
- Focused graph-export plus observability assembly evidence is `19 passed`; Ruff
  passed. This test does not contact either hosted provider and does not invent
  a second tracing framework.

Boundary kept explicit:

- Root callback binding and local official-SDK transport are now separately
  proven. Canonical Graph -> Product terminal projection -> Artifact -> browser
  observability warning/recovery, hosted LangSmith/Langfuse trace queries,
  platform tenant access controls and background transport attribution remain
  open. SDK background delivery errors still have `correlation_id=unknown`.
  Task 9 and V2 remain `PARTIAL`; production readiness remains `NO`. No commit
  or push was performed.

### 2026-07-17: Task 12 submit uncertainty and durable create-intent closure

Phase: `Task 12` Product command recovery contract, local and PostgreSQL proof

- Audited the locked official SDK contract before changing the adapter. The
  installed `langgraph-sdk==0.4.2` documents `runs.create(if_not_exists=...)`
  as a missing-Thread policy (`create` or `reject`); it is not a Run idempotency
  key, does not deduplicate metadata, and does not prevent two Runs on one
  Thread. The implementation does not claim otherwise.
- `AgentServerRunner.start()` now uses the official SDK `on_run_created` hook,
  bounded reconciliation and a per-run indeterminate guard. It also handles
  raw `httpx.TransportError` from the SDK's real transport: connect/pool
  failures are pre-accept retryable; read/write/protocol failures remain
  indeterminate. A response-header run id is bound without issuing a second
  create when the response body later fails.
- `CommandDispatcher` now writes `agent_submit_create_intent` in the same
  durable claim transaction immediately before a submit is sent. A replacement
  worker sees that marker and enters `find`-only reconciliation. A missing
  remote Run is recorded as `agent_submit_indeterminate`; it is never silently
  converted into a second create. This is an explicit at-most-once safety
  contract for unknown acceptance, not exactly-once: the official API exposes
  no client run id or conditional create primitive.
- The remote start path now has a local operation deadline. A deadline,
  cancellation, process takeover or ambiguous transport result is routed to
  the durable indeterminate state. Registration of a discovered Run clears the
  stale intent/error fields and continues through the existing fenced terminal
  projection path.
- Existing lease-takeover tests were updated to model the real contract: a
  replacement worker may bind an already visible official Run through `find`,
  but it must not call `start`. A separate PostgreSQL test verifies the intent
  is visible before the first remote start and survives replacement.

Fresh exact evidence:

- official Agent Server client contract: `34 passed`;
- real PostgreSQL `test_command_dispatcher.py`: `63 passed (12.46s)`;
- targeted Ruff, Python compile and `git diff --check`: passed;
- no `PRODUCT_DATABASE_URL` was assumed: the PostgreSQL run used a temporary
  localhost-only port over the existing Docker test volume, with no repository
  Compose change and no secret output.

Boundary kept explicit:

- This closes Product-side durable intent and at-most-once reconciliation
  semantics, not official Agent Server exactly-once semantics. The remaining
  proof must use a real worker subprocess and `SIGKILL` at claim/start/
  registration barriers, then a licensed persistent Agent Server for server
  restart durability. A zero-result `runs.list` is not proof that a remote
  POST was never accepted; the replacement therefore refuses duplicate create.
- Cross-process concurrent `list-zero -> create` remains impossible to make
  exactly-once with the current official SDK. It requires a server-side
  idempotency key/run-id or an explicitly accepted at-least-once duplicate
  contract. Hosted LangSmith/Langfuse, notification receipts, hosted OIDC/
  HTTPS and the remaining M1-M6 release gates remain open. Task 12 and V2
  remain `PARTIAL`; production readiness remains `NO`. No commit or push was
  performed.

### 2026-07-17: Task 12 provider-isolated observability bootstrap foundation

Phase: `Task 12` local observability assembly contract, not transport closure

- Replaced the misleading test that failed LangSmith and Langfuse construction
  at the same time with two provider-isolated cases. LangSmith-only bootstrap
  failure preserves the Langfuse callback and synchronous business result;
  Langfuse-only bootstrap failure preserves the official LangChain
  `LangChainTracer` and asynchronous business result.
- Structured `observability_delivery_failure` events now carry a bounded stage
  (`bootstrap`, `callback`, `transport` or `flush`) in addition to provider,
  root correlation ID, retry state, dropped/sample flags, redacted error type and
  stable alert fingerprint. Existing fingerprint material remains stable so this
  classification does not silently split existing alert aggregation.
- Current call sites classify client/tracer/handler construction as `bootstrap`,
  callback-manager attachment as `callback`, and SDK tracing/logger delivery
  errors as `transport`. The project did not add another callback or retry
  framework and continues to use the official LangSmith and Langfuse SDK
  integration points.
- The retained TDD RED was both isolated tests failing on missing `stage`. Fresh
  GREEN is `38 passed` across observability assembly, tenant policy, cardinality,
  outage and secret-redaction tests; targeted Ruff and `git diff --check` passed.
  The complete backend contract suite remained `491 passed`.

Boundary kept explicit:

- These tests inject client factory/initializer failure before network delivery.
  They do not prove official SDK HTTP batching, retry, timeout, TLS, transport or
  flush failure behavior and are not called LangSmith/Langfuse outage closure.
- Real loopback transport failure through official callbacks, Graph/Product
  terminal preservation, correlated local logs, incomplete Product observability
  scope, recovery transitions, bounded process shutdown and hosted traces remain
  open. Task 12 and V2 remain `PARTIAL`; production readiness remains `NO`. No
  commit or push was performed.

### 2026-07-17: Task 12 official SDK loopback transport foundation

Phase: `Task 12` local official-SDK transport proof, not Product/hosted closure

- Added isolated loopback tests for the locked official LangSmith `Client` plus
  `LangChainTracer` and the official Langfuse `Langfuse` plus
  `langfuse.langchain.CallbackHandler`. Both execute real LangChain Runnables,
  bind only to random `127.0.0.1` ports, use synthetic test credentials, perform
  bounded SDK flush/close or flush/shutdown, and make no external request.
- The LangSmith test sends a real `POST /runs/batch`, receives HTTP 503, observes
  the official `tracing_error_callback` and structured `langsmith/transport`
  event while preserving the business result, then changes the same loopback
  service to 204 and proves the next trace is delivered by the same client.
- The Langfuse test sends real OTLP protobuf to
  `/api/public/otel/v1/traces`. It parses the payload, binds the business span and
  official handler trace ID, returns 503 without changing the business result,
  then returns 200 and proves a distinct subsequent trace is delivered. The
  client is isolated in a subprocess because Langfuse owns process-level clients,
  an OpenTelemetry provider and background workers.
- The first Langfuse transport run retained a real security RED: the OTEL HTTP
  exporter logged the 503 response body including a synthetic Authorization
  canary. It also logged that the configured mask failed because Langfuse 4.14
  calls `mask(data=...)` while the project supplied `redact_payload(value)`.
- The fix adds a narrow `mask_langfuse_payload(*, data=...)` adapter and keeps the
  canonical redactor unchanged. The OpenTelemetry OTLP exporter prefix now passes
  through the process-wide secret redaction record factory and uses the existing
  Langfuse structured SDK failure handler. The recovered log contains only
  `Authorization: [REDACTED]`, no credential/canary, and no `Masking error`.

Fresh exact evidence:

- official LangSmith/Langfuse transport files: `4 passed` in each of three
  consecutive runs (`0.73s`, `0.57s`, `0.60s`);
- combined observability assembly, outage, transport, cardinality, tenant-policy
  and secret-redaction set: `43 passed (1.81s)`;
- complete security suite: `18 passed (0.82s)`;
- complete backend contract suite: `491 passed (22.78s)`;
- targeted Ruff and `git diff --check`: passed.

Boundary kept explicit:

- This proves local official-SDK HTTP/OTLP transport fail-open and recovery for a
  LangChain Runnable. It is not a hosted LangSmith/Langfuse acceptance trace and
  does not prove either provider's external SLA, DNS/TLS/proxy behavior or hosted
  retention/query path.
- The SDK background transport callbacks still cannot reliably attach the
  originating Product correlation ID and currently emit `correlation_id=unknown`.
  Canonical Graph/Agent execution, PostgreSQL Artifact preservation, Product
  completion scope/warning, browser rendering, correlated recovery transition,
  bounded Agent process shutdown and hosted dual-end trace gates remain open.
  Task 12 and V2 remain `PARTIAL`; production readiness remains `NO`. No commit
  or push was performed.

### 2026-07-17: G0.2 real HITL terminal projection and strict browser closure

Date: `2026-07-17` (Asia/Shanghai)

Phase: `G0.2` fresh local zero-mock Product main-flow closure; not a production
deployment attestation

Objective: explain and fix the real browser state that remained on
`waiting_human` after the Product service had committed a successful Artifact,
then rerun the complete OKX/Search/model/HITL path on Desktop and Pixel 7 under
strict DOM, accessibility, network and visual gates.

Files changed:

- `frontend/src/lib/schemas/product-api.ts`
- `frontend/src/features/work/work-surface.tsx`
- `frontend/src/features/agent-runtime/official-run-stream.tsx`
- `frontend/tests/unit/product-api-schema.test.ts`
- `frontend/tests/unit/work-surface.test.ts`
- `frontend/tests/e2e-v2/real-product-flow.spec.ts`
- root `pyproject.toml` and `uv.lock`
- this execution ledger and `15-v2-implementation-status.md`

Tests run:

- frontend unit: `29 files, 319 passed`;
- frontend TypeScript, ESLint and production Next.js build: passed; all product
  routes remained runtime dynamic;
- strict final zero-mock Desktop Product flow: `1 passed (59.1s)`;
- strict final zero-mock Pixel 7 Product flow: `1 passed (56.4s)`;
- complete backend hermetic/local suite: `758 passed, 154 skipped, 1 warning
  (20.18s)`; every skip remains unproved;
- complete explicit real PostgreSQL integration suite: `181 passed (39.51s)`;
- root migration/structure/deployment suite: all `1154` collected tests passed;
  the first two attempts retained real collection REDs for undeclared
  `pathspec` and `langgraph-cli`, after which both dev dependencies were added
  and locked (`langgraph-cli==0.4.31`, matching backend).

Evidence produced:

- The failed trace contained exactly one Product GET per polling interval. Its
  last HTTP 200 body was `succeeded`, `artifact.status=committed`, but carried
  the legitimate OKX Decimal string `funding_rate="3.399075660E-7"`. The old
  frontend numeric regex rejected exponent notation; `requestTask()` therefore
  raised the typed invalid-response error, the poll stopped, and React retained
  the previous `waiting_human` projection. Replaying the same captured body
  through the corrected production schema now returns `VALID succeeded
  committed 3.39907566e-7`.
- The Product DTO contract now accepts finite JSON-compatible exponent strings
  while continuing to reject `NaN`, `Infinity`, hexadecimal and incomplete
  exponents. A same-Task terminal projection is also absorbing against stale
  non-terminal reads; retry is the explicit reset path.
- Product polling is the only authority that writes Product Task execution
  state. The official `@langchain/react` stream remains the execution-progress
  display and no longer starts a second imperative Product GET from an
  unscoped `onCompleted` callback. This removes old-run completion ambiguity
  instead of hiding it with a longer timeout.
- The real Playwright gate no longer treats `blocked` as success. It requires
  `分析完成`, `data-artifact-state=committed`, `data-actionable=true`, at least
  one matched persisted Evidence source, zero unmatched report references,
  both structured-output prompt versions, HTTPS sources, no raw `<pre>`, no
  unexpected Product/Agent 4xx or 5xx, no console/page error, no unexpected
  request failure, zero axe violations, zero unnamed controls, no page/card
  horizontal overflow and no horizontally clipped controls.
- Final Desktop Task `cf9d9539-8822-42e3-8677-8db89eab7545` moved from Product
  Run `e2b112de-eca8-44bf-a357-27406098f17a` (`waiting_human`) to resumed Run
  `79424c57-4a5d-4936-ba07-d4f01f4d0f61` (`succeeded`). Artifact
  `07157b13-3332-47c9-bae1-6d8fff64e8ab`, version
  `04effd49-1a7c-499c-8003-06f389de4dc3`, is `committed` with 8 Web Evidence
  rows and 2 model-audit entries.
- Final Pixel 7 Task `d16b5ae2-4b15-4404-90ae-a7f52d61bcd0` moved from Product
  Run `bb140941-4ec5-4c51-aed6-2ac76504be56` (`waiting_human`) to resumed Run
  `c4bfb1db-c258-49da-9e2b-411b2f510007` (`succeeded`). Artifact
  `b5d7c2a9-5d3c-49a9-8ae6-806fea8e13f9`, version
  `df9c9614-a5c3-47fa-ac23-472c9615b134`, is `committed` with 8 Web Evidence
  rows and 2 model-audit entries.
- Both final Artifacts record `market_provider=okx`,
  `search_provider=duckduckgo`, endpoint host `codexai.club`, and the official
  `research-extraction-v1` plus `market-analysis-v1` audit sequence. No model
  credential or raw prompt/payload was printed or written to the repository.
- Fresh full-page visual evidence:
  `frontend/artifacts/playwright-real/real-product-success-real-provider-desktop.png`
  and
  `frontend/artifacts/playwright-real/real-product-success-real-provider-pixel-7.png`.
- Earlier failures remain part of the record: the previous built-in search path
  timed out, the Web market extraction path produced `MissingCitedTicker`, and
  the HITL terminal page remained stale because the successful DTO failed
  schema parsing. None was converted into a passing fallback or a longer wait.

Current result: `GREEN` for the fresh local G0.2 Desktop and Pixel 7 real main
flow. Overall V2 remains `PARTIAL`; production readiness remains `NO`.

Remaining risk: the successful topology uses local PostgreSQL, a local worker,
official `langgraph dev --no-reload`, a loopback frontend and an explicit local
HTTP proxy for provider access. It does not prove licensed persistent Agent
Server restart/checkpoint durability, hosted LangSmith/Langfuse trace
visibility, hosted OIDC and trusted HTTPS, real notification receipt,
backup/restore and DR, load/SLO, secret rotation, upgrade/rollback, signed SBOM
or release attestation.

Next single action: obtain an authorized licensed persistent Agent Server
environment and execute the same create/HITL/resume/succeeded flow across an
Agent Server process kill/restart, proving checkpoint and Product projection
durability before moving to hosted OIDC/HTTPS and dual hosted tracing.

No commit or push was performed.

### 2026-07-17: Local Product PostgreSQL backup/restore rehearsal

Date: `2026-07-17` (Asia/Shanghai)

Phase: `M6` local database recovery rehearsal; not hosted DR acceptance

Objective: prove that the current live local Product PostgreSQL schema and data
can be dumped from a stable source snapshot, restored into an isolated pinned
PostgreSQL container and verified without exposing connection credentials.

Files changed: none for the execution; the existing
`tools/v2/rehearse_product_database_backup.sh` was used unchanged. Evidence is
recorded only in the V2 ledgers.

Tests run: one fresh real rehearsal against local `crypto_alert_v2`, using
`postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777`
as a network-isolated, tmpfs-only restore target.

Evidence produced:

- result `status=passed`, proof level `local-backup-restore-rehearsal`;
- custom-format archive size `379166` bytes and SHA-256
  `c271c2b34d7c7544db6bdd1f17dce0060eea32ce4a80c064c73b97f4ed640eca`;
- `22` user tables and `912` rows in the stable source inventory;
- source row counts were unchanged before and after `pg_dump`;
- restored table inventory and every row count matched the source;
- restored unvalidated-constraint count was `0`;
- the restore container used `--network none`, no published port and ephemeral
  tmpfs storage, and was removed by the script's EXIT cleanup;
- no database credential or source URL was written to the report or repository.

Current result: `GREEN` for local logical dump/restore integrity. Overall V2
remains `PARTIAL`; production readiness remains `NO`.

Remaining risk: this does not prove hosted backup scheduling/retention,
encrypted backup custody, point-in-time recovery, cross-region restore,
production-sized restore duration, production RTO/RPO, failover or operator
runbook acceptance.

Next single action: define and execute production-sized load/SLO acceptance in
the target deployment, then repeat backup/PITR and failover under the hosted
database and operator runbook.

No commit or push was performed.

### 2026-07-18: KR-GATE-01 local key rotation and rewrap recovery rehearsal

Date: `2026-07-18` (Asia/Shanghai)

Phase: `M6 / KR-GATE-01`; local security/recovery proof, not production
acceptance

Objective: prove notification credential key overlap, resumable database
rewrap, internal JWT overlap/retirement, delivery continuity and secret-safe
operational reporting.

Implementation record:

- versioned notification decrypt-only keyring and fail-closed retired-version
  behavior in `backend/src/crypto_alert_v2/notifications/credentials.py`;
- Product settings now permits an existing destination to remain usable during
  overlap and requires re-entry only after the old key is retired;
- JWT public-key file and JSON keyring are merged with same-kid conflict
  rejection;
- bounded rewrap uses `FOR UPDATE SKIP LOCKED`, `UPDATE ... RETURNING` CAS,
  committed batches and retryable progress after process loss;
- CLI report publication uses unique `0600` temporary files, fsync and atomic
  replacement;
- Compose passes both overlap configurations to `langgraph-api` and
  `command-worker`;
- drill is `tools/v2/key_rotation_drill.sh` and is explicitly local-only.

The first real drill attempt was retained as RED: its seed transaction lacked
an ORM relationship and hit a real tenant foreign-key violation before testing
rotation. The script was corrected to flush Tenant/User/Workspace before
inserting destinations. The second fresh run was GREEN. The first full
PostgreSQL regression also retained a migration RED: the live database had a
stale five-column fork foreign key. The first repair attempt exposed its
missing six-column unique key and then an overlong Alembic revision id. The
forward repair was made conditional and renamed to the bounded
`0016_repair_fork_scope`; no error was converted into a pass by weakening a
test.

Fresh evidence:

- focused keyring/JWT/rotation/deployment contracts: `64 passed`;
- real local PostgreSQL notification rewrap/settings integration: `7 passed`;
- full real PostgreSQL integration after the migration repair: `184 passed`;
- pinned PostgreSQL 16 Docker drill: `status=passed`,
  `proof_level=local-key-rotation-rehearsal`;
- four destination rows seeded and all four rewrapped;
- old-version rows remaining: `0`;
- notification delivery before rotation, during overlap and after old-key
  retirement: `delivered`;
- duplicate deliveries: `0`;
- JWT old/new overlap accepted, retired old token rejected, retired new token
  accepted;
- first rewrap process killed after a committed batch and resumed successfully;
- secret scan findings: `0`; report mode: `0600`.
- migration `0016_repair_fork_scope` passed a local `downgrade 0015` /
  `upgrade head` round trip and restored the six-column fork scope constraint.

The detailed implementation record is
`docs/v2/implementation/2026-07-18-kr-gate-01-key-rotation.md`. The evidence
is local-only and does not prove hosted secret-manager/database/OIDC/provider
key rotation, zero-downtime rollout, or release attestation. Therefore V2
remains `PARTIAL` and `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: M6 local migration upgrade/rollback rehearsal

Phase: `M6` migration compatibility; local evidence only

- Added `tools/v2/upgrade_rollback_drill.sh` and its contract test. The drill
  uses a pinned PostgreSQL 16 container and executes `upgrade head`,
  `downgrade 0015_observability_delivery`, then `upgrade head` again.
- Direct database checks confirmed initial and final revision
  `0016_repair_fork_scope`, baseline revision `0015_observability_delivery`,
  and the six-column `fk_runs_fork_source_scope` plus
  `uq_runs_fork_checkpoint_scope` constraints.
- The first real drill RED was a script argument bug: `upgrade head` was passed
  as one Alembic argument. It was corrected to pass action and target
  separately; the fresh rerun passed with `secret_scan.findings=0`.
- Focused contract evidence: `4 passed`; Bash syntax, Ruff and diff checks
  passed; report mode was `0600`.

The detailed record is
`docs/v2/implementation/2026-07-18-migration-upgrade-rollback.md`. This is not
hosted image rollback, production zero-downtime, database failover or release
attestation. V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push
was performed.

### 2026-07-18: M6 local Product health load preflight

Phase: `M6` local load foundation; not ADR 0006 SLO acceptance

- Added `tools/v2/run_load_probe.py` and
  `backend/tests/performance/test_concurrency_stream_load.py`.
- The probe enforces loopback-only local targets, credential-free URLs,
  bounded requests/concurrency/timeouts, strict Product health JSON, bounded
  failure categories and atomic `0600` output. Hosted profile execution is
  rejected rather than silently downgraded to local.
- Fresh real FastAPI Product health run: `200/200` succeeded at concurrency
  `20`; p50 `3.446ms`, p95 `22.852ms`, p99 `25.523ms`, max `27.039ms`, failures
  `0`; focused performance contracts `4 passed`; secret findings `0`.
- The report explicitly stores `slo_claims=[]` and lists request confirmation,
  first stream event, market analysis, reconnect, duplicate events, Structured
  Output, Evidence completeness, checkpoint recovery and hosted SLO as not
  proven.

Detailed record:
`docs/v2/implementation/2026-07-18-local-health-load-preflight.md`. This is a
short loopback health preflight only. V2 remains `PARTIAL`; `Production Ready:
NO`. No commit or push was performed.

### 2026-07-18: M6 Internal Alpha SLO contract foundation

Phase: `M6` synthetic source-candidate contract; no runtime SLO claim

- Added `tools/v2/run_slo_probe.py` and
  `backend/tests/performance/test_slo_contract.py`.
- The evaluator requires all 12 Internal Alpha measurements, positive sample
  counts, timezone-aware positive windows and bounded query IDs. It enforces
  ADR 0006 p95/deadline/rate/leakage thresholds, including duplicate events
  strictly below `0.1%`.
- Missing/extra metrics, zero samples, NaN, out-of-range ratios/counts and any
  failed threshold are red. Hosted profile execution is rejected with `78`.
- Combined load/SLO performance contracts: `8 passed`. The passing fixture is
  explicitly `synthetic-source-candidate-slo-contract`; it is not counted as
  local or hosted runtime quality evidence.

Detailed record:
`docs/v2/implementation/2026-07-18-internal-alpha-slo-contract.md`. A complete
real measurement manifest, hosted time window/query provenance and production
alert receipts remain open. V2 remains `PARTIAL`; `Production Ready: NO`. No
commit or push was performed.

### 2026-07-18: Task 0B status correction after formal-bootstrap audit

- Re-ran the requirement tooling entry points and confirmed that they require
  explicit `--manifest` and `--registry`; neither formal file exists in the
  current repository.
- Existing Task 0B tooling and its 16 synthetic/temporary-Git tests are real,
  so the implementation-status matrix was corrected from `not_started` to
  `partial`.
- Formal bootstrap remains unproved: there is no reviewed immutable normative
  candidate, three-role ordered review, generated baseline/registry, owner
  assignment, pre-RED receipt or formal implementation note. The current dirty
  worktree cannot be used to backfill historical governance evidence.

No baseline, registry, receipt, commit or push was created. V2 remains
`PARTIAL`; `Production Ready: NO`.

### 2026-07-18: Task 14 local protocol secret boundary

Phase: `Task 14` local synthetic-canary security gate; not hosted acceptance

- Added `backend/tests/security/test_protocol_secret_leak.py` as a behavioral
  test of the compiled canonical Graph, not a source keyword scan. It injects
  synthetic credentials into Product input and Provider/Research/Agent runtime
  objects, serializes official LangGraph `updates`/`values`, terminal state,
  typed Product DTOs, Artifact provenance, research/model inputs, errors and
  notification settings, and requires every canary to be absent.
- The first focused run was retained as RED: `3 failed, 1 passed`. Raw
  `query_text` containing an API-key assignment and email address entered the
  Product JSON payload, Graph state, official stream, research query, model
  input and terminal state. Runtime object attributes and exception messages
  were already excluded.
- `AnalysisSubmission` now applies the centralized redactor before Product
  idempotency hashing and Task/Command persistence. `AnalysisRequest` repeats
  the same validation at the canonical Graph boundary. No second Agent loop,
  Graph, stream protocol, state store or frontend authority was introduced.
- Product and Agent BFF response/header/session boundaries were reviewed. The
  proxies already use server-owned authorization, bounded response-header
  allowlists, generic failures and no browser Run-creation route; visible
  workspace names/IDs are display metadata, while scoped internal JWTs retain
  only opaque context authority. No frontend code change was justified.
- Fresh GREEN evidence: protocol gate `4 passed`; complete security suite
  `31 passed`; Graph/Product API `115 passed`; domain/persistence DTO
  `80 passed`; backend hermetic suite `800 passed, 157 skipped, 1 warning`;
  focused Ruff passed.
- No fresh real PostgreSQL result is claimed because `PRODUCT_DATABASE_URL`
  was not configured in this shell. Existing skipped tests remain unproved,
  and the earlier `184 passed` run is not reused as evidence for this change.

Detailed record:
`docs/v2/implementation/2026-07-18-task-14-protocol-secret-boundary.md`.
This local gate does not yet scan a licensed persistent Agent Server restart,
hosted checkpoints, LangSmith/Langfuse, logs, browser HTML/screenshots,
release artifacts or real OIDC/HTTPS sessions. V2 remains `PARTIAL`;
`Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Task 7 terminal Domain Event ledger foundation

Phase: `Task 7` local Product persistence foundation; progressive stage
persistence and hosted durability remain open

- The first focused contracts retained a real collection RED because
  `DomainEvent` and `domain_event_specs` did not exist. Intermediate SQLAlchemy
  schema assertions and worker assembly contracts also failed before the model,
  migration and existing worker registration were aligned. No test was removed
  or weakened.
- Added Alembic `0017_domain_events`, a Product-scoped `DomainEvent` model,
  deterministic event builder/appender and `DomainEventProjectionWorker`.
- The exact event types are `market.snapshot.committed`,
  `research.evidence.committed`, `agent.output.committed`,
  `evidence.verdict.committed`, `risk.verdict.committed`,
  `artifact.committed`, `notification.planned` and `run.terminal`.
- Rows carry tenant/workspace/owner/task/run/thread scope, payload reference and
  SHA-256 hash, schema version, Thread-global sequence and optional official
  Run/checkpoint identity. Unique `(run_id, event_type)` makes this terminal
  projection idempotent; unique `(thread_id, sequence)` orders the Thread.
- Successful no-notification Runs append seven events in the existing terminal
  transaction; notified Runs append all eight. The existing worker process now
  repairs terminal Runs missing event rows with `FOR UPDATE SKIP LOCKED`.
- The first full integration execution on the existing long-lived Product
  database was intentionally retained as `179 passed, 5 failed`. Existing
  Outbox rows changed global `0/1` count assertions to `14/15`, and old
  notification credential versions changed rewrap counts. Existing user/local
  rows were not deleted or reset.
- A separate fresh PostgreSQL 16 container was migrated from zero through
  `0017` and passed the complete integration suite: `184 passed`. The container
  was removed afterward.
- Focused contract groups were `72 passed` and `67 passed`; backend hermetic was
  `805 passed, 157 skipped, 1 warning`; root structure/deployment was `153
  passed`. Focused Ruff lint/format for 11 files and `git diff --check` passed.
- The real upgrade/rollback drill passed
  `0017_domain_events -> 0015_observability_delivery -> 0017_domain_events`,
  reverified the repaired six-column fork FK/unique constraints and reported
  `secret findings=0` with proof level
  `local-migration-upgrade-rollback-rehearsal`.

Current result: `GREEN` for the local terminal Domain Event foundation only.
The ledger is not yet written progressively from official LangGraph Run stream
events. A failure after a paid market/research/agent/evidence/risk stage can
still occur before that stage is durable in Product PostgreSQL. The next
implementation slice must consume supported official SDK stream channels,
commit each completed stage with Run/checkpoint identity, and prove idempotent
resume after reconnect. The terminal worker remains crash repair. Licensed
persistent Agent Server restart and hosted SLO evidence remain separate open
gates.

Detailed record:
`docs/v2/implementation/2026-07-18-task-07-domain-event-ledger.md`. V2 remains
`PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Task 7 official resumable stream progressive persistence

Phase: `Task 7` local official Runtime and Product persistence proof; licensed
hosted restart remains open

- Three parallel audits confirmed the installed `langgraph-sdk==0.4.2`
  `join_stream` signature, v1 `StreamPart(event, data, id)` shape, resumability
  requirements and the existing Product command transaction boundaries.
- The audits also found that `0017`'s `(run_id, event_type)` identity,
  hash-blind replay and `MAX(sequence)+1` allocator were unsafe for progressive
  events. These defects were fixed rather than hidden behind the terminal
  worker.
- The first focused RED was an import error for the absent progressive
  projector. Intermediate GREEN work retained three failed contracts for
  missing resume options, JSONB payload schema and stale migration-drill head.
- Alembic `0018_progressive_events` adds immutable payload/source identity,
  Run cursor/timestamp, a Thread-inclusive Run scope FK and an atomic Thread
  sequence counter. Same source/same hash is a no-op; same source/different hash
  raises `DomainEventProjectionConflict`.
- Submit, resume and fork official Runs now set `stream_mode=["updates"]` and
  `stream_resumable=True`. The existing dispatcher drains bounded official
  stream slices and then retains `get/get_interrupts/join/cancel` as state,
  HITL, terminal and cancellation authorities.
- Each allowlisted Pydantic-validated stage, Domain Event and official cursor
  commits in one fenced Product transaction. Unknown nodes, request state,
  messages and runtime objects are not persisted.
- First fresh integration after the change was `185 passed, 2 failed`: the
  controlled Fake Agent Server lacked the official Run stream SSE endpoint.
  After adding a valid endpoint, both SIGKILL recovery tests passed and the
  complete fresh PostgreSQL integration was `187 passed`.
- A real Desktop run exposed that `last_event_id=None` subscribes live and does
  not replay pre-attach events even when the Run is resumable. Direct official
  SDK probing with `last_event_id="0"` replayed four stored updates with IDs.
  The adapter now uses `0` only when no Product cursor exists.
- The next real run exposed nested-null normalization drift between progressive
  and terminal DTOs, causing duplicate market hashes. Progressive domain dumps
  now use `exclude_none=True`; the next real failure had exactly market,
  research and terminal events with no duplicate stage.
- Real Desktop failures were retained as failures: two Search citation/timeout
  failures and one invalid model Structured Output. The latter preserved
  official-source market and research payloads before terminal failure.
- Fresh real Pixel 7 Product flow passed in `1.4m`. It used Product API,
  PostgreSQL, the real worker, official `langgraph dev`, OKX, Web Search, model
  Structured Output and the real rendered interface. Existing Playwright DOM,
  axe, network, overflow and responsive assertions passed.
- Direct PostgreSQL verification of the successful Pixel Run found seven events
  in strict order. market/research/analysis/evidence/risk all carried official
  source event IDs and a non-empty Run cursor; artifact and terminal came from
  the Product terminal transaction. No stage type was duplicated.
- Focused adapter/schema/migration contracts were `104 passed`; real dispatcher
  was `68 passed`; real worker recovery rerun after stopping the competing local
  worker was `2 passed`; current backend hermetic was `809 passed, 160 skipped`;
  Ruff format/lint, Bash syntax and diff checks passed.
- The migration rehearsal passed
  `0018_progressive_events -> 0015_observability_delivery -> 0018_progressive_events`
  and directly verified progressive-event schema invariants with zero secret
  findings.

Current result: `GREEN` for local official-stream progressive persistence and a
real Pixel 7 Product flow. It is not licensed hosted durability. No test in this
slice restarts a persistent Agent Server process/database and proves stream
history plus checkpoints survive. Hosted OIDC/HTTPS, production DB failover,
complete Product-flow SLO, alerts and release attestation remain open.

Detailed record:
`docs/v2/implementation/2026-07-18-task-07-progressive-stage-persistence.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

## 33. 2026-07-18 Compose BFF bootstrap authorization closure

本阶段继续围绕 `G0.2` 主流程推进，目标是让本机 loopback 栈与 Compose
DNS 拓扑在前端 BFF 到官方 Agent Server 的鉴权边界上使用同一套可审计契约。

先记录真实 RED：Compose-style non-loopback Agent BFF 在完整 bootstrap 配置
首次被覆盖时返回 502。根因不是网络，而是 `agent-proxy.ts` 从错误模块导入
`isDevelopmentBootstrapRuntime`，运行时抛出 `isDevelopmentBootstrapRuntime is
not a function` 后被宽泛 transport catch 隐藏。同时 Product BFF 对
`/auth/contexts` 先尝试 scoped `token_use=user`，而后端该路由严格要求
`token_use=identity_discovery`。

进一步的后端审计发现一次性 `development-bootstrap` 仍使用 legacy
ActorContext 构造器，可能把 `identity_issuer=legacy` 且无固定 context 写入
成员关系，而生产 Product app 已使用配置的 identity issuer/context 校验。
这会让 bootstrap 成功但运行时身份不匹配，因此一并修复，没有把它降级成测试
问题。

本阶段完成：

- BFF auth 新增 local-proof-only 的 server-owned identity discovery token；
  `/api/v2/auth/contexts` 和 `/api/v2/auth/context/select` 优先使用该 token，
  普通 Product/Agent 业务路由继续使用 scoped user token。
- Agent BFF 修正导入边界；非认证本地 Agent URL 仅允许 HTTP；非 loopback
  development 只有完整 server-owned signing config 才能继续。
- 后端一次性 bootstrap 复用 `configured_development_actor`，保证数据库
  membership、Product token、Agent token 的 issuer/context 由同一 ActorContext
  产生。
- 增加 frontend JWT claim、Product/Agent BFF、环境清理、Compose deployment
  contract 和 backend bootstrap contract 覆盖。

新鲜验证结果：frontend focused/full unit `372 passed`，typecheck、ESLint、
production build 通过；backend auth/deployment contract `41 passed`，完整
backend hermetic `850 passed, 164 skipped, 1 warning`；Ruff lint 和 179 个文件
format check 通过；Compose deployment contract 通过。

当前源代码栈重启后，Work、Product readiness、Agent docs、Worker live/ready
均为 HTTP 200。Product BFF 返回唯一固定 context，PostgreSQL
`app.memberships` 也存在同一 membership ID。真实 Playwright Desktop/Pixel 7
DOM/视觉扫描为 page errors=0、failed requests=0、raw pre=0、unnamed controls=0、
horizontal overflow=0、axe violations=0，截图人工复核未见布局遮挡。

真实 provider success-only Playwright 随后在两视口均按 RED 退出。两条链路都
穿过 Product API、PostgreSQL、Worker、官方 LangGraph development Runtime 和
真实 UI，然后在 `builtin_web_search/collect_market_snapshot` 连续 3 次
`APITimeoutError` 后失败；没有 Artifact 或 uncited market value。详细记录：
`docs/v2/implementation/2026-07-18-compose-bff-bootstrap-auth.md`。

随后保留该 RED 并定位本机 egress：OKX 与 DuckDuckGo 直连均在建立连接前
timeout，而 `127.0.0.1:7890` 代理下 OKX HTTP 200 / `code=0`，DuckDuckGo
也返回真实搜索结果。当前源码栈显式切换 `SEARCH_PROVIDER=duckduckgo`，并注入
`MARKET_DATA_HTTP_PROXY`/`SEARCH_HTTP_PROXY` 后，真实 Product Playwright
Desktop `1 passed (~1.2m)`、Pixel 7 `1 passed (~52.9s)`，合计
`2 passed (2.2m)`。

两条 GREEN 链都使用真实 OKX、真实 DuckDuckGo Web Search、模型 Structured
Output、PostgreSQL、durable Worker、官方 LangGraph development Runtime 和真实
前端。测试要求 committed/actionable Artifact、matched cited sources、模型审计、
中文 rationale、HTTPS 来源、Evidence/Risk/Provenance，以及 raw JSON、DOM
overflow、clipped/unnamed control、axe、console/page/network error 全部门禁。
PostgreSQL 新增 2 个 succeeded Task、2 个 Artifact、16 条 Web Evidence。

仓库新增无密钥 `backend/.env.example`；Compose 显式只向官方 Agent Server
透传 `SEARCH_PROVIDER`、`MARKET_DATA_HTTP_PROXY`、`SEARCH_HTTP_PROXY`，并有
deployment contracts。详细记录：
`docs/v2/implementation/2026-07-18-proxied-zero-mock-mainline.md`。

本阶段关闭本地 Compose-style BFF 鉴权、bootstrap identity 一致性和当前记录
条件下的 G0.2 local zero-mock Product 主链，但不宣称生产通过。approved
`builtin_web_search` 的
`collect_market_snapshot` 仍在 bounded retries 后失败；licensed persistent
Agent Server restart durability、hosted OIDC/HTTPS、真实通知回执和 release
source proof 仍未关闭。V2 仍为 `PARTIAL`，`Production Ready: NO`。没有执行
commit、stage 或 push。

## 35. 2026-07-18 Current source real Product revalidation

This entry is the latest current-source browser evidence and supersedes any
earlier wording that treats a historical local fallback as the current success
gate.

- The unified local stack was restarted from the current source with the
  Worker liveness/readiness and Product database readiness changes loaded.
- The real Product Playwright profile executed Desktop and Pixel 7 against the
  external frontend/Agent Server. Both tests crossed the Product API,
  PostgreSQL, Worker, official LangGraph development Runtime and actual UI.
- Both runs failed at the same canonical stage: `provider=builtin_web_search`,
  `endpoint=collect_market_snapshot`, `error_type=APITimeoutError`, attempts
  `1/2/3`. The Product UI rendered `市场数据与后备检索均失败` and retained the
  failure diagnostics; no Artifact or uncited market data was produced.
- This current-source RED is consistent with the ordinary-model capability
  GREEN and the endpoint's missing/unsupported Web Search capability. It is not
  a frontend, Worker-readiness, PostgreSQL-projection or structured-output
  regression.

Current result: `RED / EXTERNAL DEPENDENCY` for the current G0.2 real success
gate. Local readiness and partial-failure semantics remain GREEN. V2 remains
`PARTIAL`; `Production Ready: NO`.

### 2026-07-18: Worker readiness and false-health closure

Phase: `M5/M6` mainline operational reliability; external gates open

- `WorkerRuntime` now serves `/livez`, `/readyz` and `/healthz` through a small
  standard-library listener. Consecutive durable-loop failures make `/readyz`
  return 503; a successful iteration restores 200. Shutdown closes the listener
  before the Worker finishes releasing leases.
- Product now exposes `/api/v2/readiness` separately from liveness. In
  staging/production, a missing/unhealthy Product database check or Worker
  readiness URL is a 503 rather than a false healthy response.
- Compose/Frontend now wait for `command-worker: service_healthy`, and the
  frontend healthcheck calls Product readiness instead of only `/health`.
- Fresh verification: backend `850 passed, 164 skipped, 1 warning`; frontend
  `368 passed`; typecheck/lint/Ruff passed. After restarting the current local
  source stack, Worker `/livez` and `/readyz`, frontend, Agent docs and frontend
  BFF Product readiness returned 200.

Current result: `GREEN` for the Worker false-health/start-order boundary. This
does not prove licensed Agent Runtime restart durability, hosted OIDC/HTTPS,
approved Web Search success, or production release acceptance. V2 remains
`PARTIAL`; `Production Ready: NO`.

Detailed record:
`docs/v2/implementation/2026-07-18-worker-readiness-gate.md`.

### 2026-07-18: Backend QA and current provider verdict reconciliation

Phase: `G0.2/M1/M5-M6` current-worktree QA; real provider success open

- Fresh current backend hermetic verification is `848 passed, 164 skipped, 1
  warning`; the warning is the existing Starlette/httpx TestClient deprecation.
- Fresh isolated PostgreSQL verification migrated `0001 -> 0018` and ran the
  complete integration suite: `191 passed, 0 skipped`.
- Ruff check passed and the format check reported all `179` backend Python files
  already formatted.
- The controlled partial-state Product browser body is GREEN on Desktop and Pixel
  7 (`2 passed`), proving failure attribution, retained Evidence and truthful UI
  projection under controlled dependencies.
- The current `market-analysis-v2` / `web-market-extraction-v2` real success gate
  remains `RED / EXTERNAL DEPENDENCY`. With the user-provided model runtime
  configuration, ordinary model capabilities passed, but approved built-in Web
  Search timed out before market fallback could complete. Neither viewport
  produced a final Artifact.
- Earlier local zero-mock success evidence remains historical evidence for its
  recorded Provider, prompt, proxy and development Runtime conditions; it does not
  prove the current provider success gate.

Current result: `GREEN` for current hermetic, Ruff, isolated PostgreSQL and
controlled partial-state contracts; `RED / EXTERNAL DEPENDENCY` for the current
real provider success gate. G0.1 and G0.3 local boundaries remain GREEN, but G0.2
current real success remains open. V2 remains `PARTIAL`; `Production Ready: NO`.

### 2026-07-18: User endpoint model capability revalidation

Phase: `G0.2` real model capability revalidation; external Web Search acceptance open

- Re-ran the real capability and structured-analysis tests against the user-provided
  OpenAI-compatible endpoint using an ephemeral process environment. No credential
  was written to the repository or emitted in logs.
- Ordinary model capability is GREEN: tool calling, structured output, streaming,
  usage reporting and a real `MarketAnalysis` structured response all passed.
- Built-in Web Search remains RED: the capability probe produced a typed
  `ResearchUnavailable` result, no invoked Web Search tool call and no citations.
  The strict run was `1 passed, 1 failed`, with the only failure being the built-in
  Web Search assertion.
- Direct local connectivity to OKX and DuckDuckGo timed out. The result is therefore
  an external endpoint/network capability boundary, not a reason to weaken evidence
  validation or accept model-memory market data.

Current result: `GREEN` for the ordinary model path; `RED / EXTERNAL DEPENDENCY` for
the approved Web Search and full G0.2 success gate. V2 remains `PARTIAL` and
`Production Ready: NO`.

Detailed record:
`docs/v2/implementation/2026-07-18-user-endpoint-model-revalidation.md`.
No commit or push was performed.

### 2026-07-18: Search readiness error attribution

Phase: `G0.2/M1` provider failure diagnosis; production Search acceptance open

- Strict provider selection now includes the safe capability failure type in its
  startup error, for example `APITimeoutError` for an uninvoked built-in Web
  Search tool, while preserving the Tavily configuration reason.
- No secret, credential-bearing URL, request body or raw provider response is
  included.
- Search capability/runtime readiness contracts are `51 passed`; Ruff check and
  format passed.

Current result: `GREEN` for diagnosis attribution and fail-closed behavior. The
unsupported Web Search endpoint remains RED for the real mainline gate.

Detailed record:
`docs/v2/implementation/2026-07-18-search-readiness-error-attribution.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Model versus Web capability separation

Phase: `G0.2/M1` provider capability audit; Web Search acceptance open

- Real model analysis passed. Tool calling, Structured Output, streaming and
  usage reporting all passed against the configured endpoint.
- The same real capability probe failed only for built-in Web Search:
  `builtin_web_search_invoked=false`, citation count `0`, normalized failure
  `ResearchUnavailable`.
- The Product RED is therefore attributed to the endpoint's missing/unsupported
  Responses `web_search` capability, not to the generic model path.
- The production choices are explicit: a compatible built-in Search endpoint or
  a verified Tavily configuration. Neither may be silently replaced by uncited
  data or an unverified fallback.

Current result: `RED / WEB CAPABILITY ONLY`; ordinary model capability is GREEN,
but the real G0.2 success gate remains open.

Detailed record:
`docs/v2/implementation/2026-07-18-model-vs-web-capability-separation.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Backup/restore local rehearsal

Phase: `M6` Product database recovery; hosted DR open

- Pinned PostgreSQL 16 logical dump/restore passed in an isolated temporary
  database without mutating the source.
- `23` tables and `2440` rows matched, source counts stayed stable and
  unvalidated constraints were `0`.

Current result: `GREEN` for local backup/restore rehearsal. Hosted backup
policy, PITR, cross-region restore, production RTO/RPO and failover remain open.

Detailed record:
`docs/v2/implementation/2026-07-18-backup-restore-rehearsal.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: SLO observation boundary

Phase: `M6` Internal Alpha SLO measurement; formal/hosted SLO open

- Product PostgreSQL observation collection ran with valid tenant/workspace UUID
  scope, but the strict evaluator returned `formal_slo_measured=0` and rejected
  the manifest.
- Only domain-event duplicate and local run-duration proxies were available.
  Hosted health, browser-visible stage latency, reconnect, request confirmation,
  checkpoint recovery, structured-operation, cross-tenant and secret-canary
  evidence were unavailable.
- The RED is retained as evidence that incomplete provenance is rejected; no
  proxy was promoted to a formal SLO claim.

Current result: `RED / INCOMPLETE OBSERVATION PROVENANCE`. Formal SLO, production
alerts and release attestation remain open.

Detailed record:
`docs/v2/implementation/2026-07-18-slo-observation-boundary.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Upgrade/rollback local rehearsal

Phase: `M6` migration rollback and schema recovery; hosted deployment open

- Temporary PostgreSQL upgraded to `0018_progressive_events`, downgraded to
  `0015_observability_delivery`, then upgraded back to `0018_progressive_events`.
- Fork source-checkpoint scope, Domain Event source identity/thread scope,
  immutable payload columns, progressive event schema and zero secret findings
  were verified after the round trip.

Current result: `GREEN` for the local migration upgrade/rollback rehearsal. It
does not prove hosted image rollback, production zero-downtime rollout,
database failover or release attestation.

Detailed record:
`docs/v2/implementation/2026-07-18-upgrade-rollback-rehearsal.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Key rotation local rehearsal

Phase: `M6` key rotation and recovery; hosted custody/release open

- Temporary PostgreSQL migrated from 0001 through 0018 and the current Product
  database was not touched.
- Four notification credential rows were rewrapped, old-version rows reached
  zero, delivery remained successful before/during/after overlap, and duplicate
  deliveries were zero.
- Internal JWT old/new overlap, retired old-token rejection, SIGKILL recovery
  and zero secret-scan findings all passed.

Current result: `GREEN` for the local key-rotation rehearsal. It does not prove
hosted secret-manager custody, DB/OIDC/provider key rotation, zero-downtime
production rollout or release attestation.

Detailed record:
`docs/v2/implementation/2026-07-18-key-rotation-rehearsal.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Local supply-chain gate

Phase: `M6` local supply-chain evidence; hosted/release acceptance open

- `tools/v2/run_local_supply_chain_gate.sh` completed `4/4` scans with no
  skipped scan and stable source identity during the scan.
- Python audit covered `119` packages with `0` vulnerabilities; frontend audit
  covered `582` dependencies with `0` vulnerabilities.
- CycloneDX SBOM generation completed for Python (`119` components) and
  frontend (`574` components).
- Output was written to `/tmp/crypto-alert-v2-supply-chain-current`; the source
  tree is dirty and the result is local working-tree proof only.

Current result: `GREEN` for the local supply-chain gate. It does not prove a
committed candidate, hosted audit, container-image SBOM, signature, release
attestation or production release.

Detailed record:
`docs/v2/implementation/2026-07-18-local-supply-chain-gate.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Deep Agents fallback checklist alignment

Phase: `G0.3` framework boundary governance; Task 13 lifecycle open

- ADR 0009 already accepted the formal fallback: current Research uses the
  official LangChain `create_agent` Harness and does not activate the pre-1.0
  `create_deep_agent` package.
- The delivery checklist's stale unchecked “Deep Agents 0.x lock” item now
  records that approved fallback and the reintroduction trigger instead of
  implying an inactive dependency is required for this release.
- This does not close Task 13 background Deep Research, Cron/monitor,
  retention, Outcome, memory, entitlement or usage work.

Current result: `GREEN` for the documented framework decision; broader V2 remains
`PARTIAL`, while Task 13 remains `not_started`. No commit or push was performed.

Detailed record:
`docs/v2/implementation/2026-07-18-deep-agents-fallback-checklist-alignment.md`.

### 2026-07-18: M6 local Product SLO observation boundary

Phase: `M6` local Product DB proxy measurement; formal/hosted SLO remains open

- Two read-only Agents independently audited ADR 0006, all 12 metric names,
  Product timestamps, Domain Events and manifest provenance. The strict result
  is `0/12` formal SLOs independently recomputable from Product PostgreSQL.
- The audit found that the existing evaluator accepted caller-written
  `local-observed` values without executing a query, hard-coded
  `secret_scan.findings=0`, and represented no-threshold availability as
  `passed=true`. These defects were fixed rather than documented as caveats.
- The first collector test was retained as RED: collection failed with
  `ModuleNotFoundError` because the Product observation module did not exist.
- Added a tenant/workspace-bound, initial-lineage collector using a UTC
  half-open Task cohort and one `REPEATABLE READ, READ ONLY` PostgreSQL
  transaction. Reviewed query hashes, snapshot hash, migration revision,
  missing/censored/invalid counts and non-acceptance limitations are included.
- No payload/content/URL/decision/risk/failure-message columns are read, and no
  raw actor/task/run IDs or database URL are emitted. Output is atomic `0600`.
- All 12 formal metric keys are present only as `proxy` or `unavailable`;
  `formal_slo_coverage=0/12`, there is no `passed` field, and the report cannot
  be fed into the synthetic threshold evaluator.
- Fresh GREEN: collector/evaluator contracts `10 passed`; complete backend
  performance group `14 passed`; focused Ruff lint/format passed.
- A real settled local Product database window contained four initial Runs:
  one succeeded and three failed. First persisted stage p95 proxy was
  `36,986.381ms`; persisted analysis was `78,056.762ms` for `1/4` with three
  missing; Run execution max was `90,224.340ms`; persisted duplicate proxy was
  `0/15`; normalized successful projection chain was `1/1`.
- The external staged report is mode `0600`, passed a sensitive-pattern scan,
  and has SHA-256
  `1432b30664adca638a23362a3a0ff681b2de4c17c4db1258d42ecb5b641b6137`.

Current result: `GREEN` only for an honest local Product database observation
boundary. It does not measure edge ack, browser render, consumer delivery,
reconnect, Structured Output attempts, claim-level Evidence references,
recovery attempts, hosted security/secret findings, production alerts or
release acceptance. Those measurement sources and the complete hosted SLO
manifest remain open.

Detailed record:
`docs/v2/implementation/2026-07-18-m6-local-product-slo-observation.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Task 7 canonical terminal persistence and browser failure audit

Phase: `Task 7` local Product consistency; licensed hosted durability remains
open

- A terminal-path audit found Product branches that could set a terminal status
  without atomically persisting canonical output, hash and `run.terminal`.
- Five Product contract tests and four representative real-database dispatcher
  assertions were retained as RED before implementation.
- One dispatcher helper now owns Task/Run terminal state, timestamps, safe
  output, projection fence, SHA-256 hash, failure metadata and Domain Event in
  one transaction. Invalid commands, cancel, submit uncertainty, resume/fork
  and generic Runtime exhaustion, database fallback and hash conflict use it.
- Same-hash replay repairs a missing event. A conflict writes a new canonical
  failed projection instead of leaving the old success output on a failed Run.
- Failed output requires at least one bounded structured error. Unknown raw
  response/authorization fields are discarded rather than projected.
- The Work surface now runs four visibility-aware terminal revalidations over
  about 110 seconds. It permits one request in flight and stops on correction,
  Task/Run change, unmount or exhausted budget; stale responses are fenced.
- Terminal revalidation retained `3 failed, 320 passed` as RED. Combined
  terminal and actionable-error-copy focused tests are now `62 passed`.
- Fresh GREEN: real PostgreSQL dispatcher `71 passed`; backend hermetic `820
  passed, 163 skipped, 1 warning`; backend Ruff passed; formal docs `18 passed`.
- A retained local real `model_invalid_output` Task was inspected on Desktop
  and Pixel 7. Failure diagnostics, market data and four Web Evidence rows were
  visible without a success Artifact, raw JSON, horizontal overflow or clipped
  text. Expanded diagnosis and source-summary controls worked.

Current result: `GREEN` for the audited local canonical terminal paths and
local browser failure rendering only. The browser observation is not a visual
regression baseline, real device or hosted acceptance. Product stage-history,
its running-refresh browser proof, licensed persistent Agent Server restart,
hosted OIDC/HTTPS and release gates remain open. The terminal revalidation
controller is complete locally, but its dedicated browser fault-injection proof
is not yet claimed.

Detailed record:
`docs/v2/implementation/2026-07-18-task-07-canonical-terminal-persistence.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Playwright profile discovery gate

Phase: `M5/M6` local browser test admission; real profile execution remains
open

- A read-only `--list` audit found default collection mixed 36 fixtures, two
  real-provider tests and 14 failure-injection tests, while official stream,
  cancel, HITL, Inbox, Library and Fork commands collected zero tests.
- The first executable discovery contract retained `14 failed`.
- Every profile now owns an explicit spec list. Default mode collects only the
  four fixture files; unknown profiles and non-fixture profiles without their
  required environment gates fail while loading the config.
- Dedicated npm commands now collect real-provider, official stream, cancel,
  HITL, Inbox, Library, Fork and multi-interrupt specs exactly.
- A new deployment test executes Playwright `--list`, parses all project/spec
  pairs and rejects missing, extra or cross-profile collection.
- Fresh GREEN: discovery/profile/script gate `29 passed`; combined browser
  discovery structures `32 passed`; typecheck, focused ESLint, Ruff and diff
  checks passed.

Current result: `GREEN` for local Playwright discovery and profile admission
only. No E2E body ran, no Task was created, no failure injection was called and
no Product data was mutated. Real profile results, browser visuals and hosted
acceptance remain open.

Detailed record:
`docs/v2/implementation/2026-07-18-playwright-profile-discovery-gate.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Task 7 Product stage-history recovery

Phase: `Task 7/M5` Product durable progress; fresh real running-reload browser
execution open

- Product `TaskView` now returns selected/latest Run stage metadata and coherent
  Product/official cursors. The scoped query never selects event payload,
  checkpoint, source identity, model content, authorization or raw response.
- Frontend Product history is the durable baseline and official
  `@langchain/react useStream` is the live enhancement. Repeated stage versions
  collapse by greatest sequence; persisted completion cannot regress.
- Terminal, historical and pre-stream/SSE-failed views retain progress without
  rendering Run ID or either cursor.
- The real official-stream spec now requires a nonterminal persisted stage,
  reloads while running, proves same Task/binding and no duplicate POST, then
  retains terminal refresh verification. It fails rather than falling back to a
  terminal-only reload when the Run is too fast.
- Fresh GREEN: backend Product contracts `138 passed`; Product/persistence `194
  passed`; real Product service `34 passed`; real Product+dispatcher `105
  passed`; backend hermetic `835 passed, 164 skipped`; frontend `335 passed`,
  typecheck and lint passed.
- After current-code stack restart, the retained real Task projected market,
  Web Evidence and failed Run stages with Product cursor `3`.

Current result: `GREEN` for Product API, real PostgreSQL and frontend
unit/type/static recovery. The in-app browser blocked the post-restart reload by
URL policy and no workaround was attempted. The new real running-reload E2E is
discoverable but not executed, so browser acceptance remains open.

Detailed record:
`docs/v2/implementation/2026-07-18-task-07-product-stage-history-recovery.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Task 12 controlled OKX/Web Search fallback matrix

Phase: `Task 12/M5` controlled dependency browser matrix; external and hosted
failure acceptance open

- Added controlled OKX-to-Web-Search success and double-failure scenarios.
  OKX still executes the real provider/retry policy three times before the
  canonical Graph uses its existing fallback.
- Success persists `web_search_verified` market context, fallback Evidence,
  conservative Artifact/provenance and Library projection. Double failure
  persists one two-layer Product error, no market/Evidence/Artifact/Library
  result and the same DTO after refresh.
- Product diagnostics safely retain endpoint, fallback source and primary
  attempt. The failure card displays both layers while preserving code and
  correlation ID.
- Backend profile/Graph contracts `39 passed`; UI RED `2 failed, 34 passed`,
  GREEN `36 passed`.
- Isolated fresh-stack Desktop exercised A/B; focused success was `1 passed in
  9.9s`; Pixel 7 A/B were `2 passed in 20.7s` with overflow, unnamed-control and
  axe assertions.

Current result: `GREEN` only for a controlled local dependency profile through
real Product API, PostgreSQL, worker, canonical Graph, official local Agent
Server and browser. External provider outages, licensed Runtime, hosted network
and production alerts are not proved.

Detailed record:
`docs/v2/implementation/2026-07-18-task-12-market-fallback-matrix.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Web Search timeout budget and structured evidence binding

Phase: `G0.2/M1` real mainline provider and structured-output recovery

- The first fresh built-in Web Search Product run was intentionally retained as
  RED. Its three `APITimeoutError` attempts were previously collapsed into one
  attempt because the first transport received the entire remaining budget.
- `SearchRetryPolicy` now reserves future backoff and divides the remaining
  total budget into transport slices. `remaining_budget_seconds` continues to
  mean the budget at attempt start; the transport timeout is asserted separately.
- Research remains an official LangChain `create_agent` + `ToolStrategy` path,
  but its schema now returns only conclusion fields plus bounded `source_index`.
  Provider URL and timestamps are materialized from verified evidence by the
  application, and an unknown source index fails closed.
- Market Analysis, Web Market extraction and Research use one official
  `Runnable.with_retry` budget for transient transport errors and one
  `StructuredOutputError` repair (`stop_after_attempt=2`).
- Fresh GREEN: backend hermetic `837 passed, 164 skipped, 1 warning`; frontend
  unit `335 passed`, typecheck/lint/build passed; root structure/discovery and
  Ruff/diff checks passed. A newly created isolated Product PostgreSQL database
  ran migration 0018 and the complete integration suite: `191 passed`.
- With explicit local `SEARCH_PROVIDER=duckduckgo`, real Product Playwright
  Desktop passed `1` in `1.0m` and Pixel 7 passed `1` in `56.5s`. Each fresh
  Task persisted eight typed Web Evidence rows, committed Artifact, succeeded
  Run, seven ordered stages and two model audit records. DOM, axe, overflow,
  unnamed-control, console and Product/Agent network checks passed.
- This explicit DDG run is a local mainline diagnostic only. It does not amend
  ADR 0002 or close approved built-in Web Search/Tavily, hosted egress, licensed
  Agent Server, OIDC/HTTPS, restart, observability or M6 release gates.

Current result: `GREEN` for the local explicit-provider mainline slice and
retry/structured-output contracts. The latest real built-in path remains an
honest `research_unavailable` at attempt `3`, so provider acceptance remains
open. V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was
performed.

Detailed record:
`docs/v2/implementation/2026-07-18-web-search-timeout-budget.md`.

### 2026-07-18: Run detail navigation and live revalidation

Phase: `M5` local Product interaction consistency; real/hosted acceptance open

- The audit found Run list rows bypassed the dedicated detail route and active
  detail pages froze after one read.
- Run rows now enter `/runs/[runId]`. Detail owns history inspection and exposes
  a Task/Run-scoped Work action with labels for review, retry/fork and open.
- Active status revalidation is five-second, visibility-aware and single-flight.
  Request generations fence late reads. Background failure retains the last
  valid Product state and offers an explicit retry.
- Cancellation is limited to active Runs. Feedback is limited to an existing
  receipt or succeeded/blocked Run with an Artifact.
- The first browser execution retained `2 failed, 2 passed`: a global status
  heading locator matched the same correct label in two semantic regions. The
  assertion was scoped to Run metadata and no behavioral check was removed.
- The first complete lint run retained the React effect-state violation. The
  correction uses keyed Run remounting and asynchronous initial subscription;
  lint now passes without suppression.
- Fresh GREEN: focused unit `21 passed`; complete frontend `356 passed`;
  typecheck/lint/build passed; route structures `7 passed`; Playwright Desktop
  and Pixel 7 `4 passed` after the lifecycle correction.
- The browser body proves a fresh `running -> failed` projection, at least two
  reads, status-consistent Work/cancel/feedback controls, axe, no viewport
  overflow and no unnamed controls.
- The complete local topology was restarted with one generated in-memory token:
  current Product migrations/PostgreSQL, official `langgraph dev --no-reload`
  0.11.0, Product worker and Next.js. Work, Runs, Product health and Agent docs
  all returned HTTP 200.
- Fresh zero-mock real-provider Playwright created independent Tasks and passed
  Desktop `1 passed (1.5m)` plus Pixel 7 `1 passed (51.5s)`, combined `2 passed
  (2.5m)`. Both latest Runs persisted as succeeded with final actions.
- The latest dedicated Run detail rendered one committed Artifact, eight typed
  DuckDuckGo evidence cards, two model audit calls and feedback. A fresh in-app
  browser tab had zero current console errors, no raw JSON and no horizontal
  overflow. Fresh Desktop/Pixel screenshots were visually inspected but are not
  approved visual baselines.

Current result: `GREEN` for the interaction slice and explicit-DDG local
zero-mock Product mainline. DuckDuckGo is not the approved ADR 0002 production
selection, and official local Agent Server explicitly reports in-memory
development runtime. Approved screenshot baseline, licensed durability,
hosted multi-user Web Search/OIDC/HTTPS and M6 release acceptance remain open.

Detailed record:
`docs/v2/implementation/2026-07-18-run-detail-live-revalidation.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: G0.3 single Graph and Worker entry

Phase: `G0.3` official framework boundary convergence

- Audit confirmed `langgraph.json` used only `graph_factory`, but production
  Python still compiled/exported an import-time Graph and retained a second
  executable command Worker loop.
- Removed module-level `graph = create_graph()` and the package export. Tests
  now construct explicit in-process Graphs. Canonical contracts prevent the
  production export from returning.
- Deleted `commands/worker.py`. Moved local-token/internal-JWT provider assembly
  to non-executable `auth/worker_authorization.py`; unified
  `workers/__main__.py` owns the sole process entry and all existing worker loops.
- Focused GREEN: Graph/Worker/security `42 passed`, projection assembly `1
  passed`, deployment/routes `30 passed`, Ruff code check passed.
- Complete backend GREEN: `836 passed, 164 skipped, 1 warning`. The total is one
  lower than the previous suite because three tests for the deleted duplicate
  loop were removed and two new canonical-boundary tests were added.
- Current-source stack restart succeeded. Official `langgraph dev --no-reload`
  loaded `graph/__init__.py:graph_factory`; the unified Worker stayed alive; all
  four page/health probes returned 200. Import inspection reported no legacy
  Worker spec and public Graph exports `create_graph`, `graph_factory` only.
- `AgentServerRunner` remains under review rather than being deleted blindly:
  it mixes official SDK transport with Product idempotency, tenant metadata and
  indeterminate-operation reconciliation. Replacement must preserve those
  contracts with executable evidence.

Current result: `GREEN` for local single Graph/Worker source and startup
boundaries. The official Server still reports in-memory development Runtime, so
licensed persistence/restart and hosted production are not proved. V1 removal
also remains gated by parity and data attestations.

Detailed record:
`docs/v2/implementation/2026-07-18-g03-single-graph-worker-entry.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Durable cancellation stream teardown

Phase: `M5` Product lifecycle consistency; hosted/runtime durability open

- Retained the first current-source real-cancel result as RED: Desktop and
  Pixel 7 both reached durable `cancelled`, but `2 failed` because the terminal
  durable progress panel reused the live stream's DOM test identity.
- Confirmed this was not a hidden React/Next stream subtree. The official
  `useStream` owner had unmounted; `DurableRunProgress` had replaced it with the
  same `data-testid`.
- Split live and durable progress identities and centralized official-stream
  eligibility in a pure rule covering active, cancel-requested, terminal,
  historical and absent Task states.
- Strengthened the real profile to prove live DOM teardown, terminal durable
  replacement, exactly one Product cancel POST, no browser Run write, and no
  new Agent read after terminal cancellation or terminal reload.
- Fresh GREEN: frontend `30 files / 364 tests`; typecheck, focused ESLint and
  production build passed. Corrected real cancel passed Desktop and Pixel 7 in
  `22.6s`; the strengthened lifecycle proof passed both in `27.8s`.

Current result: `GREEN` for local durable cancellation and official stream
teardown. The Server is still an in-memory official development Runtime; hosted
OIDC/HTTPS, licensed persistence/restart and M6 acceptance remain open. V2
remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

Detailed record:
`docs/v2/implementation/2026-07-18-cancel-stream-teardown.md`.

### 2026-07-18: Real Inbox, HITL, Fork and official-stream closure

Phase: `G0.2/M2-M5` current-source local Product interaction regression;
licensed/hosted production acceptance open

- Re-executed four independent Product browser profiles against PostgreSQL,
  unified worker, canonical Graph and official local Agent Server. Each profile
  retained its RED before correction.
- Inbox retained absolute-bottom scroll and same-symbol wrong-card failures;
  exact Task href binding and actionable viewport recovery now pass.
- HITL retained unpadded countdown and obsolete English Evidence/Risk heading
  failures; stable `HH:MM:SS` and `证据门禁`/`风险门禁` now pass.
- Fork retained Node 22 visual differences, then exposed checkpoint GET failure
  from private `_ReadRuntime` state leaking into compiled Graph defaults.
  Upgrading to `langgraph-api 0.11.1` did not solve the defect by itself, and the
  first sanitization still reintroduced ambient child config.
- The final `graph_factory` uses official `Pregel.copy` with only newly created
  root callbacks and sanitized metadata/tags. It excludes `configurable`,
  checkpointer, Runtime and all execution coordinates. An ambient regression
  contract prevents recurrence; no official Runtime class is monkey patched.
- Official stream retained four independent REDs: terminal-only waiting logic,
  a wrong durable-fallback requirement during HITL, dynamic reload-copy
  comparison, and a real `StructuredOutputValidationError`.
- The browser contract now recognizes `waiting_human` without weakening failed
  or succeeded assertions. Market Analysis uses official
  `ToolStrategy(handle_errors=...)` repair bounded by
  `ModelCallLimitMiddleware(run_limit=3)`; outer retry remains transport-only.
- Fresh GREEN: Inbox Desktop/Pixel 7 `2 passed (8.5s)`; HITL approve `2 passed
  (16.4s)`; Fork `2 passed (15.4s)`; official stream `2 passed (1.5m)`;
  framework/factory/observability `46 passed`; focused agent/graph `21 passed`;
  Ruff passed.
- Official stream additionally proves real OKX, explicit local DuckDuckGo,
  model structured output, active-stage reload, same Product Task/Run, official
  Agent reads, a real HITL pause, DOM/axe/overflow and no browser Agent writes.

Current result: `GREEN` for these local interaction and framework-boundary
slices. The Agent Server is the official in-memory development Runtime, so this
is not licensed persistence, hosted OIDC/HTTPS, approved production Search or a
release proof. The Task matrix is corrected to `partial=15/not_started=1`.

Detailed record:
`docs/v2/implementation/2026-07-18-real-inbox-hitl-fork-stream-closure.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Web Evidence partial state and full QA convergence

Phase: `G0.2/M1/M5-M6` truthful provider projection and current-worktree
verification; hosted acceptance open

- Audit proved `research_unavailable + web_evidence` is a valid same-Run state:
  Web market fallback can persist Evidence before the later independent
  `research_events` search fails. Product DB/API did not mix Runs.
- Retained RED: Graph lacked the stage endpoint; Product/API and frontend both
  claimed no verified source existed; the header rendered `检索不可用` above a
  source card; bounded structured-output repair exhaustion was misclassified as
  generic model unavailability.
- Graph now emits `endpoint=research_events`, preserves Evidence and maps the
  official `ModelCallLimitExceededError` repair-budget exhaustion to typed
  non-retryable `model_invalid_output`.
- Product public errors count Evidence from the same terminal payload. Frontend
  uses an explicit amber `partial` state and renders `已保留 N 条来源，研究未完成`
  while preserving the failed status, diagnostics and source cards.
- Full QA also corrected the dev `langgraph-api 0.11.1` dependency contract and
  migrated the historical-stream structure gate to the pure official-stream
  eligibility function. Production image 0.11.0 assertions remain separate.
- Fresh GREEN: focused backend `151 passed`; complete backend `840 passed, 164
  skipped, 1 warning`; fresh PostgreSQL `0001 -> 0018` and integration `191
  passed`; frontend `366 passed`, typecheck/full ESLint/build passed; root `1184
  passed`; Playwright discovery `29 passed`; Ruff check/format passed.
- Discovery currently lists 78 project-test instances across 11 profiles. This
  was `--list` only and is not recorded as 78 passing browser tests.

Current result: `GREEN` for local partial-state semantics and current-worktree
static/integration gates. The partial-state browser body, approved hosted Search,
licensed restart durability, hosted identity and release proof remain open.
Seven real provider/model tests remain skip-gated and unproved.

Detailed record:
`docs/v2/implementation/2026-07-18-web-evidence-partial-state-and-full-qa.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Deterministic availability and Web market fallback

Phase: `G0.2/M1/M5` truthful provider projection; hosted acceptance open

- The real RED was a same-Run contradiction: eight persisted Web Evidence
  records and a rendered ticker coexisted with model-provided
  `unavailable_data`, followed by an independent `research_events` failure.
- Availability is now derived from typed market/research/Evidence facts in the
  Graph. Model output cannot override that authority, and historical Artifacts
  remain immutable.
- Stable capability codes are mapped to readable Chinese labels in the
  frontend view model. Raw provider codes and JSON are not user-facing output.
- Existing `WebSearchMarketCollector` is reused for built-in Web Search,
  DuckDuckGo and Tavily. DuckDuckGo research remains News; its market fallback
  uses Text. Market values require an exact cited quote and source URL and are
  marked `web_search_verified`; execution still requires exchange-native data.
- `web-market-extraction-v2` adds fetched/published timestamps, explicit
  current/as-of selection and a prohibition on averaging conflicting values.
- Fresh local verification is backend `848 passed, 164 skipped, 1 warning`,
  frontend `368 passed` in `30 files`, typecheck/lint/build passed, Ruff passed
  with `179` formatted backend files, and root `1184 passed`.
- Real local browser behavior: OKX timeout -> retry exhaustion -> successful
  DuckDuckGo Text market fallback -> one typed market snapshot and eight
  persisted Evidence records -> later `research_events` failure. The UI
  correctly shows `后续研究检索未完成`, `已保留 8 条来源，研究未完成`, latest
  ticker `62,040.82`, eight source cards and provider `DuckDuckGo`.

Current result: `GREEN` for deterministic partial-state semantics and the
explicit local fallback slice. This is not a successful final analysis and does
not close approved provider selection, hosted egress, licensed Agent Server
durability, hosted OIDC/HTTPS or release gates. A fresh success using
`market-analysis-v2` and `web-market-extraction-v2` remains required.

Detailed record:
`docs/v2/implementation/2026-07-18-deterministic-availability-and-web-market-fallback.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Live DOM accessibility scan

Phase: `M5` frontend QA; hosted acceptance open

- A live DOM scan of the real partial-failure Work page found one unnamed
  control: the Bark notification checkbox's hidden input had no explicit name.
- The control now has `aria-label="完成后通知 Bark"`; visual structure, state and
  request behavior are unchanged.
- Fresh frontend unit tests are `368 passed` in `30 files`; typecheck, lint,
  production build and `git diff --check` passed.
- The live page now reports `rawJson=0`, `horizontalOverflow=0` and
  `unnamedControls=0`. Frontend and Agent docs probes returned HTTP 200.

Current result: `GREEN` for this local accessibility correction. It does not
close hosted identity, licensed Runtime durability, real notification receipts
or release acceptance.

Detailed record:
`docs/v2/implementation/2026-07-18-live-dom-accessibility-scan.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Partial-state Playwright body

Phase: `M5` cross-layer browser QA; controlled execution open

- Added a real Product Playwright body for OKX retry exhaustion, successful Web
  market fallback, later `research_events` failure and retained Evidence.
- Desktop and Pixel 7 discovery both succeed; the body checks Product API error
  provenance, no Artifact, Evidence lineage, reload persistence, partial copy,
  raw JSON, overflow, unnamed controls and axe.
- Isolated execution is now GREEN: failure-injection Desktop and Pixel 7 both
  passed, combined `2 passed (17.3s)`. The run used separate Agent/frontend
  ports, shared the existing Product PostgreSQL schema without resetting it,
  and restored the normal Worker afterward.
- Both viewports proved `failed + one web_evidence + no artifact`,
  `research_events` error provenance, source-card retention after reload, raw
  JSON absence, overflow=0, unnamed controls=0 and axe=0.
- The existing external-dependency real browser RED/GREEN partial evidence is
  unchanged. This new result is controlled-dependency QA evidence and cannot
  close hosted provider, licensed Runtime or production release gates.

Current result: `GREEN` for the local controlled partial-state browser body. It
is not a production acceptance result and does not close hosted Search,
licensed durability, OIDC/HTTPS or release gates.

Detailed record:
`docs/v2/implementation/2026-07-18-partial-state-playwright-body.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Real provider revalidation after prompt update

Phase: `G0.2/M1` real provider mainline; external provider acceptance open

- Re-ran the real Product Desktop/Pixel 7 success-only profile after loading
  `market-analysis-v2` and `web-market-extraction-v2`.
- Diagnostic DuckDuckGo: both viewports reached OKX retry exhaustion, successful
  Text market fallback and eight persisted Evidence records, then hit three
  `research_events` News timeouts. The truthful partial UI remained failed and
  produced no final Artifact.
- Approved `builtin_web_search`: both viewports hit three
  `APITimeoutError` attempts at `collect_market_snapshot`; Product rendered the
  two-layer market/fallback failure and produced no analysis Artifact.
- The test failure is an external provider/endpoint/network capability result,
  not a UI assertion weakness. No uncited price or model-only result was
  accepted, and no success was declared.

Current result: `RED / EXTERNAL DEPENDENCY` for the real provider success gate.
The local partial-state semantics remain GREEN, but G0.2 real success,
approved hosted Web Search, licensed Runtime and production release gates stay
open.

Detailed record:
`docs/v2/implementation/2026-07-18-real-provider-revalidation-after-prompt-update.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.

### 2026-07-18: Readiness, provider integrity and real regression closure

Phase: `G0.2/M1/M5-M6` local production-auth proof; hosted acceptance open

- A provider audit proved the configured `ddgs==9.14.3` path used automatic
  metasearch, so prior provider-identity statements calling that path
  DuckDuckGo are superseded. The real URLs, citations and historical execution
  sequence remain evidence, but current persistence and UI use
  `source=ddgs_metasearch` and `parser=ddgs-metasearch-v1`.
- Alembic `0019_ddgs_provenance` reversibly rewrites only structured provenance
  keys in Evidence, Run output, Artifact versions and Domain Events. Real local
  rollback/re-upgrade changed 178 Evidence identities in each direction without
  changing the row count; the initial upgrade corrected 274 structured rows.
- OKX now rejects mixed-instrument responses and negative candle volume.
  Retry-policy construction rejects invalid attempts, budget and backoff values.
- The long-running Agent readiness monitor now has a first-success barrier,
  bounded semantic probe, consecutive-failure threshold, monotonic stale-state
  protection, exact provider-drift detection and recovery. Product readiness
  requires PostgreSQL, Agent monitor and Worker readiness.
- Worker readiness now covers every required loop, hung active iterations,
  failure thresholds, listener bind failures and recovery without treating
  normal poll sleep as stale.
- Submit/resume/fork reconciliation and remote Run reads now share bounded
  dispatcher deadlines while preserving typed indeterminate semantics.
- The browser-facing Product BFF now applies a server-owned eight-second
  upstream deadline and returns a redacted 502 for a hung Product upstream.
  Task 8 deliberately hosts Product under Agent Server `/app`; the shared
  process failure domain is an approved topology property, and whole-process
  outage is expected to degrade through the bounded BFF transport response.
- Real fault injection retained the transitions: pausing only the monitor made
  Product readiness 503 and recovery restored 200; pausing the whole Agent made
  the monitor 503 and Product BFF return the bounded 502, then all readiness
  endpoints recovered after resume.
- Fresh gates are backend `887 passed, 166 skipped, 1 warning`; fresh isolated
  PostgreSQL `0001 -> 0019` integration `198 passed`; dispatcher PostgreSQL `73
  passed`; focused providers `55 passed`; frontend `374 passed` in 30 files plus
  typecheck/lint/build; root structure/deployment exit 0; Ruff check and 183-file
  format check; `git diff --check` passed. The 166 skips remain unproved.
- The corrected production-auth local mainline passed Desktop `1 passed (1.4m)`
  and Pixel 7 `1 passed (1.1m)`, combined `2 passed (2.5m)`. A follow-up local
  PostgreSQL query found two Tasks, four Runs, two committed Artifacts, sixteen
  corrected Evidence rows and four model audit entries. Real Library/Artifact
  detail passed both viewports in `12.7s`; four screenshots were inspected for
  content, clipping and overlap.
- Exact pass totals, timings, database counts and SIGSTOP transitions are local
  session evidence. They are not yet bound to a clean candidate SHA, image
  digest and retained machine-readable test manifest, so they are not release
  attestation.
- The active local chain still depends on host HTTP proxy `127.0.0.1:7890` and
  the official in-memory development Runtime. Approved built-in Web Search,
  licensed persistence/restart, hosted OIDC/HTTPS, hosted traces, real
  notification receipts, HA/PITR/SLO, signed supply-chain and release
  attestation remain open. Task 13 remains `not_started`.

Detailed record:
`docs/v2/implementation/2026-07-18-readiness-provider-integrity-and-real-regression.md`.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit, stage or push was
performed.

### 2026-07-18: Task 8 Protocol v2 and persistent Runtime harness

Phase: `M2/M4` Product/Agent protocol and durability acceptance harness

Evidence correction: 2026-07-19

- Architecture review confirmed Product is deliberately mounted as the Agent
  Server `/app` custom application. The shared process failure domain is the
  approved Task 8 topology; an independent `product-api` service is not a
  missing requirement.
- Added locked official route, Protocol command/channel and Python SDK transport
  contracts. They prove Runs API durability/checkpoint serialization, official
  resume command shape, Product `/app` non-shadowing and the observed
  `state.fork -> unknown_command` boundary. Serialization is not
  server-effective `durability="exit"` proof.
- Added an official `@langchain/langgraph-sdk` Protocol probe for root channels,
  `run.start`, single/batch `input.respond`, ordered `since` replay and cleanup.
- Added a licensed Runtime harness with controller and staged
  `prepare -> verify` modes. Its live pytest cases are skip-gated when licensed
  inputs are absent; this is `UNPROVED`, not fail-closed acceptance. The outer
  shell harness is designed to reject skips, but no successful licensed
  zero-skip run exists.
- The first parallel shell implementation was retained as RED because it named
  nonexistent tests, expected mounted routes in root OpenAPI, did not perform a
  restart and could print success when all licensed tests skipped. Review fixed
  those harness defects and added an intended zero-skip JUnit gate. This
  historical repair did not itself produce zero-skip acceptance.
- Task 8 now builds a pinned official QA image with one explicit
  `multi_interrupt_fixture`. The production verifier remains strict; the extra
  Graph is allowlisted only with `--allow-multi-interrupt-fixture` and any other
  graph mapping still fails. This scoped image-verifier allowance is unrelated
  to acceptance of either Protocol compatibility exception.
- A macOS Bash 3.2 RED found that an empty optional-argument array fails under
  `set -u`. Start orchestration now uses explicit production/QA verifier branches.

Current version and evidence matrix:

| Surface | Version | Current evidence |
|---|---|---|
| Development Agent Server | `langgraph-api 0.11.1` | Root `checkpoints` live capability is `RED`; isolated `state.fork` dispatch returns `unknown_command`. |
| Development graph runtime | `langgraph 1.2.9` | Upstream full `StateSnapshot` shape is discarded at the boundary expecting a lightweight Protocol checkpoint envelope. |
| Protocol | `langchain-protocol 0.0.18`, `@langchain/protocol 0.0.18` | Declares `checkpoints` with `id/parent_id/step/source` and declares `state.fork`; declarations are not live capability proof. |
| Official clients | `langgraph-sdk 0.4.2`, `@langchain/langgraph-sdk 1.9.25` | Transport serialization and live diagnostic client usage exist. |
| Licensed image verifier | `langgraph-api 0.11.0` | Licensed Protocol, restart and `durability="exit"` behavior are `UNPROVED`. |

Current compatibility correction:

- The root stream does not deliver a usable lightweight checkpoint event. The
  official `getState` fallback supplies a checkpoint ID only so the JavaScript
  probe can continue independent diagnostics; the probe still exits
  `EX_DATAERR` (`65`). It cannot prove checkpoint-channel conformance, checkpoint
  replay, licensed persistence or exception acceptance.
- Protocol `state.fork` remains declared but returns `unknown_command`. The
  Product fallback uses authorized Product admission and official Runs create
  with top-level `checkpoint_id=`. A working Product fork does not make the
  Protocol command GREEN.
- Both records are `PROPOSED / NOT ACCEPTED`:
  `docs/v2/compatibility-exceptions/langgraph-api-0.11.0-checkpoints.md` and
  `docs/v2/compatibility-exceptions/langgraph-api-0.11.0-state-fork.md`.
- Historical evidence is preserved: adjacent Product/Agent/Protocol/HITL
  `193 passed, 5 skipped`; focused Task 8 `26 passed, 5 skipped`; development
  Server OpenAPI coexistence `1 passed`; Task 8/start/image deployment
  contracts `28 passed`; syntax, Ruff check/focused format and diff checks
  passed. These counts establish harness and static contract work only. They do
  not establish Task 8 GREEN, a valid root checkpoint event, zero-skip licensed
  acceptance, restart survival, or server-effective `durability="exit"`.
- One historical live OpenAPI gate was separately executed. Four licensed
  restart/routing tests were not executed and remain UNPROVED.

Detailed record:
`docs/v2/implementation/2026-07-18-task-08-protocol-persistent-harness.md`.
Task 8 is `RED / PARTIAL`; V2 remains `PARTIAL`; `Production Ready: NO`. No
commit, stage or push was performed.

### 2026-07-19: Task 8 persistent evidence hardening follow-up

- `probe_product_api.sh` now requires an explicit retained evidence directory,
  binds its URL to the owned Compose `langgraph-api:8000` target, verifies image
  identity, proves an HTTP-unavailable stop window and recovery, and hashes the
  retained OpenAPI/version/log/JUnit/container/restart artifacts.
- The harness now admits a real Product Task, records its official Thread/Run,
  and requires the same binding after restart. `AgentServerRunner.start()` also
  exposes the official Runs API `sync/exit` durability choice while Product
  production callers retain the `sync` default.
- Licensed prepare/verify uses separate `sync` and `exit` state manifests and
  explicit server-effective post-restart tests. Receipt validation now requires
  Compose service, target outage/recovery, image ID, locked base image and image
  verifier proof in addition to generation change.
- `--expect-contract-failure` no longer exits after contract pytest. It must run
  Node, Product admission, both durability prepares, stop/start, both verifies
  and interrupt routing, and it must observe an explicit `CAPABILITY GAP` with
  zero skip.
- Fresh local results: Task 8 static/deployment `14 passed`; focused
  Agent/Protocol/graph/durability `95 passed, 8 skipped`; Task 8 plus formal-doc
  contracts `32 passed`; complete backend `925 passed, 174 skipped, 1 warning`;
  root structure/deployment `exit 0`; frontend `374 passed` plus typecheck,
  lint and production build; Bash syntax, focused Ruff and diff checks passed.
  The skips remain unproved.
- Read-only Browser/DOM QA covered Work, Home, Runs, Inbox, Library and Settings
  at Desktop `1280x720` and Pixel 7 `412x915`. Every route rendered its Product
  heading with zero horizontal overflow, clipped text, duplicate IDs, unnamed
  visible controls, raw JSON signals or console warnings/errors. No Product
  command was submitted during this pass.
- No live licensed execution was attempted because the current process has no
  LangGraph/LangSmith entitlement credential and the existing Product
  PostgreSQL container occupies the same Compose project. The running stack was
  preserved. Therefore no licensed restart receipt or server-effective
  `durability="exit"` evidence exists yet.
- The existing local frontend/Agent/readiness/Worker topology remains healthy,
  but its no-reload backend processes predate this Task 8 hardening. They were
  preserved because the parent process owns ephemeral model/auth material; the
  browser audit is not evidence that the changed backend ran live.

Verdict remains Task 8 `RED / PARTIAL`, V2 `PARTIAL`, and
`Production Ready: NO`. No commit, stage or push was performed.

### 2026-07-19: Canonical custom events, Deep Research foundation and Product truth

Phase: `M1/M2/M5 + Task 13 foundation`; local implementation only

- Parallel architecture, UI/product and QA audits kept the global verdict at
  `V2 PARTIAL / Production Ready: NO`. External provider, licensed restart,
  hosted OIDC/HTTPS, hosted observability and release gates remain open.
- The architecture audit selected canonical versioned custom events as the
  highest-value implementation gap that did not require a commercial license.
- RED executed three custom-event contract bodies and failed on the missing
  schema/module. GREEN adds six strict events through LangGraph's official
  `get_stream_writer()`, stable event identity, bounded payloads, Run scope and
  both `stream_mode=custom` and `astream_events(version="v3")` coverage.
- Official Runs submit/fork/resume now request `updates+custom` and attach the
  official Thread ID to metadata. Product progressive persistence intentionally
  remains `updates`-only; no second durable event store was introduced.
- Frontend uses the official `useChannel` selector for six named custom
  channels. Zod rejects unknown/raw payloads; replay is bounded and deduplicated
  by stable event ID; Product Run filtering prevents serial-run bleed; UI shows
  bounded progress rather than event JSON.
- Task 13's first RED executed six test bodies. ADR 0010 then accepted the
  restricted official Deep Agents boundary triggered by the planned background
  multi-stage Research product. Stable `deepagents==0.6.12`, deny-all
  filesystem, disabled general-purpose subagent, one verified-source subagent,
  typed citation indexes, model budgets and explicit LangChain fallback are
  covered. No Graph/Product/background integration exists yet.
- Two UI P1 defects were repaired in parallel: waiting-human Run Detail links no
  longer force Work into historical mode, and Home now labels exchange-native,
  Web Search fallback and controlled dependency snapshots truthfully with
  fetched time and fallback disclosure.
- Fresh evidence: backend `935 passed, 174 skipped, 1 warning`; root tests
  `exit 0`; focused framework/Agent/event `57 passed`; frontend `390 passed`
  plus typecheck/lint/build; Ruff and diff checks passed. Every skip remains
  unproved.
- The preserved local Agent/Worker processes predate this code. No live custom
  channel, current-source browser, licensed restart, hosted or production proof
  is claimed.

Detailed record:
`docs/v2/implementation/2026-07-19-custom-events-deep-research-foundation-and-product-truth.md`.
Task 13 changes from `not_started` to `partial`; all 16 planned Tasks are now
`partial`, none is `done`. V2 remains `PARTIAL`; `Production Ready: NO`. No
commit, stage or push was performed.

### 2026-07-19: Run Detail current/history authority closure

Phase: `M2/M5` Product API and rendered main-flow consistency

- Real browser inspection found that a resolved first-attempt Run remained
  `waiting_human`, while `_task_view(selected_run_id=...)` projected that immutable
  status as an ordinary current Task after its pause was resolved. The frontend
  correctly rejected `waiting_human + pending_interrupts=null`; the error was not
  hidden or normalized.
- Product Run Detail now separates immutable `run`, current action-authority `task`,
  selected historical `run_projection` and server-owned `is_current_run`.
  `TaskView.projection_scope` makes latest/selected semantics explicit and validates
  selected Run identity and stage-history scope.
- Run Detail now stops polling superseded waiting attempts, hides stale cancellation,
  discloses that a later Run handled the review, renders `历史审核节点`, and links to
  the current Task. Selected evidence, report and stage data remain scoped to the
  requested Run rather than silently switching to the latest report.
- The first Desktop/Pixel 7 visual GREEN failed axe `color-contrast`; the warning text
  was moved to the existing high-contrast warning token and the unchanged axe gate then
  passed on both viewports.
- Fresh evidence: backend full `936 passed, 174 skipped, 1 warning`; focused backend
  API/projection `181 passed`; frontend `397 passed` plus typecheck/lint/build; Run
  Detail Playwright `6 passed`; Ruff check passed. A modified real PostgreSQL
  waiting/respond/resume/terminal/history lifecycle passed `1 passed` on the shared
  local Product database.
- A production-profile current-source startup with deliberately invalid placeholder
  model credentials failed closed on four required model capabilities. A separate,
  explicitly local-development current-source Agent Server `8124` and frontend `3002`
  then proved the real persisted historical Run through the real BFF. Desktop and Pixel
  7 scans had zero overflow, clipped text, duplicate IDs, unnamed controls, raw JSON or
  current-page console warnings/errors. Following the CTA rendered the latest persisted
  report with seven saved stages, eight Web Evidence cards, source provenance and two
  model-call audits.
- The current-source local read proof is not licensed durability, approved-provider,
  hosted identity, hosted trace or release evidence. All 174 default skips remain
  unproved. V2 remains `PARTIAL`; `Production Ready: NO`.

Detailed record:
`docs/v2/implementation/2026-07-19-run-detail-current-history-authority.md`.
No code was staged, committed or pushed.

### 2026-07-19: Task 13 Deep Research canonical Product mainline

Phase: `M1/M2/M5 + Task 13 partial`; local implementation and isolated persistence proof

- Architecture, Product lifecycle and QA audits selected one canonical path: Market
  Analysis remains on its existing branch, while `deep_research` enters one restricted
  node in the same `StateGraph`. No second Graph, Runtime, queue, Agent Server, Thread
  authority or durable event store was introduced.
- The restricted `deepagents==0.6.12` harness now has explicit model, search and
  delegation budgets; filesystem/execute tools are excluded and denied; the broad
  subagent is disabled; only `verified-source-researcher` can call
  `verified_web_search`. Deployment selects either Deep Agents or the official
  LangChain fallback, never both.
- A per-Run source ledger gives the model only bounded index/title/excerpt/published
  metadata, retains at most eight deduplicated `WebEvidence` records and materializes a
  strictly cited `DeepResearchReport`.
- `POST /api/v2/deep-research` uses the existing Product admission, TaskCommand,
  dispatcher, Worker, Assistant, Thread and official Run lifecycle. Success commits one
  `deep_research_report` ArtifactVersion plus WebEvidence and Domain Events, with no
  trading Decision.
- Work, Runs, Run Detail, Library and Artifact Detail now consume typed research
  schemas. The official stream projects bounded subagent status; the persisted Product
  Task remains authoritative after stream/browser disconnection.
- The first two-viewport Playwright GREEN failed on a real 4.4:1 subtitle contrast. The
  local text token was raised and the unchanged axe gate passed. A subsequent test-only
  false positive ignored native radio labels; the DOM scanner now resolves associated
  labels instead of adding redundant ARIA.
- Fresh frontend evidence: 33 unit files / `404 passed`, typecheck, lint and production
  build green; Deep Research Desktop `1440x1000` and Pixel 7 `412x915` fixture
  `2 passed` with persisted re-read, axe, overflow, duplicate-ID, accessible-name, raw
  JSON, source deep-scroll and screenshot checks.
- Fresh backend evidence: Deep Research/Product focused `268 passed, 35 skipped`;
  complete default backend `946 passed, 175 skipped, 1 warning`. Every skip remains
  unproved.
- Fresh root structure/deployment evidence: `1199 passed, 51 warnings`; the warnings
  are existing Starlette/httpx and pathspec deprecations, not skipped acceptance.
- A targeted lifecycle on the existing local PostgreSQL passed `1 passed, 34
  deselected`. A full run against that shared historical database correctly exposed
  stale global rows and was not counted as GREEN. A fresh isolated PostgreSQL then
  passed complete integration `204 passed, 7 skipped`, including the research report
  store and real Worker SIGKILL recovery. The two recovery tests initially collided
  with the user's live Worker health port 9090; per-subprocess loopback ports fixed the
  isolation defect without stopping the running stack.
- The official Deep Agent delegation proof uses the real Deep Agents runtime with a
  controlled fake chat model/search tool. It is runtime contract evidence, not a live
  external model/Search success claim.
- No fresh external Provider Deep Research Run, licensed restart, hosted OIDC/HTTPS,
  hosted LangSmith/Langfuse trace or release attestation exists. Dedicated research
  HITL fails closed when required. Monitor/Cron, retention/export/deletion, Outcome,
  memory, entitlement/usage/webhook workers and Product UI remain open.

Detailed record:
`docs/v2/implementation/2026-07-19-task-13-deep-research-mainline.md`.
Task 13 remains `partial`; all 16 planned Tasks remain `partial`, with `done=0`,
`blocked=0` and `not_started=0`. Task 8 remains `RED / PARTIAL`; V2 remains `PARTIAL`;
`Production Ready: NO`. No code was staged, committed or pushed.

### 2026-07-19: Real Deep Research runner, delegation repair and provider RED

Phase: `G0.2 / Task 13 real-provider closure`; RED, not release evidence

- Added a current-source runner with an isolated PostgreSQL database, Alembic head,
  official development Agent Server, unified Worker, production Next build and the same
  no-route-override Desktop/Pixel 7 Deep Research path. It retains JUnit/JSON/HTML,
  traces/screenshots/videos, secret-safe DB lineage, review-policy receipts, redacted
  logs and SHA-256 manifests. It does not source dotenv, scrape process environments or
  stop the user-owned `3110` service.
- Runner contracts are `8 passed`; Bash syntax/profile contract, frontend typecheck/lint
  and diff check pass. Two pre-admission defects were fixed honestly: PostgreSQL `-v`
  variables inside `psql -c` did not interpolate, and an exact accessible-name locator
  could not match the wrapped range `select`. Retained RED receipts:
  `/tmp/crypto-alert-real-deep-research-20260719-131256` and
  `/tmp/crypto-alert-real-deep-research-20260719-131444`.
- The first real two-viewport Product run then exposed a bounded orchestration defect:
  the coordinator emitted three topic delegations while the official
  `ToolCallLimitMiddleware` allowed only one. `SUBAGENT_DELEGATION_LIMIT` is now a finite
  `3` for macro, regulation and market structure. Filesystem remains deny-all, default
  general-purpose delegation remains disabled, verified Search remains one call per
  subagent, and model budgets remain enforced. Focused Graph/harness regression:
  `36 passed`.
- A direct real Deep Agent after this repair reached `verified_web_search`; the explicit
  approved `builtin_web_search` then exhausted all three attempts with
  `APITimeoutError`. Explicit Tavily failed preflight because no Tavily credential is
  configured. DDGS was not substituted as production evidence.
- Safe Graph errors now retain `provider`, `endpoint`, `error_type`, `attempt` and
  correlation ID while excluding exception text, HTTP bodies, prompts, authorization and
  credentials. The retained full-browser provider RED receipt is
  `/tmp/crypto-alert-real-deep-research-20260719-132947`: two Tasks and two failed first
  Runs, with zero pauses, evidence, Artifacts or Decisions.

This does not close G0.2. Approved real Provider success, full required-review GREEN,
licensed persistence, hosted OIDC/HTTPS, hosted LangSmith/Langfuse and release
attestation remain open. Task 13 remains `partial`; Task 8 remains `RED / PARTIAL`; V2
remains `PARTIAL`; `Production Ready: NO`. No code was staged, committed or pushed.

### 2026-07-19: Controlled post-draft Deep Research report HITL

Phase: `M2/M5 + Task 13 local controlled post-draft HITL`; not release evidence

- This entry supersedes only the preceding Task 13 mainline statement that dedicated
  research HITL was absent/fail-closed. Every other production and Task 13 boundary in
  that entry remains open.
- Deep Research now shares the canonical Graph review node instead of introducing a
  second Graph, Runtime, Assistant, queue, checkpoint store or event store. The executor
  returns a typed draft; required review uses official LangGraph `interrupt()`. Resume
  preserves the same Thread/checkpoint/interrupt lineage, while each accepted review
  batch creates a new Product resume Run and a new official Run on the same Thread.
- The typed Product interrupt projection is a discriminated union. Work and Inbox render
  dedicated Deep Research approve, reject and full-report edit controls without exposing
  raw JSON. Edit replaces the complete `DeepResearchReport`, preserves the immutable
  source catalog, revalidates citation indexes and always enters a second review round.
- Scope and integrity are fail closed: wrong task type, symbol, horizon, edit type,
  no-op edit and invalid citation are rejected. Source catalog, harness mode, model
  audits and artifact status cannot be supplied by the browser.
- Approve/bypass is the only path that creates a committed ArtifactVersion. Reject keeps
  a blocked draft, creates no committed ArtifactVersion or trading Decision and emits no
  `artifact.committed` Domain Event. Edit does not re-run model or Search execution.
- RED/GREEN was not limited to assertions. The current-source browser stack first failed
  on a notification credential that was not 32 bytes and a Next 16 same-directory dev
  lock; the isolated stack now uses a valid key and the current production Next build,
  while preserving the user's existing dev process. Browser iterations then exposed an
  exact source locator error, textarea accessible-name ambiguity, disabled-control
  contrast and a transient `4.36/4.47` primary-button contrast failure during a 180 ms
  color transition. Locators were scoped, disabled contrast was raised, and foreground /
  background colors now change atomically while only border, shadow and transform
  animate. The unchanged axe gate passes.
- Fresh backend evidence: HITL-focused `48 passed`; complete default backend
  `957 passed, 177 skipped, 1 warning`; Ruff check and format-check passed for all 194
  backend files. Every skip remains unproved and the warning is the existing
  Starlette/httpx deprecation.
- Fresh isolated PostgreSQL evidence: complete integration `209 passed, 7 skipped` plus
  a targeted Deep Research typed interrupt projection `1 passed, 73 deselected`. The
  aggregate suite covers in-memory Graph approve/reject/edit/re-review, PostgreSQL
  pause/response projection, the existing success report store and Worker recovery; it
  is not one required-review draft-to-terminal PostgreSQL E2E. The seven licensed
  persistent Agent Server tests remain explicitly unproved.
- Fresh frontend evidence: 34 unit files / `416 passed`, typecheck, lint and production
  build passed. Root structure/deployment is `1199 passed, 51 warnings`; diff check passed.
- The first final root rerun retained a real structure RED: notification polling used
  `JSON.stringify` inside a TSX product surface to compute an internal projection
  fingerprint. It did not render JSON, but it bypassed the shared identity helper and
  violated the strict product-surface boundary. The code now reuses
  `stableFingerprint()`; targeted structure/docs/discovery passed `57` tests, frontend
  remained `34 files / 416 tests`, and the complete root suite then passed all `1199`
  tests. The raw-JSON gate was not weakened.
- The first independent QA audit found that the new browser profile had escaped the
  Playwright discovery registry and that its `real-*` name overstated the controlled
  draft boundary. The profile is now `controlled-deep-research-hitl`, requires both the
  real Product stack gate and an explicit controlled-seed gate, and is covered by exact
  profile, npm command and missing-environment discovery contracts. Focused discovery is
  `32 passed`.
- Current-source browser execution used an isolated PostgreSQL database, official
  development Agent Server, unified Worker and current production Next build. Desktop
  completed `edit -> second review -> approve -> committed report -> reload`; Pixel 7
  completed `reject -> blocked -> reload`; result `2 passed (16.0s)`. Every key state ran
  axe, duplicate-ID, unnamed-control, horizontal-overflow, raw-JSON, console, page-error,
  HTTP 5xx and full-page screenshot checks.
- Evidence boundary: the controlled seeder injects a prebuilt draft through official
  development Runtime `update_state` and creates the waiting-human Product projection.
  The browser profile therefore proves only the post-draft Product respond/Worker/
  official-resume/terminal chain. It does not prove initial Product admission, initial
  Worker dispatch, Deep Agent delegation, external model/Search, real evidence
  collection, pending-state rejoin, concurrent first-writer, stale checkpoint or restart
  durability. Desktop and Pixel 7 cover different decision branches rather than every
  branch on both viewports.
- No content-addressed JUnit/HTML/trace/screenshot receipt was retained in the repository.
  The exact Playwright pass count is current-session evidence, not candidate-bound release
  attestation.

Detailed record:
`docs/v2/implementation/2026-07-19-task-13-deep-research-mainline.md`.
Task 13 remains `partial`; all 16 planned Tasks remain `partial`, with `done=0`,
`blocked=0` and `not_started=0`. Task 8 remains `RED / PARTIAL`; V2 remains `PARTIAL`;
`Production Ready: NO`. No code was staged, committed or pushed.

### 2026-07-19: Final single-delegation Deep Research provider audit

Phase: `G0.2 / Task 13 official harness and provider closure`; provider RED

- The temporary `SUBAGENT_DELEGATION_LIMIT=3` is not the final design. Retained runner
  `/tmp/crypto-alert-real-deep-research-20260719-135341` proved Desktop could still
  exceed the task budget while Pixel 7 failed built-in Search with
  `APITimeoutError`; both paths produced zero pauses, WebEvidence, Artifacts and
  Decisions.
- The current design restores limit `1` and uses only official extension points:
  LangChain `AgentMiddleware` sync/async model hooks set
  `parallel_tool_calls=False` through `ModelRequest.override`, and Deep Agents
  `HarnessProfile.tool_description_overrides` replaces the generic concurrent task
  instruction with one complete delegation to the approved researcher.
- The researcher calls `verified_web_search` once with one to three queries. The Run
  ledger executes queries sequentially, preserves partial verified evidence, raises the
  earliest real typed provider exception on total failure, merges successful query
  results round-robin and caps the source catalog at eight. A first successful tool
  envelope is cached per Run so harness transport retry cannot repeat external Search.
- Detailed query failures are mapped through provider/error-kind allowlists into
  immutable Artifact-level `search_coverage`. The model receives only coarse coverage;
  report editing cannot alter coverage, sources, harness mode or model audits. Frontend
  strict Zod and the report projection render the successful/attempted count and a
  readable failed-query disclosure without raw JSON.
- Real provider evidence remains RED. Three direct real Deep Research runs ended after
  `57.65s`, `62.04s` and `125.14s` with `APITimeoutError`,
  `InternalServerError` and `APITimeoutError`. A bounded one-attempt capability probe
  reached `UnverifiedServerToolCall`; a two-attempt probe reached that state in
  `11.376s`, then preview failed with `InternalServerError` in `2.528s`. Retry timing was
  reallocated inside the unchanged maximum three attempts and 30-second total budget.
  No successful direct Run produced verified evidence or a draft, so the full browser
  runner was not repeated and DDGS was not substituted as approved proof.
- Fresh local regression: focused Deep Research/review/retry/domain-event `104 passed`,
  ledger/harness focused `15 passed`, in-memory HITL plus seed `26 passed`; frontend
  typecheck/lint and all 34 unit files / `416 passed`.
  PostgreSQL-gated Product/dispatcher selections remained `5 skipped` without
  `REAL_DATABASE_TESTS=1` and are explicitly unproved.
- A final response-shape probe emitted no content or URL and received
  `APIConnectionError` after `17.08s`, before any response block existed. No parser
  compatibility exception was added because there is still no valid provider response
  proving that the strict citation parser rejected an official shape.
- A fresh current-source local inspection stack started on Agent `8123`, Worker `19091`
  and frontend `3001` with the existing PostgreSQL. Product Task
  `db35d0bf-d100-4a6f-9402-9bc391f93da4` passed admission/dispatch/official Run and ended
  `failed` with one safe `builtin_web_search / APITimeoutError / attempt=3` error,
  correlation `748be9fb-5328-5886-84a4-4efb121bc19f`, zero WebEvidence, zero Artifact
  and zero interrupts. Desktop/Pixel 7 browser reloads retained the same terminal Task;
  DOM scans found no horizontal overflow, duplicate IDs, unnamed controls, raw JSON or
  console errors.
- The live Pixel 7 screenshot exposed canonical diagnostic values wrapping awkwardly in
  a two-column grid. The below-700px grid is now one column; live computed value widths
  are `333px` with no scroll overflow, and Desktop values fit four real columns. A
  vertical skip-link seen only in one full-page capture was a fixed-element stitching
  artifact: its computed Y position was `-56px`, it was not focused, and viewport
  screenshots did not render it.
- Controlled Artifact Playwright now uses typed partial `search_coverage` and explicitly
  asserts `1 / 2`, expands query 2 timeout metadata and then runs persisted rejoin,
  source deep-scroll, axe, overflow, duplicate-ID, accessible-name and raw-JSON gates.
  Desktop and Pixel 7: `2 passed (7.3s)`. This is UI evidence only, not real Search
  success.
- The production provider now uses the official locked `ChatOpenAI.bind_tools` contract
  rather than prompt-only tool selection. Every attempt supplies the current well-known
  server tool as `tool_choice` plus `parallel_tool_calls=False`; LangChain converts
  `web_search` and `web_search_preview` to the Responses API `{"type": ...}` shapes.
  Focused Search capability/readiness/retry regression: `126 passed, 1 warning`; the
  warning is the existing Starlette/httpx deprecation.
- Safe real probes returned no content, URL or raw provider payload. Forced
  `web_search` produced only one plain text block with zero completed Search calls, zero
  tool calls and zero provider citations, proving the configured endpoint ignored the
  forced server tool. Forced `web_search_preview` returned `InternalServerError`.
  Running the repaired `BuiltinWebSearchProvider` under its hard 30-second budget then
  produced attempt 1 `UnverifiedServerToolCall` in `13.12s`, preview attempts 2/3
  `APITimeoutError` in `7.04s`/`7.52s`, and terminal retryable
  `APITimeoutError attempt=3`.
- Provider preflight therefore remained RED and correctly prevented another expensive
  full Deep Agent/browser run. The local inspection stack was restarted on Agent
  `8123`, Worker `19091` and frontend `3001`; those processes now run the exact
  forced-tool source. No stage, commit or push was performed.

Task 13 remains `partial`; Task 8 remains `RED / PARTIAL`; all 16 planned Tasks remain
`partial` (`done=0`, `blocked=0`, `not_started=0`). V2 remains `PARTIAL`;
`Production Ready: NO`. No code was staged, committed or pushed.

### 2026-07-19: G0.2 blocked-audit and explicit unblock conditions

Phase: `G0.2 / external provider unblock audit`; status: `BLOCKED`, with product
verdict still `PARTIAL` and `Production Ready: NO`

- The same external provider blocker has been reproduced across three consecutive
  goal turns. The configured production search path is `builtin_web_search` through
  the compatibility endpoint origin `https://xixiapi.cc`; the model credential is
  configured, but the Tavily credential is not configured.
- The official forced-tool probes did not return a completed server search, a
  provider URL citation, or a valid web-search tool envelope. The repaired provider
  consequently exhausted its bounded retry policy with a typed terminal
  `APITimeoutError` after observing `UnverifiedServerToolCall`; the real Product
  Task failed safely with zero WebEvidence and no Artifact. This is a provider
  capability/configuration failure, not a parser failure and not a reason to weaken
  citation or schema gates.
- G0.2 is therefore not passed. Peripheral M5/M6 expansion remains paused until
  the canonical Deep Research path can produce verified external evidence in the
  real Product chain.

G0.2 may resume only when one of these approved conditions is met and re-verified by
the existing capability/readiness probes:

1. The configured Responses Web Search endpoint is replaced or repaired so a forced
   official server-tool request returns a completed search and provider URL
   citations; or
2. A configured, reachable Tavily credential is supplied and the approved Tavily
   provider passes its readiness and citation checks.

After either condition, rerun the real Deep Research/Product browser profile on
Desktop and Pixel 7, retain the evidence receipt, and only then reassess Task 8 and
the remaining M1-M6 gates. No stage, commit or push was performed.

### 2026-07-19: resumed goal configuration audit

The resumed production goal performed a safe local configuration audit without
reading or emitting secret values. Current state is unchanged: `APP_ENVIRONMENT`
is `development`, the selected provider is `builtin_web_search`, the model
credential is configured, and `TAVILY_API_KEY` is not configured. Worker readiness
remains `live=true, ready=true`. The first frontend probe omitted quoting around the
query string and zsh expanded `?`; this was a probe invocation error, not a product
failure. The correctly quoted retry returned HTTP `200`. An unauthenticated Agent
Server `/health` request returned the expected HTTP `401` and was not treated as a
readiness failure.

No provider switch or service restart was performed. G0.2 remains blocked on the
external capability conditions recorded above; no search, artifact, or browser
success claim was added.

### 2026-07-19: transient Tavily real-provider Deep Research GREEN

Phase: `G0.2 / Task 13 real-provider closure`; local real evidence GREEN, production
delivery still open

- The user supplied a Tavily credential for this test turn. It was injected only into
  the isolated runner process; it was not printed, written to `backend/.env`, stored in
  the repository, or included in the retained evidence. The runner explicitly selected
  `SEARCH_PROVIDER=tavily` so this result does not claim that the default Compose
  `builtin_web_search` setting has changed.
- Three earlier Tavily browser attempts were retained as honest RED evidence before the
  final pass. The first (`/tmp/crypto-alert-real-tavily-20260719-081215`) exposed a
  legitimate `waiting_human` race plus a Pixel provider connector failure. The second
  (`/tmp/crypto-alert-real-tavily-rerun-20260719-083110`) exposed bounded structured
  output failure on Desktop and missing HITL-time WebEvidence on Pixel. The third
  (`/tmp/crypto-alert-real-tavily-final-20260719-085356`) completed the business flow
  through approval on both viewports but failed the approval confirmation axe contrast
  gate.
- The fixes are bounded and directly correspond to those failures: aiohttp connector
  failures are classified as retryable under the existing three-attempt/30-second
  policy; official LangChain `ToolStrategy` instances use bounded repair messages;
  strictly validated Tavily evidence is persisted idempotently before each
  `waiting_human` pause; the Playwright state machine accepts a valid first-round
  `waiting_human` recovery state; dark confirmation text meets axe contrast; and the
  real Deep Research admission wait is 300 seconds instead of reusing the 180-second
  market-analysis SLO.
- Final isolated runner:
  `/private/tmp/crypto-alert-real-tavily-final-20260719-091648`. It used an isolated
  temporary PostgreSQL database, Alembic head, official LangGraph development Agent
  Server, unified Worker and a production Next build. Playwright ran the same full
  Product path on `fixture-desktop` and `fixture-pixel-7`: admission, official
  Thread/Run identity, Tavily retrieval, report draft, pending reload, edit, second
  review, approval confirmation, committed report and terminal reload. Result:
  `2 passed`, `0 skipped`, `0 unexpected`, total `6.3m`; JUnit validation is valid and
  both expected projects contain exactly one passing testcase.
- Database validation is `valid=true` with no errors. Each task ended `succeeded` with
  three Product Runs (`waiting_human`, `waiting_human`, `succeeded`), two resolved
  pauses, six domain events, one committed `ArtifactVersion`, and 24 persisted Web
  Evidence rows. Each task has eight unique content hashes and eight unique URL hashes;
  every provider value is `tavily`, and no duplicate evidence was created across the
  pause/edit/resume sequence. The current Deep Research contract intentionally expects
  zero trading `Decision` rows; the accepted review is represented by the command,
  pause/resume lineage, committed ArtifactVersion and domain events.
- The browser quality receipts passed the existing DOM/axe/visual/network gates:
  no axe violations, duplicate IDs, unnamed controls, raw JSON, horizontal overflow,
  browser console/page errors or HTTP 5xx were recorded. Agent logs contain expected
  development-runtime stream-disconnect warnings during page reloads, but no exception
  or traceback; this is not licensed restart/durability evidence.

This closes the transient local real-provider proof for the Deep Research mainline. It
does not close Task 13 as a whole, G0.2 for the default built-in provider, Task 8
licensed durability, hosted OIDC/HTTPS, external LangSmith/Langfuse delivery,
production notifications, backup/recovery, SLO, security/release attestation or the
remaining M1-M6 requirements. V2 remains `PARTIAL`; `Production Ready: NO`. No code
was staged, committed or pushed.

### 2026-07-19: real Tavily Market Analysis mainline and blank-proxy repair

Phase: `G0.2 / real market-analysis Product closure`; local real evidence GREEN,
production delivery still open

- Main-flow priority moved from the not-yet-implemented Scheduled Monitor slice back to
  the central trading-analysis path. The tested chain was Product admission -> durable
  TaskCommand -> unified Worker -> official development Agent Server -> one canonical
  StateGraph -> real OKX -> real Tavily -> `gpt-5.5` structured research and market
  analysis -> Evidence/risk gates -> committed ArtifactVersion/Decision -> readable
  frontend. The user-supplied Tavily credential was injected only into the isolated
  Agent/Worker process environments and was never written, printed or copied into the
  retained evidence.
- The first Desktop/Pixel 7 run is retained at
  `/tmp/crypto-alert-real-market-tavily-20260719-100000`. Both Tasks failed honestly with
  `ValueError: Unknown scheme for proxy URL URL('')`; each retained a failed/error Run,
  one terminal event and zero Snapshot/Evidence/Artifact/Decision. The documented
  optional proxy settings had preserved blank environment values as empty strings, and
  `OkxProvider` passed `proxy=""` into `httpx.Client`.
- `Settings` now normalizes blank optional URL/string values and optional secrets to
  `None`. `SEARCH_PROVIDER=tavily` also requires a nonblank `TAVILY_API_KEY` during
  Settings validation. Focused contracts cover blank proxy/config normalization and
  blank credential rejection. The rerun deliberately retained blank market/search proxy
  variables, directly proving the repaired runtime assembly.
- The GREEN evidence is retained at
  `/tmp/crypto-alert-real-market-tavily-rerun-20260719-100400`. Desktop passed in `39.6s`,
  Pixel 7 in `41.4s`; aggregate result `2 passed in 1.4m`, `0 skipped`, `0 unexpected`.
  Both viewports asserted a committed actionable result, matched citations, zero
  unmatched sources, Evidence/risk gates, provider provenance, `research-extraction-v1`
  and `market-analysis-v2` model audits, Chinese rationale and public HTTPS source links.
- DOM/visual/network gates were not weakened: zero axe violations, duplicate IDs,
  unnamed/clipped controls, raw-JSON `<pre>` surfaces, horizontal overflow,
  console/page errors or failed Product/Agent responses. Full-page screenshots are
  `frontend/artifacts/playwright-real/real-product-success-real-provider-desktop.png`
  (`1440x6326`) and
  `frontend/artifacts/playwright-real/real-product-success-real-provider-pixel-7.png`
  (`1082x24830`). Manual inspection confirms real market data, eight readable source cards,
  analysis/risk/provenance/model-audit content and a single-column mobile layout without
  overlap.
- Isolated Product database `crypto_alert_v2_market_tavily_20260719095531` contains two
  successful Tasks: `8ccffa67-a4d8-4640-99c2-44245bafaaec` and
  `27f73d6d-9d0d-42b4-912d-a35121d9a9ff`. Each has one succeeded/success Run, one real
  OKX snapshot, eight Tavily Evidence rows with eight unique URLs and content hashes,
  one committed ArtifactVersion, one `no_trade`/manual Decision and seven ordered Domain
  Events from market snapshot through `run.terminal`. Artifact provenance is
  `okx/tavily/openai-compatible/gpt-5.5`. Notification count is zero because the browser
  submission intentionally used `notify=false`.
- Fresh regression is backend provider/runtime/Graph `198 passed, 0 skipped`, Ruff all
  checks passed, root docs/routes/Playwright discovery/runner `74 passed`,
  frontend typecheck/lint and all `34` unit files / `416 passed`, plus Playwright
  discovery/profile contracts `35 passed`; `git diff --check` passed. Prettier is not
  configured or installed, so no Prettier result is claimed. A secret scan excluding all
  `.env*`, generated evidence, dependencies and Git data found no `tvly-dev-` occurrence
  in the repository.
- The active local inspection stack remains available at frontend `3001`, Agent Server
  `8123` and Worker readiness `19091`. Agent logs contain successful Tavily attempts and
  successful terminal Runs, with only normal page-reload stream disconnect warnings and
  no post-restart traceback. This is development Runtime evidence, not licensed
  persistence.
- Multi-Agent backend/QA/frontend audits agree that Scheduled Monitor/Cron is currently
  essentially absent, not a nearly complete UI task. The accepted next boundary uses
  locked official SDK `client.crons.create/search/update/delete`, one canonical Graph
  with strict `monitor_ingress`, stable-reference-only Cron input, and the existing
  `task_commands` plus `CommandDispatcher` as the only Product analysis admission path.
  Local development Cron capability cannot replace licensed/hosted proof.

Detailed record:
`docs/v2/implementation/2026-07-19-real-tavily-market-analysis-mainline.md`.
This closes the local real Tavily Market Analysis slice, not the default built-in Search
provider, hosted/licensed Agent Server, hosted OIDC/HTTPS, notifications, external
LangSmith/Langfuse, release/SLO/security evidence or full M1-M6 delivery. V2 remains
`PARTIAL`; `Production Ready: NO`. No code was staged, committed or pushed.

### 2026-07-19: G0.2 real Monitor path, mounted-auth correction, and fixture boundary

Phase: `G0.2 / real Product + Monitor mainline`; local evidence is mixed but the
Monitor browser slice is GREEN. The overall V2 verdict remains `PARTIAL` and
`Production Ready: NO`.

- The earlier mounted Product API `401 resource_token_invalid` was reproduced directly:
  Agent Server `/app/api/v2/health` accepted the local Agent token, while
  `/app/api/v2/artifacts` rejected it because the Product API requires a scoped user
  identity. The failure was caused by starting the host stack with `APP_ENVIRONMENT=local`
  and a bootstrap identity/context that did not match the existing PostgreSQL membership;
  it was not evidence that the Library had no reports. The corrected local-proof runtime
  uses the repository's explicit `development` bootstrap boundary and the matching
  existing membership. Direct mounted Product API and Next BFF requests then returned
  `200` and exposed three real committed `analysis_report` artifacts. No Product API
  authentication bypass or custom header was added.
- The live test Monitor that was generating five-minute external calls was paused before
  further debugging. The final real Browser profile used the existing live PostgreSQL,
  official development Agent Server, unified Product Worker, Next BFF, real committed
  Artifact and real Monitor/Cron API. It ran Desktop Chrome and Pixel 7 with no route
  interception or fixture API. After one honest selector RED and one honest axe contrast
  RED, the corrected run passed `2 passed in 8.3s` in:
  `/tmp/crypto-alert-real-monitor-e2e-20260719-continue-3`.
- The real Monitor flow covered Library -> committed Artifact -> create Monitor ->
  scheduler activation -> refresh/rejoin -> trigger history -> pause -> resume ->
  manual trigger -> admitted Product Task -> delete while retaining history. Both
  viewports passed DOM/axe, one-main-landmark, duplicate-ID, named-control, overflow,
  clipping, raw-JSON, sentinel, console, request-failure and HTTP-5xx gates. The first
  selector failure was corrected to use accessible `role=combobox` names. The second
  failure exposed low-contrast action states; the action text colors were raised to
  verified high-contrast values in `frontend/src/features/monitors/monitors.module.css`.
- Two real manual-trigger Tasks were then observed in PostgreSQL. Task
  `b0b29dfb-b98e-412f-9126-5bff9eb8bef9` ended `succeeded` with one real MarketSnapshot,
  16 WebEvidence rows, one Decision, one committed ArtifactVersion and eight Domain
  Events. Task `5e784f61-19ec-4086-be63-2e07bdff345c` ended honestly `failed` with
  `provider_unavailable`; its terminal event records a Tavily `TimeoutError` and zero
  WebEvidence. This is retained as RED, not converted to a pass.
- G0.1 follow-up tightened `tools/v2/start_integration_stack.sh`: the default
  `production` profile accepts only `backend/langgraph.json`; the multi-interrupt graph
  is accepted only under the explicit `task8-multi-interrupt-qa` profile used by the
  Task 8 probe. The rejection was executed and returned exit `65` for a production
  invocation with the fixture config. Focused syntax/profile tests passed. This does not
  prove the licensed Agent Server image or persistent restart path.
- Multi-Agent audit found a remaining product-quality P0: current historical Tavily
  evidence includes unrelated corporate sources that were persisted as `supports` while
  the no-trade Evidence/Risk gates still reported sufficient/allowed. This is an open
  deterministic relevance-gate repair; the current evidence is not being reclassified
  retroactively and no production-quality claim is made for it. Unsupported Monitor
  condition kinds likewise remain fail-closed work until the backend admission patch and
  tests complete.
- The local development Agent Server still emits the known upstream temporary-thread
  cleanup `404` after successful temporary Cron runs and its in-memory queue counters do
  not constitute hosted durability evidence. Licensed persistent Agent Server restart,
  checkpoint replay, `state.fork`, hosted OIDC/HTTPS, real LangSmith/Langfuse delivery,
  notifications, backup/restore, SLO, security and release attestation remain open.

No code was staged, committed or pushed.

### 2026-07-20: G0.2 relevance boundary and real Product/Monitor regression closure

Phase: `G0.2 / local real Product + Monitor regression`; the current local mainline is
GREEN, while the overall V2 verdict remains `PARTIAL` and `Production Ready: NO`.

- The open 2026-07-19 research-relevance P0 is superseded for newly executed runs by a
  deterministic BTC/ETH/SOL, crypto and macro relevance classifier. Provider results
  classified as unrelated are retained in Graph state and PostgreSQL as
  `evidence_relation="excluded"` for audit, but are not sent to either structured-output
  model, counted as verified/available Evidence, used by Evidence/Risk gates, included
  in Artifact `source_references`, or included in provenance aggregation. An all-excluded
  result fails closed as `NoRelevantResearchEvidence`. Historical rows were not rewritten
  or retroactively reclassified. The focused backend relevance/Graph suite passed
  `33 passed`; the frontend separately renders usable and excluded counts and labels
  excluded cards `已排除（相关性不足）`.
- The first fresh zero-route-override Product Playwright run retained two honest REDs:
  Desktop ended `provider_unavailable` after a Tavily `TimeoutError`; Pixel 7 ended
  `provider_unavailable / MissingCitedTicker`. Direct Tavily diagnosis showed the market
  fallback query `What is the current BTC price in USD? Return the exact numeric price.`
  returned unrelated general-finance pages. The query was changed to
  `current BTC USD price market data live`; strict cited-value and source validation was
  not weakened. Focused Web Market/Graph/runtime regression then passed `67 passed`
  with the existing Starlette/httpx deprecation warning, and Ruff passed.
- The second real Product run retained a separate frontend RED. Pixel 7 passed, and the
  Desktop Task reached `succeeded` in PostgreSQL, but the page remained `分析中` for 360
  seconds. Its Playwright trace showed one terminal projection GET exceeded the BFF
  eight-second budget and returned `502`; `pollTask` then permanently stopped despite
  the next PostgreSQL projection being readable. Product polling now retries transport,
  `408`, `429` and `5xx` failures with `1s, 2s, 4s, 8s`, capped at `10s`, while reporting
  the temporary read interruption. Non-retryable failures still stop and the BFF timeout
  was not increased, so the slow request is not hidden.
- The final real Product Desktop/Pixel 7 run passed `2 passed (1.7m)`. Task
  `ed45ba2c-fb2d-4b81-96d3-5bfef08bb8c3` and Task
  `29a172ae-824d-4aed-9910-32636515cb0a` each persisted 1 MarketSnapshot, 8 WebEvidence,
  1 committed ArtifactVersion, 1 Decision and 7 DomainEvents. Each Artifact has eight
  source references. These particular provider responses contained zero excluded rows;
  a direct PostgreSQL audit returned `excluded_urls_cited=0` for both Tasks. The Graph
  contracts, rather than the absence of excluded rows in these two responses, prove the
  downstream exclusion invariant.
- Frontend regression is `39 test files / 445 tests passed`; typecheck and lint passed.
  The final Product run also passed its existing DOM, axe, accessible-name, raw-JSON,
  overflow, clipping, console, request-failure and HTTP-5xx assertions on Desktop and
  Pixel 7.
- The first Monitor rerun retained a React console RED: the now-single-option condition
  `<select>` had a controlled `value` without `onChange`. The immutable condition is now
  the semantic non-interactive `<output>定期复核</output>`. The final real Monitor profile
  passed Desktop/Pixel 7 `2 passed (8.7s)` and retained JUnit, JSON, HTML, two traces and
  eight visual screenshots at
  `/tmp/crypto-alert-real-monitor-e2e-20260720-after-readonly-fix`.
- That Monitor run covered Library -> committed Artifact -> create scheduled Monitor ->
  scheduler active -> refresh/rejoin -> trigger history -> pause -> resume -> manual
  trigger -> Product Task admission -> delete with retained history. Its two admitted
  background Tasks have now reached terminal PostgreSQL states. Task
  `c53c4e94-fd63-41d8-9ee3-ecfd42cee19a` is deliberately `blocked` with zero execution
  errors, 1 MarketSnapshot, 8 supported WebEvidence, a draft output, 0 committed
  ArtifactVersion, 0 Decision and 6 DomainEvents. Task
  `d584e7d0-6ccf-4f35-a150-75c24c303f2e` is `succeeded` with 1 MarketSnapshot,
  8 supported WebEvidence, 1 committed ArtifactVersion, 1 Decision and 7 DomainEvents.

This evidence uses local PostgreSQL, the official in-memory development Agent Server,
the local Product Worker, Next development server and caller-injected real provider
credentials. It does not prove a licensed persistent Agent Server, restart/replay,
hosted OIDC/HTTPS, production egress, external LangSmith/Langfuse delivery, notification
receipts, backup/PITR, SLO/security or signed release acceptance. No code was staged,
committed or pushed. V2 remains `PARTIAL`; `Production Ready: NO`.

### 2026-07-20: Task 13 Product data-lifecycle local closure

Phase: `Task 13 / retention-export-deletion vertical slice`; local evidence GREEN,
Task 13 and V2 still `PARTIAL`, `Production Ready: NO`

- Added actor/workspace-scoped lifecycle policy, durable export/deletion jobs,
  reversible `0022_data_lifecycle`, and one `LifecycleWorker` inside the existing
  unified `WorkerRuntime`. Defaults are 365-day Product/Artifact retention, 30-day
  completed-checkpoint/technical/log retention, 35-day backup rotation, and raw
  Prompt/Response retention disabled. No second Graph, Agent Runtime or queue exists.
- Added strict Product API/BFF routes for policy, export status/manifest/bundle and
  deletion status. Admission uses the existing `Idempotency-Key` boundary. Export
  manifests and bundles are canonical SHA-256 verified. Deletion removes only current
  actor Product rows, preserves lifecycle audit jobs, scrubs prior export bundles, and
  truthfully leaves object storage/checkpoint/Store/search/LangSmith/Langfuse/log/backup
  systems `pending_external` without receipts.
- The shared development migration retained an honest `DuplicateTable` RED because an
  integration fixture had already used `Base.metadata.create_all`. Existing tables and
  indexes were checked against `0022`, then the shared database was stamped only to
  preserve local data; that stamp is not migration proof. A fresh temporary PostgreSQL
  completed the real `0001 -> 0022` upgrade, and the earlier clean upgrade/downgrade
  rehearsal remains local-only GREEN.
- The first mounted lifecycle BFF request retained `401 resource_token_invalid`: Next
  sent the local Agent token to an inner Product endpoint that requires a user context.
  Restarting the stack with the repository's explicit `development/local-proof` actor
  and matching membership restored Agent, Worker, frontend and policy health to `200`.
  No auth bypass was added.
- Real BFF export `a1bce70d-d750-4119-a89d-d7de1ddd2794` was admitted with `202`, claimed
  once by the unified Worker, completed with a released lease and no error, and returned
  a 23-group manifest/bundle pair. The shared actor had three exported watchlist rows.
  Independent canonical validation matched the persisted manifest and bundle hashes.
- Settings now renders typed policy, legal hold, export, manifest/download and deletion
  receipt states. The latest export pointer is stored only as an owner-UUID-scoped local
  UUID; reload re-fetches every object through the owner-scoped Product API and clears
  invalid, missing or actor-mismatched pointers. Pixel 7 navigation changed from an
  accidental six-column/one-orphan layout to stable four-column/two-row labels with no
  horizontal overflow.
- The first isolated Playwright run retained four REDs: both viewports failed axe color
  contrast for lifecycle panel descriptions, and both deletion paths timed out because
  a decorative switch track intercepted the native input. Text contrast and pointer hit
  testing were fixed in CSS. Axe was not excluded and clicks were not forced.
- Final zero-route-override production-build Playwright passed Desktop and Pixel 7
  export/reload plus legal-hold/deletion: `4 passed (10.0s)`. It retained strict response,
  idempotency, Worker polling, independent hash, parsed download, rejoin, DOM, axe,
  main-landmark, duplicate-ID, accessible-name, raw-JSON, sentinel, overflow, clipping,
  console/page-error, request-failure and HTTP-5xx gates. Receipt:
  `/tmp/crypto-alert-real-lifecycle-e2e-20260720-after-contrast-fix` with JUnit, JSON,
  HTML, four traces and ten screenshots.
- Final isolated PostgreSQL evidence contained two `blocked_legal_hold` jobs and two
  `pending_external` jobs. Actual deletions each had one Worker attempt,
  `product_db=succeeded`, external systems including LangSmith still
  `pending_external`, null external receipts and the explicit unavailable-adapter error.
  Both prior export bundles were scrubbed; legal hold was restored inactive. The
  isolated stack and database were removed after inspection.
- Fresh regression is backend unit/contract `975 passed, 1 skipped`, isolated
  PostgreSQL integration `220 passed, 7 skipped`, frontend `40 files / 453 passed`,
  lint/typecheck/build GREEN, root structure/deployment GREEN, Ruff and
  `git diff --check` GREEN. The eight skips are explicitly unproved live/licensed Agent
  Server Protocol, restart, authorization and durability capabilities; none count as
  passes.

Detailed record:
`docs/v2/implementation/2026-07-20-task-13-data-lifecycle.md`.
This does not close external deletion receipts, hosted OIDC/HTTPS, licensed Agent
Server restart/replay, Memory, Outcome, complete entitlement/usage, webhooks,
PITR/DR/SLO/security or release attestation. Task 13 remains `partial`; V2 remains
`PARTIAL`; `Production Ready: NO`. No code was staged, committed or pushed.

### 2026-07-20: Inbox direct-review slice and Windows/Docker handoff

Phase: `M3 follow-up / Product Inbox direct review`; implementation is recorded in
the current worktree and is being prepared for a remote checkpoint commit. The V2
verdict remains `PARTIAL`, `Production Ready: NO`.

- Added the Product-owned `POST /api/v2/inbox/{pause_id}/respond` boundary for a
  single-member Inbox pause. The server resolves the real interrupt member and
  response version before reusing the existing official interrupt persistence path;
  runtime checkpoint and namespace coordinates are not exposed to the browser.
- Added typed frontend schemas, Product client/BFF forwarding, direct approve/reject/
  edit states, idempotent retry handling, permission/conflict/network error states,
  focus refresh and timed refresh. Multi-member pauses intentionally remain a Work
  atomic-review flow and are not silently reduced to a partial Inbox action.
- The current `real-inbox-flow.spec.ts` still proves Inbox read/navigation behavior;
  it does not yet prove the new direct review click-through against a real persistent
  Agent Server. This is explicitly not counted as a full Playwright end-to-end pass.
- Added `docs/v2/19-windows-docker-development.md`, covering Windows 11 + WSL2 +
  Docker Desktop setup, environment/secret boundaries, full Compose topology,
  migrations, backup/recovery limits, memory pressure and local troubleshooting.
- Final local verification for this checkpoint covers the focused Product Inbox
  contract/API tests, frontend unit/build checks and repository structure/deployment
  checks. A real database test is only claimed when `REAL_DATABASE_TESTS=1` and a
  configured `PRODUCT_DATABASE_URL` are present; in-memory Agent Server evidence is
  labeled local-only.

The checkpoint intentionally does not claim hosted durable Agent Server restart/
replay, external LangSmith/Langfuse delivery, notification receipts, Memory/Outcome,
PITR/DR, hosted OIDC/HTTPS multi-user matrices, formal SLO/security/SBOM or release
attestation. Those remain the next production gates after this backup commit.
