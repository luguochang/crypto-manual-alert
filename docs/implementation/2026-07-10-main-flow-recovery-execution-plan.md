# 2026-07-10 Main Flow Recovery Execution Plan

> Scope: this is the active execution plan for recovering the manual-only crypto alert workbench around the product main flow first. It is not a new AgentSwarm roadmap and does not supersede the proof boundary in `2026-07-09-current-delivery-checklist.md`.

## User Intent

The user concern is that the project became more complex while the visible business flow still felt unproven: frontend pages looked like JSON or empty projections, real model content was not obvious, backend modules drifted toward sidecars/eval/AgentSwarm, and migration checkpoints mixed local/mock/staging evidence with production claims.

The execution objective is therefore:

```text
/manual-run
  -> POST /api/runs/manual
  -> RunExecutor
  -> LegacyPlanRunnerAdapter / LegacyDecisionWorkflow
  -> legacy_prompt final LLM decision
  -> parser / production_control_gate / risk gate
  -> journal + notification projection
  -> /runs
  -> /runs/{traceId}
  -> readable model conclusion, price levels, risk, evidence, notification, result review
```

Everything else is secondary until this path is readable, testable, and honestly proven.

## Non-Negotiable Boundary

- Product remains manual-only.
- `manual_execution_required=true`.
- `auto_order_enabled=false`.
- No OKX trade, withdraw, or private-key path.
- Production MVP final input remains `legacy_prompt`.
- `query_text` remains an operator audit note, not the final facts or final-input driver.
- AgentSwarm, candidate final, eval, replay, raw payloads, and matrix views remain sidecar/audit/eval/diagnostic surfaces.
- Pre-final candidate/shadow audit may block through `production_control_gate`, but must not replace `legacy_prompt`.
- Local, fixture, mock, staging, Docker hosted-runtime, and fake-server tests must not be described as production success.

## Multi-Agent Audit Result

### Architecture

Current backend main path is back on the intended manual-only / `legacy_prompt` chain:

```text
POST /api/runs/manual
  -> create_manual_run()
  -> build_manual_decision_request()
  -> RunExecutor.submit()
  -> DecisionRunContext.create()
  -> LegacyPlanRunnerAdapter.run()
  -> PlanRunner.run_once()
  -> LegacyDecisionWorkflow.run()
  -> select_final_input(final_input_mode=legacy_prompt)
  -> decision_engine.run(legacy prompt payload)
  -> parser.strict_json
  -> production_control.check
  -> risk.check
  -> persist_run_result()
  -> JournalQueryRepository.get_run_detail()
  -> business_summary / result_review / notification / main_path_contract
```

The remaining architecture P0 is not another backend module rewrite. It is production proof: hosted `prod-actionable`, same hosted visual proof, and hosted real outcome after horizon maturity.

### UI/UX

Default product paths are no longer raw JSON-first, but the product still had a content-quality gap: model content was not treated as first-class product content. Specific risks:

- `business_summary.generation_summary.response_summary` could fall back to generic success text.
- frontend product-copy sanitization could replace natural model text containing market indicators such as `funding_rate` or `open_interest` with `内容已记录，当前摘要不可读`.
- `/runs` list can still become sparse when optional projections are malformed.
- Product pages should prioritize `动作 + 模型结论 + 关键价位 + 风险/证据`, with diagnostic metadata kept secondary.

### QA / Playwright

Current automation is useful but proof levels are separate:

- default Playwright: real Chromium + production Next + local FastAPI + SQLite, still localhost.
- full local matrix: local/fixture/mock/staging/collector wiring, not production success.
- hosted-positive visual: skipped unless public HTTPS hosted frontend/API and explicit `PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true`.
- hosted real-outcome: separate after horizon maturity; it does not prove fresh LLM/Bark.

Canonical browser commands must use `npm --prefix frontend run e2e ...` or run from `frontend/`, not a root-level bare Playwright invocation that loses `baseURL`.

