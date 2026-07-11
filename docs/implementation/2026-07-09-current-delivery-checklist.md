# Current Delivery Checklist

> Scope: this is the current execution checklist for the manual-only crypto alert workbench. It supersedes older mixed-status checklist sections for day-to-day execution, but does not delete historical checkpoints.

## Product Main Line

The main line remains:

```text
user query / audit note
  -> readable manual alert
  -> safety and readiness proof
  -> notification projection
  -> replay / outcome visibility
```

Do not expand blocked AgentSwarm sidecars, Langfuse, DeepEval, or new formal design docs until the open P0 evidence below is closed.

## Canonical Production Main Path

- `POST /api/runs/manual`
- `build_manual_decision_request()`
- `RunExecutor.submit()`
- `LegacyPlanRunnerAdapter`
- `LegacyDecisionWorkflow`
- `decision.final` with `decision.final_input_mode=legacy_prompt`
- `parser.strict_json`
- `production_control.check`
- `risk.check`
- `persist_run_result()`
- `JournalQueryRepository.get_run_detail()`
- `business_summary`, `result_review`, and notification projection

`production_candidate_swarm`, candidate final, eval, raw payloads, and agent audit panels remain sidecar/audit/eval/diagnostic surfaces. They are not production final input.

## Current Proof Levels

- `fixture`: default local flow only.
- `mock`: local mock LLM or mocked outcome visibility only.
- `staging`: local OKX mock plus no-active-event wiring proof only.
- `local-browser`: Playwright production Next local stack with DOM/visual/runtime checks.
- `hosted-runtime`: deployed API/frontend health and manual-run path only.
- `prod-config`: hosted runtime has explicit production-intent config.
- `prod-actionable`: public HTTPS hosted API, real external LLM, real OKX public data, Bark sent, complete event assertion, allowed manual review, legacy prompt, no candidate sidecar, manual-only safety.
- `real-outcome`: at least one exchange-native matured scorable outcome in OutcomeStore.

Every release note and migration checkpoint must use one of these proof levels. Local/mock/staging/fixture/hosted-runtime success is `not production success`.

Machine-readable proof ladder:

```bash
python3 tools/deployment/proof_ladder.py
```

The script prints `schema_version=2026-07-09.main-flow-proof-ladder` and records the current sequence: `local_no_secret_matrix`, `strict_local_prod_actionable_guard`, `docker_hosted_runtime`, `hosted_prod_config`, `hosted_prod_actionable`, `hosted_prod_actionable_visual`, and `hosted_real_outcome`. `tools/deployment/proof_ladder.py` does not run the gates; it is the contract that prevents fixture/mock/staging/hosted-runtime or negative visual checks from being relabeled as production success.

## Closed Local/Main-Flow Items

- [x] Default product routes are not JSON-first: `/`, `/manual-run`, `/runs`, `/runs/{trace_id}`, `/eval?tab=quality`, and `/config` show product copy first.
- [x] Raw/matrix run-detail views are gated behind `columns=observability`; direct product URLs do not open raw payloads.
- [x] Manual-run success and run detail expose `business_summary`, price levels, risks/gaps, evidence, generation chain, notification, and `result_review`.
- [x] Manual-run success and default run detail expose a product `模型审阅` projection with user focus, model conclusion excerpt, and evidence references, while keeping raw `request_json`/`response_json` hidden from default product pages.
- [x] `business_summary.generation_summary` now exposes safe machine-checkable `provider`, `model`, and `status` fields in addition to product text (`provider_label`, `status_label`, `response_summary`), so API/visual gates can verify real model evidence without reading raw provider payloads.
- [x] `POST /api/runs/manual` fails loudly when persisted `business_summary` or `result_review` projection is missing.
- [x] Staging allowed results remain visible as local/pre-prod proof and say `不是生产成功` unless persisted real external proof is present.
- [x] `/eval?tab=quality` does not load eval run detail diagnostics by default.
- [x] Long-running manual-run and eval submissions show visible progress, disable duplicate submits, and pass DOM/visual checks during pending state.
- [x] Mobile run-detail deep-scroll covers summary, model/evidence summary, review status, result review, and notification history.
- [x] Mobile `/runs` keeps primary record content or empty-state actions in the first viewport.
  - The mobile filter form is now a collapsed `筛选条件` drawer with a compact active-filter summary, while desktop keeps the expanded toolbar.
  - Empty records now provide direct `清空筛选` and `新建提醒` actions.
  - Playwright mobile coverage asserts `.table-wrap` or `.empty-state` appears before the first viewport falls away, then runs DOM/visual scroll-point scanning.
- [x] Run-detail observability diagnostics no longer regress into a JSON-first matrix: `tab=matrix&columns=observability` renders span/LLM/object summaries as readable text, not `<pre>` blocks or object literals; `tab=raw&columns=observability` keeps JSON behind collapsed details by default. Playwright now asserts no `main pre`, no visible object JSON in matrix, and no opened raw JSON details on first render.
- [x] Diagnostic frontend entry points now respect `diagnostic.routes_enabled=false`: direct `/runs?columns=observability`, `/runs/{trace_id}?columns=observability&tab=raw`, `/eval?tab=cases`, and `/eval/runs/{id}` show a product recovery page (`诊断入口已关闭`) instead of rendering engineering matrices, raw payloads, eval forms, or replay details. Playwright verifies this with a real local API/production Next stack launched via `--diagnostic-routes-disabled`.
- [x] Manual-run success can jump to `/runs?latest={trace_id}`; `/runs` shows `刚生成的提醒` and highlights the matching business row with stable `data-latest-run="true"` DOM evidence.
- [x] README and tests README mention ports `8010/3001/8011/8012/8013` and distinguish no-secret matrix from strict production proof.
- [x] `config/prod.yaml` explicitly declares the current MVP production-intent main path: `manual_execution_required=true`, `auto_order_enabled=false`, `decision.final_input_mode=legacy_prompt`, `decision.candidate_sidecar_mode=disabled`, and `workflow.execution_mode=legacy_baseline`.
- [x] `.env.production.example` provides a machine-readable hosted-workbench production-intent template with `CONFIG_PATHS=config/default.yaml:config/prod.yaml:config/staging.yaml`, manual-only safety, diagnostic routes disabled, scheduler disabled, OpenAI-compatible/Bark/no-active-event placeholders, and no trade/withdraw key fields.
- [x] Scheduler operational boundary is explicit: `crypto-alert scheduler` refuses to start with `SCHEDULER_DISABLED` when `scheduler.enabled=false`; the deployment runbook requires `SCHEDULER_ENABLED=true` / `scheduler.enabled=true` before using the `scheduler` compose profile. This keeps default hosted workbench startup manual-only and prevents a profile command from silently bypassing config intent.
- [x] `tools/deployment/smoke_hosted_prod_actionable.py` provides a hosted run-level production proof gate. It submits one manual run and requires public HTTPS API base, `allowed=true`, real `decision.final` OpenAI-compatible `status=ok`, exchange-native fresh execution evidence, Bark `sent`, `legacy_prompt` final input, production main-path readiness, and manual-only safety. Localhost, private IPs, non-HTTPS URLs, and hostnames resolving to private/local/reserved addresses are rejected by default. The gate exists and is tested; it has not passed against a real production-ready hosted environment in this workspace.
  - Main-path strictness: `readiness.prod_actionable.production_main_path_ready=true` and empty `main_path_blockers` are required in addition to `decision.final_input_mode=legacy_prompt`, `decision.candidate_sidecar_mode=disabled`, and `workflow.execution_mode=legacy_baseline`.
  - LLM strictness: non-production model names containing `mock`, `fixture`, `fake`, `stub`, `test`, or `local` cannot satisfy hosted production proof.
  - Bark strictness: success requires the same notification-history row to have `channel=bark`, `status=sent`, `ok=true`, HTTP 2xx `status_code`, and a timezone-aware `created_at`/`sent_at` not earlier than this smoke's manual-run start. Non-Bark channels, failed Bark rows, stale rows, or non-2xx rows cannot satisfy hosted production proof.
  - Positive-proof artifact: `--proof-output hosted-prod-actionable-proof.json` writes a machine-readable API proof manifest with `schema_version=2026-07-09.hosted-prod-actionable-proof.v1`, `trace_id`, `api_base_url`, `config_digest`, `run_detail_digest`, `run_detail_summary`, `prod_actionable_proven=true`, and `does_not_prove=hosted_real_outcome`; it stores summaries/digests only, not raw model payloads or secrets.
