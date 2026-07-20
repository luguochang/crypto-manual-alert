# 2026-07-19 Task 13 Deep Research Mainline Slice

```yaml
slice_id: task-13-deep-research-mainline
phase: task-13-partial
owner_role: current_codex_implementer
owner_agent_id: current-thread-019f3c9c-9a47-78e1-a3b7-a82ff06effcb
normative_sha: unavailable-task-0-not-attested
base_sha: e9def238edbf1e04ef809d75a1eb293a4a81e310
candidate_sha: null
requirement_ids:
  - task-13-step-1-background-semantics-partial
  - task-13-step-3-restricted-research-harness
  - task-13-step-5-subagent-task-ui-partial
status: partial
```

`normative_sha` and `candidate_sha` are deliberately unavailable. Task 0 has no
attested normative candidate, this worktree is dirty, and the user explicitly requested
no stage, commit or push. This note records implementation evidence; it is not a Task 13
attestation.

## 1. Goal and Scope

This slice moves Deep Research from an isolated factory foundation into the existing
Product mainline:

1. Admit a typed Deep Research request through Product API.
2. Dispatch it through the existing Task, TaskCommand, Worker and official Agent Server
   lifecycle.
3. Route it inside the one canonical `StateGraph` without creating another graph,
   runtime, queue or event store.
4. Execute exactly one selected official harness: restricted Deep Agents or the explicit
   LangChain fallback.
5. Persist a cited `deep_research_report` ArtifactVersion and WebEvidence without
   creating a trading Decision.
6. Render the report, citations and sources through typed Product frontend projections.
7. Prove local browser disconnect/rejoin semantics and real PostgreSQL persistence.
8. Route a draft report through the canonical Graph's official HITL interrupt, Product
   Inbox/Work review, approve/reject/full-report edit and mandatory re-review lifecycle.

This is not all of normative Task 13. Monitor/Cron, lifecycle retention/export/deletion,
Outcome maturation, long-term memory controls, entitlements, usage reconciliation,
webhooks and their Product UI remain open.

## 2A. 2026-07-19 Real Tavily Mainline Revalidation

The isolated real-provider runner
`/private/tmp/crypto-alert-real-tavily-final-20260719-091648` completed the full
required-review browser path on both Desktop and Pixel 7 with `2 passed`, `0 skipped`.
The caller injected Tavily only for this process; no credential was persisted. Each
task produced three Product Runs, two resolved review pauses, 24 persisted Tavily
Evidence rows, eight unique content hashes, eight unique source URL hashes and one
committed `ArtifactVersion`. The contract intentionally creates no trading `Decision`
for a Deep Research report.

The final pass followed three honest RED runs. The repaired boundaries were: retryable
aiohttp connector classification, official bounded `ToolStrategy` repair messages,
idempotent evidence persistence at the HITL boundary, valid `waiting_human` recovery
recognition, dark confirmation contrast, and a 300-second Deep Research admission wait
separate from the market-analysis 180-second SLO. This proves the local real Tavily
Deep Research slice, not the default built-in provider, hosted/licensed Agent Server
durability, or the remaining Task 13 lifecycle and M1-M6 production requirements.

## 2. Official Framework Boundary

| Capability | Official component | Local decision |
|---|---|---|
| Deep research coordinator | `deepagents.create_deep_agent` | One restricted coordinator with no broad tools |
| Read-only delegation | Deep Agents `task` and named subagent | Only `verified-source-researcher`; one complete delegation covering macro, regulatory and market structure |
| Fallback | `langchain.agents.create_agent` | Explicit deployment mode; never dual-active |
| Structured result | `ToolStrategy` | Typed `DeepResearchReport` and `ResearchSection` |
| Budgets | `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware` | Fail closed on model, search or delegation excess |
| Filesystem boundary | `HarnessProfile`, `FilesystemPermission`, `StateBackend` | General-purpose subagent disabled; filesystem and execute tools excluded and denied |
| Graph orchestration | LangGraph `StateGraph` and async node execution | `task_type` conditional branch inside the existing graph |
| Report review | LangGraph `interrupt()` and `Command(resume=...)` | Same canonical review node and checkpoint authority as Market Analysis; no second review runtime |
| Server lifecycle | Existing Agent Server Thread/Run APIs | Same assistant, Thread lineage and Worker |
| Frontend stream | Existing `@langchain/react` stream plus Product projection | Live stream is enhancement; Product Task remains durable authority |