## Work Completed In This Execution Slice

- [x] Added P0 data-transparency projection for model and trading data.
  - `business_summary.generation_summary.raw_completion_excerpt` now carries a safe excerpt extracted from model completion text, including OpenAI-compatible `choices[0].message.content`.
  - `business_summary.generation_summary.response_summary` remains the productized decision summary; raw completion is a separate field so provider JSON shape is not shown as business copy.
  - `llm_interactions[].completion_excerpt` is available in default run detail responses without exposing `request_json` or `response_json`.
  - `business_summary.market_data_status` now states market provider, success/failed/missing counts, per-endpoint status for ticker/mark/index/funding/OI/order book/candles, and whether OKX execution facts are complete enough for manual review.
  - Failure reasons are endpoint-level and product-safe. Paths, trace IDs, tokens, raw payload keys, and secrets are filtered before product display.
  - Frontend schemas explicitly model and sanitize the new fields instead of relying on `.passthrough()` unknown data.
  - `/manual-run` and `/runs/{traceId}` now show `交易数据状态` on the default business path; `模型返回摘要` and `模型审阅` show `模型原始返回摘录` when present.
  - The engineering LLM tab now prefers `completion_excerpt` for response summary while keeping full payload behind Raw diagnostics.
- [x] Clarified data-source boundary for the user-facing product.
  - Web search / Responses web search can enrich research, news, event context, and audit notes.
  - Web search must not satisfy exchange-native execution facts.
  - Manual review for actionable opening/triggering still requires OKX public or equivalent exchange-native mark, index, and order-book facts plus event-state assertion.
  - Current local network probes could not reach OKX public domains; the product must surface OKX endpoint failures instead of treating search, fixture, or stale data as success.
- [x] Fixed backend product projection so successful model paths prefer concrete safe model excerpts.
  - If `llm_summary.output_summary` contains safe text, show it.
  - If provider-shaped raw payload such as `choices` appears, hide raw payload and fall back to parsed-plan model excerpt.
  - If only `main_action` exists, show a concrete excerpt such as `模型结论：触发做多。`.
  - If no safe model conclusion can be formed, show an honest degradation message instead of `模型已返回结构化提醒。`.
  - If runtime config enables OpenAI-compatible but this run has no persisted `llm_summary`, show `模型配置已启用 / 本次未记录模型返回` instead of implying the model returned.
  - Backend safe excerpt filtering now rejects secret/path/token/raw/internal-token shaped text before it reaches `business_summary.generation_summary.response_summary`.
  - String `llm_summary.output_summary` is accepted when safe; raw/provider-shaped or unsafe summaries fall back to parsed-plan excerpts.
  - Parsed-plan fallback keeps `probability=0` and list-shaped `invalidation` text.
- [x] Added/updated `tests/storage/test_business_summary.py` coverage.
  - Red before implementation: generic model success placeholder appeared.
  - Red during code review hardening: unsafe summaries, string `output_summary`, zero probability, list invalidation, and config-without-persisted-LLM boundaries were not fully covered.
  - Green after implementation: `tests/storage/test_business_summary.py` plus the focused API projection test passed: `20 passed`.
- [x] Fixed frontend product-copy sanitization for model free text.
  - Pure unknown internal tokens still fall back to product-safe copy.
  - Common market indicator names in natural model text, such as `funding_rate`, `open_interest`, and `BTC.D`, remain visible.
  - Uppercase internal/secret-shaped tokens such as `BARK_DEVICE_KEY`, `OPENAI_API_KEY`, `REQUEST_JSON`, and full dotted internal tokens are hidden before product-copy replacements run.
- [x] Added Playwright contract coverage in `frontend/tests/e2e/product-copy.spec.ts`.
  - Red before implementation: `funding_rate` / `open_interest` were replaced by `内容已记录，当前摘要不可读`.
  - Red during code review hardening: uppercase internal tokens were visible, and full dotted internal tokens could be partially translated.
  - Green after implementation: full `product-copy.spec.ts` passed on desktop and mobile: `26 passed`.