- [x] `frontend/tests/e2e/hosted-prod-actionable-visual.spec.ts` provides the hosted prod-actionable visual gate entrypoint. By default it proves the local/fixture Playwright stack cannot be mistaken for hosted production visual proof. When explicitly run with `PLAYWRIGHT_REUSE_EXISTING_STACK=true`, `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true`, `PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend>`, and `PLAYWRIGHT_API_BASE_URL=<public-https-api>`, it submits one hosted manual run, reopens the same `/runs/{trace_id}` detail page, and requires model review, evidence, Bark sent status, no raw JSON/secrets, and DOM/deep-scroll health.
  - Config strictness: the hosted visual gate also requires `readiness.prod_actionable.production_main_path_ready=true` and empty `main_path_blockers` before it can be treated as a hosted-positive visual proof.
  - Strict-proof parity: the hosted visual gate mirrors the run-level API smoke by rejecting `market_data.okx_base_url` values other than empty or `https://www.okx.com`, rejecting `readiness.market_data.status=unsafe`, rejecting non-production model names, and requiring a Bark notification-history row with `channel=bark`, `status=sent`, `ok=true`, HTTP 2xx `status_code`, and a timezone-aware timestamp not earlier than the manual-run start.
  - Positive-proof artifact: when the hosted-positive gate passes, it writes and attaches `hosted-prod-actionable-proof-manifest.json` with `trace_id`, `frontend_base_url`, `api_base_url`, `config_digest`, `run_detail_digest`, `run_detail_summary`, `screenshot_path`, and `does_not_prove=hosted_real_outcome`; the manifest stores only summaries/digests and screenshot paths, not raw model payloads or secrets.
  - Limitation: the gate entrypoint exists and its default negative guard passes locally. The positive hosted prod-actionable visual proof has not passed in this workspace because production readiness is missing.
- [x] `tools/deployment/smoke_hosted_real_outcome_collection.py` provides the hosted real-outcome collection gate. It runs `collect-outcomes` in the hosted collector environment, then requires `tools/deployment/smoke_real_outcome_evidence.py` to see at least one real exchange-native matured scorable outcome through the hosted API.
  - Required operator confirmation: collector and API must share the same-host DATA_DIR/volume; the script requires `--same-host-data-dir-confirmed`.
  - Config preflight: the gate reads `/api/system/config` and requires `api_config_preflight=production_outcome_config_ready`, including `market_data.provider=okx_public`, `market_data.okx_base_url` unset or `https://www.okx.com`, `decision.final_input_mode=legacy_prompt`, `decision.candidate_sidecar_mode=disabled`, `workflow.execution_mode=legacy_baseline`, and safe manual-only trading flags.
  - Contract strictness: collector stdout must be JSON object with integer `collected`; evidence stdout must assert `ok=true`, `smoke_profile=real_outcome_evidence`, `real_exchange_native_matured_outcome_proven=true`, and `prod_actionable_alert_proven=false`.
  - Default strictness: `collection_errors_allowed=false`; collector JSON `errors` fail the gate unless `--allow-collection-errors` is explicitly passed for troubleshooting.
  - Default strictness: `collected=0` fails with `no_new_outcome_collected`; older sidecar samples cannot masquerade as this collection run succeeding.
  - Linkage strictness: the script runs evidence before and after collection; success requires `new_refs_verified=true`, meaning the hosted API exposes a new matched ref collected after gate start or a ref updated after gate start. That matched ref must be one of this run's `collect-outcomes.collected_refs`, keyed by `(decision_ref, evaluation_target, symbol, window_name)`. If pre-collection evidence is unavailable, an old matched ref still cannot masquerade as this collection run succeeding.
  - Symbol/freshness strictness: when `--symbol` is provided, the wrapper passes the same symbol and `--collected-after <gate_started_at>` into both lower-level `tools/deployment/smoke_real_outcome_evidence.py` calls. Matched evidence must be from the same symbol, and `window.collected_at` must be at or after this gate start; old samples, concurrent samples for another symbol, or same-symbol fresh samples outside this run's `collected_refs` cannot satisfy the hosted real-outcome proof.
  - Positive-proof artifact: `--proof-output hosted-real-outcome-proof.json` writes a machine-readable real-outcome manifest with `schema_version=2026-07-09.hosted-real-outcome-proof.v1`, `collect_outcomes_digest`, `real_outcome_evidence_digest`, `outcome_summary`, `new_or_updated_refs`, `new_or_updated_ref_details`, `real_exchange_native_matured_outcome_proven=true`, and `does_not_prove=hosted_prod_actionable`; it stores summaries/digests only, not raw model payloads or secrets.
  - Limitation: this gate proves `real-outcome` only. It is not `prod-actionable`, does not prove Bark sent, and does not prove a fresh LLM decision run.
- [x] Default fixture Docker/hosted-runtime smoke completes after an actual `docker compose up -d --build api frontend` on isolated ports `18010/13001`.
  - Proof level: `hosted-runtime` only.
  - Repeatable gate: `tools/deployment/smoke_docker_hosted_runtime.py` now wraps compose build/up, standard hosted smoke, strict fixture rejection with `--require-prod-config`, and cleanup.
  - Runtime: Docker compose project `crypto-alert-runtime-smoke`, ECR base images `public.ecr.aws/docker/library/python:3.12-slim` and `public.ecr.aws/docker/library/node:22-alpine`.
  - API/frontend containers reached healthy state; `/api/system/health` returned `ok=true` with `mode=SHADOW`; frontend served the production workbench HTML.
  - `tools/deployment/smoke_hosted_workbench.py` exited `0` with `smoke_profile=hosted_workbench`, `hosted_runtime_only_not_prod_actionable=true`, `decision_engine=fixture`, `market_provider=fixture`, `candidate_sidecar_mode=same_engine`, `decision_final_input_mode=legacy_prompt`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - Strict hosted config negative smoke with `--require-prod-config` exited `1` and rejected the default fixture container because production config requires `decision.engine=openai_compatible`.
  - Limitation: this proves the containerized workbench runtime can start and run the manual path; it is not `prod-config`, not `prod-actionable`, and not `real-outcome`.
- [x] Main-flow module ownership is documented in `docs/implementation/2026-07-09-main-flow-module-ownership.md`.
  - It fixes the backend production boundary around `POST /api/runs/manual -> LegacyPlanRunnerAdapter -> LegacyDecisionWorkflow -> legacy_prompt -> parser/gates -> journal/query projections`.
  - It explicitly classifies AgentSwarm, candidate, eval, raw payload, and observability modules as sidecar/audit/eval/diagnostic until P0 external proof is closed.
  - It adds `runtime_role` categories: `production_main`, `production_blocking_audit`, `product_projection`, `diagnostic_projection`, `eval_sidecar`, `replay_only`, and `future_candidate`.
  - It records the important nuance that pre-final shadow/candidate audit can feed `production_control_gate` as block evidence, but cannot enter `FinalDecisionAgent` or replace `legacy_prompt`.
  - Structure test: `tests/structure/test_formal_docs_current_state.py::test_main_flow_module_ownership_map_keeps_backend_boundaries_explicit`.
- [x] Hosted prod-actionable visual gate now requires actual model summary projection, not just generic model-review text.
  - `frontend/tests/e2e/hosted-prod-actionable-visual.spec.ts` reads API `business_summary.generation_summary` for the same hosted trace and requires provider/model/status/response summary to appear in the DOM `模型返回摘要` panel.
  - The positive hosted gate rejects fixture/mock/fallback text such as `本地演练`, `mock`, `fixture`, `未调用外部模型`, or `摘要暂不可用`, and now also rejects the generic placeholder `模型已返回结构化提醒。`.
  - Positive hosted visual proof now requires `PLAYWRIGHT_REUSE_EXISTING_STACK=true` when `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true`; `frontend/playwright.config.ts` enforces this at config-load time before `webServer` can stop ports or start a local fixture stack.
  - Positive hosted visual proof now also requires explicit `PLAYWRIGHT_FRONTEND_BASE_URL` and `PLAYWRIGHT_API_BASE_URL`; in hosted-positive mode the Playwright config disables the local `webServer` block entirely, so a missing hosted URL cannot silently start or stop a local fixture stack.
  - Positive hosted visual proof now requires both frontend and API URLs to be public HTTPS URLs; localhost, private IPs, non-HTTPS URLs, and hostnames resolving through DNS to local/private/reserved addresses are rejected before a browser run can claim hosted visual proof.
  - Default local run still acts as a negative guard and must not be reported as hosted prod-actionable proof.