The implementation follows ADR 0009 and ADR 0010. It does not introduce a custom agent
loop or a second production graph.

## 3. Data Flow

```text
POST /api/v2/deep-research
  -> Product Task(task_type=deep_research)
  -> existing submit TaskCommand
  -> existing CommandDispatcher
  -> existing Agent Server assistant / Thread / Run
  -> canonical StateGraph validate_request
  -> run_deep_research
  -> restricted official harness
  -> verified_web_search source ledger
  -> typed draft DeepResearchReport
  -> canonical review_policy
  -> official interrupt(deep_research_review)
  -> Product InterruptPause / Inbox / Work
  -> approve | reject | full-report edit
  -> edit returns to a second official interrupt
  -> approve/bypass commits deep_research_report ArtifactVersion
  -> WebEvidence + Domain Events
  -> Product Task / Run / Library / Artifact projections
  -> typed frontend report and source disclosure
```

Browser disconnection only removes the UI stream. It does not cancel the Product Task or
official Run. Reopening the Task reads the persisted Product projection.

## 4. Contracts and Invariants

- One Run gets one source ledger; evidence cannot leak between Runs.
- Search accepts at most three bounded queries in one tool call.
- At most eight deduplicated sources are retained.
- Model-visible source data contains only assigned index, title, excerpt and publication
  time. Raw URL and provider payload are not model output fields.
- Every finding cites unique indexes in `1..8`.
- Source catalog indexes are ordered and contiguous; every citation resolves.
- URL/content-hash duplicates fail the artifact materialization contract.
- Deep Research commits `deep_research_report`; it never masquerades as an
  `analysis_report` and never creates a trading Decision.
- The executor creates only a typed draft. Only the canonical approve/bypass commit node
  can create a committed `deep_research_report` ArtifactVersion.
- Required review emits the typed `deep_research_review` interrupt through official
  LangGraph `interrupt()` and resumes through official `Command(resume=...)`.
- Edit replaces the complete typed `DeepResearchReport`, revalidates every citation
  against the immutable source catalog and always enters a second review round.
- Source catalog, harness mode, model audits and artifact status cannot be edited by the
  browser. Wrong task type, symbol, horizon, edit type, no-op edit or out-of-range
  citation fails closed.
- Reject preserves a blocked draft, creates no committed ArtifactVersion or trading
  Decision, and emits no `artifact.committed` Domain Event.
- Unknown harness mode fails closed. Deep Agents and LangChain fallback cannot both run.
- No raw prompt, response payload, Authorization, Cookie or secret is persisted by this
  slice.

## 5. Product Surface

- `POST /api/v2/deep-research` and the same-origin Product BFF route.
- Work segmented mode for Market Analysis and Deep Research.
- Typed report rendering with sections, findings, citation indexes, risk notes, evidence
  gaps and verified source links.
- Run list/detail, Artifact Library and Artifact Detail recognize research task/artifact
  types.
- Official progress UI can expose the bounded `verified-source-researcher` state without
  rendering raw stream JSON.
- Work and Inbox parse a discriminated interrupt union and render a dedicated typed
  report-review surface for approve, reject and full-report edit.
- The research report remains readable when `agent_stream` is absent or disconnected.

## 6. Persistence

The existing Product schema is reused. No new database queue or second durable event
store was added. A required-review Deep Research lifecycle first persists a Product
pause/projection while the report remains a draft. Approval records:

- one Product Task with `task_type=deep_research`;
- one initial submit command and initial Product/official Run binding;
- one durable respond command and a new Product resume Run for each accepted review
  batch; official resume keeps the same Thread/checkpoint/interrupt lineage but creates
  a new official Run on that Thread;