- [x] Promoted model output to first-class product content on the main UI path.
  - Added a shared `ModelConclusionPanel` with `aria-label="模型结论"` backed by `business_summary.generation_summary.response_summary`.
  - Rendered it in `/manual-run` success results and `/runs/{traceId}` summary before proof-level and mode metadata.
  - Kept `动作 + 模型结论 + 关键价位` together before mode/proof metadata, so proof labels no longer push the business result down the page.
  - Added a `/runs` business table column for `模型结论` so the list no longer looks empty when model output exists.
  - Added Playwright DOM/order assertions proving the default business path shows action, model conclusion, and price levels before evidence/proof metadata.
  - Tightened `/runs` list assertions to inspect the model-conclusion cell itself, including raw/secret negative checks.
  - Red before implementation: `full-stack-visual.spec.ts` could not find `aria-label="模型结论"`.
  - Red before ordering fix: action/model conclusion appeared below proof/mode metadata.
  - Red during code review hardening: key price levels still appeared after mode/proof metadata, the model conclusion panel still displayed mode labels, and `/runs` row-level assertions were too broad.
  - Green after implementation: desktop and mobile focused full-stack visual checks passed.
- [x] Fixed mobile result discovery and density for the main path.
  - `/manual-run` success results now focus and scroll to `本次提醒建议` after a successful async run, so mobile users do not stay stranded above the generated result.
  - Small-screen layout now avoids the old column-flex `flex-basis` gap in the detail summary card.
  - Small-screen density was tightened so the detail page shows action, model conclusion, and the top of price levels near the first mobile viewport.
  - Added Playwright mobile assertions for price-level visibility near the first viewport.
  - Updated fixed fixture visual baselines only after inspecting the actual desktop/mobile screenshots and confirming the differences were the intended information hierarchy changes.

## Active P0 Checklist

- [x] Restate the target and separate main flow from sidecars.
- [x] Run real multi-agent audit for architecture, UI/UX, and QA/proof boundaries.
- [x] Make safe model completion excerpts first-class product/API data.
  - Backend red/green coverage:
    - `tests/storage/test_business_summary.py::test_business_summary_generation_summary_describes_real_model_with_safe_completion_excerpt`
    - `tests/api/test_runs_routes.py::test_run_detail_projects_safe_llm_completion_excerpt_without_raw_payloads`
  - Frontend coverage:
    - `frontend/tests/e2e/product-copy.spec.ts` validates the new excerpt field is sanitized and not raw-payload shaped.
- [x] Make OKX public trading data success/failure visible on the business path.
  - Backend red/green coverage:
    - `tests/storage/test_business_summary.py::test_business_summary_projects_okx_market_data_status_without_hiding_failures`
    - `tests/storage/test_business_summary.py::test_business_summary_market_status_distinguishes_fixture_points_from_exchange_native_facts`
  - Frontend coverage:
    - `business_summary.market_data_status` schema sanitizes endpoint status, failure reason, and display text.
    - `/manual-run` and `/runs/{traceId}` render `交易数据状态`.
    - `full-stack-visual.spec.ts` now explicitly asserts `交易数据状态`, counts, at least one data item, and raw/secret negative checks on both `/manual-run` success and `/runs/{traceId}` detail.
- [x] Preserve the web-search boundary.
  - Search-derived context remains research/audit material only.
  - `market_data_status.execution_facts_ready` is based on exchange-native OKX execution facts, not search text.