- [x] Hosted prod-actionable API gate is stricter about real evidence.
  - `tools/deployment/smoke_hosted_prod_actionable.py` no longer trusts `readiness.prod_actionable=ready` alone; it also requires complete `macro_event` no-active-event metadata in the hosted config projection.
  - The gate now independently requires `macro_event.valid_until` to be ISO parseable, timezone-aware, and unexpired; stale operator no-active-event assertions cannot pass even if readiness is misreported as ready.
  - The gate rejects `decision.final` LLM evidence whose model name is non-production-like, including `mock`, `fixture`, `fake`, `stub`, `test`, or `local` tokens, with an explicit non-mock error.
  - The gate now requires strict Bark notification history evidence: `channel=bark`, `status=sent`, `ok=true`, HTTP 2xx `status_code`, and a timezone-aware send timestamp no earlier than the manual run must appear on the same row.
  - The gate now requires DNS-resolved public-host evidence for hosted API URLs; a public-looking hostname that resolves to local/private/reserved addresses cannot satisfy hosted proof.
  - The gate now requires production main-path readiness fields: `production_main_path_ready=true` and empty `main_path_blockers`.
- [x] Local strict `--prod-actionable` success and skip/failure outputs are self-described as non-production proof.
  - Successful localhost rehearsal and missing/unsafe readiness skip payloads now include `proof_level=local-prod-actionable-rehearsal`, `production_success=false`, `hosted_proof_required=true`, and `does_not_prove=hosted_prod_actionable`.
  - This prevents a screenshot/log of local `smoke_profile=prod_actionable` from being pasted as hosted production evidence, even when the script exits `2` with `skip_reason=missing_readiness`.
- [x] Each persisted manual run now carries a durable `main_path_contract` proof boundary.
  - `POST /api/runs/manual` and `/api/runs/{trace_id}` expose the same contract through API projection and frontend schemas.
  - The contract records environment-specific proof levels such as `proof_level=mock` for the local mock-LLM stack and `proof_level=production-intent-contract` only for production-intent config contracts. In both cases it records `production_success=false`, `hosted_proof_required=true`, and `does_not_prove=hosted_prod_actionable`.
  - The contract records `runtime_role=production_main`, `final_input_contract.mode=legacy_prompt`, `manual_only.manual_execution_required=true`, and `manual_only.auto_order_enabled=false`.
  - This is a run-level audit contract. It prevents local/mock evidence from being relabeled as hosted proof; it does not close the hosted `prod-actionable` P0.
- [x] Model summary projection now gives users a concrete model excerpt when safe.
  - `storage/business_summary.py` uses safe `llm_summary.output_summary` text when available.
  - If the LLM output summary is raw provider-shaped data such as `choices`, the product projection hides it and falls back to a productized parsed-plan excerpt such as `模型结论：触发做多；置信度 58%。`.
  - It filters raw/secret markers and avoids exposing raw JSON, provider payload keys, or engineering-only English conditions in product pages.
- [x] Manual-run success and run-detail summary now expose a visible `提醒证据级别` status strip.
  - The strip shows proof level such as `本地流程验证`, `模型链路演练`, `本地预发人工复核`, or `生产可复核证据已记录`.
  - It also shows model status, notification status, and `人工核对后手动执行`, so users do not need raw JSON or diagnostic views to understand whether a run is local/mock/staging/production-evidence.
  - Desktop and mobile visual baselines for `run-detail-summary-fullpage` were intentionally updated.
- [x] Product error states no longer claim a failed request was saved.
  - Manual-run POST failure, `/runs` load failure, and `/runs/{trace_id}` load failure now say the write state cannot be confirmed and ask the operator to verify in reminder records or retry.
  - Mixed-version/partial projection fallback no longer says `本次记录已保存`; it says the core alert plan and detail entry were returned.
  - Playwright covers manual-run HTTP 500, partial projection, and server-component `/runs` plus `/runs/{trace_id}` failures, and asserts no visible `本次记录已保存` / `本次访问记录已保存` copy.
- [x] Eval diagnostic submit errors now use an accessible alert state.
  - `RunEvalForm` renders failed submit messages as `.error-inline[role="alert"]`.
  - Playwright eval error-state cases require the alert role and still assert backend internals and secrets stay hidden.
- [x] Product fallback copy no longer sends default users to engineering diagnostics.
  - Unknown internal tokens and unsafe product-visible text now say the content is recorded but the current summary is unreadable; operators should rely on alert summary, price levels, risk, and notification status.
  - Diagnostic routes still identify themselves as engineering diagnostics when explicitly opened.

## Open P0

- [ ] Real external `prod-actionable` smoke succeeds with:
  - public HTTPS OpenAI-compatible endpoint/model/key;
  - real OKX public market data;
  - Bark notification row `sent`;
  - `MACRO_EVENT_PROVIDER=no_active_event`;
  - complete unexpired operator assertion metadata;
  - `allowed=true`;
  - `decision.final_input_mode=legacy_prompt`;
  - `decision.candidate_sidecar_mode=disabled`;
  - `workflow.execution_mode=legacy_baseline`;
  - `readiness.prod_actionable.production_main_path_ready=true`;
  - empty `readiness.prod_actionable.main_path_blockers`;
  - `manual_execution_required=true`;
  - `auto_order_enabled=false`.
  - Required hosted gate: `tools/deployment/smoke_hosted_prod_actionable.py --proof-output hosted-prod-actionable-proof.json` must pass against a public HTTPS hosted API for the same production-ready environment, and the proof manifest must be retained as release evidence.
- [ ] Hosted prod-actionable visual gate succeeds against the same production-ready environment:
  - `PLAYWRIGHT_REUSE_EXISTING_STACK=true`;
  - `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true`;
  - `PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend>`;
  - `PLAYWRIGHT_API_BASE_URL=<public-https-api>`;
  - required desktop command: `npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts`;
  - required mobile command: `npm --prefix frontend run e2e -- --project=chromium-mobile hosted-prod-actionable-visual.spec.ts`;
  - desktop and mobile must each submit a fresh manual run, verify the same trace through API detail, open `/runs/{trace_id}`, and prove concrete model review/evidence/Bark status render without generic model placeholders, raw JSON, secrets, DOM overlap, responsive layout defects, or deep-scroll layout defects.
  - it must preflight `readiness.prod_actionable.production_main_path_ready=true` and empty `main_path_blockers`.
  - frontend/API base URLs must be public HTTPS and must DNS-resolve only to public addresses; public-looking hostnames that resolve to local/private/reserved addresses cannot satisfy hosted visual proof.
  - it must retain the Playwright-attached `hosted-prod-actionable-proof-manifest.json` and screenshot artifact as release evidence; this manifest does not close the separate `hosted_real_outcome` P0.
- [ ] At least one real `exchange_native + matured + can_score` outcome is collected in the hosted environment and passes `tools/deployment/smoke_hosted_real_outcome_collection.py --same-host-data-dir-confirmed`.
  - Collector and hosted API must read/write the same-host DATA_DIR/volume.
  - Default gate output must include `api_config_preflight=production_outcome_config_ready`.
  - Default gate output must keep `collection_errors_allowed=false`.
  - Default gate output must include `new_refs_verified=true`.
  - Default gate output must prove 同一 symbol only and exact ref linkage; lower-level evidence uses `--symbol` and `--collected-after <gate_started_at>`, so matched `window.collected_at` must be new for this collection gate, and post evidence must hit a `(decision_ref, evaluation_target, symbol, window_name)` tuple emitted by this run's `collect-outcomes.collected_refs`.
  - Release evidence must retain `hosted-real-outcome-proof.json` with `collect_outcomes_digest`, `real_outcome_evidence_digest`, `outcome_summary`, `new_or_updated_ref_details`, and `does_not_prove=hosted_prod_actionable`.
  - The lower-level evidence check remains `tools/deployment/smoke_real_outcome_evidence.py`.
- [ ] Production-intent hosted runtime with a filled `.env.production.example` profile passes `smoke_hosted_workbench.py --require-prod-config` and `tools/deployment/smoke_hosted_prod_actionable.py`. The default fixture hosted-runtime smoke above and local `--prod-actionable --fail-on-skip` rehearsal do not satisfy this item.