- one `deep_research_report` Artifact;
- one ArtifactVersion;
- verified WebEvidence and Domain Events;
- zero trading Decisions.

Library and Artifact Detail read the same persisted version and expose no synthetic
market snapshot or Decision. Rejection leaves the draft blocked and does not create a
committed ArtifactVersion. Edit updates the typed draft and persists a second interrupt;
it does not re-run the model or Search executor.

## 7. Fresh Evidence

| Gate | Command/result | Evidence boundary |
|---|---|---|
| Restricted official harness | earlier focused backend suite: `268 passed, 35 skipped`; HITL closure focus: `48 passed` | Includes a real `create_deep_agent` delegation path with controlled fake chat model/search and typed review contracts; not an external Provider run |
| Complete default backend | `uv run pytest -q`: `957 passed, 177 skipped, 1 warning` | 177 skips remain unproved; warning is the existing Starlette/httpx deprecation |
| Root structure/deployment | `uv run pytest`: `1199 passed, 51 warnings` | Full root suite green; warnings are existing deprecations, not skips |
| Deep Research PostgreSQL lifecycle | process-local `REAL_DATABASE_TESTS=1` and isolated PostgreSQL: `1 passed, 34 deselected` | Real PostgreSQL persistence, no licensed Agent Server restart |
| Complete PostgreSQL integration | isolated temporary PostgreSQL: `209 passed, 7 skipped` | Aggregate coverage: in-memory Graph review semantics, PostgreSQL pause/response projection, existing success report store and real Worker SIGKILL recovery; not one required-review PostgreSQL E2E; 7 licensed durability tests remain unproved |
| Frontend unit/static/build | `416 passed`; lint, typecheck and production build passed | Typed Product/BFF/UI contracts only |
| Deep Research Playwright | Desktop `1440x1000` and Pixel 7 `412x915`: `2 passed` | Fixture Product response; persisted re-read, axe, DOM, overflow, raw JSON and screenshots |
| Controlled post-draft HITL Playwright | Desktop edit/re-review/approve plus Pixel 7 reject: `2 passed (16.0s)` | Isolated PostgreSQL, current-source dev Agent Server/Worker and production Next build; controlled seeder injects the draft, so provider/model/Search and initial dispatch are not proved |
| Playwright discovery | focused contract `32 passed` | Profile is explicitly named and gated as `controlled-deep-research-hitl`; discovery is not body execution |
| Code/diff hygiene | Ruff check and format-check passed for 194 files; `git diff --check` passed | No stage, commit or push |

Test logs were not written to a retained content-addressed evidence directory, so no log
SHA-256 is claimed. The controlled HITL `2 passed` result is current-session execution
evidence, but no JUnit/HTML/trace/screenshot receipt was retained in the repository.
Playwright screenshots were inspected during execution; they are not release attestation.

## 8. Visual and DOM Verification

The original report-projection Playwright scenario verifies:

- the report and source link render on Desktop and Pixel 7;
- navigation to `about:blank` and back causes the same Product Task to be read again;
- no `<pre>` or raw artifact JSON is shown;
- no horizontal document overflow, duplicate IDs or unnamed controls;
- full axe scan has zero violations;
- deep scroll reaches the verified source catalog;
- full-page screenshots contain the report, source disclosure and request controls.

The controlled post-draft HITL scenario additionally verifies Desktop
`edit -> second review -> approve -> committed report -> reload` and Pixel 7
`reject -> blocked -> reload`. Each key state runs axe, duplicate-ID, unnamed-control,
horizontal-overflow, raw-JSON, console, page-error and HTTP 5xx checks plus full-page
screenshots. These are complementary viewport branches, not proof that every action ran
on both viewport sizes.

The first report-projection GREEN exposed a real `color-contrast` failure at 4.4:1 in the official stream
subtitle. The local text now uses the existing higher-contrast token and the unchanged
axe gate passes. A second failure came from the test auditor ignoring native associated
`<label>` elements on radio inputs; the scanner now resolves `aria-label`,
`aria-labelledby`, native labels and text instead of adding redundant production ARIA.
The HITL run then exposed disabled-control contrast and a transient `4.36/4.47` primary
button contrast failure during a 180 ms color transition. Disabled terminal controls now
meet contrast, while foreground/background switch atomically and only border, shadow and
transform animate.

