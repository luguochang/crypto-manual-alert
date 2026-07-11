# Main Flow Production Recovery Checklist

Date: 2026-07-09

## User Intent Restatement

The goal is not to keep expanding sidecars, eval pages, AgentSwarm experiments, or raw observability views. The goal is to recover a production-deliverable manual crypto alert workbench.

The first priority is to prove the main business flow end to end:

```text
manual user request / audit note
  -> readable manual alert
  -> real readiness and safety gates
  -> model review and evidence projection
  -> Bark/manual notification status
  -> replay and outcome visibility
```

The user-visible product must not require reading API JSON, trace payloads, or eval diagnostics to understand the alert. Engineering diagnostics can exist, but they must remain clearly separated from the product path.

## Current State From Multi-Agent Audit

Three read-only agents reviewed architecture, UI/UX, and QA. The local coordinator also ran the real no-secret stack and deployment smoke commands.

### Architecture Facts

- The current main path is still manual-only, not auto trading.
- The production MVP path remains `legacy_prompt`.
- `manual_execution_required=true` and `auto_order_enabled=false` are non-negotiable safety boundaries.
- `production_candidate_swarm`, candidate final, eval, raw payload, agent audit, and matrix/raw observability are sidecar/audit/eval/diagnostic surfaces, not production final input.
- Pre-final shadow/candidate evidence is `production_blocking_audit`: it can feed `production_control_gate` as block evidence, but it does not enter `FinalDecisionAgent` input and does not replace `legacy_prompt`.
- `query_text` is still an operator audit note. It does not drive facts, lead plan, worker selection, tool budget, or final input.
- The production overlay declares `decision.final_input_mode=legacy_prompt`, `decision.candidate_sidecar_mode=disabled`, and `workflow.execution_mode=legacy_baseline`.
- The scheduler operational boundary is now explicit: `crypto-alert scheduler` refuses to start with `SCHEDULER_DISABLED` when `scheduler.enabled=false`.
- Backend ownership is now documented in `docs/implementation/2026-07-09-main-flow-module-ownership.md` with `runtime_role` categories: `production_main`, `production_blocking_audit`, `product_projection`, `diagnostic_projection`, `eval_sidecar`, `replay_only`, and `future_candidate`.
- Each persisted manual run now exposes a durable `main_path_contract` through the immediate manual-run API response, run detail API projection, and frontend schemas. The contract records environment-specific proof levels such as `proof_level=mock` for the local mock-LLM stack and `proof_level=production-intent-contract` only for production-intent config contracts. It also records `production_success=false`, `hosted_proof_required=true`, `does_not_prove=hosted_prod_actionable`, `runtime_role=production_main`, `final_input_contract.mode=legacy_prompt`, `manual_only.manual_execution_required=true`, and `manual_only.auto_order_enabled=false`.

### UI/UX Facts

- Default product routes are no longer JSON-first: `/`, `/manual-run`, `/runs`, `/runs/{trace_id}`, `/eval?tab=quality`, and `/config` render product copy first.
- `/runs/{trace_id}?tab=raw` without `columns=observability` is forced back to summary mode.
- Raw JSON is only intentionally exposed in diagnostic mode, and raw details are collapsed by default.
- The likely reason a user still sees "all JSON" is one of:
  - they opened API URLs directly;
  - they entered `columns=observability` or raw/eval diagnostic URLs;
  - they are running fixture/mock/hosted-runtime rather than real `prod-actionable`.
- The reason real model content is not visible in no-secret default runs is not primarily a rendering issue. The default stack uses fixture/mock providers and intentionally cannot claim real LLM/Bark/OKX production evidence.

### QA Facts

- Local no-secret checks run a real local FastAPI API, production Next frontend, SQLite state, and Chromium desktop/mobile Playwright. This is real local-browser coverage, but not production success.
- Deployment tests under `tests/deployment/*` are mostly fake-server/fake-runner/static contract tests. They protect gate semantics but do not start real hosted production infrastructure.
- Docker hosted-runtime smoke proves containerized API/frontend build and start. It remains `hosted-runtime`, not `prod-config`, `prod-actionable`, or `real-outcome`.
- Strict production gates correctly block this workspace because real external readiness is missing.

### Migration Gap Facts