## Open P1

- [ ] Decide whether `query_text` remains `audit_note` or receives a separate design to drive intent, facts, and final input.
- [ ] Operationalize `collect-outcomes`: runbook, schedule, matured-window handling, failure handling, and proof artifact storage.
- [ ] Continue productizing diagnostic-only pages where useful, while keeping them explicitly labeled as engineering diagnostics.
- [ ] Continue productizing or access-gating diagnostic-only routes for role-based/shared hosted use. Config-disabled environments now have a frontend recovery gate for shared `columns=observability` links, `/eval?tab=cases`, and `/eval/runs/{id}`; remaining work is explicit operator/role access policy for environments that intentionally keep `DIAGNOSTIC_ROUTES_ENABLED=true`.
- [ ] Keep Playwright evidence archived after no-secret matrix runs: stdout, HTML report, screenshots, trace/video on failure, and `.last-run.json`.

## Required Verification Before Any Completion Claim

No-secret local verification:

```bash
python3 tools/local_stack/run_local_checks.py
```

Focused browser checks for the current UX slice:

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run e2e -- --project=chromium-desktop async-and-mobile-depth.spec.ts
```

Strict production gate:

```bash
python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip
```

If strict production readiness is missing, exit code `2` is an honest block and must not be reported as production success.

Hosted prod-actionable visual gate, only after a production-ready hosted API/frontend is already running:

```bash
PLAYWRIGHT_REUSE_EXISTING_STACK=true \
PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true \
PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend> \
PLAYWRIGHT_API_BASE_URL=<public-https-api> \
npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts
```

Without `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true`, this spec only proves the current stack is not being mislabeled as hosted prod-actionable visual proof.

## Latest Authoritative Verification Snapshot

This section is the current status anchor for execution and review. Historical records below are retained as chronology and should not be read as the latest verification count when they show older totals.

- Latest no-secret local matrix:
  - `python3 tools/local_stack/run_local_checks.py`
  - Python pytest `1113 passed, 2 warnings`.
  - frontend typecheck passed.
  - frontend production build passed.
  - Playwright `48 passed, 10 skipped`.
  - fixture, mock LLM, actionable staging, seeded mock-outcome, and collect-outcomes fixture smokes passed.
  - Proof level: local-browser + fixture/mock/staging/collector wiring only; this is not production success.
- Strict production readiness gate:
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`
  - `prod-actionable` still exits `2` with `missing_readiness`.
  - Missing readiness remains `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`.
  - The exit `2` payload is the correct honest block and does not prove hosted prod-actionable.
- Hosted OKX public proof hardening:
  - `smoke_hosted_workbench.py --require-prod-config` and `smoke_hosted_prod_actionable.py` now reject `market_data.okx_base_url` values other than empty or `https://www.okx.com`.
  - Both hosted gates also reject `readiness.market_data.status=unsafe`.
  - This prevents exchange-shaped mock/local OKX endpoints from being accepted as real OKX public proof.
- Per-run main-path contract:
  - `main_path_contract` is now persisted and projected for manual run immediate responses and run detail.
  - Current main-flow contract fields include `proof_level=mock` for the local mock-LLM stack, `proof_level=production-intent-contract` for production-intent config contracts, `production_success=false`, `hosted_proof_required=true`, `does_not_prove=hosted_prod_actionable`, `runtime_role=production_main`, `final_input_contract.mode=legacy_prompt`, `manual_only.manual_execution_required=true`, and `manual_only.auto_order_enabled=false`.
  - Frontend schemas preserve this contract instead of filtering it out.
- Hosted runtime proof:
  - `python3 tools/deployment/smoke_docker_hosted_runtime.py`
  - Latest result: exit `0`, proof level `hosted-runtime`, default runtime still fixture, strict prod-config negative correctly rejects fixture config.
  - This is not `prod-config`, not hosted prod-actionable, and not `real-outcome`.
- Current live local stack check:
  - Local frontend/API/mock-LLM are reachable on `127.0.0.1:3001`, `127.0.0.1:8010`, and `127.0.0.1:8011`.
  - `POST /api/runs/manual` produced a persisted readable `business_summary` with `generation_summary.provider=openai_compatible`, `model=mock-crypto-plan`, and `status=ok`.
  - Focused Playwright checks for desktop manual-run flow, mobile run-detail deep scroll, and `/runs?latest={trace_id}` highlighting passed against the current local stack.
  - Screenshots saved under `frontend/test-results/current-run-detail-ready.png` and `frontend/test-results/current-runs-highlight-ready.png` prove the default product pages render readable alert content, not raw JSON.
- Remaining production P0:
  - Start production-intent hosted API/frontend from filled `.env.production.example`.
  - Pass hosted prod-config smoke.
  - Pass hosted prod-actionable smoke.
  - Pass hosted prod-actionable visual proof against the same hosted trace.
  - Pass hosted real-outcome collection after horizon maturity.

## Fresh Verification Record

2026-07-09 user-requested main-flow rerun:

- [x] Three read-only subagents audited architecture, UI/UX, and QA boundaries. Shared conclusion: the default code path has been pulled back to the manual-only workbench, but real production delivery still requires hosted `prod-actionable`, hosted visual proof, and real matured outcome evidence.
- [x] `python3 -m pytest tests/cli/test_runner_cli.py::test_cli_scheduler_refuses_when_config_disabled -q`
  - Red result before implementation: failed with `assert 0 == 2`, proving `crypto-alert scheduler` ignored `scheduler.enabled=false`.
- [x] `python3 -m pytest tests/deployment/test_container_config_commands.py::test_deployment_docs_describe_hosted_workbench_services -q`
  - Red result before documentation update: failed because deployment docs did not mention `SCHEDULER_DISABLED`.
- [x] `python3 -m pytest tests/cli/test_runner_cli.py::test_cli_scheduler_refuses_when_config_disabled tests/cli/test_runner_cli.py::test_cli_scheduler_uses_workflow_executor tests/deployment/test_container_config_commands.py -q`
  - Result: `22 passed`.
  - Proof level: CLI/deployment contract.
- [x] `npm --prefix frontend run typecheck`
  - Result: passed.
- [x] `python3 tools/local_stack/run_local_checks.py`
  - Python full pytest: `1092 passed, 2 warnings`.
  - frontend typecheck: passed.
  - frontend production build: passed.
  - Playwright production local stack: `48 passed, 10 skipped`.
  - fixture smoke: passed with `decision_engine=fixture`, `market_provider=fixture`, `allowed=false`.
  - mock LLM smoke: passed with `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `allowed=false`.
  - actionable staging smoke: passed with local mock OKX and `allowed=true`.
  - seeded mock-outcome smoke: passed with `visibility_only_not_financial_quality`.
  - collect-outcomes fixture smoke: passed with `local_mock_okx_collector_wiring_only` and `real_financial_quality_proven=false`.
  - Proof level: local-browser + fixture/mock/staging only. This is not production success.
- [x] `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`
  - Result: exit `2`, `skip_reason=missing_readiness`.
  - Missing: `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, `MACRO_EVENT_PROVIDER=no_active_event`.
  - Safety fields remained true: `manual_execution_required=true`, `auto_order_enabled=false`.
  - This is an honest production readiness block, not production success.
- [x] `python3 tools/deployment/smoke_docker_hosted_runtime.py`
  - Result: exit `0`, `ok=true`, `stage=complete`, `proof_level=hosted-runtime`.
  - Hosted smoke used `decision_engine=fixture`, `market_provider=fixture`, `candidate_sidecar_mode=same_engine`, `hosted_runtime_only_not_prod_actionable=true`.
  - Strict prod-config negative check rejected fixture runtime with `production config requires decision.engine=openai_compatible`.
  - Cleanup check after the script: no listeners on `8010/3001/8011/8012/8013/18010/13001` and no `crypto-alert-runtime-smoke` containers.
- [x] `python3 -m pytest tests/deployment/test_container_config_commands.py::test_hosted_prod_actionable_visual_gate_requires_reusing_existing_hosted_stack -q`
  - Red before implementation: failed because hosted-positive visual mode did not require explicit hosted frontend/API URLs and still carried a local `webServer` startup block.
  - Green after implementation: `1 passed`.
  - Proof level: deployment/visual-gate contract only.
- [x] `npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "manual run API 500"`
  - Red before implementation: failed because the error alert said `本次记录已保存`.
  - Green after implementation: `1 passed`.
  - Meaning: manual-run API failures no longer claim a failed request was saved and still hide backend internals.