## 9. Additional Regression Repairs

| Failure | Root cause | Repair | Regression |
|---|---|---|---|
| Graph export contract expected five context fields | Deep Research runtime fields were not added to the exact schema assertion | Include executor and harness mode in the official context contract | targeted `2 passed`; full backend green |
| Product stream test expected four queries and scalar artifact lookup | Product projection now includes scoped cancellation and typed artifact query | Assert all five scoped statements and the current execute path | targeted `2 passed`; full backend green |
| Shared PostgreSQL full suite produced 9 failures | Existing database contained prior notifications/credentials and invalidated global-count tests | Preserve the shared database and rerun on a fresh isolated PostgreSQL container | initial `204 passed, 7 skipped`; current HITL closure `209 passed, 7 skipped` |
| Worker recovery timed out before contacting fake Agent Server | Real Worker subprocess collided with the user's live health port 9090 | Allocate an isolated loopback health port per subprocess | recovery `2 passed`; full integration green |
| Retry/run-list integration assertions failed | New selected-run projection and `task_type` were absent from old expected values | Assert the explicit projection scope and task type | full integration green |
| Notification credential startup failed | Controlled stack supplied a key that was not exactly 32 bytes | Generate a valid isolated credential key | current-source stack started |
| Next 16 refused a second dev server in the same directory | Existing user process owned the development lock | Use the current production build on an isolated port without terminating the user's process | HITL Playwright `2 passed` |
| Review controls failed axe contrast | Disabled terminal controls and a color transition crossed the contrast threshold | Raise disabled contrast and synchronize foreground/background state changes | unchanged axe scan green |
| New Playwright profile escaped discovery coverage | Profile, npm command and missing-environment gate were absent from the registry test | Rename it `controlled-deep-research-hitl`, require an explicit controlled flag and add all discovery cases | focused discovery `32 passed` |
| Final root product-surface gate found `JSON.stringify` in notification TSX | Notification polling used ad hoc serialization only as an internal change fingerprint | Reuse the existing deterministic `stableFingerprint()` helper; keep the raw-JSON structure gate strict | targeted structure/docs/discovery `57 passed`; final root `1199 passed` |

## 10. Explicitly Open

P0/P1 completion gaps:

- Fresh real external model plus Web Search Deep Research Runs were executed, but all
  remain RED before verified evidence; no successful external Deep Research Run exists.
- No licensed persistent Agent Server restart/replay/durability proof exists.
- No hosted OIDC/HTTPS, LangSmith or Langfuse trace is attached to a Deep Research Run.
- The browser starts from a controlled injected draft. Product admission, initial Worker
  dispatch, Deep Agent/model/Search execution and evidence collection are not part of
  that browser proof.
- Pending-review reload, concurrent first-writer/double-submit, stale checkpoint and
  restart recovery are covered only partially by lower-level contracts, not by this
  Deep Research browser profile.
- Task 13 monitor/Cron, retention/export/deletion, Outcome, memory,
  entitlement/usage/webhook implementation and UI remain absent.
- No candidate commit, independent review, requirement receipt or attestation exists.

Therefore Task 13 remains `partial`, Task 8 remains `RED / PARTIAL`, V2 remains
`PARTIAL`, and `Production Ready: NO`.

## 11. Real Provider Runner Follow-up

A current-source zero-route-override runner now creates an isolated PostgreSQL database,
migrates `0001 -> 0019`, starts `langgraph dev --no-reload`, the unified Worker and a
production Next build, and executes the same admission/reload/edit/re-review/approve path
on Desktop and Pixel 7. It retains JUnit, JSON, HTML, traces, screenshots, videos,
secret-safe database lineage, review-policy receipts, redacted logs and SHA-256 manifests.
It never reads `backend/.env`, scrapes another process environment or terminates the
user-owned port `3110` process.