`docs/migration` is not empty or useless; the problem is proof-level mixing. Many `[x]` items prove fields, scripts, trace panels, candidate/eval sidecars, mocked outcomes, local Playwright, or hosted fixture runtime. They do not prove a production-deliverable manual alert.

Open P0 from migration review:

| Item | Current state | Required closure |
| --- | --- | --- |
| `prod-actionable` manual alert | Script and gate exist; no successful real hosted run in this workspace. | Public HTTPS API base, real OpenAI-compatible endpoint/model/key, real OKX public data, Bark `sent`, unexpired no-active-event assertion, `allowed=true`, `legacy_prompt`, sidecar disabled. |
| Hosted prod-actionable visual proof | Playwright spec exists; positive branch requires explicit hosted env and is not satisfied by default local runs. | Run `hosted-prod-actionable-visual.spec.ts` with `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true` against the same public HTTPS hosted environment and trace; frontend/API hostnames must DNS-resolve only to public addresses, not local/private/reserved addresses. |
| Real outcome | Collector/evidence scripts exist; mock seeded samples are not financial quality proof. | After horizon maturity, collect a new exchange-native scorable outcome through the hosted DATA_DIR. |
| Production-intent hosted runtime | Default Docker smoke proves `hosted-runtime` only. | Start with filled `.env.production.example`, pass `--require-prod-config`, then pass prod-actionable gate. |
| Proof boundary consistency | Latest docs name proof levels, but old formal/migration `[x]` can still be misread. | Every new checkpoint/release must state proof level and avoid calling fixture/mock/staging/hosted-runtime production success. |

Machine-readable proof boundary:

```bash
python3 tools/deployment/proof_ladder.py
```

It prints `schema_version=2026-07-09.main-flow-proof-ladder` and lists `local_no_secret_matrix`, `strict_local_prod_actionable_guard`, `docker_hosted_runtime`, `hosted_prod_config`, `hosted_prod_actionable`, `hosted_prod_actionable_visual`, and `hosted_real_outcome`. `hosted_prod_actionable` requires a public HTTPS API base. `tools/deployment/proof_ladder.py` does not run the gates; it only defines the proof levels, commands, and "does not prove" boundaries that release notes must follow.

Open P1 from migration review:

- `query_text` product semantics: still `audit_note`; any intent-driving upgrade needs a separate design, tests, release gate, and rollback plan.
- `collect-outcomes` operations: schedule, matured-window policy, retry/failure handling, artifact storage, and operator runbook remain open.
- Diagnostic/audit shared hosted access: pages exist, but role/operator policy is still open.
- Langfuse/DeepEval/mature observability platform: post-v1 only, paused until P0 external proof closes.
- Backend cognitive load: ownership doc now exists, but broader code cleanup remains post-P0 unless it directly protects the main flow.

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
  - Frontend schemas preserve this contract, so product/API consumers cannot silently lose the proof boundary.
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

Commands run on 2026-07-09 in `/Users/chase/Documents/面试/crypto-manual-alert`:

- `python3 -m pytest tests/cli/test_runner_cli.py::test_cli_scheduler_refuses_when_config_disabled -q`
  - Red before implementation: failed because scheduler returned `0` while `scheduler.enabled=false`.
- `python3 -m pytest tests/deployment/test_container_config_commands.py::test_deployment_docs_describe_hosted_workbench_services -q`
  - Red before documentation update: failed because deployment docs did not mention `SCHEDULER_DISABLED`.
- `python3 -m pytest tests/cli/test_runner_cli.py::test_cli_scheduler_refuses_when_config_disabled tests/cli/test_runner_cli.py::test_cli_scheduler_uses_workflow_executor tests/deployment/test_container_config_commands.py -q`
  - Result: `22 passed`.
  - Proof level: CLI/deployment contract.
- `npm --prefix frontend run typecheck`
  - Result: passed.
- `python3 tools/local_stack/run_local_checks.py`
  - Python full pytest: `1082 passed, 2 warnings`.
  - frontend typecheck: passed.
  - frontend production build: passed.
  - Playwright: `48 passed, 6 skipped`.
  - fixture smoke: passed, `decision_engine=fixture`, `market_provider=fixture`, `allowed=false`.
  - mock LLM smoke: passed, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `allowed=false`.
  - actionable staging smoke: passed, local mock OKX, `allowed=true`.
  - mock outcome visibility smoke: passed, `visibility_only_not_financial_quality`.
  - collect-outcomes fixture smoke: passed, local mock OKX collector wiring only, `real_financial_quality_proven=false`.
  - Proof level: local-browser + fixture/mock/staging only. This is not production success.