- [x] `PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "runs list and detail failures"`
  - Result: `1 passed`.
  - Meaning: `/runs` and `/runs/{trace_id}` load failures no longer claim a record or visit was saved, and unsafe backend text stays hidden.
- [x] `npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "manual run partial success"`
  - Result: `1 passed`.
  - Meaning: partial projection fallback remains readable and no longer uses unproven saved-state wording.
- [x] `python3 -m pytest tests/local_stack/test_scripts.py::test_mock_error_api_server_enables_diagnostic_routes_for_diagnostic_error_tests tests/local_stack/test_scripts.py::test_mock_error_api_server_returns_partial_run_detail_projection_fixture -q`
  - Red before implementation: the mock error API had no reusable system config fixture and returned config without `diagnostic.routes_enabled=true`, causing diagnostic error tests to hit the product diagnostic-disabled page instead of diagnostic GET failure paths.
  - Green after implementation: `2 passed`.
  - Meaning: the mock error API now explicitly opens diagnostic routes only for this forced-error test profile.
- [x] `PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "Server Component"`
  - Red before mock error API fix: eval diagnostic GET-failure test rendered `诊断入口已关闭` because the mock config did not enable diagnostic routes.
  - Green after implementation: `3 passed`.
  - Meaning: eval diagnostic, `/runs`, and `/runs/{trace_id}` Server Component failure paths sanitize unsafe text and avoid unproven saved-state claims.
- [x] `npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "eval run API 500"`
  - Red before implementation: failed because eval submit errors rendered `.error-inline` without `role="alert"`.
  - Green after implementation: `1 passed`.
  - Meaning: eval diagnostic submit failures are accessible alert states and still hide backend internals.
- [x] `npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts`
  - Result after eval alert-role implementation: `6 passed, 3 skipped`.
  - The skipped cases require the special internal-error API profile and were verified separately.
- [x] `PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "Server Component"`
  - Result after eval alert-role implementation: `3 passed`.
  - Note: an earlier attempt was invalid because two Playwright commands were run in parallel and raced on `.next`; the sequential rerun passed.
- [x] `python3 tools/local_stack/run_local_checks.py`
  - Python full pytest: `1082 passed, 2 warnings`.
  - frontend typecheck: passed.
  - frontend production build: passed.
  - Playwright production local stack: `48 passed, 6 skipped`.
  - fixture smoke, mock LLM smoke, actionable staging smoke, seeded mock-outcome smoke, and collect-outcomes fixture smoke all passed.
  - Proof level: local-browser + fixture/mock/staging only. This is not production success.
- [x] `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`
  - Result: exit `2`, `skip_reason=missing_readiness`.
  - Missing: `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, `MACRO_EVENT_PROVIDER=no_active_event`.
  - Safety fields remained true: `manual_execution_required=true`, `auto_order_enabled=false`.
  - This is an honest production gate block, not production success.
- [x] `python3 tools/deployment/smoke_docker_hosted_runtime.py`
  - Result: exit `0`, `ok=true`, `stage=complete`, `proof_level=hosted-runtime`.
  - Hosted smoke used `decision_engine=fixture`, `market_provider=fixture`, and `hosted_runtime_only_not_prod_actionable=true`.
  - Strict prod-config negative check correctly rejected the default fixture runtime with `production config requires decision.engine=openai_compatible`.
  - Cleanup check after the script: no listeners on `8010/3001/8011/8012/8013/18010/13001` and no `crypto-alert-runtime-smoke` containers.
- [x] `docs/implementation/2026-07-09-main-flow-production-recovery-checklist.md`
  - Added as the current execution plan and checklist for main-flow recovery.
  - It records P0 gates, P1 work, proof levels, and the rule that fixture/mock/staging/hosted-runtime success is not production success.
- [x] `PLAYWRIGHT_EXPECT_DIAGNOSTIC_DISABLED=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --diagnostic-routes-disabled" npm --prefix frontend run e2e -- --project=chromium-desktop diagnostic-access-gate.spec.ts`
  - Red result before implementation: failed because `/runs?columns=observability` still rendered the engineering diagnostic view while diagnostic routes were disabled.
  - Green result after implementation: `1 passed`.
  - Proof level: local-browser + config-disabled diagnostic gate.
- [x] `npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"`
  - Result: `1 passed`.
  - Meaning: the default diagnostic-enabled local E2E path still renders the intentional engineering views; the new gate only affects environments with `diagnostic.routes_enabled=false`.
- [x] `python3 -m pytest tests/structure/test_formal_docs_current_state.py::test_main_flow_module_ownership_map_keeps_backend_boundaries_explicit -q`
  - Red result before documentation: failed with `FileNotFoundError` for `docs/implementation/2026-07-09-main-flow-module-ownership.md`.
  - Additional red/green refinements required `runtime_role` and `production_blocking_audit` wording before passing.
  - Green result after documentation: `1 passed`.
  - Meaning: backend main-path ownership and sidecar/eval/diagnostic boundaries are now enforced by a structure test.
- [x] `npm --prefix frontend run typecheck`
  - Result: passed after hosted visual gate strengthening.
- [x] `npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts -g "default stack"`
  - Result: `1 passed`.
  - Meaning: the strengthened hosted visual gate still refuses to treat the default local/fixture stack as production visual proof.
- [x] `python3 tools/local_stack/run_local_checks.py`
  - First result after this round of edits: failed in `tests/api/test_system_routes.py` because three readiness tests used fixed `MACRO_EVENT_VALID_UNTIL=2026-07-09T15:30:00+08:00`, which is now expired.
  - Fix: test fixtures now generate `MACRO_EVENT_CONFIRMED_AT` and `MACRO_EVENT_VALID_UNTIL` from the current UTC time, preserving the production rule that no-active-event assertions must be unexpired.
  - Focused green: `python3 -m pytest tests/api/test_system_routes.py::test_config_readiness_reports_prod_actionable_ready_when_event_and_external_env_are_ready tests/api/test_system_routes.py::test_config_readiness_requires_candidate_sidecar_disabled_for_prod_actionable tests/api/test_system_routes.py::test_config_readiness_rejects_local_endpoints_for_prod_actionable -q` -> `3 passed`.
  - Full rerun: Python full pytest `1084 passed, 2 warnings`; frontend typecheck passed; frontend production build passed; Playwright `48 passed, 8 skipped`; fixture, mock LLM, actionable staging, seeded mock-outcome, and collect-outcomes fixture smokes passed.
  - Proof level: local-browser + fixture/mock/staging only. This is not production success.
- [x] `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`
  - Result: exit `2`, `skip_reason=missing_readiness`.
  - Missing: `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, `MACRO_EVENT_PROVIDER=no_active_event`.
  - Safety fields remained true: `manual_execution_required=true`, `auto_order_enabled=false`.
  - Meaning: strict production readiness is honestly blocked in this workspace.
- [x] `python3 tools/deployment/smoke_docker_hosted_runtime.py`
  - Result: exit `0`, `ok=true`, `stage=complete`, `proof_level=hosted-runtime`.
  - Hosted runtime smoke used `decision_engine=fixture`, `market_provider=fixture`, `candidate_sidecar_mode=same_engine`, and `hosted_runtime_only_not_prod_actionable=true`.
  - Strict prod-config negative check rejected the default fixture runtime with `production config requires decision.engine=openai_compatible`.
  - Cleanup check after the script: no listeners on `8010/3001/8011/8012/8013/18010/13001` and no `crypto-alert-runtime-smoke` containers.
- [x] `npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"`
  - Red result before implementation: failed because `aria-label="提醒证据级别"` was missing on the manual-run success page.
  - Green result after implementation and intentional desktop screenshot update: `1 passed`.
- [x] `npm --prefix frontend run e2e -- --project=chromium-mobile full-stack-visual.spec.ts -g "manual run async flow"`
  - Green result after intentional mobile screenshot update: `1 passed`.
- [x] `npm --prefix frontend run typecheck`
  - Result: passed after adding the shared proof-level strip.
- [x] `python3 -m pytest tests/deployment/test_hosted_prod_actionable_smoke.py -q`
  - Red before implementation: new tests showed the hosted prod-actionable smoke could trust `readiness.prod_actionable=ready` while `macro_event` metadata was missing, and mock-model rejection did not produce a specific non-mock error.
  - Initial green before unexpired event-assertion hardening: superseded by the latest `8 passed` contract entry below.
  - The latest contract also proves localhost/private/non-HTTPS `--api-base` is rejected by default and rejects expired or timezone-less `macro_event.valid_until`; fake-server tests must opt in with `allow_local_api_base=True`.
  - Proof level: fake-server deployment contract only; this is not hosted production success.