The first run exposed two runner defects before Product admission: a `psql -c` variable
binding error and an exact Playwright label locator that could not match the wrapped
`select`. Both were repaired; runner contracts are `8 passed`, Bash/profile validation
and frontend typecheck/lint pass. The retained pre-admission RED receipts are:

- `/tmp/crypto-alert-real-deep-research-20260719-131256`
- `/tmp/crypto-alert-real-deep-research-20260719-131444`

The next full run admitted two real Tasks and exposed a production code defect. The
coordinator generated three bounded `task` delegations for macro, regulation and market
structure, but `SUBAGENT_DELEGATION_LIMIT=1` rejected them before verified Search. A
temporary increase to `3` allowed progress but the retained
`/tmp/crypto-alert-real-deep-research-20260719-135341` run proved that this was not a
stable design: Desktop exceeded the new delegation budget while Pixel 7 reached built-in
Search and timed out. The final design therefore restores the hard limit to `1`, applies
official `ModelRequest.override(model_settings={..., "parallel_tool_calls": False})`
middleware to coordinator/researcher/fallback, and overrides the official Deep Agents
`task` description through `HarnessProfile` so one complete delegation carries all
research angles. Filesystem remains deny-all and the general-purpose subagent remains
disabled.

After that repair, the direct real Deep Agent reached `verified_web_search`, but the
explicit approved `builtin_web_search` provider exhausted all three attempts with
`APITimeoutError`. Explicit Tavily cannot run because no Tavily key is configured; DDGS
is not accepted as production evidence. Safe terminal diagnostics now preserve provider,
stage, error type, attempt and correlation ID without exception text, credentials or raw
payloads. The retained two-viewport provider RED receipt is:

- `/tmp/crypto-alert-real-deep-research-20260719-132947`

That receipt contains two failed Tasks, two failed first Runs, zero pauses, zero evidence,
zero Artifacts and zero Decisions. This is correct fail-closed behavior, not a successful
mainline claim. The approved real Provider success, required-review end-to-end GREEN and
release gates remain open.

## 12. Single-delegation and typed search-coverage closure

The final current-source implementation no longer treats the temporary delegation limit
of `3` as accepted. One coordinator turn may delegate exactly one complete task to the
single `verified-source-researcher`; the researcher may call `verified_web_search` once
with one to three normalized queries. LangChain's official sync and async middleware
hooks set `parallel_tool_calls=False`, while `ToolCallLimitMiddleware` remains the hard
runtime upper bound. No custom model loop or custom tool scheduler was added.

The per-Run source ledger now:

- searches the bounded queries independently and sequentially so one tool call cannot
  amplify to three simultaneous provider retry storms;
- preserves successful verified evidence when only part of the query set fails;
- raises the earliest real typed provider exception when every query fails, even if an
  earlier query merely returned an empty result;
- merges successful result sets round-robin and retains exactly eight sources at most,
  preventing the first research angle from monopolizing the catalog;
- caches the first successful tool envelope inside the Run ledger so a LangChain
  transport retry cannot repeat external Search;
- exposes only source indexes and coarse query coverage to the model;
- persists allowlisted provider/error-kind/attempt coordinates in the immutable
  Artifact-level `search_coverage`, not in the user-editable report text.

The strict backend and frontend schemas both validate complete/partial coverage counts,
ordered failed query indexes, canonical provider/error kinds and retry attempt bounds.
The Product UI renders a readable coverage band and optional failed-query disclosure;
report edit/re-review preserves this server-owned coverage together with sources,
harness mode and model audits.

Fresh evidence after these changes:

- focused backend Deep Research/review/retry/domain-event suites: final `104 passed`;
  the narrower harness/ledger rerun is `15 passed`;
- in-memory HITL plus controlled seed: `26 passed`;
- frontend typecheck and lint passed; all 34 unit files / `416 passed`;
- PostgreSQL-gated Product/dispatcher cases were discovered but remained `5 skipped`
  without `REAL_DATABASE_TESTS=1`; those skips are not evidence;
- direct real Deep Research remained RED in three current-session runs: first
  `APITimeoutError` after `57.65s`, then `InternalServerError` after `62.04s`, and final
  sequential single-delegation execution `APITimeoutError` after `125.14s`;