- `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`
  - Result: exit `2`.
  - Missing readiness: `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, `MACRO_EVENT_PROVIDER=no_active_event`.
  - Safety fields stayed true: `manual_execution_required=true`, `auto_order_enabled=false`.
  - Interpretation: honest production gate block, not a hidden pass and not a product failure by itself.
- `python3 tools/deployment/smoke_docker_hosted_runtime.py`
  - Result: exit `0`.
  - Proof level: `hosted-runtime`.
  - Output proved hosted workbench smoke passed with `decision_engine=fixture`, `market_provider=fixture`, `hosted_runtime_only_not_prod_actionable=true`.
  - Strict production config negative check correctly rejected the default fixture runtime with `production config requires decision.engine=openai_compatible`.
  - Cleanup check: no residual listeners on `8010/3001/8011/8012/8013/18010/13001`; no `crypto-alert-runtime-smoke` containers remained.
- `PLAYWRIGHT_EXPECT_DIAGNOSTIC_DISABLED=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --diagnostic-routes-disabled" npm --prefix frontend run e2e -- --project=chromium-desktop diagnostic-access-gate.spec.ts`
  - Red before implementation: failed because `/runs?columns=observability` still rendered engineering diagnostics while `diagnostic.routes_enabled=false`.
  - Result after implementation: `1 passed`.
  - Proof level: local-browser + config-disabled diagnostic gate.
- `npm --prefix frontend run typecheck`
  - Result: passed.
- `npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"`
  - Result: `1 passed`.
  - Meaning: intentional diagnostic-enabled engineering views still work in the default local E2E environment.
- `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_api_env_disables_notification_by_default tests/local_stack/test_scripts.py::test_local_smoke_api_env_can_disable_diagnostic_routes_without_prod_actionable tests/local_stack/test_scripts.py::test_local_smoke_api_env_enables_prod_actionable_when_ready -q`
  - Result: `3 passed`.
  - Meaning: local-stack env construction now supports non-prod diagnostic-disabled browser proof while preserving default local diagnostics and prod-actionable diagnostics-off semantics.
- `python3 -m pytest tests/structure/test_formal_docs_current_state.py::test_main_flow_module_ownership_map_keeps_backend_boundaries_explicit -q`
  - Red before documentation: failed because `docs/implementation/2026-07-09-main-flow-module-ownership.md` did not exist.
  - Green after documentation: `1 passed`.
  - Follow-up red/green: added `runtime_role` and `production_blocking_audit` requirements; tests failed until the ownership document recorded the categories and gate semantics.
  - Proof level: structure/documentation boundary only.
- `npm --prefix frontend run typecheck`
  - Result: passed after strengthening the hosted prod-actionable visual gate.
- `npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts -g "default stack"`
  - Result: `1 passed`.
  - Meaning: the default local/fixture stack still cannot be mistaken for hosted prod-actionable visual proof.
- `python3 tools/local_stack/run_local_checks.py`
  - First result in this round: failed because three readiness tests used fixed `MACRO_EVENT_VALID_UNTIL=2026-07-09T15:30:00+08:00`, now expired. This exposed a test fixture time bug, not a production-rule bug.
  - Focused fix verification: `python3 -m pytest tests/api/test_system_routes.py::test_config_readiness_reports_prod_actionable_ready_when_event_and_external_env_are_ready tests/api/test_system_routes.py::test_config_readiness_requires_candidate_sidecar_disabled_for_prod_actionable tests/api/test_system_routes.py::test_config_readiness_rejects_local_endpoints_for_prod_actionable -q` -> `3 passed`.
  - Full rerun: Python full pytest `1084 passed, 2 warnings`; frontend typecheck passed; frontend production build passed; Playwright `48 passed, 8 skipped`; fixture, mock LLM, actionable staging, seeded mock-outcome, and collect-outcomes fixture smokes passed.
  - Proof level: local-browser + fixture/mock/staging only.