- [x] Add an explicit production network escape hatch for OKX public HTTP without weakening the default.
  - `MARKET_DATA_HTTP_TRUST_ENV=false` remains the default, so local mock/fixture/CI traffic is not silently routed through ambient proxy variables.
  - `MARKET_DATA_HTTP_TRUST_ENV=true` allows an intentional hosted deployment to inherit `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY`.
  - `MARKET_DATA_HTTP_PROXY=<http-or-https-url>` provides a dedicated proxy for the OKX public client.
  - Invalid proxy URLs fail configuration loading.
  - Safe config output never exposes the proxy URL; it emits `<redacted>` / `<unset>` plus `http_proxy_set`.
  - Focused config/provider tests were red before implementation and passed after the minimal client/config change.
  - This is a network escape hatch only. It does not turn search, fixture, local OKX mock, or proxy metadata into exchange-native execution evidence.
- [x] Re-run focused verification after the data-transparency slice.
  - `python3 -m pytest tests/storage/test_business_summary.py tests/api/test_runs_routes.py::test_run_detail_projects_safe_llm_completion_excerpt_without_raw_payloads tests/api/test_runs_routes.py::test_run_detail_business_summary_uses_persisted_mock_llm_interaction tests/storage/test_query_repository.py -q`
    - Result: `26 passed`.
  - `npm --prefix frontend run typecheck`
    - Result: passed.
  - `npm --prefix frontend run e2e -- product-copy.spec.ts`
    - Result: desktop and mobile `30 passed`.
  - `PLAYWRIGHT_EXPECT_MOCK_LLM=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm --seed-mock-outcome" npm --prefix frontend run e2e -- --project=chromium-desktop --project=chromium-mobile full-stack-visual.spec.ts -g "manual run async flow"`
    - Initial result: failed because a JSON-shaped model completion excerpt was visible in the engineering LLM response summary.
    - Fix: JSON completion strings are parsed into productized model excerpts; raw JSON completion is no longer displayed on default pages.
    - Final result: desktop and mobile `2 passed`.
  - `OPENAI_BASE_URL=<external-compatible-endpoint> OPENAI_MODEL=gpt-5.5 OPENAI_API_KEY=<runtime-secret> python3 tools/local_stack/smoke_local_stack.py --with-real-llm`
    - Result: `ok=true`, `decision_engine=openai_compatible`, `decision_model=gpt-5.5`, `real_llm_enabled=true`, `market_provider=fixture`, `allowed=false`, trace `8f1d01ea4dd849c79ed4e29f1414cb18`.
    - Proof level: real external model path with fixture market. This proves LLM call/parse/persist/projection, not production-actionable trading data.
  - `OPENAI_BASE_URL=<external-compatible-endpoint> OPENAI_MODEL=gpt-5.5 OPENAI_API_KEY=<runtime-secret> python3 tools/local_stack/smoke_local_stack.py --with-real-llm --with-real-market`
    - Result: failed honestly at `real market smoke expected evidence sources`.
    - Observed OKX failures in the run detail: `ticker: ConnectTimeout`, `mark: ConnectError`, `funding_rate: ConnectError`, `open_interest: ConnectError`, `order_book: ConnectError`, `candles: ConnectError`.
    - The model returned safe `no trade`; OKX execution facts were not proven in this network environment.
  - Real LLM browser check against trace `17b11c5ed9c54b5e9d17e2a8102a8db5`:
    - API business summary included `model=gpt-5.5`, `status_label=模型已返回`, safe `raw_completion_excerpt`, and `market_data_status.execution_facts_ready=false`.
    - Playwright DOM checks passed on desktop and mobile for `模型结论`, `模型原始返回摘录`, `交易数据状态`, `执行事实不完整`, no raw JSON, and no secret-shaped text.
    - Screenshots saved under `frontend/test-results/real-llm-p0/` for local review.
  - Latest real LLM smoke using runtime secret via stdin only:
    - `python3 tools/local_stack/smoke_local_stack.py --with-real-llm`
      - Result: `ok=true`, `decision_engine=openai_compatible`, `decision_model=gpt-5.5`, `market_provider=fixture`, `allowed=false`, trace `4b733df6848d48fcb2a65ff1a5997b5d`.
      - Journal projection contains both `business_summary.generation_summary.raw_completion_excerpt` and `llm_interactions[].completion_excerpt`.
      - Market status now says `执行事实不完整：缺少交易所原生 index、mark、order_book`, so fixture data is no longer described as absent.
    - `python3 tools/local_stack/smoke_local_stack.py --with-real-llm --with-real-market`
      - Result: failed honestly at `real market smoke expected evidence sources`, trace `76c3906ec8c74fc1953373cd91f758d4`.
      - LLM returned safe `no trade` and persisted completion excerpt.
      - OKX endpoint failures persisted under `market_data_status.failures`: `ticker: ConnectTimeout`, `mark/funding_rate/open_interest/order_book/candles: ConnectError`.
      - Proof level: real LLM plus attempted real OKX from this workstation. It is not production-actionable success because exchange-native evidence was not obtained.