- [x] `python3 -m pytest tests/deployment/test_container_config_commands.py::test_deployment_docs_reference_machine_readable_proof_ladder tests/deployment/test_container_config_commands.py::test_hosted_prod_actionable_visual_gate_requires_reusing_existing_hosted_stack tests/deployment/test_proof_ladder.py -q`
  - Red before documentation/spec updates: docs did not reference `tools/deployment/proof_ladder.py`, and hosted visual enforcement could happen after Playwright webServer startup.
  - Green after updates: passed.
  - Proof level: structure/deployment contract.
- [x] `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts -g "default stack"`
  - Result: exit `1` at Playwright config load with `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_REUSE_EXISTING_STACK=true`.
  - Meaning: missing reuse mode fails before Playwright can stop local ports or start a fixture stack.
- [x] `python3 -m pytest tests/storage/test_business_summary.py tests/api/test_runs_routes.py::test_run_detail_business_summary_uses_persisted_mock_llm_interaction -q`
  - Red before implementation: model summary still rendered `模型已返回结构化提醒。` and then exposed internal enum/English plan wording when first improved.
  - Green after implementation: `15 passed`.
  - Meaning: product projection now prefers safe model excerpts and productized parsed-plan fallbacks without raw provider payloads.
- [x] `PLAYWRIGHT_EXPECT_MOCK_LLM=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm --seed-mock-outcome" npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"`
  - Result: `1 passed`.
  - Meaning: a real browser local mock-LLM flow renders `模型结论` in `模型返回摘要` and does not fall back to the generic placeholder. This is local/mock proof only, not production success.

2026-07-09:

- [x] `python3 tools/local_stack/run_local_checks.py`
  - Python full pytest: `1054 passed, 2 warnings`.
  - frontend typecheck: passed.
  - frontend production build: passed.
  - Playwright production local stack: `46 passed, 4 skipped`.
  - fixture smoke: passed.
  - mock LLM smoke: passed.
  - actionable staging smoke: passed with local mock OKX and `allowed=true`.
  - seeded mock-outcome smoke: passed with `visibility_only_not_financial_quality`.
  - collect-outcomes fixture smoke: passed with `local_mock_okx_collector_wiring_only` and `real_financial_quality_proven=false`.
- [x] `PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "Server Component"`
  - Result: `2 passed`.
- [x] `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`
  - Result: exit `2`, `skip_reason=missing_readiness`.
  - Missing: `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, `MACRO_EVENT_PROVIDER=no_active_event`.
  - Safety fields remained true: `manual_execution_required=true`, `auto_order_enabled=false`.
  - This is an honest production gate block, not production success.
- [x] `python3 -m pytest tests/config/test_config.py::test_prod_config_declares_manual_only_legacy_main_path_explicitly -q`
  - Result: `1 passed`.
  - Proof level: `prod-config`.
  - Meaning: the production overlay itself, not only merged defaults, declares the current manual-only legacy main path.
- [x] `python3 -m pytest tests/config/test_config.py tests/deployment/test_hosted_workbench_smoke.py tests/deployment/test_container_config_commands.py -q`
  - Result: `61 passed`.
  - Proof level: `prod-config`.
  - Limitation: this validates configuration/deployment command boundaries only; it is not `prod-actionable` and not `real-outcome`.
- [x] `PLAYWRIGHT_EXPECT_MOCK_LLM=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm" npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"`
  - Red result before implementation: failed because `aria-label="模型审阅"` was missing from the manual-run success panel.
  - Green result after implementation: `1 passed`.
  - Proof level: `mock` + `local-browser`.
  - Limitation: this proves product rendering of the model-review projection through the local mock LLM path, not a real external model success.
- [x] `npm --prefix frontend run typecheck`
  - Result: passed.
- [x] `npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"`
  - Result: `1 passed`.
  - Proof level: `fixture` + `local-browser`.
- [x] `python3 -m pytest tests/deployment/test_container_config_commands.py::test_prod_env_template_declares_hosted_workbench_production_intent tests/deployment/test_container_config_commands.py::test_deployment_docs_reference_prod_env_template_and_strict_smokes -q`
  - Red result before implementation: failed because `.env.production.example` was missing and README/deployment docs did not reference it.
  - Green result after implementation: `2 passed`.
  - Proof level: `prod-config` runbook/template.
  - Limitation: this proves production-intent startup is machine-readable and documented; it is not a Docker runtime smoke and not `prod-actionable`.
- [x] `python3 -m pytest tests/deployment -q`
  - Result: `29 passed`.
  - Proof level: deployment config/smoke-script tests.
- [x] `API_PORT=18010 FRONTEND_PORT=13001 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:18010 PYTHON_BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim NODE_BASE_IMAGE=public.ecr.aws/docker/library/node:22-alpine docker compose -p crypto-alert-runtime-smoke up -d --build api frontend`
  - Result: API and frontend images built; both containers started and became healthy.
  - Proof level: `hosted-runtime`.
  - Limitation: default compose config is fixture-oriented and is not production config.
- [x] `curl -fsS http://127.0.0.1:18010/api/system/health`
  - Result: `ok=true`, `service=crypto-manual-alert`, `storage=sqlite`, `mode=SHADOW`.
- [x] `curl -fsS http://127.0.0.1:13001`
  - Result: production frontend HTML was served and contained the manual alert workbench copy.
- [x] `python3 tools/deployment/smoke_hosted_workbench.py --api-base http://127.0.0.1:18010 --frontend-base http://127.0.0.1:13001 --symbol ETH-USDT-SWAP --query "Docker hosted runtime smoke：验证容器工作台人工提醒入口" --horizon 6h`
  - Result: exit `0`, `ok=true`, `smoke_profile=hosted_workbench`, `hosted_runtime_only_not_prod_actionable=true`, `decision_engine=fixture`, `market_provider=fixture`, `production_config_required=false`, `prod_actionable_ready=false`, `manual_execution_required=true`, `auto_order_enabled=false`.
  - Proof level: `hosted-runtime`.
- [x] `python3 tools/deployment/smoke_hosted_workbench.py --api-base http://127.0.0.1:18010 --frontend-base http://127.0.0.1:13001 --symbol ETH-USDT-SWAP --query "Docker hosted runtime strict config negative smoke" --horizon 6h --require-prod-config`
  - Result: exit `1`, `ok=false`, `production_config_required=true`, error `production config requires decision.engine=openai_compatible`.
  - Meaning: the default fixture hosted runtime is correctly blocked from being labeled `prod-config`.
- [x] `API_PORT=18010 FRONTEND_PORT=13001 docker compose -p crypto-alert-runtime-smoke down --remove-orphans`
  - Result: API/frontend containers and compose network removed; no leftover listeners on ports `18010/13001`.
- [x] `python3 -m pytest tests/deployment/test_docker_hosted_runtime_smoke.py -q`
  - Red result before implementation: failed because `tools/deployment/smoke_docker_hosted_runtime.py` did not exist.
  - Red result after first real run: actual Docker runtime exposed a transient frontend `ConnectionResetError`, proving the gate needed hosted-smoke retry after compose startup.
  - Green result after implementation: `3 passed`.
  - Meaning: Docker hosted-runtime proof is now represented by a repeatable gate script that runs compose build/up, hosted smoke, strict fixture rejection, and cleanup; the test uses a subprocess fake and does not start Docker.
- [x] `python3 tools/deployment/smoke_docker_hosted_runtime.py`
  - Result: exit `0`.
  - Proof level: `hosted-runtime`.
  - Output included `ok=true`, `stage=complete`, `proof_level=hosted-runtime`, `hosted_runtime_only_not_prod_actionable=true`.
  - Hosted smoke output included `smoke_profile=hosted_workbench`, `decision_engine=fixture`, `market_provider=fixture`, `decision_final_input_mode=legacy_prompt`, `candidate_sidecar_mode=same_engine`, `manual_execution_required=true`, `auto_order_enabled=false`, `production_config_required=false`, `prod_actionable_ready=false`.
  - Strict prod-config check output was `expected_negative_rejected_fixture`; `--require-prod-config` returned `ok=false` with `production config requires decision.engine=openai_compatible`.
  - Cleanup check after the script: no `crypto-alert-runtime-smoke` containers and no listeners on ports `18010/13001`.