- bounded capability probes showed one 30-second attempt reached
  `UnverifiedServerToolCall`; a two-attempt probe reached that state in `11.376s` and
  then failed preview with `InternalServerError` in `2.528s`. The retry allocator now
  gives the first negotiation turn half of the same hard 30-second budget; it does not
  increase total attempts or total time. A final content-free structure probe received
  `APIConnectionError` after `17.08s` before any response blocks were available, so
  there is no evidence that the strict parser discarded a valid official citation.
- a fresh Product browser task
  `db35d0bf-d100-4a6f-9402-9bc391f93da4` traversed real admission, PostgreSQL,
  Worker, official local Agent Server and canonical Graph, then failed safely at
  built-in Search with `APITimeoutError` attempt `3`. The Product projection persisted
  one correlation ID and zero Evidence/Artifact/interrupts; mobile and Desktop reloads
  showed the same terminal task with readable diagnostics, no raw JSON, no horizontal
  overflow, duplicate IDs, unnamed controls or browser console errors.
- the mobile failure diagnostics changed from a two-column layout that split canonical
  identifiers to a one-column layout below `700px`; live computed dimensions confirm
  every diagnostic value fits on one line. The apparent vertical skip-link in one
  full-page capture was isolated to fixed-element screenshot stitching; viewport
  capture and computed geometry confirmed the actual link remained offscreen.
- the controlled Artifact browser fixture was strengthened to partial typed coverage.
  Desktop and Pixel 7 both assert `1 / 2`, expand the canonical timeout reason, rejoin
  the persisted report, deep-scroll sources and pass unchanged axe/DOM/raw-JSON gates:
  `2 passed (7.3s)`.
- official `ChatOpenAI.bind_tools` inspection confirmed that the locked
  `langchain-openai==1.3.5` accepts a well-known server tool name as `tool_choice` and
  converts it to the Responses API `{"type": ...}` shape. `BuiltinWebSearchProvider`
  now binds each attempt with `tool_choice=search_tool_type` and
  `parallel_tool_calls=False`; preview retry updates the forced type instead of relying
  only on prompt wording. Focused Search/readiness/retry regression is `126 passed`.
- safe real probes prove that this correction cannot make the configured compatibility
  endpoint production-capable. Forced `web_search` returned a successful HTTP/model
  response containing only one plain text block: zero completed Search calls, zero tool
  calls and zero provider citations. Forced `web_search_preview` returned
  `InternalServerError`. The repaired provider's own 30-second probe then recorded
  attempt 1 `UnverifiedServerToolCall` in `13.12s`, followed by preview
  `APITimeoutError` in `7.04s` and `7.52s`; terminal result remained retryable
  `APITimeoutError`, attempt `3`.
- because the Search preflight remained RED, no additional full Deep Agent or browser
  run was launched. Repeating downstream tests cannot manufacture provider citations.
  The local Agent/Worker/frontend stack was restarted on `8123/19091/3001` so the
  inspection URL now runs this exact forced-tool source.

No direct run produced verified evidence, a draft, pause, committed Artifact or
Decision. No browser runner was repeated after the direct provider gate stayed RED.
This is an external Search capability failure, not a production GREEN and not a reason
to substitute DDGS silently. Task 13 remains `partial`; Task 8 remains `RED / PARTIAL`;
V2 remains `PARTIAL`; `Production Ready: NO`.

## 13. Next Entry Point

1. Run one current-source Deep Research Task with an approved real model/Search provider
   and retain Product Task, official Run, citations, screenshots and traces.
2. Extend the real-provider run through required review from Product admission to final
   commit, then retain pending reload and concurrent first-writer evidence.
3. Continue normative Task 13 with Product-owned Monitor/Cron ingress and lifecycle data
   controls, each behind its own RED/GREEN and persisted UI slice.
4. Keep licensed Agent Server, hosted identity/observability and Task 14 release evidence
   as separate production gates; local fixture success must not close them.

No code was staged, committed or pushed.