- [x] Fix generic model-success projection so the product path shows concrete model conclusion text when safe.
- [x] Fix product-copy sanitizer so natural model summaries are not erased by internal-token hiding.
- [x] Re-run focused frontend and backend checks for the changed slices:
  - `python3 -m pytest tests/storage/test_business_summary.py -q`
    - Result after review hardening: included in the wider focused run below.
  - `python3 -m pytest tests/storage/test_business_summary.py tests/api/test_runs_routes.py::test_run_detail_business_summary_uses_persisted_mock_llm_interaction -q`
    - Result: `20 passed`.
  - `npm --prefix frontend run e2e -- product-copy.spec.ts -g "model free-text keeps market indicator names"`
    - Red before implementation: `funding_rate` and `open_interest` were replaced by `内容已记录，当前摘要不可读`.
    - Result after implementation: desktop and mobile `2 passed`.
  - `npm --prefix frontend run e2e -- product-copy.spec.ts`
    - Result after review hardening: desktop and mobile `26 passed`.
  - `npm --prefix frontend run typecheck`
    - Result: passed.
  - `PLAYWRIGHT_EXPECT_MOCK_LLM=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm --seed-mock-outcome" npm --prefix frontend run e2e -- --project=chromium-desktop full-stack-visual.spec.ts -g "manual run async flow"`
    - Result after the first failing assertion and implementation: `1 passed`.
    - Proof level: local Chromium + local FastAPI + production Next + SQLite + mock OpenAI-compatible server. This is not production success.
  - `PLAYWRIGHT_EXPECT_MOCK_LLM=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm --seed-mock-outcome" npm --prefix frontend run e2e -- --project=chromium-mobile full-stack-visual.spec.ts -g "manual run async flow"`
    - Result: `1 passed`.
    - Proof level: local mobile Chromium viewport only. This is not hosted mobile proof.
  - `python3 tools/local_stack/smoke_local_stack.py --with-mock-llm`
    - Result: `ok=true`, `smoke_profile=mock_real_engine`, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `manual_execution_required=true`, `auto_order_enabled=false`.
    - Proof level: local mock-model HTTP path only. This is not real LLM, not real market, not hosted production.
- [x] Start the local full stack through the project scripts and run the no-secret matrix:
  - `python3 tools/deployment/proof_ladder.py`
    - Result: printed `schema_version=2026-07-09.main-flow-proof-ladder` and kept hosted prod-config/prod-actionable/visual/real-outcome in definition of done.
  - `python3 tools/local_stack/run_local_checks.py`
    - Result after UI order/mobile hardening: Python pytest `1143 passed, 2 warnings`; frontend typecheck passed; frontend production build passed; Playwright `54 passed, 10 skipped`; fixture, mock LLM, actionable staging, seeded mock-outcome, and collect-outcomes fixture smokes passed.
    - Proof level: local-browser + fixture/mock/staging/collector wiring only. This is not production success.