- [x] `python3 -m pytest tests/deployment/test_hosted_prod_actionable_smoke.py -q`
  - Red result before implementation: failed because `tools/deployment/smoke_hosted_prod_actionable.py` did not exist.
  - Latest green result after public HTTPS/DNS, unexpired event-assertion, production main-path readiness, non-production model denylist, and strict Bark evidence hardening: `15 passed`.
  - Meaning: the hosted run-level `prod-actionable` proof gate is now automated. It validates config readiness plus run-level `allowed=true`, real LLM interaction, exchange-native fresh execution evidence, strict Bark notification row with 2xx/fresh timestamp, `legacy_prompt`, production main-path readiness, manual-only safety, rejects localhost/private/non-HTTPS/private-DNS `--api-base` by default, and rejects expired or timezone-less `macro_event.valid_until`.
  - Limitation: this is a fake-server contract test. The real hosted production-ready environment has not passed this gate yet.
- [x] `python3 -m pytest tests/deployment/test_hosted_real_outcome_collection_smoke.py -q`
  - Red result before implementation: failed because the HTTP `/api/system/config` preflight failure path did not return `api_config_preflight=failed`.
  - Green result after config preflight and old-outcome linkage hardening: `16 passed`.
  - Meaning: the hosted real-outcome collection wrapper now has contract coverage for both injected config and real HTTP API config preflight. Fixture/HTTP 404 config responses stop before the collector command and are machine-readable as config preflight failures. If pre-collection evidence is unavailable, an old outcome with `collected_at` before gate start cannot be counted as a new collection result.
  - Limitation: this is a fake-server/fake-runner contract test. It does not collect a real hosted outcome.
- [x] `python3 -m pytest tests/deployment tests/structure/test_formal_docs_current_state.py -q`
  - Result: `67 passed`.
  - Proof level: deployment/structure contract tests only.
- [x] `npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts`
  - Result: `1 passed, 1 skipped`.
  - Proof level: local-browser negative guard.
  - Meaning: the default local/fixture Playwright stack cannot be mislabeled as hosted prod-actionable visual proof. The positive test is intentionally skipped unless `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true` is set against a production-ready hosted stack.
  - Limitation: this is not production visual proof; the positive hosted visual gate has not passed in this workspace.
- [x] `npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"`
  - Red result before implementation: failed because `/runs/{trace_id}?tab=matrix&columns=observability` rendered 25 `<pre>` elements and object literals such as candidate gate errors.
  - Green result after implementation: `1 passed`.
  - Meaning: the run-detail matrix diagnostic page now uses readable summaries for span/LLM/object fields, while raw JSON remains in the explicit Raw tab and is collapsed by default.
- [x] `npm --prefix frontend run typecheck`
  - Result: passed.
- [x] `npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts`
  - Red result before implementation: six product-copy assertions still rendered `工程详情` / `工程诊断` fallback text in product-visible sanitization paths.
  - Green result after implementation: `11 passed`.
  - Proof level: local browser/product-copy contract.
- [x] `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true PLAYWRIGHT_REUSE_EXISTING_STACK=true PLAYWRIGHT_FRONTEND_BASE_URL=http://127.0.0.1:3001 PLAYWRIGHT_API_BASE_URL=https://api.example.com npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts -g "default stack"`
  - Result: exit `1` at Playwright config load with `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_FRONTEND_BASE_URL to be a public HTTPS URL`.
  - Meaning: hosted-positive visual proof now rejects localhost before it can start or reuse any browser stack.
- [x] `python3 -m pytest tests/deployment/test_container_config_commands.py::test_hosted_prod_actionable_visual_gate_requires_reusing_existing_hosted_stack tests/deployment/test_proof_ladder.py -q`
  - Red result before implementation: hosted visual gate and proof ladder did not require public HTTPS frontend/API base URLs.
  - Green result after implementation: `2 passed`.
  - Proof level: deployment/visual-gate contract only.
- [x] `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_success_boundary_is_not_production_success tests/local_stack/test_scripts.py::test_local_smoke_profile_names_prod_actionable tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_reports_missing_readiness tests/local_stack/test_scripts.py::test_local_smoke_api_env_enables_prod_actionable_when_ready -q`
  - Red result before implementation: `_local_proof_boundary` did not exist.
  - Green result after implementation: `4 passed`.
  - Meaning: localhost `--prod-actionable` success output is explicitly labeled as local rehearsal, with `production_success=false` and `does_not_prove=hosted_prod_actionable`.
- [x] `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_requires_event_assertion_metadata tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_rejects_local_mock_endpoints tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_rejects_mock_model_name tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_default_skip_returns_zero tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_fail_on_skip_returns_nonzero -q`
  - Red result before implementation: missing/unsafe readiness skip output lacked the local rehearsal proof boundary fields.
  - Green result after implementation: `5 passed`.
  - Meaning: local strict `--prod-actionable` skip/failure artifacts now also carry `local-prod-actionable-rehearsal`, `production_success=false`, `hosted_proof_required=true`, and `does_not_prove=hosted_prod_actionable`.
- [x] `python3 tools/local_stack/run_local_checks.py`
  - Result: Python pytest `1113 passed, 2 warnings`; frontend typecheck passed; frontend production build passed; Playwright `48 passed, 10 skipped`; fixture, mock LLM, actionable staging, seeded mock-outcome, and collect-outcomes fixture smokes passed.
  - Proof level: local-browser + fixture/mock/staging/collector wiring only. This remains not production success.
  - Regression caught and fixed during this run: `error-states.spec.ts` still expected the old `工程诊断中核对` fallback; the test now requires the new product fallback and confirms default result panels do not send users to engineering diagnostics.
- [x] `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`
  - Result: exit `2`, `skip_reason=missing_readiness`.
  - Missing readiness: `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, `MACRO_EVENT_PROVIDER=no_active_event`.
  - Safety fields stayed true: `manual_execution_required=true`, `auto_order_enabled=false`.
- [x] `python3 tools/deployment/smoke_docker_hosted_runtime.py`
  - Result: exit `0`, `proof_level=hosted-runtime`, `hosted_runtime_only_not_prod_actionable=true`.
  - Hosted runtime remained fixture: `decision_engine=fixture`, `market_provider=fixture`, `prod_actionable_ready=false`.
  - Strict prod-config negative correctly rejected fixture with `production config requires decision.engine=openai_compatible`.
- [x] Cleanup checks after verification:
  - `git diff --check` passed.
  - No listeners remained on `8010/3001/8011/8012/8013/18010/13001`.
  - No `crypto-alert-runtime-smoke` containers remained.

## Fresh Verification Record - production-intent API and visual DNS hardening

- [x] `python3 -m pytest tests/api/test_runs_routes.py::test_manual_run_production_intent_path_projects_model_notification_and_legacy_lineage -q`
  - Red result before implementation: failed with `KeyError: 'provider'` because `business_summary.generation_summary` only exposed user-facing labels and did not give API/visual gates a safe machine-checkable model provider/status contract.
  - Green result after implementation: `1 passed`.
  - Proof level: production-intent API contract only. OpenAI-compatible response, OKX public HTTP, and Bark send are deterministic test doubles; the test exercises the real FastAPI `/api/runs/manual`, legacy workflow, gates, journal persistence, notification projection, run detail projection, `legacy_prompt` lineage, and hidden raw LLM payload boundary. It is not hosted `prod-actionable`.
- [x] `python3 -m pytest tests/api/test_runs_routes.py tests/storage/test_business_summary.py tests/structure/test_frontend_route_states.py -q`
  - Result: `53 passed`.
  - Meaning: the production-intent API contract, business summary projection, and frontend route-state/schema structure remain consistent.
- [x] `npm --prefix frontend run typecheck`
  - Result: passed.
  - Meaning: frontend schemas accept the new safe `generation_summary.provider` and `generation_summary.status` fields without changing existing product text fields.
- [x] `python3 -m pytest tests/deployment/test_container_config_commands.py::test_hosted_prod_actionable_visual_gate_rejects_private_dns_hostnames -q`
  - Red result before implementation: failed because `hosted-prod-actionable-visual.spec.ts` did not import `node:dns` and did not reject public-looking hostnames that DNS-resolve to local/private/reserved addresses.
  - Green result after implementation: `1 passed`.
  - Proof level: deployment/visual-gate contract only.
- [x] `python3 -m pytest tests/deployment/test_container_config_commands.py::test_hosted_prod_actionable_visual_gate_rejects_private_dns_hostnames tests/deployment/test_container_config_commands.py::test_hosted_prod_actionable_visual_gate_requires_reusing_existing_hosted_stack -q`
  - Result: `2 passed`.
  - Meaning: hosted-positive visual proof now requires explicit hosted reuse, explicit frontend/API URLs, public HTTPS syntax, and DNS-resolved public addresses before any hosted-positive visual run can be accepted.
- [x] `PLAYWRIGHT_REUSE_EXISTING_STACK=true npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts -g "default stack"`
  - Result: `1 passed`.
  - Note: an earlier attempt without `PLAYWRIGHT_REUSE_EXISTING_STACK=true` exited before tests because the existing local frontend already occupied `127.0.0.1:3001`; the rerun reused the current stack and verified the default local/fixture stack still cannot be mistaken for hosted prod-actionable visual proof.
- [x] `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true PLAYWRIGHT_REUSE_EXISTING_STACK=true PLAYWRIGHT_FRONTEND_BASE_URL=https://127.0.0.1.nip.io PLAYWRIGHT_API_BASE_URL=https://api.example.com npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts -g "default stack"`
  - Expected negative result: exit `1`.
  - Error: `127.0.0.1.nip.io resolves to a local/private/reserved address: 127.0.0.1`.
  - Meaning: hosted-positive visual proof now rejects public-looking HTTPS hostnames that DNS-resolve to local/private/reserved addresses.