- `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`
  - Result: exit `2`, `missing_readiness`.
  - Missing: `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, `MACRO_EVENT_PROVIDER=no_active_event`.
  - Safety fields: `manual_execution_required=true`, `auto_order_enabled=false`.
  - Interpretation: honest production gate block.
- `python3 tools/deployment/smoke_docker_hosted_runtime.py`
  - Result: exit `0`, `proof_level=hosted-runtime`, `stage=complete`.
  - Default runtime remained fixture: `decision_engine=fixture`, `market_provider=fixture`, `candidate_sidecar_mode=same_engine`, `hosted_runtime_only_not_prod_actionable=true`.
  - Strict prod-config negative check rejected the fixture runtime with `production config requires decision.engine=openai_compatible`.
  - Cleanup: no residual listeners on `8010/3001/8011/8012/8013/18010/13001`; no `crypto-alert-runtime-smoke` containers.

## P0 Checklist

- [ ] Start a production-intent hosted API/frontend from a filled env derived from `.env.production.example`.
  - Required config paths: `config/default.yaml:config/prod.yaml:config/staging.yaml`.
  - Required safety: `manual_execution_required=true`, `auto_order_enabled=false`.
  - Required main path: `decision.final_input_mode=legacy_prompt`, `decision.candidate_sidecar_mode=disabled`, `workflow.execution_mode=legacy_baseline`.
  - Do not include trade, order, withdraw, or private exchange keys.

- [ ] Pass hosted production-config workbench smoke.
  - Command:
    ```bash
    python3 tools/deployment/smoke_hosted_workbench.py \
      --api-base <hosted-api> \
      --frontend-base <hosted-frontend> \
      --symbol ETH-USDT-SWAP \
      --query "生产工作台配置 smoke" \
      --horizon 6h \
      --require-prod-config
    ```
  - This proves `prod-config`, not `prod-actionable`.

- [ ] Pass hosted run-level `prod-actionable` smoke.
  - Command:
    ```bash
    python3 tools/deployment/smoke_hosted_prod_actionable.py \
      --api-base <public-https-api> \
      --symbol ETH-USDT-SWAP \
      --query "Hosted prod-actionable smoke：验证真实人工提醒证据链" \
      --horizon 6h
    ```
  - Must prove public HTTPS API base, real OpenAI-compatible `decision.final status=ok`, real OKX public execution evidence, Bark `sent`, complete and unexpired no-active-event assertion, `allowed=true`, `legacy_prompt`, candidate sidecar disabled, and manual-only safety.

- [ ] Pass hosted prod-actionable visual gate against the same hosted environment.
  - Command:
    ```bash
    PLAYWRIGHT_REUSE_EXISTING_STACK=true \
    PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true \
    PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend> \
    PLAYWRIGHT_API_BASE_URL=<public-https-api> \
    npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts
    ```
  - The positive test must not be skipped.
  - It must submit a fresh hosted manual run, reopen the same `/runs/{trace_id}`, and prove concrete model review, evidence, Bark sent status, no raw JSON/secrets, and DOM/deep-scroll health.
  - The gate now also requires API `business_summary.generation_summary` provider/model/status/response summary to render inside the DOM `模型返回摘要` panel, rejects fixture/mock/fallback text such as `本地演练`, `mock`, `fixture`, `未调用外部模型`, or `摘要暂不可用`, and rejects generic placeholder text such as `模型已返回结构化提醒。`.
  - `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true` now requires `PLAYWRIGHT_REUSE_EXISTING_STACK=true` at Playwright config-load time, before `webServer` can stop ports or launch a local fixture stack.
  - `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true` now also requires explicit `PLAYWRIGHT_FRONTEND_BASE_URL` and `PLAYWRIGHT_API_BASE_URL`; in hosted-positive mode the Playwright config has no local `webServer` startup block.
  - `PLAYWRIGHT_FRONTEND_BASE_URL` and `PLAYWRIGHT_API_BASE_URL` must be public HTTPS URLs; localhost, private IPs, non-HTTPS URLs, and hostnames that DNS-resolve to local/private/reserved addresses are rejected before any hosted-positive browser run.

- [ ] Pass hosted real-outcome collection after the alert horizon matures.
  - Command:
    ```bash
    python3 tools/deployment/smoke_hosted_real_outcome_collection.py \
      --api-base <hosted-api> \
      --symbol ETH-USDT-SWAP \
      --limit 50 \
      --min-count 1 \
      --same-host-data-dir-confirmed
    ```
  - Required evidence: `api_config_preflight=production_outcome_config_ready`, `collection_errors_allowed=false`, `collected>0`, non-empty `collect-outcomes.collected_refs`, `new_refs_verified=true`, `real_exchange_native_matured_outcome_proven=true`, `prod_actionable_alert_proven=false`.
  - Freshness and exact-link boundary: the wrapper passes the same symbol and `--collected-after <gate_started_at>` into lower-level `smoke_real_outcome_evidence.py`; matched evidence must be for the same symbol, have timezone-aware `window.collected_at` at or after this collection gate, and match one of this run's `collected_refs` by `(decision_ref, evaluation_target, symbol, window_name)`. Older outcomes, concurrent outcomes for a different symbol, or same-symbol fresh outcomes outside this run's exact `collected_refs` cannot close this P0.

- [x] Keep diagnostic URLs out of ordinary user paths when diagnostics are disabled.
  - Product navigation must not expose `columns=observability` by default.
  - `/eval?tab=quality` must remain the default product quality page.
  - When `diagnostic.routes_enabled=false`, direct `columns=observability`, raw run-detail, `/eval?tab=cases`, and `/eval/runs/{id}` URLs now render `诊断入口已关闭` with product recovery links instead of engineering matrices, raw payloads, eval forms, or replay details.
  - Remaining P1: define role/operator policy for shared hosted environments that intentionally keep diagnostics enabled.

- [x] Keep product error states honest about write uncertainty.
  - Manual-run API failures no longer say `本次记录已保存`.
  - `/runs` and `/runs/{trace_id}` Server Component load failures no longer say records or visits were saved.
  - Partial projection fallback avoids unproven saved-state wording and instead points to the returned core plan/detail entry.

## P1 Checklist

- [ ] Decide `query_text` product semantics.
  - Option A: keep it as "关注点/审计备注" and make the UI copy unmistakable.
  - Option B: create a separate design where user text can drive intent, facts, and final input.
  - Do not silently make free text drive production decisions without a new design, tests, and release gate.

- [ ] Operationalize `collect-outcomes`.
  - Define schedule, matured-window handling, retry/failure policy, proof artifact storage, and operator runbook.
  - Keep `real-outcome` separate from `prod-actionable`.

- [ ] Add stronger visual regression evidence for full product pages.
  - Add true full-page or segmented screenshots for `/manual-run` success, `/runs/{trace_id}` summary, `/eval?tab=quality`, `/config`, and raw collapsed diagnostic mode.
  - Done in this slice: `/runs/{trace_id}` summary desktop/mobile screenshots were intentionally updated to include the visible `提醒证据级别` strip.
  - Keep fixture/mock/staging baselines separate from hosted prod-actionable evidence.

- [x] Reduce backend cognitive overhead without changing the production path.
  - Documented a module ownership map: `docs/implementation/2026-07-09-main-flow-module-ownership.md`.
  - Structure gate: `tests/structure/test_formal_docs_current_state.py::test_main_flow_module_ownership_map_keeps_backend_boundaries_explicit`.
  - The ownership map now distinguishes `production_main`, `production_blocking_audit`, `product_projection`, `diagnostic_projection`, `eval_sidecar`, `replay_only`, and `future_candidate`.
  - It records that pre-final shadow/candidate audit can block unsafe output through `production_control_gate`, but cannot enter `FinalDecisionAgent` or replace `legacy_prompt`.
  - Avoid moving production final input away from `legacy_prompt` during this recovery.
  - Avoid expanding blocked AgentSwarm work until P0 production evidence is closed.

## Fresh P1 Verification

- `python3 -m pytest tests/structure/test_formal_docs_current_state.py::test_main_flow_module_ownership_map_keeps_backend_boundaries_explicit -q`
  - Red before documentation: failed because `docs/implementation/2026-07-09-main-flow-module-ownership.md` did not exist.
  - Green after documentation and `runtime_role`/`production_blocking_audit` refinements: `1 passed`.
  - Proof level: structure/documentation boundary. This reduces backend drift risk, but it is not `prod-actionable` or `real-outcome`.
- `npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts -g "default stack"`
  - Result: `1 passed`.
  - Proof level: local negative guard. This proves the strengthened hosted visual gate does not mistake the default local stack for production visual proof.
- `npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"`
  - Red before UI implementation: failed because product pages did not expose `aria-label="提醒证据级别"`.
  - Green after implementation and intentional desktop screenshot update: `1 passed`.