- [x] Run strict local production-readiness guard:
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`
  - Expected in this workspace if real secrets/readiness are absent: exit `2` with `missing_readiness` or `unsafe_readiness`.
  - This is an honest block, not production success.
  - Result: exit `2`, `missing_readiness` for `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`; output kept `production_success=false` and `does_not_prove=hosted_prod_actionable`.
- [x] Re-run Docker hosted-runtime smoke if time and Docker are healthy:
  - `python3 tools/deployment/smoke_docker_hosted_runtime.py`
  - Passing this proves `hosted-runtime` only, not `prod-config`, not `prod-actionable`, not `real-outcome`.
  - Result: `ok=true`, `proof_level=hosted-runtime`, default runtime `decision_engine=fixture`, `market_provider=fixture`; strict prod-config negative check rejected fixture config with `production config requires decision.engine=openai_compatible`.
- [x] Keep ordinary product routes free from raw JSON:
  - `/manual-run`
  - `/runs`
  - `/runs/{traceId}`
  - diagnostic `columns=observability` stays opt-in and labeled as engineering diagnostics.
  - Latest local-browser evidence: `python3 tools/local_stack/run_local_checks.py` ran `full-stack-visual.spec.ts` on desktop and mobile; ordinary product pages passed the no raw JSON / no secret / DOM health checks inside the local production Next + FastAPI stack.
  - Latest focused browser evidence after QA review:
    - `PLAYWRIGHT_EXPECT_MOCK_LLM=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm --seed-mock-outcome" npm --prefix frontend run e2e -- --project=chromium-desktop --project=chromium-mobile full-stack-visual.spec.ts -g "manual run async flow"`
    - Result: desktop and mobile `2 passed`.
    - Added assertions now lock the P0 product contract: `交易数据状态`, counts, data items, `模型原始返回摘录`, and no raw payload/secret-shaped text on manual-run result and run detail summary.

### 2026-07-11 Real OKX + Real LLM Closure Evidence

- [x] Correct the OKX index contract instead of accepting a null index from `mark-price`.
  - `mark` comes from `/api/v5/public/mark-price`.
  - `index` comes from `/api/v5/market/index-tickers`.
  - `ETH-USDT-SWAP` is mapped to index instrument `ETH-USDT`.
  - Both the main market provider and the liquidity/order-book provider use the independent index endpoint.
  - Local mock responses and tests no longer place `idxPx` in a mark-price response.
- [x] Fail closed on unusable execution and event facts.
  - Null/non-finite mark or index values cannot satisfy execution facts.
  - Empty, single-sided, or malformed order-book levels cannot satisfy execution facts.
  - Empty or unknown `active_event_status` values cannot clear the event hard block.
  - The business summary cannot display `可人工复核` unless `facts_gate.passed=true`, the production gate explicitly allows the run, and usable OKX mark/index/order-book values are present.
  - Frontend proof level cannot display `生产可复核证据已记录` when `execution_facts_ready=false`.
- [x] Prove the workstation's real OKX path through the explicit ClashX proxy without changing the default proxy isolation.
  - Runtime-only setting: `MARKET_DATA_HTTP_PROXY=http://127.0.0.1:7890`.
  - Real provider probe returned all snapshot points, `unavailable=[]`, non-null mark/index, and 20 ask + 20 bid levels.
  - Real-market fixture-decision smoke passed with trace `780c7bbf6c1049768be94f137cdaecb6` and stayed `allowed=false` because the decision engine was fixture and event status was disabled.
- [x] Prove the combined real external model + real OKX public path.
  - Model secret was supplied through stdin only and was not written to env files, logs, journal projections, or frontend output.
  - Smoke trace: `af40d5dbe1b04044af35533738751498`.
  - Result: `decision_engine=openai_compatible`, `decision_model=gpt-5.5`, `market_provider=okx_public`, seven grouped market endpoint items all successful, `execution_facts_ready=true`, and a persisted safe model completion excerpt.
  - The run correctly stayed `allowed=false` because `active_event_status` was missing and notification was disabled. Real market/model success does not override the event and notification gates.
  - Desktop and mobile Playwright DOM audits found the market panel, mark/index/order book, `gpt-5.5`, the model excerpt, and the blocking state; horizontal overflow was `0`, and no raw request/response JSON or secret value was visible.
  - Screenshots: `artifacts/real-flow/desktop.png` and `artifacts/real-flow/mobile.png`.