- [x] `python3 -m pytest tests/deployment/test_container_config_commands.py::test_deployment_docs_reference_hosted_prod_actionable_visual_gate -q`
  - Red result before documentation update: deployment docs/README did not mention the hosted visual DNS `local/private/reserved` rejection.
  - Green result after documentation update: `1 passed`.
- [x] `python3 tools/local_stack/run_local_checks.py`
  - Initial attempt was blocked by an already-running local API on `8010`; after `python3 tools/local_stack/stop_local_stack.py --force-ports --kill-any-listener`, the full matrix rerun exited `0`.
  - Python full pytest: `1113 passed, 2 warnings`.
  - frontend typecheck: passed.
  - frontend production build: passed.
  - Playwright production local stack: `48 passed, 10 skipped`.
  - fixture smoke, mock LLM smoke, actionable staging smoke, seeded mock-outcome smoke, and collect-outcomes fixture smoke all passed.
  - Proof level: local-browser + fixture/mock/staging/collector wiring only. This is not production success.
- [x] `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`
  - Result: exit `2`, `skip_reason=missing_readiness`.
  - Missing: `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, `MACRO_EVENT_PROVIDER=no_active_event`.
  - Safety fields remained true: `manual_execution_required=true`, `auto_order_enabled=false`.
  - Proof boundary fields remained explicit: `proof_level=local-prod-actionable-rehearsal`, `production_success=false`, `hosted_proof_required=true`, `does_not_prove=hosted_prod_actionable`.
- [x] `python3 tools/deployment/smoke_docker_hosted_runtime.py`
  - Result: exit `0`, `ok=true`, `stage=complete`, `proof_level=hosted-runtime`.
  - Hosted runtime remained fixture: `decision_engine=fixture`, `market_provider=fixture`, `candidate_sidecar_mode=same_engine`, `prod_actionable_ready=false`, `hosted_runtime_only_not_prod_actionable=true`.
  - Strict prod-config negative check correctly rejected fixture with `production config requires decision.engine=openai_compatible`.
- [x] Cleanup checks after the latest verification:
  - No listeners remained on `8010/3001/8011/8012/8013/18010/13001`.
  - No `crypto-alert-runtime-smoke` containers remained.

## Fresh Verification Record - runs readiness empty state and real-outcome symbol freshness

- [x] `/runs` empty state now explains proof/readiness instead of looking like a broken empty table.
  - Red before implementation: `npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "runs empty state explains"` failed because no `aria-label="当前记录状态"` empty state existed.
  - Green after implementation: desktop and mobile focused Playwright checks require `当前没有可审计提醒`, explain that the state is local/empty and not production proof, show `真实模型`、`真实行情`、`Bark 通知`、`宏观事件状态`, and link to `/config` plus `/manual-run`.
  - Proof level: local-browser UX contract only. It does not prove hosted prod-actionable.
- [x] Hosted real-outcome evidence can no longer be satisfied by a different symbol or a stale pre-gate sample.
  - Red before implementation:
    - `tests/deployment/test_real_outcome_evidence_smoke.py::test_real_outcome_evidence_smoke_filters_by_symbol_and_collection_time` failed because `run_smoke()` did not accept `symbol` or `collected_after`.
    - `tests/deployment/test_hosted_real_outcome_collection_smoke.py::test_hosted_real_outcome_collection_runs_compose_collector_then_evidence_gate` failed because the wrapper did not pass `--symbol` into the evidence command.
  - Green after implementation: `tools/deployment/smoke_real_outcome_evidence.py` accepts `--symbol` and `--collected-after`, requires matched top-level/window symbol equality, and only counts timezone-aware `window.collected_at` values at or after the requested timestamp.
  - Wrapper behavior: `tools/deployment/smoke_hosted_real_outcome_collection.py` passes the requested `--symbol` and `--collected-after <gate_started_at>` into both pre- and post-collection evidence checks, and then requires post evidence to match one of this run's `collect-outcomes.collected_refs` by `(decision_ref, evaluation_target, symbol, window_name)`.
  - Documentation updated in `README.md`, `docs/deployment.md`, and this checklist; docs now state that 同一 symbol and `window.collected_at >= gate_started_at` are required but insufficient on their own. Same-symbol fresh evidence must also be exact-ref linked to this run's `collected_refs`.
- [x] Focused verification for this slice:
  - `python3 -m pytest tests/deployment/test_real_outcome_evidence_smoke.py tests/deployment/test_hosted_real_outcome_collection_smoke.py tests/deployment/test_container_config_commands.py::test_deployment_docs_describe_real_outcome_evidence_gate tests/deployment/test_container_config_commands.py::test_deployment_docs_reference_hosted_real_outcome_proof_output -q`
  - Result: `26 passed`.
  - `npm --prefix frontend run typecheck`
  - Result: passed.
  - `npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "runs empty state explains|manual run async flow"`
  - Result: `2 passed`.
  - `npm --prefix frontend run e2e -- --project=chromium-mobile full-stack-visual.spec.ts -g "runs empty state explains|core pages stay usable"`
  - Result: `2 passed`.
  - Note: an earlier parallel desktop/mobile attempt made two Next builds race on `.next` and failed with `ENOENT ... .next/export/500.html`; sequential rerun passed, confirming it was a local build race, not a UI regression.
- [x] Full local verification after this slice:
  - `python3 tools/local_stack/run_local_checks.py`
  - Python full pytest: `1131 passed, 2 warnings`.
  - frontend typecheck: passed.
  - frontend production build: passed.
  - Playwright production local stack: `52 passed, 10 skipped`.
  - fixture smoke, mock LLM smoke, actionable staging smoke, seeded mock-outcome smoke, and collect-outcomes fixture smoke all passed.
  - Proof level: local-browser + fixture/mock/staging/collector wiring only. This is not production success.
- [x] Strict production readiness and hosted-runtime checks after this slice:
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`
  - Result: exit `2`, `skip_reason=missing_readiness`.
  - Missing readiness: `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, `MACRO_EVENT_PROVIDER=no_active_event`.
  - Safety fields remained true: `manual_execution_required=true`, `auto_order_enabled=false`; proof boundary remained `production_success=false`, `does_not_prove=hosted_prod_actionable`.
  - `python3 tools/deployment/proof_ladder.py`
  - Result: printed `schema_version=2026-07-09.main-flow-proof-ladder` with current gates and required hosted P0 sequence.
  - `python3 tools/deployment/smoke_docker_hosted_runtime.py`
  - Result: exit `0`, `proof_level=hosted-runtime`, `hosted_runtime_only_not_prod_actionable=true`; strict prod-config negative correctly rejected fixture with `production config requires decision.engine=openai_compatible`.
  - Cleanup: `git diff --check` passed; no listeners remained on `8010/3001/8011/8012/8013/18010/13001`; no `crypto-alert-runtime-smoke` containers remained.