- `npm --prefix frontend run e2e -- --project=chromium-mobile full-stack-visual.spec.ts -g "manual run async flow"`
  - Green after intentional mobile screenshot update: `1 passed`.
- `npm --prefix frontend run typecheck`
  - Result: passed.
- `python3 -m pytest tests/deployment/test_hosted_prod_actionable_smoke.py -q`
  - Red before implementation: hosted prod-actionable smoke did not independently reject missing `macro_event` assertion metadata when readiness was claimed ready.
  - Green after public HTTPS and unexpired event-assertion hardening: `8 passed`.
  - The gate now rejects localhost/private/non-HTTPS `--api-base`, expired `macro_event.valid_until`, and timezone-less `macro_event.valid_until` by default; fake-server contract tests opt in with `allow_local_api_base=True`.
  - Proof level: fake-server contract; not production success.
- `python3 -m pytest tests/storage/test_business_summary.py tests/api/test_runs_routes.py::test_run_detail_business_summary_uses_persisted_mock_llm_interaction -q`
  - Red before implementation: product model summary used the generic placeholder `模型已返回结构化提醒。`.
  - Green after implementation: `15 passed`.
  - Meaning: safe `llm_summary.output_summary` can become a concrete model excerpt, and raw provider-shaped `choices` stays hidden behind a productized parsed-plan fallback.