- [x] Re-run integrated verification after the closure fixes.
  - `pytest -q`: passed, exit `0`.
  - `npm --prefix frontend run typecheck`: passed.
  - Desktop + mobile Playwright for `product-copy`, `error-states`, and `full-stack-visual`: `52 passed`, `6 skipped`, `0 failed`.
  - The six skips are environment-gated Server Component first-load fault cases, not failures.
- [x] Keep the web-search boundary explicit.
  - Exchange execution facts must come from exchange-native APIs. Web search must not supply or repair mark, index, or order-book facts.
  - Web/Responses search remains useful for news, macro events, sentiment, and research context. In the real combined smoke it was not configured, so `research.results` remained a visible missing confirmation instead of being silently fabricated.

## Hosted Production P0 Checklist

These cannot be closed by local work alone.

Current blocker summary as of 2026-07-11:

- Local default is intentionally fixture: `config/default.yaml` uses fixture market data, fixture decision engine, and disabled research.
- Production overlay enables `okx_public`, OpenAI-compatible decisioning, and Responses web search, but it still needs a public HTTPS hosted deployment and real hosted env vars.
- Direct DNS/routing from this workstation remains unsuitable for OKX, but the explicit ClashX proxy path now proves real exchange-native mark, index, and order-book retrieval locally. This is local-network proof, not hosted production proof.
- The user-provided OpenAI-compatible endpoint/model/key and real OKX public data have now succeeded in the same local run. The run still correctly blocked because the event-state assertion and Bark notification proof were absent.
- Research/web search was not enabled in the combined smoke. That is a remaining research-context capability, not a valid substitute for exchange execution facts.

- [ ] Start a production-intent public HTTPS hosted API/frontend using a filled env derived from `.env.production.example`.
- [ ] Pass hosted production-config smoke:

```bash
python3 tools/deployment/smoke_hosted_workbench.py \
  --api-base <hosted-api> \
  --frontend-base <hosted-frontend> \
  --symbol ETH-USDT-SWAP \
  --query "生产工作台配置 smoke：验证非 fixture 配置和人工提醒入口" \
  --horizon 6h \
  --require-prod-config
```

- [ ] Pass hosted run-level production proof:

```bash
python3 tools/deployment/smoke_hosted_prod_actionable.py \
  --api-base <public-https-api> \
  --symbol ETH-USDT-SWAP \
  --query "Hosted prod-actionable smoke：验证真实人工提醒证据链" \
  --horizon 6h \
  --proof-output hosted-prod-actionable-proof.json
```

Required evidence:

- public HTTPS API base;
- real OpenAI-compatible endpoint/model/key;
- model name is not mock/fixture/fake/stub/test/local;
- `decision.final` status is `ok`;
- real OKX public market data and exchange-native fresh execution evidence;
- complete unexpired `MACRO_EVENT_PROVIDER=no_active_event` operator assertion;
- Bark notification row is same-run `sent`, `ok=true`, HTTP 2xx;
- `allowed=true`;
- `decision.final_input_mode=legacy_prompt`;
- `decision.candidate_sidecar_mode=disabled`;
- `workflow.execution_mode=legacy_baseline`;
- `manual_execution_required=true`;
- `auto_order_enabled=false`.

- [ ] Pass hosted prod-actionable visual proof against the same hosted environment:

```bash
PLAYWRIGHT_REUSE_EXISTING_STACK=true \
PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true \
PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend> \
PLAYWRIGHT_API_BASE_URL=<public-https-api> \
npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts

PLAYWRIGHT_REUSE_EXISTING_STACK=true \
PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true \
PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend> \
PLAYWRIGHT_API_BASE_URL=<public-https-api> \
npm --prefix frontend run e2e -- --project=chromium-mobile hosted-prod-actionable-visual.spec.ts
```

- [ ] After horizon maturity, pass hosted real-outcome collection:

```bash
python3 tools/deployment/smoke_hosted_real_outcome_collection.py \
  --api-base <public-https-api> \
  --symbol ETH-USDT-SWAP \
  --limit 50 \
  --min-count 1 \
  --same-host-data-dir-confirmed \
  --proof-output hosted-real-outcome-proof.json
```

Required boundary: matched evidence must exact-match this collection run's `collected_refs` by `(decision_ref, evaluation_target, symbol, window_name)` and have timezone-aware `collected_at` at or after gate start.

## P1 Checklist

- [x] Make model conclusion a more obvious first-class panel on `/manual-run` and `/runs/{traceId}` instead of burying it under generation metadata.
- [x] Add `/runs` list model-summary text or status so successful model runs do not look empty in the table.
- [x] Add a success-state focus/scroll behavior on `/manual-run` so after a long async run keyboard and mobile users land directly on `本次提醒建议`.
- [x] Ensure mobile detail view keeps action, model conclusion, and price levels near the first viewport without proof/mode metadata pushing them down.
- [x] Split productized model summary from safe raw completion excerpt.
- [x] Add default business-page trading data status instead of requiring Raw/diagnostic tabs for OKX endpoint failures.
- [ ] Decide whether default `/runs/{traceId}` should keep the review status bar in the ordinary business tab or move it behind diagnostic/observability mode.
- [ ] Improve fallback semantics to distinguish:
  - model not called;
  - model failed;
  - model returned but display projection is missing;
  - model returned but safety filter hid the raw excerpt.
- [x] Add production network configuration for OKX reachability where required, such as an explicitly configured proxy/env-proxy policy.
- [x] Verify local real OKX reachability and exchange-native execution evidence through the explicit proxy without weakening the default isolated client.
- [ ] Verify OKX reachability and exchange-native execution evidence in a hosted environment rather than claiming local timeout as fixed.
- [ ] Decide whether `query_text` should remain audit-only for MVP or become a controlled strategy input in a separate design; do not silently let it drive execution facts.
- [ ] Operationalize outcome collection schedule, matured-window policy, retries, and proof artifact storage.
- [ ] Define role/operator policy for diagnostic routes in shared hosted environments.
- [x] Add Raw diagnostic expanded-JSON E2E coverage proving request/response payload display is still redacted after details are opened.
  - Red evidence: JSON-string payloads containing `api_key`, `device_key`, and `secret` values were visible after expanding `LLM 交互 JSON`; only Bearer and Bark URL text had been redacted.
  - Fix: `RawTab` parses `request_json` / `response_json` with `JSON.parse` before passing them to the existing recursive `JsonDetails` redactor.
  - Green evidence: focused full-stack Playwright passed on desktop and mobile with seeded unsafe diagnostic payloads and explicit negative assertions for every seeded secret value.
- [x] Add targeted long-text/failure-state visual regression for `TradingDataStatusPanel` on mobile and desktop.
  - Red evidence: a long continuous market failure token produced `3834px` desktop and `4203px` mobile body horizontal overflow.
  - Fix: analysis/step grid children and list items now use `min-width: 0`, `overflow-wrap: anywhere`, and `word-break: break-word`; trading status item spans use the same constrained wrapping.
  - Green evidence: the focused failure-state Playwright test passed on desktop and mobile with full scroll-point DOM audits.

## Completion Rule

Do not mark the product production-deliverable until the same public HTTPS hosted environment passes:

1. hosted prod-config;
2. hosted prod-actionable API proof;
3. hosted prod-actionable desktop visual proof;
4. hosted prod-actionable mobile visual proof;
5. hosted real-outcome collection after horizon maturity.

Until then, local green tests mean the local product path is healthier. They do not mean production success.