- `PLAYWRIGHT_EXPECT_MOCK_LLM=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm --seed-mock-outcome" npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"`
  - Result: `1 passed`.
  - Proof level: local browser + mock LLM only.
- `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts -g "default stack"`
  - Result: exit `1` at Playwright config load with the expected reuse-stack error.
  - Meaning: positive hosted visual proof cannot accidentally stop or replace a hosted stack with a local fixture stack.
- `python3 -m pytest tests/deployment/test_container_config_commands.py::test_hosted_prod_actionable_visual_gate_requires_reusing_existing_hosted_stack -q`
  - Red before implementation: failed because hosted-positive Playwright mode did not require explicit hosted frontend/API URLs and still carried a local `webServer` startup block.
  - Green after implementation: `1 passed`; later proof-ladder/public-HTTPS hardening verified with `python3 -m pytest tests/deployment/test_container_config_commands.py::test_hosted_prod_actionable_visual_gate_requires_reusing_existing_hosted_stack tests/deployment/test_proof_ladder.py -q` -> `2 passed`.
  - Proof level: deployment/visual-gate contract only. This prevents hosted-positive proof from mutating local ports, but it is not production visual proof.
- `npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "manual run API 500"`
  - Red before implementation: failed because the manual-run error alert said `本次记录已保存`.
  - Green after implementation: `1 passed`.
  - Proof level: local browser error-state UX.
- `PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "runs list and detail failures"`
  - Result: `1 passed`.
  - Meaning: `/runs` and `/runs/{trace_id}` load failures no longer claim a record or visit was saved, and still hide unsafe backend text.
- `npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "manual run partial success"`
  - Result: `1 passed`.
  - Meaning: partial projection fallback remains readable and no longer uses unproven saved-state wording.

## Execution Rules

- Do not claim production success from local fixture, mock LLM, mock OKX, staging allowed, Docker hosted-runtime, or fake-server deployment tests.
- Treat strict gate exit `2` for `missing_readiness` as an honest block.
- For every fix, prefer the smallest main-flow change with a failing test first.
- If a hosted/prod gate fails, debug the failing production field directly: readiness, real LLM, exchange-native evidence, no-active-event metadata, Bark `sent`, production control, risk gate, or UI rendering of that same trace.
- Do not hide errors by weakening gates, converting failures to warnings, or relabeling lower proof levels.

## Definition Of Done For This Recovery

This recovery is complete only when:

- hosted production-config workbench smoke passes;
- hosted `prod-actionable` smoke passes;
- hosted prod-actionable visual gate passes on the same trace/environment;
- hosted real-outcome collection passes after horizon maturity;
- default product pages remain readable and non-JSON-first;
- diagnostic pages remain clearly labeled or gated;
- final reporting includes explicit proof levels and remaining limitations.
