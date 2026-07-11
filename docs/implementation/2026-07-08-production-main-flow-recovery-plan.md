# Production Main Flow Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not treat fixture smoke, schema tests, or visual snapshots as proof of production delivery.

**Goal:** Recover the product to a production-deliverable manual crypto alert workbench: one user query must produce a readable, safe, auditable, optionally notified manual alert before the project invests further in sidecar Agent Swarm or external observability platforms.

**Architecture:** The current MVP production path remains `legacy_prompt` until a separate release review changes it. Agent Swarm, candidate final, and eval artifacts remain audit/eval sidecars. The immediate recovery architecture adds a user-facing `business_summary` contract, explicit readiness for real LLM/market/Bark modes, and test gates that distinguish fixture flow from real/actionable flow.

**Tech Stack:** Python 3.14, FastAPI, SQLite journal/eval stores, Next.js 15 App Router, React 19, Zod, Playwright, pytest.

---

## 1. Current Evidence

This plan is based on a fresh multi-agent audit on 2026-07-08 plus local verification.

### 1.1 Verified Commands

- [x] `python3 -m pytest -q`
  - Result: pass with 2 warnings.
  - Meaning: Python unit/API/workflow/storage/eval contract tests are currently green.

- [x] `python3 tools/local_stack/smoke_local_stack.py`
  - Result: pass.
  - Meaning: fixture local stack can start API/frontend, submit one manual run, read run detail, and open eval/config pages.
  - Limitation: notification was `enabled=false`; this does not prove real Bark, real LLM, real market data, or allowed actionable alert delivery.

- [x] `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm run build`
  - Result: pass.
  - Meaning: production frontend build compiles with the correct API base embedded.

- [x] `cd frontend && npm run e2e`
  - Initial result: 3 passed, 1 failed.
  - Failure: mobile audit recorded React production hydration error `#418`.
  - Evidence path: `frontend/test-results/full-stack-visual-full-sta-e1b80--without-visual-DOM-defects-chromium-mobile/error-context.md`.
  - Root-cause evidence: `--project=chromium-mobile -g "core pages stay usable" --repeat-each=3` passed; `--workers=1` full suite passed; default 2-worker full suite reproduced the error. The shared API/frontend stack and shared SQLite journal are mutable test state, so cross-project parallel execution is unsafe.
  - Fix applied: `frontend/playwright.config.ts` sets `workers: 1` with an explanation. After this, default `npm run e2e` passes 4/4.
  - 2026-07-08 follow-up: a later desktop failure screenshot ended on `/config`, but trace timing showed the `#418` event occurred earlier around filtered `/runs` -> run detail matrix navigation. Narrow production checks for `/config`, default run detail, matrix, and raw did not reproduce. The suite now keeps shared-stack tests serial and adds default cockpit assertions so product rendering remains covered.

### 1.2 Architecture Facts

- [x] Default local config is not production-real:
  - `config/default.yaml`: `market_data.provider=fixture`.
  - `config/default.yaml`: `decision.engine=fixture`.
  - `config/default.yaml`: `notification.enabled=false`.
  - `config/default.yaml`: `research.enabled=false`.

- [x] The current default API chain is:

```text
POST /api/runs/manual
  -> build_manual_decision_request
  -> RunExecutor.submit
  -> DecisionRunContext.create
  -> LegacyPlanRunnerAdapter
  -> LegacyDecisionWorkflow
  -> market.fetch
  -> research_orchestration
  -> build_legacy_final_input_step
  -> pre_final_orchestration / shadow audit sidecar
  -> decision.final via selected final_input_mode=legacy_prompt
  -> parser.strict_json
  -> production_control.check / risk.check
  -> persist_run_result
  -> journal + optional notification
  -> API response
```

- [x] `DecisionRequest.query_text` is currently audit context, not production decision control:
  - `drives_lead_plan=False`.
  - `drives_worker_selection=False`.
  - `drives_tool_budget=False`.
  - `drives_final_input=False`.

- [x] True LLM calls require `decision.engine=openai_compatible` plus `OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_API_KEY` or the configured key env.

- [x] Candidate sidecar is now independently configurable:
  - default `decision.candidate_sidecar_mode=same_engine` preserves current local/audit behavior.
  - `config/prod.yaml` and prod-actionable smoke set `candidate_sidecar_mode=disabled` so the production final LLM is not automatically reused for a second candidate-sidecar call.

### 1.3 Product Facts

- [x] The frontend has improved from raw-only toward three surfaces:
  - `/manual-run`: manual alert entry and result.
  - `/runs`: business alert history.
  - `/runs/[traceId]`: default product summary.
  - `/runs/[traceId]?columns=observability&tab=matrix` and `?columns=observability&tab=raw`: engineering audit/debug surfaces.

- [x] 2026-07-08 follow-up after UI/UX and QA review:
  - `/runs` default view now uses business columns: reminder time, symbol, suggested action, review result, risk summary, notification, detail link.
  - Raw/matrix tabs require explicit `columns=observability`; directly visiting `?tab=raw` in business mode falls back to the summary.
  - Playwright now includes a generic "business page is not raw JSON/API envelope" assertion for product routes.
  - Run detail and run list visual regression snapshots now cover the main manual alert path, not only the dashboard.

- [x] 2026-07-08 continuation: manual-run success and run detail business headers no longer show a support/debug reminder id in the primary business surface; run detail creation time is now human-readable instead of a raw ISO string.

- [ ] Product polish still has P1 work:
  - Query text is still audit note only; P1 intent parsing remains future work.
  - `/eval` now defaults to the product-facing `quality` view and hides the eval-run form plus non-quality diagnostic tabs from the default product path; explicit `?tab=runs`, `?tab=cases`, and `?tab=outcomes` remain engineering/evaluation diagnostics.
  - Run detail now provides a per-run `result_review` visibility panel. This closes the UI visibility loop for pending/mock/scorable states, but real exchange-native matured outcome evidence is still required before claiming financial quality.

### 1.4 Highest Authority For Direction

- [x] `docs/formal/37-真实多Agent对抗审查与交付方向裁决.md` is the current direction authority.
- [x] Do not create new `docs/formal/*` documents for this recovery.
- [x] Do not keep expanding blocked `production_candidate_swarm` or Langfuse/DeepEval work before the real manual alert loop is delivered.

### 1.5 2026-07-08 Multi-Agent Review Update

- [x] UI/UX Agent finding: default product routes were still leaking engineering vocabulary (`Trace`, `LLM`, `Spans`, `legacy_prompt`, `decision_input`, raw/JSON fallback, English `allowed/blocked`, and `Cockpit` semantics). P0.3 follow-up moved these into explicit diagnostic paths and added Playwright negative assertions.
- [x] 2026-07-08 second UI/QA follow-up: `/runs` still behaved like a trace/history log and `?tab=raw` could be opened from a business URL. Fixed the default list to business history, guarded raw/matrix behind `columns=observability`, and added generic DOM/Playwright raw-JSON checks.
- [x] Architecture Agent finding: backend main flow is now structurally understandable, but production delivery is still blocked by real external proof. `prod.yaml`-style readiness for OKX/OpenAI/Bark does not by itself prove that a manual alert can reach `allowed=True`; the run-level facts gate still needs exchange-native mark/index/order-book facts plus event status (`macro_event.provider=no_active_event` or a real event pool assertion).
- [x] Architecture Agent finding: do not make `shadow.worker_mode=llm_tool_shadow` a P0 YAML-only dependency unless real shadow LLM client factory wiring is implemented. The MVP production path remains `legacy_prompt` until a separate release review changes it.
- [x] Product priority reaffirmed: first deliver `user query -> readable manual alert -> manual-only safety/readiness proof -> notification status -> replay/outcome`, then revisit broader Agent/eval platform expansion.
- [x] 2026-07-08 final multi-agent cleanup:
  - Backend/readiness: `prod_actionable_ready` now requires `candidate_sidecar_mode=disabled`; `market_data.provider` is validated as `fixture|okx_public`; `OutcomeCollector` default HTTP client uses `trust_env=False`.
  - Release gate: `--prod-actionable` now rejects local/private/mock OpenAI and OKX endpoints with `skip_reason=unsafe_readiness`; localhost cannot be used to spoof production success.
  - Frontend/product copy: default product surfaces no longer expose `LONG/SHORT`, `instrument`, `阻断原因（top N）`, or `/eval` as an engineering-first "Eval 工作台"; `/eval?tab=quality` is now a light product-facing `质量复盘/金融质量` page while retaining explicit mock/non-real quality evidence.
  - QA: Playwright now covers production Next + local API desktop/mobile, direct `?tab=raw` business guard, mock LLM product rendering, seeded notification history, mock outcome visibility, financial-quality target-gate productization, DOM/visual scans, and page/runtime errors.
- [x] 2026-07-08 real subagent audit rerun:
  - Backend/architecture Agent: main backend chain is now understandable and centered on `manual alert`, but it is not production-complete until a real external prod-actionable smoke succeeds and at least one exchange-native matured outcome is visible. `query_text` remains `audit_note`, candidate/swarm remains sidecar/audit, and event readiness is currently only `MACRO_EVENT_PROVIDER=no_active_event`.
  - UI/UX Agent: `/manual-run -> /runs -> /runs/[traceId]` is no longer a JSON/trace-first product path; remaining front-end gaps are `/config`, non-quality `/eval`, query semantics, and per-run outcome/replay visibility. `/config` was selected as the next no-secret P1 fix because it explains why no real LLM/Bark/production content appears.
  - QA Agent: existing tests prove local fixture/product rendering, mock LLM rendering, actionable staging, and strict readiness skips, but not real production. Release wording must require `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`; structured skip or staging success is not production success.
- [x] 2026-07-08 current real subagent audit and recovery pass:
  - Backend/architecture Agent confirmed the main backend chain is now centered on manual-alert execution, but found the immediate `POST /api/runs/manual` response was thinner than the persisted run detail. Fixed by rebuilding the synchronous response from `query_repository.get_run_detail(trace_id)` after persistence while preserving stable `plan_id` and `expires_at` response fields.
  - UI/UX Agent confirmed the default `/manual-run -> /runs -> /runs/[traceId]` path is no longer raw JSON, but found `/eval` defaulted to engineering replay/judge tables and the homepage still exposed raw mode/storage/service values. Fixed by routing default quality links to `/eval?tab=quality`, making `/eval` default to `quality`, and projecting homepage status/time into product language.
  - QA Agent confirmed Playwright/default smoke prove local product UX and mock/staging profiles only. Sequential smoke rerun showed fixture, mock LLM, actionable staging, and mock outcome visibility pass independently; `--prod-actionable --fail-on-skip` correctly exits `2` with `missing_readiness` in this environment.
  - Current release boundary remains unchanged: local/mock/staging success is not production success. A production claim still requires real HTTPS OpenAI-compatible endpoint, real OKX public market, Bark `sent`, `MACRO_EVENT_PROVIDER=no_active_event`, `allowed=true`, `candidate_sidecar_mode=disabled`, `manual_execution_required=true`, and `auto_order_enabled=false`.
- [x] 2026-07-08 code-review follow-up:
  - Reviewer found that persisted `parsed_plan` could overwrite normalized immediate-response fields such as `expires_at`, causing the frontend schema to reject an otherwise successful manual run.
  - Fixed `POST /api/runs/manual` response plan merging so persisted fields can add business context, but normalized executor fields (`plan_id`, ISO `expires_at`, manual-only fields, numeric price fields) win.
  - Added regression test `test_manual_run_response_preserves_normalized_plan_fields_when_payload_has_overlaps`, which first failed with `expires_at=None` leaking from raw payload and then passed after the merge-order fix.
  - Reviewer also flagged that frontend `result_review` is a hard-required run-detail field. This remains an intentional lockstep API/UI contract so missing backend result-review projection fails loudly instead of being hidden as a default "not collected" UI state. Deployment must avoid mixing a new frontend with an old API for `/api/runs/{trace_id}`.
- [x] 2026-07-08 final UI/QA/code-review follow-up:
  - UI/UX review found `/eval?tab=quality` still exposed outcome/eval implementation tokens such as `mocked_outcome`, `legacy_final`, and `price_source_not_exchange_native` in the default product quality page.
  - Fixed the Financial Quality panel so known outcome target/source/action/reason/score values render as Chinese product copy, and unknown target/source/action/reason/score fall back to safe product text such as `其他复盘目标`, `其他样本来源`, `未识别动作`, `暂未分类原因`, and `其他评分标签` instead of raw enum values.
  - Added a Playwright seed for an unknown outcome row so `/eval?tab=quality` proves raw fallback tokens like `mystery_target`, `mystery_source`, and `mystery_unscored_reason` are not visible.
  - Updated Python local-stack smoke so API assertions still require raw machine fields (`source_type=mocked_outcome`, `unscored_reason=price_source_not_exchange_native`), while frontend assertions require only product copy (`本地展示样本`, `价格不是交易所原生样本`, `不可评分`) and reject internal outcome codes.
  - QA review also found React `#418` diagnostics lacked the first failing route. `frontend/tests/e2e/audit-helpers.ts` now attaches timestamp and URL context to console/page/runtime/request failures; console messages prefer Playwright's `message.location().url`.
  - `frontend/src/app/shared/sidebar.tsx` now renders a stable non-active/non-diagnostic first pass and only applies active state and diagnostic navigation after client hydration, reducing SSR/client route-state mismatch risk.
- [x] 2026-07-08 eval product/diagnostic boundary follow-up:
  - Default `/eval` is now a product quality page: it shows only the `质量指标/金融质量` context and no longer renders the eval-run form, `Dataset`, `Badcase IDs`, `Mode`, `judge_only_fixture`, `judge_openai`, or direct tabs for `复盘批次` / `问题样本` / `结果样本`.
  - Explicit non-quality eval URLs now identify themselves as `工程复盘诊断` and keep the eval-run form plus diagnostic tabs available for engineering review.
  - Red check: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed while `/eval` still exposed the engineering eval form and non-quality tabs.
  - Green check: the same focused Playwright command passed after gating diagnostic controls behind explicit non-quality tabs.
- [x] 2026-07-08 user-directed multi-agent rerun after main-flow restatement:
  - Backend/architecture Agent reconfirmed the backend chain is structurally closed, but called out a production-delivery mismatch: the Docker/Compose deployment still defaults to a scheduler-style `MANUAL_ALERT` service and does not expose a production manual-query API/frontend entry. This is now an explicit P0 delivery blocker unless the product contract is narrowed to CLI-only `run-once`.
  - UI/UX Agent reconfirmed the default product path is readable, then found two remaining visible product issues: `/eval?tab=quality` still exposed internal sample IDs such as `mocked-outcome-seed`, and `/eval/runs/[evalRunId]` was an English engineering detail page (`Eval Run Detail`, `Run ID`, `Promotion Artifacts`, `Frozen Input`).
  - QA Agent reconfirmed Playwright/local stack exercises a real browser, production Next build, local FastAPI, SQLite journal/eval stores, desktop/mobile DOM scans, screenshot checks, notification-history seeding, result-review seeding, and strict readiness gates. It also found `stop_local_stack.py` did not include the mock OKX port `8012`, so actionable-staging listeners could remain after failures.
  - Fixed `/eval/runs/[evalRunId]` into an explicit Chinese `工程复盘诊断` page with `复盘批次详情`, `发布证据`, and `回放输入摘要` sections; it remains diagnostic, but no longer presents as a raw English developer page.
  - Fixed `/eval?tab=quality` so product users see `样本 1`, `样本 2`, etc. instead of raw decision refs or local seed IDs. API/smoke still verify `decision_ref`, `source_type=mocked_outcome`, and `unscored_reason=price_source_not_exchange_native`; the frontend now rejects those raw tokens in visible product text.
  - Fixed local-stack cleanup by adding `8012` to `stop_local_stack.py` and a regression test, so mock OKX cannot linger outside the shared-stack cleanup contract.
  - Red check: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed before the eval-run detail page exposed the new `工程复盘诊断` / `复盘批次详情` boundary.
  - Red check: `python3 -m pytest tests/local_stack/test_scripts.py::test_stop_local_stack_covers_mock_okx_port -q` failed while `8012` was absent from `stop_local_stack.py`.
  - Green check: `python3 -m pytest tests/local_stack/test_scripts.py::test_stop_local_stack_covers_mock_okx_port tests/local_stack/test_scripts.py::test_local_smoke_assert_eval_quality_outcome_visible_requires_mocked_outcome tests/local_stack/test_scripts.py::test_local_smoke_rejects_mock_outcome_without_unscored_product_explanation tests/local_stack/test_scripts.py::test_local_smoke_rejects_quality_page_internal_outcome_codes -q` passed after the cleanup and smoke/front-end text changes.
  - Green check: `npm --prefix frontend run typecheck` passed.
  - Green check: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` passed with the new eval-run detail boundary, hidden product sample IDs, and the existing product/raw-DOM negative assertions.
- [x] 2026-07-08 final verification for this pass:
  - `python3 -m pytest -q` passed with 2 warnings.
  - `npm --prefix frontend run typecheck` passed.
  - `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
  - `npm --prefix frontend run e2e` passed 4/4 across desktop and mobile, using the production Next build and local API stack.
  - `git diff --check` passed.
  - Sequential `python3 tools/local_stack/smoke_local_stack.py` passed with `smoke_profile=fixture`, `allowed=false`, `decision_engine=fixture`, `market_provider=fixture`, `macro_event_provider=disabled`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - Sequential `python3 tools/local_stack/smoke_local_stack.py --with-mock-llm` passed with `smoke_profile=mock_real_engine`, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `market_provider=fixture`, and `allowed=false`.
  - Sequential `python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging` passed with `smoke_profile=actionable_staging`, `market_provider=okx_public`, `macro_event_provider=no_active_event`, `allowed=true`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - Sequential `python3 tools/local_stack/smoke_local_stack.py --seed-mock-outcome` passed and reported `mock_outcome_quality_scope=visibility_only_not_financial_quality`.
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` returned exit code `2` with `skip_reason=missing_readiness`; missing readiness is `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`. This remains an honest production release-gate block, not a production success.

---

## 2. Non-Negotiable Product Definition

The product is not an auto-trader and not a generic Agent platform. It is a manual crypto alert workbench.

A deliverable run must answer these questions in product language:

- What is the suggested action?
- What price levels matter?
- Is this only a fixture/demo run or did real providers participate?
- Can the output enter manual review, or is it blocked?
- Why is it blocked or downgraded?
- What evidence was used, and what is missing?
- Was a notification sent?
- How can the result be replayed and later evaluated?

The engineering views may expose trace/span/LLM/gate/raw payload details, but the primary product route must not require reading JSON to understand the answer.

Production deployment must also expose or define the manual-query entry used by the product contract. Today the code path exists (`POST /api/runs/manual` and `crypto-alert run-once`), but the container default is still scheduler-first; that deployment shape is not, by itself, proof that the user-facing manual-query workbench is delivered.

---

## 3. P0 Recovery Checklist

### Task P0.1: Preserve The Current Verification Baseline

**Files:**
- Modify: `docs/implementation/2026-07-08-production-main-flow-recovery-plan.md`
- Modify as needed: `frontend/tests/e2e/full-stack-visual.spec.ts`
- Modify as needed: `frontend/tests/e2e/audit-helpers.ts`

- [ ] Record fresh verification after every P0 change:

```bash
python3 -m pytest -q
cd frontend && npm run typecheck
cd frontend && NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm run build
cd frontend && npm run e2e
python3 tools/local_stack/smoke_local_stack.py
```

- [x] Keep the current Playwright mobile React `#418` failure as open until a deterministic root cause is documented.
  - 2026-07-08 09:32 CST update: root cause documented as unsafe cross-project parallelism against one mutable local stack; fixed by serializing the shared-stack Playwright suite in `frontend/playwright.config.ts`.

- [ ] Add a short verification section to this document after each P0 milestone with command, date, result, and remaining failures.

**Acceptance:**
- All P0 status updates in this document distinguish `fixture smoke`, `mock real-engine smoke`, and `real external smoke`.

### Task P0.2: Define `business_summary` As The Product Contract

**Files:**
- Create: `src/crypto_manual_alert/storage/business_summary.py`
- Modify: `src/crypto_manual_alert/storage/journal_rows.py`
- Modify: `src/crypto_manual_alert/api/routes_runs.py`
- Modify: `src/crypto_manual_alert/api/schemas.py`
- Modify: `frontend/src/lib/schemas/manual-run.ts`
- Modify: `frontend/src/lib/schemas/runs.ts`
- Modify: `frontend/src/app/manual-run/run-form.tsx`
- Modify: `frontend/src/app/runs/[traceId]/decision-tab.tsx`
- Modify: `frontend/src/app/runs/[traceId]/decision-summary-card.tsx`
- Test: `tests/storage/test_business_summary.py`
- Test: `tests/api/test_runs_routes.py`
- Test: `frontend/tests/e2e/product-primary-flow.spec.ts`

`business_summary` should be generated server-side from already persisted facts:

```ts
type BusinessSummary = {
  title: string;
  mode_notice: string;
  decision_label: "本地样本" | "可人工复核" | "已阻断" | "生成失败";
  action_text: string;
  confidence_text: string;
  price_levels: {
    reference_price: number | null;
    entry_trigger: number | null;
    stop_price: number | null;
    target_1: number | null;
    target_2: number | null;
    expires_at: string | null;
  };
  reason_bullets: string[];
  risk_bullets: string[];
  evidence_bullets: string[];
  data_gap_bullets: string[];
  next_steps: string[];
  safety_notice: string;
  notification: {
    enabled: boolean;
    channel: string | null;
    status: "sent" | "disabled" | "failed" | "not_recorded";
    message: string;
  };
};
```

- [ ] Generate `mode_notice` from effective config and run telemetry:
  - fixture/no LLM: "当前为本地样本/规则模式，本次未调用真实 LLM；结果仅用于流程验证。"
  - real LLM: include provider/model status without exposing secret or raw completion by default.

- [ ] Generate `reason_bullets` from plan notes, `why_not_opposite`, verdict warnings, and gate reasons.

- [ ] Generate `risk_bullets` from `production_control_gate`, `facts_gate`, risk rule hits, and unavailable data.

- [ ] Generate `data_gap_bullets` from `analysis.data_gaps`, `facts_gate.missing_execution_facts`, and plan unavailable data.

- [ ] Generate `next_steps` with manual-only language:
  - blocked: "补齐缺失事实后重新评估。"
  - allowed: "人工核对价格、事件状态、仓位风险后再手动执行。"

**Acceptance:**
- `/api/runs/manual` and `/api/runs/{trace_id}` both expose `business_summary`.
- Cockpit and manual-run result render `business_summary` first.
- Product-primary Playwright test fails if the primary product area contains raw JSON markers such as `request_json`, `response_json`, `Worker Matrix`, `Span`, or `legacy_prompt`.

**Execution record:**

- [x] Added server-side `build_business_summary()` in `src/crypto_manual_alert/storage/business_summary.py`.
- [x] `/api/runs/manual` now returns `business_summary` next to `trace_id`, `plan`, and `verdict`.
- [x] `/api/runs/{trace_id}` now exposes `plan_run.business_summary`.
- [x] Frontend schemas now parse `business_summary` for manual-run and run detail responses.
- [x] `/manual-run` success view now leads with "本次手动提醒计划", fixture/no-real-LLM notice, reasons, risks/gaps, next steps, and notification message.
- [x] Run detail cockpit consumes `plan_run.business_summary` in `DecisionSummaryCard`.
- [x] Updated Playwright to assert the new product summary wording instead of the old "返回结果" shell.
- [x] 2026-07-08 current pass: `POST /api/runs/manual` now reads back the persisted run detail projection before returning, so the immediate response and `GET /api/runs/{trace_id}` use the same `business_summary` for risk bullets, data gaps, evidence, and notification state.
- [x] 2026-07-08 current pass: the response still preserves stable frontend contract fields such as `plan.plan_id` and `plan.expires_at` while adding the richer persisted parsed-plan fields. Red check caught the missing `plan_id` regression before Playwright could render the result panel.
- [x] 2026-07-08 code-review fix: persisted raw plan fields can no longer overwrite normalized response fields. A raw `parsed_plan.expires_at=null` stays visible only in the persisted diagnostic payload; the POST response keeps the executor-normalized ISO `expires_at`.
- [x] Verification:
  - `python3 -m pytest tests/api/test_runs_routes.py -q` passed.
  - `npm run typecheck` passed.
  - `npm run e2e` passed 4/4.
  - `python3 -m pytest -q` passed.

### Task P0.3: Fix Product/UI Debug Leakage

**Files:**
- Modify: `frontend/src/app/runs/[traceId]/page.tsx`
- Modify: `frontend/src/app/runs/[traceId]/decision-tab.tsx`
- Modify: `frontend/src/app/runs/[traceId]/agent-tab.tsx`
- Modify: `frontend/src/app/runs/[traceId]/raw-tab.tsx`
- Modify: `frontend/src/app/runs/[traceId]/format-helpers.ts`
- Modify: `frontend/src/app/shared/json-details.tsx`
- Modify: `frontend/src/app/runs/page.tsx`
- Test: `frontend/tests/e2e/product-primary-flow.spec.ts`

- [ ] Rename the primary product surfaces:
  - `/manual-run`: "新建提醒".
  - `/runs`: "提醒历史".
  - `/runs/[traceId]`: "提醒详情".

- [ ] Move `Trace ID`, `legacy_prompt`, `fixture/未调用`, `Spans`, raw LLM payload, and hash fields below a "技术信息" or "工程详情" area.

- [ ] Make `matrix` and `raw` debug routes explicit engineering views. Keep direct links for engineers, but do not let them dominate the default run detail navigation.

- [ ] For non-raw product pages, replace object-to-`JSON.stringify` fallback with readable summary or "已记录，见工程详情".

- [ ] `/runs` default columns must prioritize:
  - created time
  - symbol
  - decision label
  - action
  - manual-review status
  - risk/block reason
  - notification status
  - detail link

**Acceptance:**
- Default product pages remain readable without opening Raw.
- Raw JSON is available only from an explicit engineering/debug surface.
- Mobile cockpit first screen contains conclusion, price levels, risk reason, and next action before debug metadata.

**Execution record:**

- [x] 2026-07-08 P0.3 follow-up completed after UI/UX Agent review.
- [x] Default product routes now use product language:
  - `/`: `提醒控制台` with `新建提醒`, `提醒记录`, `质量复盘`, and config shortcuts. The default home no longer exposes `Trace`, `baseline`, `outcome`, or direct diagnostic quick links.
  - `/manual-run`: `新建提醒`, `提醒参数`, `关注点`, `生成提醒建议`, `本次提醒建议`, and `查看详情`.
  - `/runs`: `提醒记录`, `提醒时间`, `建议动作`, `复核结果`, `风险摘要`, `通知`; default list hides `提醒编号`, raw ISO `创建时间`, `Trace`, `Spans`, `LLM`, English `allowed/blocked`, and `columns=all`.
  - `/runs/{trace_id}` default tab is `summary`/`建议摘要`, not `cockpit`; `matrix` and `raw` require explicit `columns=observability`.
- [x] Added frontend product-copy projection for default pages so backend/internal strings such as `fixture`, `LLM`, `provider`, `legacy_prompt`, `decision_input`, `manual_execution_required`, `trace`, `raw`, `baseline`, `outcome`, `blocking`, and `warn` are not directly rendered in the primary product surface.
- [x] Default run detail now shows the product summary and复核状态 first; engineering analysis/rule tables remain in diagnostic views instead of the default summary page.
- [x] Sidebar no longer shows `诊断视图` in the default product context. It appears only after entering an explicit diagnostic context.
- [x] 2026-07-08 multi-agent follow-up: UI/UX review found that default pages were mostly productized but dynamic backend fields could still leak English action/gate terms. Added Playwright negative assertions for action enums and internal payload field names, then productized dynamic `final_action` / `main_action` rendering on the dashboard, manual result, runs list, run detail status bar, and decision summary card.
- [x] Product text projection now maps common backend action and gate phrases such as `trigger long`, `no trade`, `effective_allowed_actions`, `worker contribution`, and `hard block` into Chinese product language on default product surfaces.
- [x] Product text projection now maps execution-fact and fixture phrases such as `index/mark/order_book present but not execution fact source`, `active_event_status: missing`, `BTC structure is not confirming...`, and `Invalid if ETH loses...` into Chinese product language on default product surfaces.
- [x] `/api/runs` list projection now includes `business_summary` and notification status, so the default history page can show action, risk/gaps, and Bark state without opening raw/detail.
- [x] Business route guard: direct `/runs/{trace_id}?tab=raw` no longer opens raw payloads unless `columns=observability` is present. In business mode it stays on `建议摘要` and does not request `include_payloads=true`.
- [x] Playwright `expectBusinessPageNotJson()` asserts product pages render HTML product content, not bare JSON, `<pre>` raw dumps, or visible API envelope markers.
- [x] Local stack smoke now rejects raw JSON/API-envelope frontend pages and requires business anchor text for `/manual-run`, `/runs`, `/eval`, and `/eval?tab=quality`.
- [x] 2026-07-08 current pass: `/eval` itself now defaults to the product-facing `质量指标/金融质量` view; engineering replay/judge tabs remain available only through explicit `?tab=runs`, `?tab=cases`, or `?tab=outcomes` URLs.
- [x] 2026-07-08 current pass: homepage and sidebar "质量复盘" links now point to `/eval?tab=quality`, and the dashboard status bar projects `SHADOW`, storage, and service into product language instead of rendering raw backend values.
- [x] 2026-07-08 current pass: local smoke now requires `/eval` default visible text to include both `质量复盘` and `金融质量`, preventing the default product entry from drifting back to engineering eval tables.
- [x] Added desktop visual regression baselines for:
  - `run-detail-summary-fullpage`
  - `runs-business-fullpage`
- [x] Visual regression assets were renamed from `cockpit-fullpage` to `dashboard-fullpage` and regenerated for desktop/mobile after the intentional product-language change.
- [x] Local smoke frontend assertion now checks visible product summary text and uses the default summary page. It strips Next.js script payloads before negative text checks so framework serialization does not mask real visible-DOM leaks.
- [x] Verification on 2026-07-08:
  - `npm --prefix frontend run typecheck` passed.
  - `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
  - `npm --prefix frontend run e2e` passed 4/4, covering desktop and mobile, screenshots, DOM/visual audit, async manual run, detail, list, diagnostic matrix/raw, eval, and config.
  - `python3 -m pytest tests/local_stack/test_scripts.py -q` passed.
  - `python3 tools/local_stack/smoke_local_stack.py` passed with `smoke_profile=fixture`, `allowed=false`, `manual_execution_required=true`, `auto_order_enabled=false`.
  - `python3 tools/local_stack/smoke_local_stack.py --with-mock-llm` passed with `smoke_profile=mock_real_engine`, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `allowed=false`.
  - `python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging` passed with `smoke_profile=actionable_staging`, `market_provider=okx_public`, `macro_event_provider=no_active_event`, `allowed=true`, `manual_execution_required=true`, `auto_order_enabled=false`.

### Task P0.4: Add Runtime Readiness For Real Providers

**Files:**
- Modify: `src/crypto_manual_alert/api/routes_system.py`
- Modify: `src/crypto_manual_alert/config/models.py`
- Modify: `src/crypto_manual_alert/config/loader.py`
- Modify: `frontend/src/lib/schemas/system.ts`
- Modify: `frontend/src/app/config/page.tsx`
- Test: `tests/api/test_system_routes.py`

- [ ] Add a readiness object for:
  - `decision.engine`
  - `OPENAI_BASE_URL`
  - `OPENAI_MODEL`
  - configured OpenAI key env presence, without exposing key
  - `market_data.provider`
  - `skill_providers.liquidity_order_book`
  - `notification.enabled`
  - Bark device key env presence
  - `trading.auto_order_enabled=false`
  - `trading.manual_execution_required=true`
  - forbidden trade envs are absent
  - macro event provider readiness for `active_event_status`
  - explicit prod-actionable readiness (`real_external_ready + event_ready`)

- [ ] Expose statuses:
  - `fixture_only`
  - `ready`
  - `missing_env`
  - `disabled`
  - `unsafe`

- [x] Display the readiness status in `/config` and in product `mode_notice`.

**Acceptance:**
- A user can tell from the UI why no real LLM content appears.
- A missing LLM key is visible as readiness failure, not discovered only after a blocked run.

**Execution record:**

- [x] `Config.safe_dict()` now exposes `readiness` for decision engine, OpenAI key, market data, order book provider, notification, trading safety, and forbidden envs.
- [x] 2026-07-08 follow-up: readiness now also exposes `event_status` and `prod_actionable`.
  - `event_status.status=ready` only when `macro_event.provider=no_active_event`.
  - Default `macro_event.provider=disabled` is shown as disabled and explains that opening/trigger/flip actions will be blocked for missing `active_event_status`.
  - `prod_actionable.prod_actionable_ready=true` only when real LLM, non-fixture market, Bark, manual-only safety, forbidden-env absence, and event readiness are all satisfied.
- [x] `/config` now leads with `生产提醒就绪检查`, `当前能证明什么`, and `生产提醒缺口`; config keys remain available only as product-language `配置明细`.
- [x] 2026-07-08 `/config` productization red/green:
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed because `/config` still rendered `配置快照`.
  - Green: the same Playwright command passed after replacing the config snapshot with the readiness checklist and product-language details.
- [x] 2026-07-08 review follow-up:
  - Backend readiness now matches the strict prod-actionable gate for unsafe endpoints: localhost/private/non-HTTPS OpenAI endpoints and non-official OKX base URLs make readiness `unsafe`, not production-ready.
  - Backend readiness also rejects `OPENAI_MODEL=mock-*` for prod-actionable semantics.
  - `/config` no longer renders backend readiness diagnostic `message/summary` strings directly; it uses fixed product-language projections so default product UI does not leak `fixture`, `LLM`, `provider`, `execution facts`, `active_event_status`, `MACRO_EVENT_PROVIDER`, or `CANDIDATE_SIDECAR_MODE`.
  - Strict smoke now rejects `OPENAI_MODEL=mock-*` with `skip_reason=unsafe_readiness`; mock model names cannot spoof production success.
  - Red: `python3 -m pytest tests/api/test_system_routes.py::test_config_readiness_rejects_local_endpoints_for_prod_actionable -q` failed while `/api/system/config` marked localhost endpoints as `real_external_ready=true`.
  - Green: `python3 -m pytest tests/api/test_system_routes.py -q` passed after adding unsafe readiness.
  - Red: `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_rejects_mock_model_name -q` failed while strict smoke allowed `mock-crypto-plan`.
  - Green: `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_rejects_mock_model_name tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_rejects_local_mock_endpoints -q` passed after tightening strict smoke.
  - Green: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` passed after tightening `/config` visible-DOM negative assertions.
- [x] Backend readiness test covers the redacted config snapshot.
- [x] Backend readiness test covers a fully configured prod-actionable environment and asserts `prod_actionable.status=ready`.
- [x] Frontend typecheck passed after schema/UI updates.

### Task P0.4b: Show Notification Status In The Product Path

**Files:**
- Modify: `src/crypto_manual_alert/storage/journal.py`
- Modify: `src/crypto_manual_alert/storage/journal_rows.py`
- Modify: `src/crypto_manual_alert/storage/business_summary.py`
- Modify: `src/crypto_manual_alert/api/routes_runs.py`
- Modify: `frontend/src/lib/schemas/manual-run.ts`
- Modify: `frontend/src/app/manual-run/run-form.tsx`
- Modify: `frontend/src/app/runs/[traceId]/decision-summary-card.tsx`
- Test: `tests/api/test_runs_routes.py`

- [x] Expose the latest persisted notification row for a plan in run detail.
- [x] Project `sent`, `failed`, `disabled`, and `not_recorded` into `business_summary.notification`.
- [x] Make `/api/runs/manual` synchronous response reflect the notification row written during the run, when one exists.
- [x] Product UI displays "Bark 已发送", "发送失败", "通知未启用", or "未记录" as a status badge.

**Acceptance:**
- Manual-run result and run detail answer whether Bark was sent.
- Notification failures do not mutate the risk verdict.
- Default fixture path remains honest: "通知未启用；本次只写入运行记录。"

**Execution record:**

- [x] Added regression tests:
  - `test_run_detail_projects_persisted_notification_status`
  - `test_manual_run_response_projects_notification_status`
- [x] Verification:
  - `python3 -m pytest tests/api/test_runs_routes.py -q` passed.
  - `python3 -m pytest tests/api/test_runs_routes.py tests/storage/test_query_repository.py tests/workflow/test_run_persistence_step.py -q` passed.
  - `npm --prefix frontend run typecheck` passed.

### Task P0.4c: Make Query Semantics Honest In The Product UI

**Files:**
- Modify: `frontend/src/lib/schemas/manual-run.ts`
- Modify: `frontend/src/app/manual-run/run-form.tsx`
- Modify: `frontend/tests/e2e/full-stack-visual.spec.ts`

- [x] Rename the UI label from "分析问题" to "关注点/审计备注".
- [x] Explain that current production planning is driven by symbol, horizon, position, and config; the note is retained for trace/audit context and does not switch final input mode.
- [x] Keep the backend `DecisionRequest.query_semantics().mode == "audit_note"` unchanged until a separate P1 design makes query text actually drive intent/facts/final input.
- [x] Update Playwright to fill the new label and assert the honesty copy.

**Acceptance:**
- The UI no longer implies free-form query text drives the final decision.
- Product copy matches the backend contract documented in `DecisionRequest.query_semantics()`.

### Task P0.5: Build A Mock Real-Engine Smoke Path

**Files:**
- Create: `tools/local_stack/mock_openai_server.py`
- Modify: `tools/local_stack/smoke_local_stack.py`
- Modify: `tools/local_stack/start_local_stack.py`
- Test: `tests/local_stack/test_scripts.py`
- Test: `tests/deployment/test_mock_real_engine_smoke.py`

- [x] Add an opt-in mock OpenAI-compatible server that returns strict JSON matching `DecisionPlan`.

- [x] Add a smoke mode that uses:
  - `DECISION_ENGINE=openai_compatible`
  - `OPENAI_BASE_URL=http://127.0.0.1:<mock_port>`
  - `OPENAI_MODEL=<mock-model>`
  - a fake local key
  - `MARKET_DATA_PROVIDER=fixture` or a mocked OKX-compatible provider
  - `NOTIFICATION_ENABLED=false`

- [x] Assert that LLM interactions are recorded and redacted.

- [x] Assert the UI states "mock LLM path" or equivalent, so this cannot be mistaken for real external production proof.

**Acceptance:**
- CI/local can verify the real LLM code path without spending money or requiring external secrets.
- The mock path catches regressions in request shape, telemetry, redaction, and final decision parsing.
- Mock smoke remains blocked when market data is fixture; it proves the LLM path, not H1 actionable delivery.

**Execution record:**

- [x] Added `tools/local_stack/mock_openai_server.py`.
- [x] Added `python3 tools/local_stack/smoke_local_stack.py --with-mock-llm`.
- [x] Added `tools/local_stack/start_local_stack.py --with-mock-llm` and stop-script cleanup for the mock OpenAI port.
- [x] Fixed the OpenAI-compatible client to use `httpx.Client(..., trust_env=False)` so local/mock/internal base URLs are not intercepted by environment proxy settings.
- [x] `business_summary` now distinguishes fixture, mock LLM, LLM-with-fixture-market, and real external modes. Notification disabled no longer masks an LLM-path run as "未调用真实 LLM".
- [x] Run detail rebuilds `business_summary` from persisted LLM interaction rows, so `/api/runs/{trace_id}` preserves mock LLM mode even without runtime config.
- [x] Mock smoke verifies:
  - `DECISION_ENGINE=openai_compatible`.
  - `OPENAI_BASE_URL=http://127.0.0.1:8011`.
  - `OPENAI_MODEL=mock-crypto-plan`.
  - fake local key only.
  - `MARKET_DATA_PROVIDER=fixture`.
  - `NOTIFICATION_ENABLED=false`.
  - default detail includes LLM interaction summary but not `request_json`/`response_json`.
  - `include_payloads=true` returns payload fields without leaking `local-mock-openai-key` or `Bearer`.
  - run detail `business_summary.mode_notice` visibly contains `mock LLM`.
- [x] Verification on 2026-07-08 10:42 CST:
  - `python3 -m pytest tests/api/test_runs_routes.py tests/local_stack/test_scripts.py tests/storage/test_business_summary.py tests/skills/test_openai_compatible.py -q` passed.
  - `python3 tools/local_stack/smoke_local_stack.py --with-mock-llm` passed and returned `smoke_profile=mock_real_engine`, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `market_provider=fixture`, `allowed=false`.
- [x] 2026-07-08 continuation: added browser-level mock LLM product rendering proof.
  - Playwright can now pass local-stack flags via `PLAYWRIGHT_LOCAL_STACK_FLAGS`.
  - `PLAYWRIGHT_EXPECT_MOCK_LLM=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm --seed-mock-outcome" npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` passed.
  - This verifies the mock OpenAI-compatible response reaches the React product surface as `模型链路演练` with model-derived price levels (`3,510`, `3,435`) and no raw request/response payload leakage.

**2026-07-08 10:45 CST regression record:**

- [x] `npm --prefix frontend run typecheck` passed.
- [x] `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
- [x] `npm --prefix frontend run e2e` passed 4/4 after rerunning sequentially. A prior attempt failed because Playwright and `smoke_local_stack.py` were started in parallel and fought over ports `8010/3001`; that was an invalid test orchestration, not a product regression.
- [x] `python3 tools/local_stack/smoke_local_stack.py` passed and returned `smoke_profile=fixture`, `decision_engine=fixture`, `market_provider=fixture`, `allowed=false`.
- [x] `python3 -m pytest -q` passed. A prior full-suite run observed one `tests/agent_swarm/test_shadow_orchestration.py` ordering failure; the specific test, the file, and a fresh full-suite rerun all passed, so it is not currently reproducible. Keep this noted if it recurs.

### Task P0.6: Prove The H1 Actionable Path

**Files:**
- Inspect and modify as needed:
  - `src/crypto_manual_alert/decision/decision_input.py`
  - `src/crypto_manual_alert/decision/gate_candidate.py`
  - `src/crypto_manual_alert/decision/production_control_gate.py`
  - `src/crypto_manual_alert/workflow/decision_control_step.py`
  - `src/crypto_manual_alert/workflow/persistence_payload.py`
  - `src/crypto_manual_alert/storage/agent_audit_view.py`
- Test:
  - `tests/workflow/test_execution_fact_unblock.py`
  - `tests/api/test_runs_routes.py`
  - `tests/local_stack/test_scripts.py`

- [x] Preserve safe defaults: fixture/default remains blocked or clearly demo-only.

- [x] Treat `docs/migration/2026-07-06-checkpoint-execution-fact-unblock.md` and `config/staging.yaml` as the current implementation baseline, not as work to redo.

- [x] Define the exact conditions under which a trigger/open action may enter manual review:
  - exchange-native mark ref present
  - exchange-native index ref present
  - exchange-native order book ref present
  - symbol consistency passed
  - manual execution required
  - auto order disabled
  - no forbidden envs
  - macro/event hard-block status not unsafe

- [x] Add tests showing:
  - missing exchange-native refs blocks opening actions
  - search-derived refs cannot satisfy execution facts
  - valid exchange-native refs can unblock manual-review eligibility
  - allowed still means manual review only, not order placement

- [x] Add a local/staging smoke profile using `config/default.yaml + config/staging.yaml` semantics to prove the already implemented exchange-native execution facts can reach the manual-review eligibility path.

- [x] Add a prod/actionable smoke that either:
  - runs with real OKX public data and Bark when env is explicitly configured, or
  - fails/skips with a visible readiness reason when env is missing.

**Acceptance:**
- The system can produce a safe `allowed=True` manual-review result in a controlled actionable test.
- The system still blocks unsafe or fixture-only opening plans.
- The plan no longer spends P0 time re-solving H1 internals that migration already implemented; it proves the main flow profile.

**Execution record:**

- [x] Added API-level H1 proof in `tests/api/test_runs_routes.py::test_manual_run_staging_actionable_path_allows_manual_review_without_auto_order`.
  - Path exercised: `POST /api/runs/manual -> RunExecutor -> LegacyPlanRunnerAdapter/PlanRunner -> journal -> /api/runs/{trace_id}`.
  - Assertions: `verdict.allowed=True`, `business_summary.decision_label=可人工复核`, `production_control_gate.allowed=True`, `facts_gate.missing_execution_facts=[]`, `facts_gate.missing_event_facts=[]`, `manual_execution_required=True`, `auto_order_enabled=False`.
- [x] Fixed product projection so an allowed staging/actionable result is no longer mislabeled as `本地样本`.
  - `business_summary` now distinguishes `actionable_manual_review` from default fixture/demo and mock LLM modes.
  - Default fixture blocked regression remains covered by `test_manual_run_creates_trace_and_returns_plan_summary`.
- [x] Added `tools/local_stack/mock_okx_server.py` and `python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging`.
  - This starts a local OKX public mock at `127.0.0.1:8012`, points `MARKET_DATA_OKX_BASE_URL` at it, sets `MARKET_DATA_PROVIDER=okx_public`, and sets `MACRO_EVENT_PROVIDER=no_active_event`.
  - This is a controlled local/staging proof, not a real external OKX/Bark/LLM production proof.
- [x] Fixed `OkxPublicMarketDataProvider` to use `httpx.Client(..., trust_env=False)`.
  - Root cause found during smoke: `httpx.Client(trust_env=True)` returned `502` for `http://127.0.0.1:8012/api/v5/public/mark-price`, while `trust_env=False` returned `200`. The environment proxy was intercepting local mock OKX calls.
  - Regression test: `tests/workflow/test_execution_fact_unblock.py::test_okx_public_provider_disables_environment_proxy_for_default_client`.
- [x] Verification on 2026-07-08:
  - `python3 -m pytest tests/workflow/test_execution_fact_unblock.py tests/api/test_runs_routes.py::test_manual_run_staging_actionable_path_allows_manual_review_without_auto_order tests/local_stack/test_scripts.py::test_local_smoke_api_env_enables_actionable_staging_with_local_okx_mock -q` passed.
  - `python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging` passed and returned:
    - `smoke_profile=actionable_staging`
    - `allowed=true`
    - `decision_engine=fixture`
    - `market_provider=okx_public`
    - `macro_event_provider=no_active_event`
    - `manual_execution_required=true`
    - `auto_order_enabled=false`
    - `mock_okx=http://127.0.0.1:8012`
- [ ] Remaining P0/P1 boundary: a real external prod/actionable smoke with actual OKX public network and Bark still requires explicit environment readiness and should not be claimed from the local mock proof.
- [x] Added `python3 tools/local_stack/smoke_local_stack.py --prod-actionable`.
  - This mode is separate from `--with-actionable-staging`; it does not start local OKX or OpenAI mocks.
  - It requires `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY` or configured key env, and the currently implemented `MACRO_EVENT_PROVIDER=no_active_event` operator assertion.
  - When readiness is missing, it exits successfully with structured JSON `ok=false`, `smoke_profile=prod_actionable`, `skip_reason=missing_readiness`, and a `missing` list.
  - When readiness is present, it forces `NOTIFICATION_ENABLED=true`, `DECISION_ENGINE=openai_compatible`, and `MARKET_DATA_PROVIDER=okx_public`; it then expects a real LLM interaction, real market evidence, Bark notification, and `allowed=true` manual-review result.
- [x] Added release-gate strict mode: `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`.
  - Default `--prod-actionable` still returns exit code `0` for structured readiness skips so local no-secret environments can report missing readiness without looking like infrastructure failure.
  - `--fail-on-skip` returns non-zero when readiness is missing and adds `exit_semantics=fail_on_skip`, so CI/release gates cannot accidentally treat skip as production success.
- [x] Verification on 2026-07-08:
  - `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_reports_missing_readiness tests/local_stack/test_scripts.py::test_local_smoke_api_env_enables_prod_actionable_when_ready tests/local_stack/test_scripts.py::test_local_smoke_profile_names_prod_actionable -q` passed.
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable` returned structured skip:
    - `ok=false`
    - `smoke_profile=prod_actionable`
    - `skip_reason=missing_readiness`
    - missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and event provider readiness.
  - `python3 -m pytest tests/local_stack/test_scripts.py -q` passed.
  - Sequential `python3 tools/local_stack/smoke_local_stack.py`, `--with-mock-llm`, and `--with-actionable-staging` passed.
- [x] README and deployment runbook now distinguish fixture, mock LLM, actionable staging, prod-actionable readiness skip, and prod-actionable release success.
  - `docs/deployment.md` now states that Docker/healthcheck success is not production alert success.
  - `docs/deployment.md` now removes the stale `formal/34` direction pointer and points current delivery back to `formal/37` plus explicit release review for any future Swarm/candidate switch.
- [x] 2026-07-08 verification after strict-mode/runbook update:
  - `python3 -m pytest tests/local_stack/test_scripts.py tests/deployment/test_container_config_commands.py -q` passed.
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable` returned `ok=false`, `skip_reason=missing_readiness`, `exit_semantics=skip_exit_0`, and exit code `0`.
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` returned the same missing readiness list with `exit_semantics=fail_on_skip` and exit code `2`.
  - `python3 -m pytest -q` passed after updating the stale formal-doc structure guard from `formal/34` to `formal/37` and removing a nondeterministic ordering assertion from a parallel shadow-worker test.
  - Sequential `python3 tools/local_stack/smoke_local_stack.py`, `--with-mock-llm`, and `--with-actionable-staging` passed again.
  - `npm --prefix frontend run typecheck` passed.
  - `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
  - `npm --prefix frontend run e2e` passed 4/4.
  - `git diff --check` passed.
- [x] 2026-07-08 multi-agent follow-up: Architecture/QA review found that `--prod-actionable` enabled notification but only asserted Bark delivery when `--with-bark` was passed. Added a regression test and changed prod-actionable success to always call `_assert_notification_sent(trace_id)`, output `notification_enabled=true`, and include `notification.status="sent"` in the machine-readable success payload.
- [x] 2026-07-08 multi-agent follow-up: Architecture review found readiness accepted future macro event provider names that the config loader does not support. The release gate now accepts only the implemented `MACRO_EVENT_PROVIDER=no_active_event` operator assertion; `operator_assertion` / `event_pool` remain future work until implemented in config, provider code, and tests.
- [x] Verification for the follow-up fixes:
  - Red check: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed before the UI fix because the result panel exposed `trigger long`, `effective_allowed_actions`, and `worker contribution` text.
  - Green check: the same Playwright command passed after productizing dynamic fields.
  - Red check: `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_requires_bark_delivery_assertion -q` failed before the smoke fix because prod-actionable did not call the Bark assertion.
  - Green check: `python3 -m pytest tests/local_stack/test_scripts.py -q` passed after requiring Bark delivery and tightening event readiness.
- [x] 2026-07-08 final verification for this follow-up:
  - `npm --prefix frontend run typecheck` passed.
  - `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
  - `npm --prefix frontend run e2e` passed 4/4 across desktop and mobile.
  - `python3 -m pytest -q` passed with 2 warnings.
  - `python3 tools/local_stack/smoke_local_stack.py` passed with `smoke_profile=fixture`, `allowed=false`, `notification_enabled=false`.
  - `python3 tools/local_stack/smoke_local_stack.py --with-mock-llm` passed with `smoke_profile=mock_real_engine`, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `allowed=false`.
  - `python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging` passed with `smoke_profile=actionable_staging`, `market_provider=okx_public`, `macro_event_provider=no_active_event`, `allowed=true`, `manual_execution_required=true`, `auto_order_enabled=false`.
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable` returned structured skip with missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`; this is not production success.
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` returned the same readiness skip with `exit_semantics=fail_on_skip` and exit code `2`.
  - `git diff --check` passed.
  - `lsof -ti tcp:8010 -ti tcp:3001 -ti tcp:8011 -ti tcp:8012 || true` returned no listeners.
- [x] 2026-07-08 final verification after product error/empty-state copy cleanup:
  - `npm --prefix frontend run typecheck` passed.
  - `npm --prefix frontend run e2e` passed 4/4 across desktop and mobile, using the production frontend build and local API stack.
  - `python3 -m pytest -q` passed with 2 warnings.
  - `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
  - `git diff --check` passed.
  - `python3 tools/local_stack/smoke_local_stack.py` passed with `smoke_profile=fixture`, `allowed=false`, `decision_engine=fixture`, `market_provider=fixture`, `macro_event_provider=disabled`, and no notification.
  - `python3 tools/local_stack/smoke_local_stack.py --with-mock-llm` passed with `smoke_profile=mock_real_engine`, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `market_provider=fixture`, and `allowed=false`.
  - `python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging` passed with `smoke_profile=actionable_staging`, `market_provider=okx_public`, `macro_event_provider=no_active_event`, `allowed=true`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` returned `ok=false`, `skip_reason=missing_readiness`, missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`, with `exit_semantics=fail_on_skip` and exit code `2`; this is an honest release-gate block, not production success.
- [x] 2026-07-08 final multi-agent review cleanup:
  - Sidebar diagnostic navigation is now only shown when `columns=observability`; direct product URLs such as `/runs/:traceId?tab=raw` stay in the business summary context.
  - Default product error states no longer mention backend logs.
  - Playwright now asserts direct `?tab=raw` without observability mode does not reveal the diagnostic sidebar entry.
  - `npm --prefix frontend run typecheck` passed.
  - `npm --prefix frontend run e2e` passed 4/4 across desktop and mobile.
- [x] 2026-07-08 final release-gate hardening:
  - `--prod-actionable` now rejects unsafe local/private endpoints before starting the stack. `OPENAI_BASE_URL=http://127.0.0.1:8011` or `MARKET_DATA_OKX_BASE_URL=http://127.0.0.1:8012` returns `skip_reason=unsafe_readiness` with exit code `2` under `--fail-on-skip`.
  - Readiness now requires `candidate_sidecar_mode=disabled`, so prod-actionable cannot silently reuse the production decision engine for candidate sidecar calls.
  - `market_data.provider` is config-validated; unsupported provider names cannot look ready and fail later at provider construction.
- [ ] Remaining P0/P1 boundary: a successful real external prod/actionable run has not been executed on this machine because required external environment variables/readiness are absent. The structured skip is an honest gate, not a production success proof.

### Task P0.7: Make Production Local Stack Scripts Honest

**Files:**
- Modify: `tools/local_stack/start_local_stack.py`
- Modify: `tools/local_stack/smoke_local_stack.py`
- Modify: `frontend/playwright.config.ts`
- Test: `tests/local_stack/test_scripts.py`

- [x] If `--frontend-mode production` is used, run a fresh production build explicitly before `next start`.

- [x] Ensure production build always receives `NEXT_PUBLIC_API_BASE_URL`.

- [x] Add a clear output field that says:
  - frontend mode: dev or production
  - API base embedded in frontend
  - notification enabled
  - real LLM enabled
  - real market enabled
  - actionable staging enabled
  - market provider
  - macro event provider
  - manual execution required
  - auto order enabled

**Acceptance:**
- A developer cannot accidentally start a broken production frontend because `.next` is missing or was built without API base.

**Execution record:**

- [x] 2026-07-08 follow-up: `python3 tools/local_stack/start_local_stack.py --frontend-mode production --reset-data --keep-running` initially failed waiting for the frontend. Root cause was a stale/dev `.next` directory without `.next/BUILD_ID`; `next start` then reported "Could not find a production build".
- [x] `start_local_stack.py` production mode now always runs `npm run build` with `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010` before `next start`, even if `.next/BUILD_ID` already exists. This prevents stale builds from being mistaken for a valid production local stack.
- [x] Updated regression tests:
  - production mode rebuilds even when `BUILD_ID` exists;
  - production mode starts with `next start` after the fresh build.
- [x] 2026-07-08 continuation: tightened `start_local_stack.py` PID/output JSON so it reports `frontend_mode`, `frontend_api_base_url`, `api_base_embedded_in_frontend`, notification/mock LLM/real LLM/real market/actionable-staging booleans, `market_provider`, `macro_event_provider`, and manual-only safety fields.
- [x] Red check: `python3 -m pytest tests/local_stack/test_scripts.py::test_start_local_stack_can_seed_mock_eval_outcome -q` failed because `start_local_stack.py` did not fetch `/api/system/config` and did not emit the production-readiness output fields.
- [x] Green check: the same focused test passed after fetching the config snapshot and writing the explicit startup contract to `data/dev-server/pids.json`.
- [x] Verification:
  - `python3 -m pytest tests/local_stack/test_scripts.py -q` passed.
  - `npm --prefix frontend run e2e` passed 4/4 after stopping the previously running local stack.
  - `python3 -m pytest -q` passed with 2 warnings.
  - 2026-07-08 final check: `python3 -m pytest tests/local_stack/test_scripts.py -q` passed after the always-rebuild contract and mock-outcome quality-page assertions were tightened.

### Task P0.8: Root-Cause And Fix Playwright Mobile React `#418`

**Files:**
- Inspect:
  - `frontend/test-results/**/trace.zip`
  - `frontend/test-results/**/error-context.md`
  - `frontend/src/app/layout.tsx`
  - `frontend/src/app/shared/sidebar.tsx`
  - `frontend/src/app/config/page.tsx`
  - `frontend/src/app/manual-run/run-form.tsx`
- Modify as needed:
  - exact file depends on root cause
  - `frontend/playwright.config.ts` only if the cause is shared-state concurrency, not as a way to hide a product bug

- [x] Reproduce with production build and mobile viewport.

- [x] Identify whether the cause is:
  - SSR/CSR text mismatch
  - mobile-only DOM branch
  - shared backend state between Playwright projects
  - concurrent tests mutating the same local stack data
  - stale production build

- [x] Fix root cause, then run `cd frontend && npm run e2e`.

**Acceptance:**
- `npm run e2e` passes without ignoring page errors.
- If concurrency is the cause, tests must isolate data or run serially for the shared-stack scenario with an explanation in the test file.

**Execution record:**

- [x] Reproduced the default failure with Playwright's shared webServer and 2 workers.
- [x] Verified the mobile core-page audit alone is stable: `npm run e2e -- --project=chromium-mobile -g "core pages stay usable" --repeat-each=3` passed 3/3.
- [x] Verified full suite stability under serial execution: `npm run e2e -- --workers=1` passed 4/4.
- [x] Fixed the shared-stack suite by setting `workers: 1` in `frontend/playwright.config.ts`; this does not ignore page errors.
- [x] Verified default command after the fix: `npm run e2e` passed 4/4.
- [x] 2026-07-08 second root-cause follow-up: a later full-suite run still produced React production hydration `#418` after navigating through `?tab=raw&columns=observability`.
  - Root cause: `Sidebar` was reading `useSearchParams()` during hydration to decide whether the diagnostic nav item existed and which `/runs` item was active. URL-dependent nav visibility could mismatch between SSR and CSR in the shared production-stack sequence.
  - Fix: `frontend/src/app/shared/sidebar.tsx` now waits until client hydration before consuming `columns/tab` search params or showing diagnostic-only navigation.
  - Verification: `npm --prefix frontend run e2e -- --project=chromium-mobile -g "manual run async flow"` passed, then default `npm --prefix frontend run e2e` passed 4/4.

---

## 4. P1 Product And Backend Convergence

### Task P1.1: Decide Whether Query Text Should Drive Decisions

**Files:**
- Modify one of:
  - `src/crypto_manual_alert/context/request.py`
  - `src/crypto_manual_alert/workflow/legacy_decision_workflow.py`
  - `frontend/src/app/manual-run/run-form.tsx`

- [x] Minimum honesty path completed in P0.4c: UI copy now calls the field "关注点/审计备注" and states that current planning is driven by symbol/horizon/position/config.

- [x] Choose the current delivery behavior:
  - Option A: make `query_text` actually influence intent, required facts, final input, and summary.
  - Option B: keep it as audit context and preserve the current product wording.

**Decision:** Current delivery stays on Option B. `query_text` remains an audit/review note and must not be presented as driving the final plan. Option A remains the recommended future product direction, but it needs a separate design for intent parsing, required-facts expansion, final-input construction, and release gates before it can become production behavior.

**Execution record:**

- [x] 2026-07-08 continuation: Playwright red check caught that `/manual-run` still said the关注点 would "帮助生成更贴近当前仓位的提醒", which contradicted backend `query_semantics.mode=audit_note`.
- [x] Updated the manual-run form copy to state that关注点 is recorded as a review note and current planning remains driven by symbol, horizon, position, and config.

### Task P1.2: Split Decision Control Responsibilities

**Files:**
- Modify:
  - `src/crypto_manual_alert/workflow/decision_control_step.py`
- Create as needed:
  - `src/crypto_manual_alert/workflow/candidate_sidecar_step.py`
  - `src/crypto_manual_alert/workflow/risk_merge_policy.py`

- [x] Split sidecar final decision, candidate audit, production gate, and risk merge into focused functions/classes.

- [x] Add tests around each split boundary before moving behavior.

**Acceptance:**
- Candidate sidecar can be disabled/configured independently from production final LLM.
- Tests prove production final behavior does not change unintentionally.

**Execution record:**

- [x] 2026-07-08 continuation: kept the split intentionally narrow so it improves maintainability without changing the manual-alert release gate.
  - Added `src/crypto_manual_alert/workflow/candidate_sidecar_step.py` to own candidate-final sidecar gating and execution.
  - Added `src/crypto_manual_alert/workflow/risk_merge_policy.py` to own deterministic verdict merging.
  - `src/crypto_manual_alert/workflow/decision_control_step.py` now coordinates candidate audit, production control, symbol consistency, and risk merge without directly running the sidecar gate.
  - `src/crypto_manual_alert/decision/production_control_gate.py` now only owns production-control promotion rules, not generic risk merging.
- [x] TDD evidence:
  - Red check: `python3 -m pytest tests/workflow/test_candidate_sidecar_step.py tests/workflow/test_risk_merge_policy.py -q` failed because the new workflow boundary modules did not exist.
  - Green check: `python3 -m pytest tests/workflow/test_candidate_sidecar_step.py tests/workflow/test_risk_merge_policy.py tests/workflow/test_decision_control_step.py tests/decision/test_production_control_gate.py -q` passed after the split.
  - Structure check: `python3 -m pytest tests/structure/test_tests_layout.py tests/structure/test_formal_docs_current_state.py tests/workflow/test_workflow_package_structure.py tests/decision/test_decision_package_structure.py -q` passed.
- [x] Invariants preserved: candidate sidecar remains `decision_effect=none` and `production_final_input=false`; production final input remains `legacy_prompt`; no auto-order path was added.
- [x] 2026-07-08 Architecture Agent follow-up completed:
  - Added `decision.candidate_sidecar_mode` with `same_engine` and `disabled`.
  - Added `CANDIDATE_SIDECAR_MODE` env override and config validation.
  - `config/prod.yaml` and prod-actionable smoke now disable candidate sidecar.
  - `LegacyDecisionWorkflow` resolves the candidate sidecar engine from config instead of always reusing the production final engine.
  - Red check: focused config/staging test failed before the field/resolver existed.
  - Green check: `python3 -m pytest tests/config/test_config.py::test_default_config_disables_auto_ordering tests/config/test_config.py::test_prod_config_uses_real_public_market_data_provider tests/config/test_config.py::test_candidate_sidecar_mode_can_be_disabled_by_environment tests/config/test_config.py::test_config_rejects_unknown_candidate_sidecar_mode tests/workflow/test_execution_fact_unblock.py::test_staging_actionable_can_disable_candidate_sidecar_without_changing_final_verdict -q` passed.
  - Green check: `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_api_env_enables_prod_actionable_when_ready tests/config/test_config.py::test_prod_config_uses_real_public_market_data_provider tests/workflow/test_execution_fact_unblock.py::test_staging_actionable_can_disable_candidate_sidecar_without_changing_final_verdict -q` passed.

### Task P1.3: Continuous Outcome Collection Runbook

**Files:**
- Modify: `docs/deployment.md`
- Modify: `src/crypto_manual_alert/cli/main.py` if needed
- Test: `tests/cli/test_runner_cli.py`

- [x] Write an ops runbook for `collect-outcomes`.

- [x] Define maturity horizon, candle source, skipped reasons, and where results appear in eval.

- [ ] Collect at least one real exchange-native outcome before calling financial quality non-empty.

- [x] Add an explicitly mocked local outcome visibility proof that is not counted as real financial quality.

**Execution record:**

- [x] Added `--seed-mock-outcome` to `tools/local_stack/start_local_stack.py` for local visual/e2e stacks.
  - It writes one `DecisionOutcome` to the eval sidecar OutcomeStore at `data/eval/crypto-outcomes.db`.
  - It does not write the production journal, notifications, traces, trace spans, LLM interactions, or manual outcomes.
  - The sample uses `decision_ref=mocked-outcome-seed`, `source_type=mocked_outcome`, `can_score=false`, and `unscored_reason=price_source_not_exchange_native`.
- [x] Playwright local stack now seeds this mocked outcome and asserts the Eval Quality page shows product copy such as `样本 1`, `本地展示样本`, `价格不是交易所原生样本`, and `不可评分`, while internal IDs/enums such as `mocked-outcome-seed`, `mocked_outcome`, `price_source_not_exchange_native`, and `legacy_final` remain absent from the product page.
- [x] Python smoke can also run `--seed-mock-outcome`; it uses an isolated `.tmp/smoke/data` API `DATA_DIR`, asserts `/api/eval/outcomes`, asserts `/eval?tab=quality` visible text, requires the "本地展示样本 / 价格不是交易所原生样本 / 不可评分" explanation, and outputs `mock_outcome_quality_scope=visibility_only_not_financial_quality`.
- [x] Python smoke can now run `--collect-outcomes-fixture`; it uses an isolated `.tmp/smoke/data` API `DATA_DIR`, starts local mock OKX with `/api/v5/market/history-candles`, seeds a matured eligible journal trace, runs the real `collect-outcomes` CLI, asserts `/api/eval/outcomes`, asserts `/eval?tab=quality` visible text, and outputs `outcome_collection_profile=local_mock_okx_collector_wiring_only`, `collected_exchange_native_outcomes=3`, and `real_financial_quality_proven=false`.
- [x] `docs/deployment.md` now documents the real `collect-outcomes` runbook, the Playwright/local-stack mock seed, the Python smoke mock seed, and the mocked outcome visibility-only boundary.
- [x] Verification:
  - Red check: `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_seed_mock_eval_outcome_writes_eval_sidecar_only tests/local_stack/test_scripts.py::test_start_local_stack_can_seed_mock_eval_outcome -q` failed before the helper/flag existed.
  - Red check: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed before `--seed-mock-outcome` existed.
  - Red check: after the first seed helper, the local-stack test failed because the mocked sample was incorrectly marked `source_type=exchange_native`; this caught the risk that a mock could be mistaken for real financial quality.
  - Green check: `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_seed_mock_eval_outcome_writes_eval_sidecar_only tests/local_stack/test_scripts.py::test_start_local_stack_can_seed_mock_eval_outcome -q` passed after changing the source to `mocked_outcome` and keeping it unscored.
  - Red check: `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_api_env_uses_explicit_data_dir_when_provided tests/local_stack/test_scripts.py::test_local_smoke_assert_eval_quality_outcome_visible_requires_mocked_outcome tests/local_stack/test_scripts.py::test_local_smoke_seed_mock_outcome_flag_runs_quality_assertions_and_reports_scope -q` failed before the smoke `DATA_DIR`, API/HTML outcome assertion, and `--seed-mock-outcome` output fields existed.
  - Green check: the same focused smoke tests passed after adding explicit API data-dir wiring, `/api/eval/outcomes` contract checks, Eval Quality visible-text checks, and the visibility-only output metadata.
  - Green check: `python3 tools/local_stack/smoke_local_stack.py --seed-mock-outcome` passed, started the real local API/frontend, seeded `mocked-outcome-seed`, rendered it through `/eval?tab=quality`, and output `mock_outcome_quality_scope=visibility_only_not_financial_quality`.
  - Green check: `npm --prefix frontend run typecheck` passed.
  - Green check: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` passed and rendered the explicit mocked outcome sample.
  - Green check: `npm --prefix frontend run e2e` passed after tightening the Quality panel DOM assertions to require no `.error-state`, no outcome-table empty state, `1（可评分 0 / 待成熟 0 / 不可评分 1）`, and a mobile table-scroll check that can reveal the `price_source_not_exchange_native` explanation on small viewports.
  - 2026-07-08 UI/QA review caught that the prior wording incorrectly classified a matured mocked outcome as "待成熟". Fixed the UI to split `可评分 / 待成熟 / 不可评分`, keeping `price_source_not_exchange_native` visible as the reason a mock sample is not real financial quality.
  - 2026-07-08 final UI/QA/code-review follow-up caught that keeping `price_source_not_exchange_native` visible in the product page still leaked a raw implementation token. The API and seed still retain `source_type=mocked_outcome` and `unscored_reason=price_source_not_exchange_native`, but the frontend now renders `本地展示样本` and `价格不是交易所原生样本` and rejects raw outcome codes.
  - Red check: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed with `mystery_target`, `mystery_action`, and `mystery_source` visible before safe fallback mapping.
  - Green check: the same command passed after safe fallback mapping and after aligning the unknown-outcome fixture with the backend rule that non-exchange-native sources map to `price_source_not_exchange_native`.
  - Red check: `python3 tools/local_stack/smoke_local_stack.py --seed-mock-outcome` failed after UI productization because the smoke still expected raw `mocked_outcome` text in the frontend.
  - Green check: `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_assert_eval_quality_outcome_visible_requires_mocked_outcome tests/local_stack/test_scripts.py::test_local_smoke_rejects_mock_outcome_without_unscored_product_explanation tests/local_stack/test_scripts.py::test_local_smoke_rejects_quality_page_internal_outcome_codes -q` passed after splitting API raw-field assertions from frontend product-copy assertions.
  - Green check: `python3 tools/local_stack/smoke_local_stack.py --seed-mock-outcome` passed again with `mock_outcome_quality_scope=visibility_only_not_financial_quality`.
  - 2026-07-08 Playwright now seeds a latest eval run with `swarm_candidate_final`, `no_trade`, and `baseline_reference` target gates to prove the default quality page renders them as `候选建议链路`, `不操作基线`, and `基线参考` instead of leaking raw engineering tokens.
  - 2026-07-08 red/green checks:
    - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed while the UI still said `待成熟 1`.
    - Green: the same command passed after the `不可评分` split and target/status productization.
    - Red: `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_rejects_mock_outcome_without_unscored_product_explanation -q` failed before smoke required the product explanation.
    - Green: `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_assert_eval_quality_outcome_visible_requires_mocked_outcome tests/local_stack/test_scripts.py::test_local_smoke_rejects_mock_outcome_without_unscored_product_explanation -q` passed.
  - Red check: `python3 -m pytest tests/local_stack/test_scripts.py::test_mock_okx_server_returns_exchange_native_public_payloads -q` failed while local mock OKX returned `404` for `/api/v5/market/history-candles`.
  - Red check: `python3 -m pytest tests/eval/test_outcome_collector.py::test_collect_fetches_exchange_native_window_from_local_mock_okx_http -q` failed while `OutcomeCollector` could not fetch history candles from local mock OKX.
  - Green check: both tests passed after adding deterministic OKX history candle rows and collector HTTP coverage.
  - Green check: `python3 -m pytest tests/cli/test_runner_cli.py::test_cli_collect_outcomes_reads_history_candles_from_local_mock_okx_http -q` passed, proving the real CLI can collect from local mock OKX into eval sidecar without mutating production journal tables.
  - Red check: `python3 tools/local_stack/smoke_local_stack.py --collect-outcomes-fixture` first failed with `collected=0, skipped=40` because stale `.tmp/smoke/data` traces polluted the collector limit window.
  - Green check: `python3 tools/local_stack/smoke_local_stack.py --collect-outcomes-fixture` passed after seeded smoke profiles reset their isolated data dir; output included `smoke_profile=collect_outcomes_fixture`, `collected_exchange_native_outcomes=3`, and `real_financial_quality_proven=false`.
  - Honest blocker check: `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` still exits `2` with missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`.

### Task P1.4: Notification History And Operations View

The P0 product path now shows the latest notification status. P1 work should add a richer history/operator view if needed.

- [x] Expose full notification history for a run detail, not only the latest row.
- [x] Keep list/manual-run responses latest-only so the business history page stays compact.
- [x] Add channel/status/status-code/error fields to the run-detail schema; provider expansion beyond Bark remains conditional on adding a second notification provider.
- [x] Render a product-facing `通知历史` section in `/runs/[traceId]` summary mode with no raw JSON, no `<pre>`, and no `plan_id`/secret/payload leakage.
- [x] Add deployment runbook steps for real Bark smoke and failure triage.

**Execution record:**

- [x] Backend detail now returns `notification_history` ordered newest-first from persisted notification rows.
- [x] `notification_row()` uses an allowlist projection and redacts URLs/token-like fields from errors before API exposure.
- [x] Multi-agent backend review found the redaction layer needed broader hardening for Bearer headers, JSON token/api_key fields, `BARK_DEVICE_KEY:` forms, and free-text device-key phrases; added an API regression test and tightened projection-layer redaction.
- [x] Frontend `runDetailSchema` parses `notification` and `notification_history`, and the summary page renders a vertical notification history list.
- [x] Empty history explicitly shows `暂无通知记录` and `通知未启用`; sent/failed history displays `Bark 已发送` or `发送失败` plus productized `服务响应 <code>` and `失败原因`.
- [x] Playwright product-page negative assertions now include `notification_history`, `status_code`, `device_key`, `bark_device_key`, and `BARK_DEVICE_KEY` so raw notification internals cannot leak into the business surface.
- [x] Multi-agent frontend/QA review found that the top status bar could display notification failure detail and that failure-history coverage only exercised the empty state. The top bar now shows only short status labels, failure details are categorized into safe Chinese reasons, and Playwright seeds sent/failed notification rows into the real local-stack journal to verify success/failure rendering and raw-field non-leakage.
- [x] Verification:
  - Red check: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed because the `/runs/[traceId]` summary page had no `通知历史` section.
  - Green check: `npm --prefix frontend run typecheck` passed after adding the schema and component.
  - Green check: `python3 -m pytest tests/api/test_runs_routes.py::test_run_detail_exposes_full_notification_history_without_payload_leak tests/api/test_runs_routes.py::test_run_detail_notification_history_is_empty_without_notification_rows -q` passed.
  - Red check: `python3 -m pytest tests/api/test_runs_routes.py::test_run_detail_redacts_notification_error_secret_shapes -q` failed before broad notification-error secret redaction.
  - Green check: `python3 -m pytest tests/api/test_runs_routes.py::test_run_detail_redacts_notification_error_secret_shapes tests/api/test_runs_routes.py::test_run_detail_exposes_full_notification_history_without_payload_leak -q` passed after redaction hardening.
  - Green check: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` passed after wiring the history section into the real full-stack page.
  - Red check: frontend/QA review identified untested seeded failure history and a possible top-status failure-message leak.
  - Green check: `npm --prefix frontend run typecheck` passed after making the top status latest-state-only and adding the Playwright notification-history seed helper.
  - Green check: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` passed after verifying `Bark 已发送`, `发送失败`, `服务响应 200`, `服务响应 500`, `失败原因：Bark 发送超时`, no `<pre>`, and no `secret`/`BARK_DEVICE_KEY`/`device_key`/`plan_id`/`status_code`/`notification_history`/Bark URL/raw text in the seeded history section.

---

## 5. P2 Deferred Work

These are useful but not allowed to block P0 delivery:

- [ ] Langfuse exporter.
- [ ] DeepEval runner.
- [ ] Harness policy YAML externalization.
- [ ] Candidate sidecar release-review UI.
- [ ] Long-term memory and automatic lesson retrieval.
- [ ] Large structural cleanup that does not directly improve the manual alert loop.

---

## 6. Definition Of Done For Delivery Candidate

The project is not production-deliverable until every item below is true:

- [x] `python3 -m pytest -q` passes.
- [x] `cd frontend && npm run typecheck` passes.
- [x] `cd frontend && NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm run build` passes.
- [x] `cd frontend && npm run e2e` passes with desktop and mobile projects, no ignored page errors.
- [x] `python3 tools/local_stack/smoke_local_stack.py` passes and is explicitly labeled fixture smoke.
- [x] Mock real-engine smoke proves the OpenAI-compatible path records LLM interactions and redacts payloads correctly.
- [x] Browser-level mock real-engine proof shows the mock OpenAI-compatible output in the React product result/detail surface without raw request/response payload leakage.
- [x] A controlled actionable test proves exchange-native facts can unblock manual-review eligibility without enabling auto orders.
- [x] Browser-level actionable staging proof now runs through Playwright's production Next webServer path by starting `start_local_stack.py --with-actionable-staging`; this proves local mock OKX + no-active-event rendering, not production success.
- [x] Local-stack cleanup covers all launcher-owned dependency processes, including `mock_okx_pid`, so manual `stop_local_stack.py` does not leave the actionable-staging OKX mock running on `8012`.
- [x] Product pages show `business_summary` first and do not require Raw/JSON to understand the alert.
- [x] Config/readiness UI explains whether the current run is fixture-only, mock-real, or real external.
- [x] Bark notification state is visible in the alert result/detail.
- [x] README/deployment docs explain the default safe fixture profile, mock LLM profile, actionable staging profile, prod-actionable readiness skip, and strict prod-actionable release gate.
- [x] At least one explicitly mocked outcome path is visible in eval through both Playwright and Python smoke, and marked `source_type=mocked_outcome`, `can_score=false`; real financial quality remains advisory until real exchange-native sample size is sufficient.
- [x] A local collector wiring proof runs through mock OKX `/history-candles`, real `collect-outcomes`, eval sidecar, `/api/eval/outcomes`, and `/eval?tab=quality`; it is explicitly labeled `local_mock_okx_collector_wiring_only` and does not prove real financial quality.
- [ ] At least one real exchange-native matured outcome is visible in eval before calling real financial quality non-empty.
- [x] The prod-actionable release gate has been run in strict mode and honestly reports the current missing readiness with `exit_semantics=fail_on_skip` and exit code `2`.
- [ ] A real external prod/actionable smoke succeeds with actual OKX public network, Bark, real OpenAI-compatible model, event readiness, and `allowed=true`.
- [x] CLI manual-query entry is declared and tested as `crypto-alert run-once --symbol ... --query ... --horizon ...`; `--query` is documented as operator audit note, not a direct decision driver.
- [x] CLI `run-once` output now includes `trace_id`, readable `business_summary`, `notification`, `result_review`, `requested_horizon`, and `plan_horizon`, so a CLI-first deployment can connect manual trigger, alert summary, notification status, and later outcome visibility without pretending request horizon already drives the generated final plan.
- [x] CLI `trace-show` now reads through `JournalQueryRepository`, matching API run detail projection for `business_summary`, `notification`, `notification_history`, and `result_review`; command-line operations no longer lose the follow-up review visibility available in the web product path.
- [x] CLI projection now fails explicitly with `cli_projection_missing_*` when a real executor completes but persisted detail/plan_run/business_summary/result_review cannot be read back. Non-persisting test doubles can still use fallback projection.
- [x] Docker/Compose now defines a hosted workbench deployment contract: `api` runs FastAPI on `8010`, `frontend` builds/serves Next on `3001` with `NEXT_PUBLIC_API_BASE_URL`, and docs verify `POST /api/runs/manual` as the hosted manual-query entry. This proves the deployment shape is defined, not that real external production readiness is complete.
- [x] Docker/Compose default API config is now safe-workbench first: default `api` uses `${CONFIG_PATHS:-config/default.yaml}` so a fresh checkout starts `SHADOW` + fixture. Production/staging overlays require explicit `.env` `CONFIG_PATHS=config/default.yaml:config/prod.yaml:config/staging.yaml`.
- [x] Docker/Compose can render on a fresh checkout without a root `.env`; `.env` is optional for default SHADOW/fixture startup and required only when overriding ports or providing real OpenAI/Bark/production readiness.
- [x] Docker/Compose default startup is now hosted-workbench first: default `docker compose up` includes only `api` and `frontend`; the scheduler/CLI service `manual-alert` is behind the explicit `scheduler` profile.
- [x] Docker/Compose frontend now separates browser/public API base from frontend-container server-side API base: `NEXT_PUBLIC_API_BASE_URL` remains browser-facing, while `API_INTERNAL_BASE_URL` defaults to `http://api:8010` for Next server rendering and frontend healthcheck.
- [ ] A Docker image build plus `docker compose up -d api frontend` health smoke has completed in a Docker runtime. The current attempt reached Docker daemon readiness but was blocked by Docker Hub metadata timeouts for `python:3.12-slim` and `node:22-alpine`; `PYTHON_BASE_IMAGE` / `NODE_BASE_IMAGE` overrides now provide a private-registry or pre-pulled-image path, but a real runtime health smoke still has not completed.
- [x] Product routes now have page-level `loading.tsx`, `error.tsx`, and `not-found.tsx` states so slow, broken, and missing pages stay in the manual-alert product language instead of falling back to blank/default Next.js surfaces.
- [x] `POST /api/runs/manual` now returns the same `result_review` product projection as run detail, so the first manual-query response can show whether follow-up outcome visibility is not collected, pending, mock-only, unscorable, or scorable.
- [x] Default product copy now hides unknown snake_case/dotted internal tokens behind `已记录，见工程详情`, and `/eval?tab=quality` hides unknown financial-quality status/effect enums behind product fallback copy.
- [x] `/runs` default business list now includes a product-facing `后续复盘` column sourced from the same `result_review` projection as run detail. Users can see `结果尚未生成`, `等待窗口成熟`, `本地展示样本`, `可用于质量复盘`, or `不可评分` without opening raw/detail pages; raw outcome codes remain hidden.
- [x] `tools/local_stack/run_local_checks.py` now runs a no-secret local matrix instead of only the fixture smoke: pytest, frontend typecheck/build, Playwright real-browser checks, fixture smoke, mock LLM smoke, actionable staging smoke, mocked outcome visibility smoke, collect-outcomes fixture smoke, and the opt-in Server Component fault profile port. It checks all shared local-stack ports (`8010/3001/8011/8012/8013`) and intentionally keeps strict `prod-actionable` as a separate release gate.

**2026-07-08 continuation verification record:**

- [x] `python3 -m pytest tests/config/test_config.py tests/workflow/test_candidate_sidecar_step.py tests/workflow/test_risk_merge_policy.py tests/workflow/test_decision_control_step.py tests/workflow/test_execution_fact_unblock.py tests/decision/test_production_control_gate.py tests/local_stack/test_scripts.py -q` passed.
- [x] `npm --prefix frontend run typecheck` passed.
- [x] `PLAYWRIGHT_EXPECT_MOCK_LLM=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm --seed-mock-outcome" npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` passed.
- [x] `npm --prefix frontend run e2e -- --update-snapshots` passed 4/4 and intentionally regenerated run-detail summary desktop/mobile snapshots after removing support/debug metadata from the business header.
- [x] `npm --prefix frontend run e2e` passed 4/4 with the updated snapshots.
- [x] `python3 -m pytest -q` passed with 2 warnings.
- [x] `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
- [x] `git diff --check` passed.
- [x] `python3 tools/local_stack/smoke_local_stack.py` passed with `smoke_profile=fixture`, `allowed=false`, `manual_execution_required=true`, `auto_order_enabled=false`.
- [x] `python3 tools/local_stack/smoke_local_stack.py --with-mock-llm` passed with `smoke_profile=mock_real_engine`, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `market_provider=fixture`, `allowed=false`.
- [x] `python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging` passed with `smoke_profile=actionable_staging`, local mock OKX, `allowed=true`, `manual_execution_required=true`, `auto_order_enabled=false`.
- [x] `python3 tools/local_stack/smoke_local_stack.py --seed-mock-outcome` passed with `mock_outcome_quality_scope=visibility_only_not_financial_quality`.
- [x] `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` returned exit `2` with missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`; this remains an honest release-gate block, not production success.
- [x] `BARK_DEVICE_KEY=device-key OPENAI_BASE_URL=http://127.0.0.1:8011 OPENAI_MODEL=model-a OPENAI_API_KEY=key-a MARKET_DATA_OKX_BASE_URL=http://127.0.0.1:8012 MACRO_EVENT_PROVIDER=no_active_event python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` returned exit `2` with `skip_reason=unsafe_readiness`; localhost/mock endpoints cannot spoof prod-actionable success.
- [x] Final 2026-07-08 verification after `/eval?tab=quality` productization and mock-outcome classification:
  - `npm --prefix frontend run typecheck` passed.
  - `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
  - `npm --prefix frontend run e2e` passed 4/4 across desktop and mobile.
  - `PLAYWRIGHT_EXPECT_MOCK_LLM=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm --seed-mock-outcome" npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` passed.
  - `python3 -m pytest -q` passed with 2 warnings.
  - `python3 -m pytest tests/local_stack/test_scripts.py -q` passed.
  - `python3 tools/local_stack/smoke_local_stack.py`, `--with-mock-llm`, `--with-actionable-staging`, and `--seed-mock-outcome` passed with their profile labels intact.
  - `git diff --check` passed.
- [x] Final 2026-07-08 verification after `/config` production-readiness productization and unsafe-readiness hardening:
  - `python3 -m pytest -q` passed with 2 warnings.
  - `npm --prefix frontend run typecheck` passed.
  - `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
  - `git diff --check` passed.
  - `npm --prefix frontend run e2e` passed 4/4 across desktop and mobile.
  - `python3 tools/local_stack/smoke_local_stack.py` passed with `smoke_profile=fixture`, `allowed=false`, `decision_engine=fixture`, `market_provider=fixture`, and notification disabled.
  - `python3 tools/local_stack/smoke_local_stack.py --with-mock-llm` passed with `smoke_profile=mock_real_engine`, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `market_provider=fixture`, and `allowed=false`.
  - `python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging` passed with `smoke_profile=actionable_staging`, local mock OKX, `allowed=true`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - `python3 tools/local_stack/smoke_local_stack.py --seed-mock-outcome` passed with `mock_outcome_quality_scope=visibility_only_not_financial_quality`.
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` returned exit `2` with `skip_reason=missing_readiness` and missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`; this is an honest release-gate block, not production success.
  - `BARK_DEVICE_KEY=device-key OPENAI_BASE_URL=http://127.0.0.1:8011 OPENAI_MODEL=model-a OPENAI_API_KEY=key-a MARKET_DATA_OKX_BASE_URL=http://127.0.0.1:8012 MACRO_EVENT_PROVIDER=no_active_event python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` returned exit `2` with `skip_reason=unsafe_readiness`; localhost/mock endpoints cannot spoof prod-actionable success.
  - `BARK_DEVICE_KEY=device-key OPENAI_BASE_URL=https://llm.example.test OPENAI_MODEL=mock-crypto-plan OPENAI_API_KEY=key-a MACRO_EVENT_PROVIDER=no_active_event python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` returned exit `2` with `skip_reason=unsafe_readiness`; mock model names cannot spoof prod-actionable success.
- [x] Final 2026-07-08 verification after quality-page enum fallback hardening and Playwright runtime diagnostics:
  - `python3 -m pytest -q` passed with 2 warnings.
  - `python3 -m pytest tests/local_stack/test_scripts.py -q` passed.
  - `npm --prefix frontend run typecheck` passed.
  - `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
  - `npm --prefix frontend run e2e` passed 4/4 across desktop and mobile, using the production frontend build and local API stack.
  - `python3 tools/local_stack/smoke_local_stack.py` passed with `smoke_profile=fixture`, `allowed=false`, `decision_engine=fixture`, `market_provider=fixture`, `macro_event_provider=disabled`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - `python3 tools/local_stack/smoke_local_stack.py --with-mock-llm` passed with `smoke_profile=mock_real_engine`, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `market_provider=fixture`, and `allowed=false`.
  - `python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging` passed with `smoke_profile=actionable_staging`, local mock OKX, `allowed=true`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - `python3 tools/local_stack/smoke_local_stack.py --seed-mock-outcome` passed with `mock_outcome_quality_scope=visibility_only_not_financial_quality`.
  - `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` returned exit `2` with `skip_reason=missing_readiness`, missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`; this remains an honest release-gate block, not production success.
  - `git diff --check` passed.
- [x] `lsof -ti tcp:8010 -ti tcp:3001 -ti tcp:8011 -ti tcp:8012 || true` returned no listeners.
- [x] 2026-07-08 verification after user-directed multi-agent rerun, eval diagnostic-detail productization, quality sample-id hiding, and mock OKX cleanup:
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed while `/eval/runs/[evalRunId]` lacked the `工程复盘诊断` / `复盘批次详情` boundary.
  - Red: `python3 -m pytest tests/local_stack/test_scripts.py::test_stop_local_stack_covers_mock_okx_port -q` failed while `8012` was absent from `stop_local_stack.py`.
  - Green: `python3 -m pytest tests/local_stack/test_scripts.py::test_stop_local_stack_covers_mock_okx_port tests/local_stack/test_scripts.py::test_local_smoke_assert_eval_quality_outcome_visible_requires_mocked_outcome tests/local_stack/test_scripts.py::test_local_smoke_rejects_mock_outcome_without_unscored_product_explanation tests/local_stack/test_scripts.py::test_local_smoke_rejects_quality_page_internal_outcome_codes -q` passed.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` passed against a production Next build and local API stack.
- [x] 2026-07-08 verification after CLI manual-query projection, hosted workbench Compose contract, and optional `.env` hardening:
  - Multi-agent architecture review found no automatic trading / order / withdraw boundary breach. Remaining architecture gaps are production external proof, scheduler-first `manual-alert` service posture, and `query_text` still being `audit_note`.
  - Multi-agent UI review found `/manual-run -> /runs -> /runs/[traceId]` is no longer a raw JSON/Trace-first product path. Remaining UI risks are diagnostic eval pages, page-level loading/error gaps, and mock outcome visibility being mistaken for real financial quality.
  - Multi-agent QA review confirmed Playwright starts a real local FastAPI + production Next stack, while smoke profiles must remain separated from strict production evidence.
  - Red: `python3 -m pytest tests/deployment/test_container_config_commands.py::test_compose_env_file_is_optional_for_fresh_checkout -q` failed while `docker-compose.yml` required a root `.env`.
  - Green: the same focused pytest passed after changing `manual-alert` and `api` `env_file` entries to `required: false`.
  - Green: `docker compose -p crypto-alert-prod config` rendered `api`, `frontend`, and `manual-alert` without a root `.env`.
  - Blocked: `docker compose -p crypto-alert-prod up -d --build api frontend` could not complete because Docker Hub metadata pulls timed out for `python:3.12-slim` and `node:22-alpine`; subsequent direct `docker pull` commands for both images failed with the same `context deadline exceeded`.
  - Green: `python3 -m pytest -q` passed with 2 warnings.
  - Green: `python3 -m pytest tests/deployment/test_container_config_commands.py tests/api/test_system_routes.py -q` passed.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
  - Green: `npm --prefix frontend run e2e` passed 4/4 across desktop and mobile, using the production Next build and local API stack.
  - Green: `python3 tools/local_stack/smoke_local_stack.py` passed with `smoke_profile=fixture`, `allowed=false`, `decision_engine=fixture`, `market_provider=fixture`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - Green: `python3 tools/local_stack/smoke_local_stack.py --with-mock-llm` passed with `smoke_profile=mock_real_engine`, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `market_provider=fixture`, and `allowed=false`.
  - Green: `python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging` passed with `smoke_profile=actionable_staging`, local mock OKX, `allowed=true`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - Green: `python3 tools/local_stack/smoke_local_stack.py --seed-mock-outcome` passed with `mock_outcome_quality_scope=visibility_only_not_financial_quality`.
  - Gate block: `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` returned exit `2` with `skip_reason=missing_readiness`, missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`; this is expected and remains not production success.
  - Green: `git diff --check` passed.
  - Green: `lsof -ti tcp:8010 -ti tcp:3001 -ti tcp:8011 -ti tcp:8012 || true` returned no listeners after local-stack/browser verification.
- [x] 2026-07-08 verification after product route-state hardening:
  - Red: `python3 -m pytest tests/structure/test_frontend_route_states.py -q` failed while `frontend/src/app/loading.tsx`, `error.tsx`, and `not-found.tsx` were missing.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "missing product routes"` failed while `/runs/not-a-real-alert` rendered the generic run-detail error state instead of the product missing-record recovery state.
  - Root cause: FastAPI wraps `HTTPException.detail` around the existing API envelope, and frontend `envelopeSchema` rejected backend failure envelopes with `data: null`; the run detail page therefore received `INVALID_RESPONSE` instead of stable `trace_not_found`.
  - Green: `python3 -m pytest tests/structure/test_frontend_route_states.py tests/api/test_runs_routes.py::test_unknown_trace_returns_stable_error_envelope -q` passed after adding product route-state files and aligning the frontend envelope parser with backend failure envelopes.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "missing product routes"` passed; `/runs/not-a-real-alert` now shows `没有找到这条提醒`, `返回提醒记录`, and `新建提醒` without raw JSON/default 404 text.
  - Green: `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
  - Green: `npm --prefix frontend run e2e` passed 6/6 across desktop and mobile, using the production Next build and local API stack.
  - Green: `python3 -m pytest -q` passed with 2 warnings.
  - Green: `python3 tools/local_stack/smoke_local_stack.py` passed with `smoke_profile=fixture`, `allowed=false`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - Green: `git diff --check` passed.
  - Green: `lsof -ti tcp:8010 -ti tcp:3001 -ti tcp:8011 -ti tcp:8012 || true` returned no listeners.
- [x] 2026-07-08 verification after hosted-workbench-first Compose profile:
  - Red: `python3 -m pytest tests/deployment/test_container_config_commands.py::test_compose_default_startup_is_hosted_workbench_first tests/deployment/test_container_config_commands.py::test_deployment_docs_describe_hosted_workbench_services -q` failed while `manual-alert` had no explicit `scheduler` profile and docs did not show `--profile scheduler up -d manual-alert`.
  - Green: the same focused pytest passed after moving `manual-alert` behind `profiles: ["scheduler"]` and updating deployment docs.
  - Green: `docker compose -p crypto-alert-prod config --services` returned only `api` and `frontend`.
  - Green: `docker compose -p crypto-alert-prod --profile scheduler config --services` returned `api`, `frontend`, and `manual-alert`.
  - Red: `python3 -m pytest tests/deployment/test_container_config_commands.py::test_compose_exposes_hosted_api_and_frontend_workbench tests/deployment/test_container_config_commands.py::test_deployment_docs_describe_safe_default_compose_config -q` failed while the default API still loaded `config/default.yaml:config/prod.yaml:config/staging.yaml`.
  - Green: the same focused pytest passed after changing API `CONFIG_PATHS` to `${CONFIG_PATHS:-config/default.yaml}` and documenting explicit `.env` overlay for prod/staging.
  - Green: `python3 -m pytest tests/deployment/test_container_config_commands.py -q` passed.
  - Green: `docker compose -p crypto-alert-prod config` rendered a default workbench stack containing `api` and `frontend` only.
  - Green: `docker compose -p crypto-alert-prod config | rg -n "CONFIG_PATHS"` showed `CONFIG_PATHS: config/default.yaml`.
  - Green: `git diff --check` passed.
- [x] 2026-07-09 verification after internal API-base, synchronous result-review, and product-copy fallback hardening:
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts` failed while `productDisplayText("new_internal_gate_reason")` returned the raw token.
  - Green: the same focused Playwright spec passed after unknown internal tokens fell back to `已记录，见工程详情`.
  - Red: `python3 -m pytest tests/deployment/test_container_config_commands.py::test_compose_exposes_hosted_api_and_frontend_workbench tests/deployment/test_container_config_commands.py::test_frontend_api_client_separates_browser_and_server_api_base tests/local_stack/test_scripts.py::test_start_local_stack_frontend_production_mode_uses_next_start tests/local_stack/test_scripts.py::test_start_local_stack_frontend_production_mode_builds_when_build_id_missing tests/local_stack/test_scripts.py::test_start_local_stack_frontend_production_mode_rebuilds_even_when_build_id_exists -q` failed while frontend Compose/local-stack runtime lacked `API_INTERNAL_BASE_URL`.
  - Green: the same focused pytest passed after adding `API_INTERNAL_BASE_URL`, making frontend healthcheck call `/api/system/health` through the internal base, and teaching the frontend API client to use internal base on the server and public base in the browser.
  - Green: `python3 -m pytest tests/deployment/test_container_config_commands.py tests/local_stack/test_scripts.py -q` passed.
  - Red: `python3 -m pytest tests/api/test_runs_routes.py::test_manual_run_response_uses_persisted_business_summary -q` failed while `POST /api/runs/manual` lacked `result_review`.
  - Green: the same focused API test passed after the POST response reused the persisted run-detail `result_review` projection.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed while the manual result panel did not show a short `结果尚未生成` follow-up review conclusion.
  - Green: the same focused Playwright command passed after the manual result panel rendered `后续复盘` with the synchronous `result_review` state.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed when `/eval?tab=quality` displayed seeded unknown `mystery_quality_status` and `mystery_decision_effect` values.
  - Green: the same focused Playwright command passed after unknown quality status/effect values rendered as `状态已记录` and `需人工复核`.
  - Verification caught and fixed a Compose interpolation bug: a frontend healthcheck template literal originally let Compose treat `${base}` as a Compose variable. The healthcheck now uses string concatenation (`base + '/api/system/health'`) to avoid interpolation ambiguity.
  - Green: `python3 -m pytest tests/deployment/test_container_config_commands.py -q` passed after locking the internal healthcheck command.
  - Green: `docker compose -p crypto-alert-prod config | rg -n "API_INTERNAL_BASE_URL|NEXT_PUBLIC_API_BASE_URL|api:8010|base \\+ '/api/system/health'|CONFIG_PATHS"` showed `API_INTERNAL_BASE_URL: http://api:8010`, browser `NEXT_PUBLIC_API_BASE_URL: http://127.0.0.1:8010`, and the frontend healthcheck using the internal base.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
  - Green: `npm --prefix frontend run e2e` passed 8/8 across desktop and mobile, using the production Next build and local API stack.
  - Green: `python3 tools/local_stack/smoke_local_stack.py` passed with `smoke_profile=fixture`, `allowed=false`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - Green: `python3 tools/local_stack/smoke_local_stack.py --collect-outcomes-fixture` passed with `outcome_collection_profile=local_mock_okx_collector_wiring_only`, `collected_exchange_native_outcomes=3`, and `real_financial_quality_proven=false`.
  - Gate block: `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` returned exit `2` with missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`; this remains an honest production-readiness block, not production success.
  - Green: `python3 -m pytest -q` passed with 2 warnings.
  - Green: `docker compose -p crypto-alert-prod config --services` returned `api` and `frontend`; `docker compose -p crypto-alert-prod --profile scheduler config --services` returned `api`, `frontend`, and `manual-alert`.
  - Green: `git diff --check` passed.
  - Green: `lsof -ti tcp:8010 -ti tcp:3001 -ti tcp:8011 -ti tcp:8012` returned no listeners.
- [x] 2026-07-09 verification after CLI `trace-show` detail projection alignment:
  - Red: `python3 -m pytest tests/cli/test_runner_cli.py::test_cli_trace_query_and_badcase_flow -q` failed with `KeyError: 'result_review'` while `trace-show` still called `journal.get_trace_detail()` directly.
  - Green: the same focused test passed after `trace-show` switched to `JournalQueryRepository(...).get_run_detail(...)`.
  - Green: `python3 -m pytest tests/cli/test_runner_cli.py -q` passed 32/32 with 1 warning.
- [x] 2026-07-09 verification after default run-detail quality-status fallback:
  - UI/UX subagent found that the default run detail `复核状态摘要` could render an unknown `financial_quality_gate.status` as a raw backend enum.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed after seeding a run payload with `financial_quality_gate.status=mystery_quality_status`; the default detail page did not show `状态已记录`.
  - Green: the same focused Playwright flow passed after `CockpitStatusBar` mapped unknown non-empty financial quality statuses to `状态已记录` and rejected `mystery_quality_status` / `mystery_decision_effect` in the visible default detail status bar.
- [x] 2026-07-09 verification after API manual-run projection fail-loud hardening:
  - Architecture subagent found that `POST /api/runs/manual` could still build a fallback success response if persisted run detail, `plan_run`, `business_summary`, or `result_review` was missing after executor completion.
  - Red: `python3 -m pytest tests/api/test_runs_routes.py::test_manual_run_response_fails_loudly_when_persisted_projection_missing -q` failed 4/4 because each missing projection shape still returned HTTP 200.
  - Green: the same focused pytest passed after `/api/runs/manual` raised explicit failure envelopes with `manual_run_projection_missing_detail`, `manual_run_projection_missing_plan_run`, `manual_run_projection_missing_business_summary`, or `manual_run_projection_missing_result_review`.
  - Green: `python3 -m pytest tests/api/test_runs_routes.py::test_manual_run_creates_trace_and_returns_plan_summary tests/api/test_runs_routes.py::test_manual_run_response_uses_persisted_business_summary tests/api/test_runs_routes.py::test_manual_run_response_preserves_normalized_plan_fields_when_payload_has_overlaps -q` passed, proving the positive product path still returns the persisted projection and normalized plan fields.
- [x] 2026-07-09 full local regression after multi-agent follow-up fixes:
  - Green: `python3 -m pytest -q` passed with 2 warnings.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 API_INTERNAL_BASE_URL=http://127.0.0.1:8010 npm --prefix frontend run build` passed.
  - Green: `npm --prefix frontend run e2e` passed 8/8 across desktop and mobile; this starts the real local FastAPI + production Next stack and runs DOM/visual/runtime checks.
  - Green: `python3 tools/local_stack/smoke_local_stack.py` passed with `smoke_profile=fixture`, `allowed=false`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - Green: `python3 tools/local_stack/smoke_local_stack.py --with-mock-llm` passed with `smoke_profile=mock_real_engine`, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `allowed=false`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - Green: `python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging` passed with `smoke_profile=actionable_staging`, local mock OKX, `allowed=true`, `macro_event_provider=no_active_event`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - Green: `python3 tools/local_stack/smoke_local_stack.py --collect-outcomes-fixture` passed with `outcome_collection_profile=local_mock_okx_collector_wiring_only`, `collected_exchange_native_outcomes=3`, and `real_financial_quality_proven=false`.
  - Green: `python3 tools/local_stack/smoke_local_stack.py --seed-mock-outcome` passed with `mock_outcome_quality_scope=visibility_only_not_financial_quality`.
  - Gate block: `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` exited `2` with `skip_reason=missing_readiness`, missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`; this remains not production success.
  - Green: `docker compose -p crypto-alert-prod config --services` returned `api` and `frontend`; `docker compose -p crypto-alert-prod --profile scheduler config --services` returned `api`, `frontend`, and `manual-alert`.
  - Green: `docker compose -p crypto-alert-prod config | rg -n "API_INTERNAL_BASE_URL|NEXT_PUBLIC_API_BASE_URL|api:8010|base \\+ '/api/system/health'|CONFIG_PATHS"` showed default `CONFIG_PATHS: config/default.yaml`, browser API base `http://127.0.0.1:8010`, internal API base `http://api:8010`, and the frontend healthcheck using `base + '/api/system/health'`.
  - Blocked: `docker compose -p crypto-alert-prod up -d --build api frontend` failed at Docker Hub metadata resolution for `python:3.12-slim` and `node:22-alpine` with `context deadline exceeded`; no Docker runtime health smoke is complete.
  - Green: `git diff --check` passed.
  - Green: `lsof -ti tcp:8010 -ti tcp:3001 -ti tcp:8011 -ti tcp:8012` returned no listeners after cleanup.
- [x] 2026-07-09 verification after default quality-page outcome error productization:
  - UI/QA review found that `/eval?tab=quality` could render `outcomesError` directly in the product quality page, which could expose SQL errors, filesystem paths, trace ids, or raw payload field names.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts` failed while no safe financial-quality outcome error projection existed.
  - Green: the same focused Playwright product-copy spec passed after `FinancialQualityPanel` mapped any outcome-loading error to `结果样本暂时无法加载，请稍后重试。` and rejected `SQLITE_ERROR`, `/srv/app`, `crypto-outcomes.db`, `trace_id`, and `request_json` in the product message.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` passed, proving the default quality page still renders correctly in the real local API + production Next flow.
- [x] 2026-07-09 user-directed real multi-agent rerun and actionable browser-proof follow-up:
  - Architecture Agent conclusion: backend main flow is now structurally closed around `manual query -> persisted readable summary -> gates/readiness -> notification projection -> result_review/outcome projection`; remaining delivery blockers are real external prod-actionable success and at least one real exchange-native matured outcome. Fixture/mock/staging proof remains explicitly non-production.
  - UI/UX Agent conclusion: default `/manual-run -> /runs -> /runs/[traceId]` and default `/eval` are no longer raw JSON/Trace-first surfaces. Remaining P1 product gap is list-level outcome/replay visibility; diagnostic paths such as `/runs?columns=observability`, `/runs/[traceId]?columns=observability&tab=raw|matrix`, and non-quality eval tabs should remain explicit engineering entries.
  - QA Agent conclusion: default Playwright proves seeded mock-outcome UI projection; smoke profiles prove fixture, mock LLM, actionable staging, collector fixture, and strict prod-actionable skip separately. Browser-level actionable staging required `start_local_stack.py` support and profile-aware assertions.
  - Red: `python3 -m pytest tests/local_stack/test_scripts.py::test_start_local_stack_can_start_actionable_staging_with_mock_okx -q` failed with `unrecognized arguments: --with-actionable-staging`.
  - Green: the same focused pytest passed after `start_local_stack.py` added `--with-actionable-staging`, started mock OKX, passed `actionable_staging_enabled=True` into the API environment, and wrote `mock_okx_pid` / `mock_okx` / actionable metadata to `pids.json`.
  - Green: `python3 -m pytest tests/local_stack/test_scripts.py -q` passed 52/52 after the launcher change.
  - Red: `PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-actionable-staging" npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` started successfully but failed because the test still expected fixture copy `本地演练` while the actionable product state correctly rendered `可人工复核`.
  - Green: the same Playwright command passed after the E2E assertions became profile-aware for fixture, mock LLM, and actionable staging. The actionable browser path now proves `可人工复核` in the real local API + production Next rendering path while avoiding fixture screenshot baselines for staging content.
  - Red: `python3 -m pytest tests/local_stack/test_scripts.py::test_stop_local_stack_kills_dependency_pids_from_pid_file -q` failed while plain `stop_local_stack.py` killed `frontend_pid`, `api_pid`, and `mock_openai_pid` but not `mock_okx_pid`.
  - Green: the same focused pytest passed after `stop_local_stack.py` included `mock_okx_pid` in the owned PID cleanup list.
  - Green: `python3 -m pytest tests/local_stack/test_scripts.py -q` passed 52/52 again after the cleanup fix.
  - Boundary: the actionable Playwright pass uses local mock OKX and fixture decision output; it is a browser-level allowed-path/UI proof only. Production success still requires strict `--prod-actionable --fail-on-skip` with real public OpenAI-compatible endpoint, real OKX public data, Bark `sent`, `MACRO_EVENT_PROVIDER=no_active_event`, `candidate_sidecar_mode=disabled`, `manual_execution_required=true`, and `auto_order_enabled=false`.
- [x] 2026-07-09 verification after `/runs` list-level outcome visibility:
  - UI/UX audit gap: the default `/runs` page showed business action, risk, notification, and review result, but did not show whether outcome/replay follow-up was not collected, pending, mock-only, scorable, or unscorable.
  - Red: `python3 -m pytest tests/api/test_runs_routes.py::test_run_list_projects_result_review_status -q` failed with `KeyError: 'result_review'` while list items only projected `business_summary`.
  - Green: the same focused API test passed after `JournalQueryRepository.list_runs()` added the per-run `result_review` product projection without exposing raw OutcomeStore fields.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed while `/runs` lacked the `后续复盘` column.
  - Green: the same focused Playwright command passed after `/runs` rendered `后续复盘`; the seeded run row shows `本地展示样本` and `结果样本 1 条` while rejecting `outcome`, `decision_ref`, `mocked_outcome`, `exchange_native`, `legacy_final`, `can_score`, and `unscored_reason` in the visible business row.
  - Green: `python3 -m pytest tests/api/test_runs_routes.py::test_run_list_projects_business_summary_and_notification_status tests/api/test_runs_routes.py::test_run_list_projects_result_review_status -q` passed.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Boundary: list-level visibility is product UX proof, not financial-quality proof. Mock/local result rows remain labeled as visibility-only until real exchange-native matured outcomes exist.
- [x] 2026-07-09 verification after no-secret local-check matrix hardening:
  - QA audit gap: `run_local_checks.py` still checked only ports `8010/3001` and only ran the default fixture smoke, so a green local check could miss mock LLM, actionable staging, mocked outcome visibility, and collect-outcomes wiring regressions.
  - Red: `python3 -m pytest tests/local_stack/test_scripts.py::test_run_local_checks_covers_all_shared_local_stack_ports tests/local_stack/test_scripts.py::test_run_local_checks_default_matrix_covers_browser_and_no_secret_smoke_profiles -q` failed while `LOCAL_PORTS` was `{8010,3001}` and no testable check matrix existed.
  - Green: the same focused pytest passed after `run_local_checks.py` introduced a testable no-secret `CheckSpec` matrix with `npm run e2e` plus fixture, mock LLM, actionable staging, seeded mock outcome, and collect-outcomes fixture smoke commands.
  - Documentation updated: `README.md`, `tests/README.md`, and `docs/deployment.md` now describe `run_local_checks.py` as a no-secret local matrix, not as a production success proof. Strict `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` remains separate.
  - Boundary: this improves everyday local verification coverage, but it still cannot prove real Bark/OpenAI/OKX/event readiness or real exchange-native matured outcome quality.
- [x] 2026-07-09 fresh verification after the user-directed main-flow rerun:
  - Multi-agent audit was re-read and reconciled: architecture, UI/UX, and QA agents agreed the current default product path is no longer raw JSON/Trace-first, and the backend main chain is structurally centered on `manual query -> persisted readable summary -> gates/readiness -> notification projection -> result_review/outcome projection`.
  - Green: `python3 tools/local_stack/run_local_checks.py` exited `0`. It ran full pytest (`1004 passed, 2 warnings`), frontend `npm run typecheck`, frontend `npm run build`, Playwright real-browser checks (`10 passed` across desktop and mobile), fixture smoke, mock LLM smoke, actionable staging smoke, seeded mock-outcome visibility smoke, and collect-outcomes fixture smoke.
  - The successful no-secret smoke profile boundaries were:
    - fixture: `smoke_profile=fixture`, `allowed=false`, `decision_engine=fixture`, `market_provider=fixture`, `manual_execution_required=true`, `auto_order_enabled=false`;
    - mock LLM: `smoke_profile=mock_real_engine`, `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `market_provider=fixture`, `allowed=false`;
    - actionable staging: `smoke_profile=actionable_staging`, local mock OKX, `allowed=true`, `market_provider=okx_public`, `macro_event_provider=no_active_event`, `manual_execution_required=true`, `auto_order_enabled=false`;
    - seeded mock outcome: `mock_outcome_quality_scope=visibility_only_not_financial_quality`;
    - collect-outcomes fixture: `outcome_collection_profile=local_mock_okx_collector_wiring_only`, `collected_exchange_native_outcomes=3`, `real_financial_quality_proven=false`.
  - Gate block: `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` exited `2` with `skip_reason=missing_readiness`, missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`. This is the expected honest release-gate block and is not production success.
  - Green: `docker compose -p crypto-alert-prod config` rendered the hosted workbench stack with `api` and `frontend`, default `CONFIG_PATHS: config/default.yaml`, browser API base `http://127.0.0.1:8010`, internal frontend API base `http://api:8010`, and the frontend healthcheck calling `base + '/api/system/health'`.
  - Blocked: `docker compose -p crypto-alert-prod up -d --build api frontend` still failed before application startup because Docker Hub metadata resolution timed out for `python:3.12-slim` and `node:22-alpine` with `context deadline exceeded`. No Docker runtime health smoke is complete.
  - Green: `lsof -ti tcp:8010 -ti tcp:3001 -ti tcp:8011 -ti tcp:8012` returned no listeners after the checks and failed Docker build attempt.
  - Boundary: the current code has stronger local/browser/staging proof than before, but the production deliverable remains incomplete until real external prod-actionable success, real exchange-native matured outcome evidence, and a real hosted-workbench runtime smoke are completed.
- [x] 2026-07-09 verification after Docker restricted-registry fallback:
  - Root cause: hosted-workbench runtime smoke was blocked before application startup by Docker Hub metadata timeouts for fixed base images, not by API/frontend application code.
  - Red: `python3 -m pytest tests/deployment/test_container_config_commands.py::test_container_base_images_can_be_overridden_for_restricted_registries -q` failed while `Dockerfile` and `Dockerfile.frontend` were hard-wired to `python:3.12-slim` and `node:22-alpine`.
  - Green: the same focused pytest passed after `Dockerfile` introduced `PYTHON_BASE_IMAGE`, `Dockerfile.frontend` introduced `NODE_BASE_IMAGE`, Compose passed those build args to `manual-alert`, `api`, and `frontend`, and `.env.example` exposed safe default override values.
  - Red: `python3 -m pytest tests/deployment/test_container_config_commands.py::test_deployment_docs_describe_safe_default_compose_config -q` failed while deployment docs did not mention `PYTHON_BASE_IMAGE` / `NODE_BASE_IMAGE`.
  - Green: `python3 -m pytest tests/deployment/test_container_config_commands.py -q` passed 16/16 after `docs/deployment.md` documented the restricted-network/private-registry override path.
  - Green: `docker compose -p crypto-alert-prod config | rg -n "PYTHON_BASE_IMAGE|NODE_BASE_IMAGE|CONFIG_PATHS|API_INTERNAL_BASE_URL|NEXT_PUBLIC_API_BASE_URL|api:8010|base \\+ '/api/system/health'"` showed default base image args, safe default `CONFIG_PATHS`, public/internal API bases, and the frontend healthcheck.
  - Green: `PYTHON_BASE_IMAGE=registry.example.com/library/python:3.12-slim NODE_BASE_IMAGE=registry.example.com/library/node:22-alpine docker compose -p crypto-alert-prod config | rg -n "registry.example.com|PYTHON_BASE_IMAGE|NODE_BASE_IMAGE"` showed both override values in the rendered Compose config.
  - Boundary: this gives operators a concrete path around Docker Hub metadata failures, but no Docker runtime health smoke is complete until the target environment can actually build and start `api` and `frontend`.
- [x] 2026-07-09 verification after hosted workbench runtime smoke scripting:
  - Delivery gap: deployment docs described manual curl checks after `docker compose up`, but there was no repeatable command that validated API health, frontend render, `POST /api/runs/manual`, run detail projection, and frontend detail page together against an already deployed workbench.
  - Red: `python3 -m pytest tests/deployment/test_hosted_workbench_smoke.py -q` failed while `tools/deployment/smoke_hosted_workbench.py` did not exist.
  - Green: the same pytest passed after adding `tools/deployment/smoke_hosted_workbench.py`. The script fails loudly when the manual response lacks `business_summary` or `result_review`, and outputs `smoke_profile=hosted_workbench` with `hosted_runtime_only_not_prod_actionable=true`.
  - Red: `python3 -m pytest tests/deployment/test_container_config_commands.py::test_deployment_docs_describe_hosted_workbench_services -q` failed while deployment docs did not mention the hosted workbench smoke command.
  - Green: `python3 -m pytest tests/deployment/test_hosted_workbench_smoke.py tests/deployment/test_container_config_commands.py::test_deployment_docs_describe_hosted_workbench_services -q` passed after `docs/deployment.md` documented `python3 tools/deployment/smoke_hosted_workbench.py`.
  - Real local runtime proof: `python3 tools/local_stack/start_local_stack.py --frontend-mode production --reset-data` started local FastAPI and production Next on `8010/3001`; `python3 tools/deployment/smoke_hosted_workbench.py --api-base http://127.0.0.1:8010 --frontend-base http://127.0.0.1:3001 --symbol ETH-USDT-SWAP --query '真实本地 production-mode hosted workbench smoke' --horizon 6h` returned `ok=true`, `smoke_profile=hosted_workbench`, `allowed=false`, `decision_engine=fixture`, `market_provider=fixture`, `manual_execution_required=true`, `auto_order_enabled=false`, and `result_review_status=not_collected`.
  - Boundary: this proves a hosted workbench API/frontend runtime can be checked end-to-end once services are running. It is still not Docker Compose runtime proof unless run after a real `docker compose up -d --build api frontend`, and it is not `prod-actionable` proof because fixture/default runs can legitimately return `allowed=false` and no Bark `sent`.
- [x] 2026-07-09 user-requested four-agent audit reconciliation:
  - Architecture/docs Agent conclusion: the code is now structurally centered on the manual alert workbench, but production success is still unproven. `POST /api/runs/manual`, `crypto-alert run-once`, `business_summary`, notification projection, and `result_review` exist; `query_text` remains an `audit_note`; AgentSwarm/candidate remains sidecar/audit. Production still requires real OpenAI-compatible HTTPS endpoint, real OKX public data, Bark `sent`, `MACRO_EVENT_PROVIDER=no_active_event` or a real event provider assertion, `allowed=true`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - UI/UX Agent conclusion: default `/`, `/manual-run`, `/runs`, `/runs/{trace_id}`, and `/eval` no longer present as raw JSON/Trace-first surfaces. Remaining P1 risks are diagnostic paths controlled only by query parameters, raw JSON relying on upstream redaction, and eval diagnostic pages still showing engineering terms.
  - QA Agent conclusion: there is meaningful coverage, but the evidence levels are mixed. The canonical browser command is `cd frontend && npm run e2e`; running Playwright from the wrong directory can bypass `frontend/playwright.config.ts` and fail before product assertions. Release evidence must keep separating real browser production Next proof, no-secret local matrix proof, staged allowed-path proof, hosted runtime proof, and strict external prod-actionable proof.
  - Backend Agent conclusion: no P0 fake-success code defect was found in static review. Remaining P1 backend gates are explicit config-path fail-fast, event assertion artifacting for `no_active_event`, treating Bark `sent` as required production proof, and not mistaking `/api/system/config` readiness for live external dependency proof.
- [x] 2026-07-09 verification after real outcome evidence gate scripting:
  - Delivery gap: `collect-outcomes` could write eval sidecar samples, but there was no standalone deployment gate that failed loudly until at least one real, exchange-native, matured, scorable outcome was visible through the deployed API.
  - Red: `python3 -m pytest tests/deployment/test_real_outcome_evidence_smoke.py -q` failed while `tools/deployment/smoke_real_outcome_evidence.py` did not exist.
  - Green: the same pytest passed after adding `tools/deployment/smoke_real_outcome_evidence.py`. The script reads `GET /api/eval/outcomes`, accepts only samples with `source_type=exchange_native`, `matured=true`, `can_score=true`, `window.can_score_execution_outcome=true`, trade-like action, complete trade levels, and complete OHLC window data.
  - Red: `python3 -m pytest tests/deployment/test_container_config_commands.py::test_deployment_docs_describe_real_outcome_evidence_gate -q` failed while deployment docs did not mention the evidence gate.
  - Green: the same focused docs test passed after `docs/deployment.md` documented `python3 tools/deployment/smoke_real_outcome_evidence.py`, `smoke_profile=real_outcome_evidence`, and the boundary that this is not prod-actionable success.
  - Boundary: this gate proves real outcome evidence exists in the API sidecar; it does not prove Bark delivery, a fresh allowed manual alert, or real external prod-actionable success.
- [x] 2026-07-09 fresh full-stack verification after real multi-agent audit and outcome evidence gate:
  - Green: `npm run e2e` from `frontend/` started real local FastAPI plus production Next via `frontend/playwright.config.ts` and passed 10/10 across Chromium desktop/mobile, covering manual-run async flow, run detail, eval/config rendering, DOM/visual checks, and product-copy safety.
  - Green: `python3 tools/local_stack/start_local_stack.py --frontend-mode production --reset-data --seed-mock-outcome --keep-running` started a hosted local API/frontend runtime; `python3 tools/deployment/smoke_hosted_workbench.py --api-base http://127.0.0.1:8010 --frontend-base http://127.0.0.1:3001 --symbol ETH-USDT-SWAP --query '本轮多Agent审计后 hosted workbench smoke：验证人工提醒入口和详情页' --horizon 6h` returned `ok=true`, `smoke_profile=hosted_workbench`, `allowed=false`, `decision_engine=fixture`, `market_provider=fixture`, `manual_execution_required=true`, `auto_order_enabled=false`, and `result_review_status=not_collected`.
  - Expected block: against that same local hosted runtime, `python3 tools/deployment/smoke_real_outcome_evidence.py --api-base http://127.0.0.1:8010` exited `1` with `real_exchange_native_matured_outcome_proven=false` and `matched 0 of 1 outcomes`; the only seeded sample was visibility-only mock outcome, not real financial-quality evidence.
  - Green: `python3 -m pytest tests/deployment/test_hosted_workbench_smoke.py tests/deployment/test_real_outcome_evidence_smoke.py tests/deployment/test_container_config_commands.py -q` passed 24/24.
  - Green: `git diff --check` passed.
  - Gate block: `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` exited `2` with `skip_reason=missing_readiness`, missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`. This remains the honest production blocker, not production success.
  - Green: `python3 tools/local_stack/run_local_checks.py` exited `0`. It ran full pytest (`1013 passed, 2 warnings`), frontend typecheck, frontend production build, Playwright real-browser checks (`10 passed`), fixture smoke, mock LLM smoke, actionable staging smoke, seeded mock-outcome smoke, and collect-outcomes fixture smoke.
  - Boundary: fixture/mock/actionable staging/collector fixture proof is local no-secret verification. It does not satisfy real external prod-actionable success, real exchange-native matured outcome evidence, Bark delivery, or Docker Compose runtime proof.
- [x] 2026-07-09 verification after explicit config-path fail-fast hardening:
  - Backend audit gap: `load_config()` treated any missing YAML path as `{}`, so a typo in `CONFIG_PATHS=config/default.yaml:config/prod.yaml:config/staging.yaml` could silently drop a production/staging overlay and leave a fixture/default runtime looking healthy.
  - Red: `python3 -m pytest tests/config/test_config.py::test_explicit_missing_config_path_fails_fast tests/api/test_system_routes.py::test_app_fails_fast_when_config_paths_environment_references_missing_file -q` failed while missing explicit config paths did not raise `ConfigError`.
  - Green: the same focused tests passed after `_read_yaml(..., required=True)` raised `ConfigError("Config file does not exist: ...")` for missing default or explicit overlay paths.
  - Green: `python3 -m pytest tests/config/test_config.py tests/api/test_system_routes.py tests/cli/test_runner_cli.py::test_cli_show_config_redacts tests/deployment/test_container_config_commands.py -q` passed 58/58.
  - Green: `PYTHONPATH=src python3 -m crypto_manual_alert.cli --config config/default.yaml show-config` emitted valid JSON.
  - Expected block: `PYTHONPATH=src python3 -m crypto_manual_alert.cli --config config/default.yaml --config /tmp/crypto-alert-missing-config.yaml show-config` exited `2` with `CONFIG_ERROR: Config file does not exist: /tmp/crypto-alert-missing-config.yaml`.
  - Documentation updated: `docs/deployment.md` now says `CONFIG_PATHS` typos are deployment errors and must not be downgraded into fixture workbench validation.
- [x] 2026-07-09 verification after `no_active_event` assertion metadata hardening:
  - Backend audit gap: `MACRO_EVENT_PROVIDER=no_active_event` wrote an `active_event_status` point, but the value only contained `status`, `symbol`, and `assertion`. That made production readiness look like a bare config switch instead of an auditable operator assertion.
  - Red: `python3 -m pytest tests/market/test_event_status.py tests/config/test_config.py::test_macro_event_assertion_metadata_can_be_set_by_environment tests/config/test_config.py::test_macro_event_assertion_rejects_invalid_timestamp tests/api/test_system_routes.py::test_config_readiness_reports_prod_actionable_ready_when_event_and_external_env_are_ready tests/api/test_system_routes.py::test_config_readiness_requires_no_active_event_assertion_metadata tests/workflow/test_execution_fact_unblock.py::test_no_active_event_assertion_metadata_is_persisted_in_snapshot tests/storage/test_business_summary.py::test_business_summary_explains_no_active_event_operator_assertion tests/storage/test_business_summary.py::test_business_summary_warns_when_no_active_event_metadata_is_incomplete tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_requires_event_assertion_metadata tests/local_stack/test_scripts.py::test_local_smoke_api_env_enables_prod_actionable_when_ready -q` failed before the metadata fields/provider/readiness projections existed.
  - Green: the same focused test set passed after adding `MACRO_EVENT_OPERATOR_REF`, `MACRO_EVENT_CONFIRMED_AT`, `MACRO_EVENT_SOURCE_REF`, `MACRO_EVENT_ASSERTION_HORIZON`, and `MACRO_EVENT_VALID_UNTIL` to config/env, event-status snapshots, business-summary evidence, and strict prod-actionable readiness.
  - Red: `python3 -m pytest tests/deployment/test_container_config_commands.py::test_deployment_docs_define_prod_actionable_success_contract -q` failed while `docs/deployment.md` still described only `MACRO_EVENT_PROVIDER=no_active_event`.
  - Boundary: local actionable staging can still use `no_active_event` as a wiring proof. Production `prod-actionable` proof now requires the provider plus assertion metadata; missing metadata is a readiness failure, not production success.
- [x] 2026-07-09 verification after diagnostic/raw backend boundary hardening:
  - Backend/UI audit gap: default product routes no longer show raw JSON first, but direct API access to `include_payloads=true` and `mode=judge_openai` still depended on frontend/query-string convention instead of a server-side environment boundary.
  - Red: `python3 -m pytest tests/api/test_runs_routes.py::test_run_detail_rejects_payload_inclusion_when_diagnostic_routes_are_disabled tests/api/test_runs_routes.py::test_run_detail_can_include_sanitized_llm_payloads_for_trace_review tests/api/test_eval_routes.py::test_eval_run_rejects_real_judge_when_diagnostic_routes_are_disabled -q` failed because payload inclusion returned `200` and real judge reached eval validation before a diagnostic gate.
  - Red: `python3 -m pytest tests/config/test_config.py::test_diagnostic_routes_can_be_enabled_by_environment -q` failed before `Config.diagnostic.routes_enabled` existed.
  - Green: the same focused API tests and config/system/local-stack checks passed after adding `DIAGNOSTIC_ROUTES_ENABLED`, `DiagnosticConfig`, and a shared `diagnostic_routes_disabled` 403 guard for raw payload inclusion and `judge_openai`.
  - QA follow-up found `GET /api/eval/runs/{eval_run_id}` and `/promotion-artifacts` could still return replay/promotion payloads without the diagnostic guard. Red: `python3 -m pytest tests/api/test_eval_routes.py::test_eval_run_detail_rejects_when_diagnostic_routes_are_disabled tests/api/test_eval_routes.py::test_eval_promotion_artifacts_reject_when_diagnostic_routes_are_disabled tests/api/test_eval_routes.py::test_eval_run_allows_real_judge_when_diagnostic_routes_are_enabled -q` failed on the first two routes returning `200`.
  - Green: the same focused eval route tests and `python3 -m pytest tests/api/test_eval_routes.py -q` passed after gating eval run detail and promotion artifacts while keeping explicit diagnostic-mode tests green.
  - Code-review follow-up found default `POST /api/eval/runs` and `GET /api/eval/runs` could still expose report refs, promotion artifacts, release gate, replay, and side-effect metadata. Red: `python3 -m pytest tests/api/test_eval_routes.py::test_eval_run_create_and_list_hide_diagnostic_metadata_by_default -q` failed with those metadata keys present.
  - Green: `python3 -m pytest tests/api/test_eval_routes.py -q` passed after default eval run summaries were projected to product-safe metadata (`financial_quality_gate` only) while diagnostic-enabled tests still see report artifacts.
  - Code-review follow-up also found `--prod-actionable` smoke was starting the API with diagnostic routes enabled. Red: `python3 -m pytest tests/local_stack/test_scripts.py::test_local_smoke_api_env_enables_prod_actionable_when_ready -q` failed while `DIAGNOSTIC_ROUTES_ENABLED=true`.
  - Green: local stack env tests passed after non-production local smoke kept diagnostic routes enabled for redaction testing, while `prod_actionable_enabled=True` now sets `DIAGNOSTIC_ROUTES_ENABLED=false` and skips raw-payload redaction assertions.
  - Boundary: non-production local smoke/Playwright explicitly enables diagnostic routes so raw payload redaction remains tested; prod-actionable smoke and shared/prod deployments keep the default disabled. This fixes backend bypass risk, but raw/matrix UI still needs P1 summary-first productization and defensive frontend redaction before broad shared-user exposure.
- [x] 2026-07-09 multi-agent audit synthesis:
  - Architecture Agent confirmed the backend is centered on the manual alert chain, not automatic trading. Remaining P0 proof gaps are real external prod-actionable success, Bark `sent`, hosted/Compose workbench running the intended config, production `workflow.execution_mode=legacy_baseline`, and at least one real exchange-native matured outcome.
  - UI/UX Agent confirmed `/`, `/manual-run`, `/runs`, `/runs/{trace_id}`, and default `/eval` are no longer raw JSON/Trace-first product paths. Remaining P0/P1 UI gaps are making generation/provider evidence visible in business language, sanitizing error states, and converting raw/matrix diagnostics from JSON-first to summary-first.
- [x] 2026-07-09 verification after product-facing generation-chain summary:
  - UI/UX audit gap: `/manual-run` and `/runs/{trace_id}` showed readable plans, notification, and outcome status, but a product user still could not tell whether the model path was fixture, mock LLM, or real provider without opening raw/diagnostic views.
  - Red: `python3 -m pytest tests/storage/test_business_summary.py::test_business_summary_generation_summary_marks_fixture_as_local_sample tests/storage/test_business_summary.py::test_business_summary_uses_persisted_llm_summary_without_runtime_config tests/storage/test_business_summary.py::test_business_summary_generation_summary_describes_real_model_without_raw_payload -q` failed with missing `business_summary.generation_summary`.
  - Red: `python3 -m pytest tests/api/test_runs_routes.py::test_run_detail_business_summary_uses_persisted_mock_llm_interaction -q` failed while run detail summaries did not expose model-chain fields.
  - Green: the focused storage/API tests passed after `business_summary` added `generation_summary` with fixture/mock/real mode labels, provider/model/status, duration/token text, response summary, and raw-payload exclusion.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed while the real browser product path did not show `生成链路`.
  - Green: the same focused Playwright fixture profile passed after `/manual-run` success and run detail summary rendered `生成链路`, local-sample response summary, and product copy without raw payload markers.
  - Green: `PLAYWRIGHT_EXPECT_MOCK_LLM=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--with-mock-llm --seed-mock-outcome" npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` passed and showed `mock-crypto-plan` plus `模型已返回` while still rejecting `request_json`, `response_json`, `choices`, and `chat.completion`.
  - QA follow-up: repeated Playwright runs exposed a startup flake from building the same `.next` directory twice in one webServer command. `frontend/playwright.config.ts` now delegates the production build to `start_local_stack.py --frontend-mode production` only, and `tests/structure/test_frontend_route_states.py` guards against reintroducing the duplicate `npm --prefix frontend run build`.
  - Green: `python3 -m pytest tests/storage/test_business_summary.py tests/api/test_runs_routes.py::test_run_detail_business_summary_uses_persisted_mock_llm_interaction tests/structure/test_frontend_route_states.py -q` passed 12/12.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `npm --prefix frontend run e2e` passed 10/10 across Chromium desktop/mobile after the duplicate-build startup fix.
  - Green: `python3 tools/local_stack/run_local_checks.py` exited `0`. It ran full pytest (`1034 passed, 2 warnings`), frontend typecheck, frontend production build, Playwright browser checks (`10 passed`), fixture smoke, mock LLM smoke, actionable staging smoke, seeded mock-outcome smoke, and collect-outcomes fixture smoke.
  - Expected block: `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` exited `2` with `skip_reason=missing_readiness`, missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`. This remains the honest production blocker, not production success.
  - Green: `git diff --check` passed, and no listeners remained on `8010/3001/8011/8012` after verification.
  - Boundary: this is product UX and mock/fixture browser proof. It does not prove real external model quality, real OKX data, Bark `sent`, or production success.
- [x] 2026-07-09 verification after diagnostic summary-first UI and front-end JSON redaction:
  - User-directed multi-agent rerun:
    - Architecture Agent confirmed the current production main line should remain `POST /api/runs/manual` / `crypto-alert run-once` -> `legacy_prompt` -> gates -> journal -> `business_summary` / notification / `result_review`. It also reconfirmed that `production_candidate_swarm` is blocked audit-only and must not be described as the manual-alert main path.
    - QA Agent confirmed the no-secret local matrix covers fixture, mock LLM, actionable staging, seeded mock outcome, collect-outcomes fixture, Playwright desktop/mobile, and API contracts, but none of those are production success. Strict production proof remains `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`.
    - UI/UX Agent confirmed the default product routes are no longer raw JSON/Trace-first, but called out raw/matrix diagnostics as still too JSON-first and highlighted direct backend error-message exposure as the next product-safety risk.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts` failed while `redactJsonForDisplay()` did not exist and diagnostic JSON rendering could not prove a front-end defensive redaction layer.
  - Green: the same focused Playwright spec passed after `JsonDetails` began recursively redacting secret-shaped field names and text values, including `api_key`, `token`, `device_key`, `BARK_DEVICE_KEY`, `Authorization`, `Bearer ...`, and `https://api.day.app/...`.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop -g "manual run async flow"` failed while the observability matrix page lacked `工程诊断摘要`.
  - Green: the same focused browser flow passed after the matrix page added a summary-first `工程诊断摘要` and the raw page added `原始数据摘要` with explicit `已应用展示层脱敏` status before the folded JSON details.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `npm --prefix frontend run e2e` passed 12/12 across Chromium desktop/mobile, using the production Next build and local FastAPI stack.
  - Green: `python3 tools/local_stack/run_local_checks.py` exited `0`. It ran Python full pytest (`1034 passed, 2 warnings`), frontend typecheck, frontend production build, Playwright browser checks (`12 passed`), fixture smoke, mock LLM smoke, actionable staging smoke, seeded mock-outcome smoke, and collect-outcomes fixture smoke.
  - No-secret smoke boundaries remained explicit:
    - fixture: `allowed=false`, `decision_engine=fixture`, `market_provider=fixture`, `manual_execution_required=true`, `auto_order_enabled=false`;
    - mock LLM: `decision_engine=openai_compatible`, `decision_model=mock-crypto-plan`, `market_provider=fixture`, `allowed=false`, `prod_actionable_enabled=false`;
    - actionable staging: local mock OKX, `allowed=true`, `market_provider=okx_public`, `macro_event_provider=no_active_event`, `manual_execution_required=true`, `auto_order_enabled=false`, `prod_actionable_enabled=false`;
    - seeded mock outcome: `mock_outcome_quality_scope=visibility_only_not_financial_quality`;
    - collect-outcomes fixture: `outcome_collection_profile=local_mock_okx_collector_wiring_only`, `collected_exchange_native_outcomes=3`, `real_financial_quality_proven=false`.
  - Expected block: `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` exited `2` with `skip_reason=missing_readiness`, missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`. This remains the honest production blocker, not production success.
  - Boundary: raw/matrix is now summary-first and has a front-end redaction layer, but it remains an explicit engineering diagnostic surface. Product error-state route-level failure coverage for API 500, invalid envelope, network abort, and eval list failure is still open.
- [x] 2026-07-09 verification after product error-state redaction slice:
  - QA/UI error-state audit found remaining direct `error.message` rendering in eval diagnostic paths, eval run detail partial failures, result-review messages, span errors, and candidate sidecar error objects.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts error-states.spec.ts` failed while shared `safeDisplayError()` did not exist and eval POST failure could expose backend messages.
  - Green: the same focused spec passed after adding `safeDisplayError()` and routing `RunEvalForm`, eval runs/cases/replay/score tables, eval run detail load/promotion/frozen-input errors, result-review messages, span errors, and candidate-sidecar error objects through safe product copy.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts` failed while a seeded trace span/candidate error did not render the safe `执行异常` marker and could expose raw diagnostic text.
  - Green: the same focused error-state spec passed after matrix diagnostics mapped unsafe span/candidate errors to safe labels and kept unsafe SQL/path/trace/request/Bark tokens out of the visible page.
  - New browser route-level coverage now includes:
    - manual-run `POST /api/runs/manual` API 500;
    - eval `POST /api/eval/runs` API 500;
    - eval `POST /api/eval/runs` invalid envelope;
    - eval `POST /api/eval/runs` network abort;
    - real local-stack run detail matrix with seeded unsafe span and candidate errors.
  - New function/component coverage verifies eval diagnostic list/table error messages (`问题样本`, `回放明细`, `评分明细`) map unsafe backend text to safe copy.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `npm --prefix frontend run e2e` passed 26/26 across Chromium desktop/mobile, using the production Next build and local FastAPI stack.
  - Boundary at that moment: Server Component first-load GET failures for `/eval?tab=runs|cases|quality` were sanitized through shared copy paths, but true route-level GET failure coverage still required a mock `API_INTERNAL_BASE_URL` or local-stack error fixture. This was closed in the next pass below.
- [x] 2026-07-09 verification after Server Component first-load error-state coverage:
  - Multi-agent QA review found that Playwright `page.route()` covered browser-side POST failures but could not intercept Next.js Server Component first-load `fetch()` calls, because those requests use `API_INTERNAL_BASE_URL` from the Next server runtime.
  - Red: `python3 -m pytest tests/local_stack/test_scripts.py -q` failed while local-stack had no `8013` fault API, no `--with-error-internal-api` flag, no frontend server-side API override, and no stop-script cleanup for the extra process.
  - Green: the same pytest file passed 60/60 after adding `tools/local_stack/mock_error_api_server.py`, `smoke.MOCK_ERROR_API_PORT=8013`, `start_local_stack.py --with-error-internal-api`, `API_INTERNAL_BASE_URL` override support for the frontend build/start process, and `stop_local_stack.py` cleanup for `mock_error_api_pid`.
  - New real-browser Server Component coverage:
    - `/eval?tab=runs` renders safe copy for an unsafe 500 envelope from the internal API;
    - `/eval?tab=cases` renders safe copy for an invalid internal API envelope;
    - `/eval?tab=quality` renders safe copy when the internal API connection closes during outcome loading.
  - Green: `PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "Server Component"` passed 1/1 with production Next, local FastAPI, and the 8013 internal fault API.
  - Green: `PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" npm --prefix frontend run e2e -- --project=chromium-mobile error-states.spec.ts -g "Server Component"` passed 1/1.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `python3 -m pytest tests/local_stack/test_scripts.py tests/structure/test_frontend_route_states.py -q` passed 63/63.
  - Green: `npm --prefix frontend run e2e` passed 26/26 with 2 opt-in Server Component fault tests skipped under the default local stack profile, confirming the new fault profile does not pollute the normal product flow.
  - Green: `python3 tools/local_stack/run_local_checks.py` exited `0`. It ran full pytest (`1039 passed, 2 warnings`), frontend typecheck, frontend production build, Playwright browser checks (`26 passed`, `2 skipped` opt-in fault-profile tests), fixture smoke, mock LLM smoke, actionable staging smoke, seeded mock-outcome smoke, and collect-outcomes fixture smoke.
  - Expected block: `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` exited `2` with `skip_reason=missing_readiness`, missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`. This is the honest production blocker, not a hidden success.
  - Green: `git diff --check` passed, and no listeners remained on `8010/3001/8011/8012/8013` after verification.
  - Boundary: this proves error-state UI behavior under local fault injection at the Next server/API boundary. It is not production success and does not replace the strict real external `--prod-actionable --fail-on-skip` gate.
- [x] 2026-07-09 verification after manual-run partial-success product fallback:
  - UI/UX audit follow-up found that the frontend treated `business_summary` and `result_review` as hard-required on the immediate `POST /api/runs/manual` response. If a mixed-version or partial API response still contained a valid `trace_id`, `plan`, and `verdict` but missed the display projections, the user saw only a generic failure and lost the details link.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "partial success"` failed while a mocked `ok=true` manual-run response with `trace_id`, `plan`, and `verdict` but no `business_summary` / `result_review` did not render `本次提醒建议`.
  - Green: the same Playwright test passed after `manualRunResponseSchema` began preserving the core `trace_id` / `plan` / `verdict` fields and generating a clearly labeled fallback projection: `摘要暂不可用`, `核心提醒已返回`, `通知状态未记录`, and `结果尚未生成`, plus the `/runs/{trace_id}` detail link.
  - Green: `npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts` passed 6/6 with 1 opt-in Server Component fault test skipped under the default profile.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `npm --prefix frontend run e2e` passed 28/28 with 2 opt-in Server Component fault tests skipped under the default profile, covering desktop and mobile.
  - Green: `PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "Server Component"` passed 1/1 after the fallback change.
  - Boundary: backend/API and CLI projection checks remain fail-loud for the current production contract; this frontend fallback is only a user-facing degradation path for partial or mixed-version responses and must not be treated as proof that the backend projection is healthy.
- [x] 2026-07-09 verification after hosted production-config smoke guard:
  - Architecture/QA audit gap: `tools/deployment/smoke_hosted_workbench.py` proved an already running API/frontend workbench, but it could pass against the default `config/default.yaml` fixture runtime. That is valid hosted-runtime proof, but unsafe if a release note describes the deployment as production-configured.
  - Red: `python3 -m pytest tests/deployment/test_hosted_workbench_smoke.py::test_hosted_workbench_smoke_rejects_fixture_config_when_prod_config_required tests/deployment/test_hosted_workbench_smoke.py::test_hosted_workbench_smoke_accepts_prod_config_with_explicit_runtime_boundary -q` failed while `run_smoke()` did not accept `require_prod_config`.
  - Green: the same focused pytest passed after `smoke_hosted_workbench.py` added `--require-prod-config` / `require_prod_config=True`. The strict mode now rejects fixture/default production claims unless `/api/system/config` reports `decision.engine=openai_compatible`, `decision.candidate_sidecar_mode=disabled`, `market_data.provider=okx_public`, `notification.enabled=true`, `macro_event.provider=no_active_event`, `workflow.execution_mode=legacy_baseline`, and `readiness.prod_actionable.status=ready`.
  - Red: `python3 -m pytest tests/deployment/test_container_config_commands.py::test_deployment_docs_describe_hosted_workbench_services -q` failed while deployment docs did not mention `--require-prod-config`.
  - Documentation update: `docs/deployment.md` now separates the default hosted runtime smoke (`production_config_required=false`, can pass against fixture) from strict production-config smoke (`--require-prod-config`, must output `production_config_required=true` and `production_config_ready=true`).
  - Boundary: this still does not prove production success. It prevents hosted-runtime proof from being mislabeled as production-config proof. Real production still requires strict external `--prod-actionable --fail-on-skip`, Bark `sent`, real public OpenAI-compatible endpoint, real OKX public data, and real exchange-native matured outcome evidence.
- [x] 2026-07-09 verification after default product model/evidence projection and notification consistency:
  - UI/UX audit gap: `/manual-run` and `/runs/{trace_id}` had `business_summary.generation_summary` and `evidence_bullets` in the contract, but the default product path still made users infer model/provider/evidence from the generic `生成链路` block or diagnostic/raw views.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop tests/e2e/full-stack-visual.spec.ts -g "manual run async flow"` failed while the manual-run success panel had no `模型返回摘要`.
  - Green: the same focused Playwright command passed after adding shared `GenerationSummaryPanel` / `EvidenceSummaryPanel` and rendering them in both `/manual-run` success and `/runs/{trace_id}` default summary. The panels show model status, interface, model name, duration, token count, finish reason, response summary, and evidence bullets while still rejecting `request_json`, `response_json`, `choices`, `chat.completion`, `Bearer`, and `api_key`.
  - UI/UX audit gap: `NotificationHistory` could show `暂无通知记录` plus a vague `通知记录待同步` even when the latest projected status was `sent` or `failed`.
  - Red: `python3 -m pytest tests/structure/test_frontend_route_states.py::test_notification_history_empty_latest_status_copy_is_consistent -q` failed while the component lacked `最新状态：Bark 已发送` / `最新状态：发送失败` empty-history copy.
  - Green: the same focused structure test passed after the empty-history state began showing the latest projected status and `发送明细待同步` instead of implying there was no known notification status.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `python3 -m pytest tests/structure/test_frontend_route_states.py tests/deployment/test_hosted_workbench_smoke.py tests/deployment/test_container_config_commands.py::test_deployment_docs_describe_hosted_workbench_services -q` passed 9/9.
  - Green: `npm --prefix frontend run e2e` passed 28/28 with 2 opt-in Server Component fault tests skipped under the default local stack profile, across Chromium desktop and mobile.
  - Boundary: this is product rendering and local browser proof. It does not prove a real external model, real OKX public data, Bark `sent`, or production success.
- [x] 2026-07-09 user-directed three-agent status reconciliation:
  - Architecture Agent conclusion: `docs/formal/00` and `docs/formal/37` are still the correct direction authority, and the current code is centered on `manual request -> RunExecutor -> LegacyPlanRunnerAdapter -> LegacyDecisionWorkflow -> parser/gates -> journal/notification`. `production_candidate_swarm` remains audit-only/blocked and must not become the manual-alert main path.
  - Architecture Agent also found that some `docs/formal/37` findings are now stale: the earlier pytest failures, missing manual-run price levels, and missing H1 warning in public docs have been addressed. Treat `formal/37` as direction authority, not as a fully current defect list.
  - UI/UX Agent conclusion: default `/`, `/manual-run`, `/runs`, `/runs/{trace_id}`, `/config`, and default `/eval` are no longer JSON-first. Remaining no-secret P0/P1 UX risks are partial run-detail projection fallback, mobile detail deep-scroll coverage, and long-running async submit states.
  - QA Agent conclusion: the local matrix uses real FastAPI, production Next, Chromium, SQLite journal/eval stores, DOM/visual scans, and console/request failure collection. It proves local/manual-only closure and staged allowed-path rendering; it does not prove production success.
  - Migration root cause for earlier "done but not delivered" work: many checkpoints proved sidecar/eval/fixture/mock wiring, not a production manual-alert artifact. Going forward each checkpoint must label its proof level (`local`, `fixture`, `mock`, `staging`, `hosted-runtime`, `prod-actionable`, `real-outcome`) and must not describe wiring proof as production delivery.
- [x] 2026-07-09 verification after run-detail partial-projection fallback:
  - UI/UX audit gap: manual-run immediate responses had a product fallback when `business_summary` or `result_review` was missing, but `/runs/{trace_id}` detail still treated missing display projections as an invalid response and collapsed to `提醒详情暂时无法加载`.
  - Red: `PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "run detail partial projection"` failed while the page did not render the `提醒建议摘要` region for a partial run-detail response from the 8013 internal fault API.
  - Green: the same Playwright command passed after `runDetailSchema` reused the manual-run fallback projection for missing `plan_run.business_summary` and `result_review`. The detail page now keeps the core trace/plan/verdict visible as `摘要暂不可用`, `核心提醒已返回`, `模型返回摘要`, and `结果尚未生成` instead of showing a generic error.
  - Green: `PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "Server Component"` passed 2/2, covering both eval Server Component GET failures and the partial run-detail fallback.
  - Green: `python3 -m pytest tests/local_stack/test_scripts.py::test_mock_error_api_server_returns_unsafe_envelope_for_redaction_tests tests/local_stack/test_scripts.py::test_mock_error_api_server_returns_partial_run_detail_projection_fixture -q` passed. The 8013 fault API now has a stable fixture for "core run detail present, display projections missing".
  - Green: `npm --prefix frontend run typecheck` passed.
  - Boundary: this is a frontend degradation path for mixed-version/partial responses. Backend/API/CLI tests should still fail loudly when the current production contract stops generating `business_summary` or `result_review`.
- [x] 2026-07-09 verification after projection redaction and production-gate tightening:
  - Code-review gap: fallback projections were sanitized, but a fully valid `business_summary`, `result_review`, or product-visible agent audit reason could still carry unsafe backend text if the upstream projection itself contained paths, request payload labels, Bark device-key hints, bearer/API-key fragments, SQLite/internal errors, or trace IDs.
  - Green: `businessSummarySchema`, `resultReviewSchema`, manual-run verdict parsing, run-detail fallback, run-list optional projections, and product-visible `agent_audit_view` reason paths now pass through safe product-copy projection. Bad optional run-list projections are ignored instead of hiding the run; bad detail projections fall back only when the core `trace` / `parsed_plan` / `verdict` evidence exists.
  - Green: `npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts` passed 10/10, covering valid projection sanitization, bad business-summary shapes, verdict reason redaction, agent-audit reason redaction, and run-list optional projection tolerance.
  - Green: `npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts` passed 6/6 with 2 opt-in Server Component fault tests skipped under the default profile. The opt-in fault profile remains separate so default product tests do not depend on the 8013 internal fault API.
  - Green: `PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "Server Component"` passed 2/2, covering Server Component error handling and partial run-detail fallback through a real production Next server with `API_INTERNAL_BASE_URL` pointed at the fault API.
  - Architecture gate gap: hosted strict smoke previously required production-shaped readiness, but did not explicitly reject a production-configured runtime whose `decision.final_input_mode` drifted away from `legacy_prompt`.
  - Green: `tools/deployment/smoke_hosted_workbench.py --require-prod-config` now requires `decision.final_input_mode=legacy_prompt` in addition to `decision.engine=openai_compatible`, `decision.candidate_sidecar_mode=disabled`, `market_data.provider=okx_public`, `notification.enabled=true`, `macro_event.provider=no_active_event`, `workflow.execution_mode=legacy_baseline`, and `readiness.prod_actionable.status=ready`.
  - Architecture gate gap: `MACRO_EVENT_VALID_UNTIL` existed as metadata, but production readiness only checked presence, so a stale no-active-event assertion could be replayed after it expired.
  - Green: config loading and strict local prod-actionable smoke now require timezone-aware `MACRO_EVENT_VALID_UNTIL`, require it to be later than `MACRO_EVENT_CONFIRMED_AT`, and require it to still be in the future when `MACRO_EVENT_PROVIDER=no_active_event`.
  - Green: `python3 -m pytest tests/config/test_config.py tests/local_stack/test_scripts.py::test_mock_error_api_server_returns_partial_run_detail_projection_fixture tests/local_stack/test_scripts.py::test_local_smoke_api_env_enables_prod_actionable_when_ready tests/local_stack/test_scripts.py::test_local_smoke_prod_actionable_rejects_expired_event_assertion tests/deployment/test_hosted_workbench_smoke.py -q` passed 46/46 with 1 warning.
  - Boundary: these are product-safety and release-gate hardenings. They do not prove a real external production alert; they prevent stale assertions, unsafe text, and non-legacy final-input modes from being mislabeled as production-ready.
- [x] 2026-07-09 verification after eval row-content redaction and staging proof-boundary copy:
  - UI/UX audit gap: eval diagnostic tables sanitized load-failure messages, but normal row data such as candidate `expected_behavior` / `actual_behavior`, judge `reason_summary`, evidence refs, and replay result action could still render backend paths, trace IDs, Bark/device key hints, bearer/API-key fragments, SQLite errors, or Windows/macOS/Linux file paths.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts -g "eval diagnostic table row text"` failed because the expected row-text projection helpers did not exist and the table rendered raw row values.
  - Green: the same focused Playwright test passed after eval table row projection was routed through shared safe display copy. `safe-error.ts` now recognizes `/Users/...`, `/var/...`, Windows paths, and `Authorization: Basic/Bearer` in addition to the existing SQL/path/trace/payload/Bark/API-key patterns.
  - Green: `npm --prefix frontend run typecheck` passed.
  - Green: `npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts` passed 11/11.
  - Architecture audit gap: `default+staging` can intentionally reach `allowed=true` as local wiring proof, but the primary `business_summary.mode_notice` did not say strongly enough that this is not production success when `MACRO_EVENT_PROVIDER=no_active_event` lacks complete operator assertion metadata.
  - Red: `python3 -m pytest tests/storage/test_business_summary.py::test_business_summary_labels_staging_actionable_result_as_manual_review -q` failed while the summary said only that the manual-review threshold was satisfied.
  - Green: the same focused test passed after `_mode_notice()` added explicit `本地/预发证明，不是生产成功` copy for incomplete `no_active_event` metadata.
  - Red: `python3 -m pytest tests/api/test_runs_routes.py::test_manual_run_staging_actionable_path_allows_manual_review_without_auto_order -q` then failed, showing a deeper projection bug: the API persisted/read-back `business_summary` was generated without the current `Config`, so the staging proof boundary was visible in builder tests but not in the real manual-run API response or detail projection.
  - Green: the API test passed after `JournalQueryRepository`, `Journal.get_trace_detail()`, `Journal.list_traces()`, and `journal_rows.plan_run_row()` began carrying a read-only projection config into `build_business_summary()`. API, list/detail projection, and CLI trace/run-once detail projection now use the same config-aware summary boundary.
  - Green: `python3 -m pytest tests/storage/test_query_repository.py tests/storage/test_business_summary.py -q` passed 11/11, and `python3 -m pytest tests/cli/test_runner_cli.py::test_cli_show_config_redacts tests/api/test_runs_routes.py::test_manual_run_response_uses_persisted_business_summary -q` passed 2/2.
  - Boundary: staging `allowed=true` remains a local/no-secret wiring proof. The code now makes that proof level visible in product copy instead of changing the underlying staging facts-gate behavior. Strict production proof still requires real external `--prod-actionable --fail-on-skip`, Bark `sent`, real public OpenAI-compatible endpoint, real OKX public data, unexpired complete event assertion metadata, `decision.final_input_mode=legacy_prompt`, `candidate_sidecar_mode=disabled`, and `workflow.execution_mode=legacy_baseline`.
- [x] 2026-07-09 final review follow-up after proof-boundary copy:
  - Code-review gap: eval table row projection still sanitized the major free-text cells but left several "looks like enum" fields raw: candidate `category`, candidate `eval_dataset_name`, judge `judge_name`, judge `judge_type`, and especially LLM-provided `failure_category`.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts -g "eval diagnostic table row text|shared error copy"` failed because `evalCandidateCategoryText()` / `evalCandidateDatasetText()` / `evalJudgeFailureCategoryText()` did not exist, and `safeDisplayError("321 tokens")` was incorrectly hidden by a bare `token` unsafe rule.
  - Green: the same focused Playwright command passed after eval label projection mapped known eval/judge/category values to product copy, unknown values fell back through safe display, and `token` matching was narrowed to secret-shaped contexts such as `token=...` while allowing ordinary telemetry like `321 tokens`.
  - Final review gap: judge `severity` was still raw, and a real LLM judge can provide arbitrary severity text. Candidate `severity` / `status` were also product-visible persistent strings.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts -g "eval diagnostic table row text"` failed because `evalCandidateSeverityText()` did not exist after adding unsafe severity/status coverage.
  - Green: the same focused Playwright test passed after candidate severity/status and judge severity were routed through `safeEvalLabel()`. Known values such as `high`, `critical`, and `open` now render as product labels; unsafe unknown text falls back to safe copy.
  - Code-review gap: `business_summary` could still classify a config-aware allowed run as `actionable_manual_review` before proving persisted real external evidence existed. That made "config looks production-shaped" too easy to read as "production success".
  - Red: `python3 -m pytest tests/storage/test_business_summary.py -q` failed on new cases for prod+staging with complete config but no persisted `llm_summary`, failed LLM status, and failed Bark notification.
  - Green: the same storage test file passed 12/12 after `business_summary` split `actionable_local_proof` from `actionable_manual_review`. True `actionable_manual_review` now requires persisted successful real LLM evidence, real OKX public market evidence, complete unexpired `no_active_event` assertion, Bark `sent`, and strict config readiness; otherwise the primary summary says `本地/预发证明（人工复核门槛）` and `不是生产成功`, listing the missing proof.
  - Green: `python3 -m pytest tests/storage/test_business_summary.py tests/storage/test_query_repository.py tests/api/test_runs_routes.py tests/cli/test_runner_cli.py tests/api/test_eval_routes.py -q` passed 98/98 with 2 warnings.
  - Green: `npm --prefix frontend run typecheck` passed, and `npm --prefix frontend run e2e -- --project=chromium-desktop product-copy.spec.ts` passed 11/11.
  - Boundary: `decision_label` may still be `可人工复核` when gates allow manual review, but the primary `mode_notice` no longer says the full production threshold is satisfied unless persisted external evidence and notification proof are present.
- [x] 2026-07-09 latest no-secret full local matrix:
  - Green: `python3 tools/local_stack/run_local_checks.py` exited `0`.
  - It ran Python full pytest (`1054 passed, 2 warnings`), frontend typecheck, frontend production build, Playwright browser checks (`46 passed`, `4 skipped` opt-in Server Component fault tests), fixture smoke, mock LLM smoke, actionable staging smoke, seeded mock-outcome smoke, and collect-outcomes fixture smoke.
  - Green: `PLAYWRIGHT_EXPECT_INTERNAL_API_ERRORS=true PLAYWRIGHT_LOCAL_STACK_FLAGS="--seed-mock-outcome --with-error-internal-api" npm --prefix frontend run e2e -- --project=chromium-desktop error-states.spec.ts -g "Server Component"` passed 2/2, covering the default-skipped Server Component fault profile through the 8013 internal fault API.
  - No-secret proof boundaries remained explicit: fixture and mock LLM prove local/product rendering and LLM client wiring; actionable staging proves the allowed manual-review path with local mock OKX; seeded mock outcome proves product visibility only; collect-outcomes fixture proves collector wiring with mock OKX and reports `real_financial_quality_proven=false`.
  - Expected block: `python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip` exited `2` with `skip_reason=missing_readiness`, missing `BARK_DEVICE_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `MACRO_EVENT_PROVIDER=no_active_event`. This remains the honest production blocker, not production success.
  - Green: `lsof -ti tcp:8010 -ti tcp:3001 -ti tcp:8011 -ti tcp:8012 -ti tcp:8013` returned no listeners after cleanup.
- [x] 2026-07-09 user-directed multi-agent reconciliation and P1 browser evidence follow-up:
  - Architecture Agent reconfirmed that the main path is still manual-only and centered on `POST /api/runs/manual -> RunExecutor -> LegacyPlanRunnerAdapter -> LegacyDecisionWorkflow -> parser/gates -> journal/notification projection`; AgentSwarm/candidate/eval remain audit/eval/sidecar unless explicitly enabled as diagnostic mode.
  - UI/UX Agent reconfirmed that the default product routes are not JSON-first; the remaining frontend proof gaps were mobile run-detail deep-scroll and long-running async submit states.
  - QA Agent reconfirmed that the local Playwright matrix uses real FastAPI, production Next, Chromium, SQLite stores, DOM scans, and screenshot checks, but it is still local/mock/staging proof rather than production success.
  - Docker/hosted runtime attempt: `API_PORT=18010 FRONTEND_PORT=13001 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:18010 PYTHON_BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim NODE_BASE_IMAGE=public.ecr.aws/docker/library/node:22-alpine docker compose -p crypto-alert-runtime-smoke up -d --build api frontend` successfully built both API and frontend images, including frontend production `next build`.
  - Docker blocker evidence: after image build, containers remained in `Created`; `docker start crypto-alert-runtime-smoke-api-1`, `docker inspect`, `docker run --rm public.ecr.aws/docker/library/alpine:3.20 ...`, and `docker compose down --remove-orphans` all hung or returned interrupted Docker socket requests. A minimal Alpine container also stuck at `Created`, so this is a Docker Desktop/container-start runtime blocker, not application healthcheck success and not application-code proof.
  - Docker retry after runtime recovery: `docker run --rm public.ecr.aws/docker/library/alpine:3.20 sh -c 'echo docker-minimal-ok'` returned `docker-minimal-ok`; the same `docker compose -p crypto-alert-runtime-smoke up -d --build api frontend` then built and started API/frontend containers, both reached healthy state on isolated ports `18010/13001`.
  - Hosted-runtime smoke: `python3 tools/deployment/smoke_hosted_workbench.py --api-base http://127.0.0.1:18010 --frontend-base http://127.0.0.1:13001 --symbol ETH-USDT-SWAP --query "Docker hosted runtime smoke：验证容器工作台人工提醒入口" --horizon 6h` exited `0` with `smoke_profile=hosted_workbench`, `hosted_runtime_only_not_prod_actionable=true`, `decision_engine=fixture`, `market_provider=fixture`, `decision_final_input_mode=legacy_prompt`, `manual_execution_required=true`, and `auto_order_enabled=false`.
  - Strict hosted config negative smoke: the same hosted runtime with `--require-prod-config` exited `1` and rejected the default fixture config with `production config requires decision.engine=openai_compatible`. This proves default Docker hosted-runtime cannot be mislabeled `prod-config`.
  - Cleanup: `API_PORT=18010 FRONTEND_PORT=13001 docker compose -p crypto-alert-runtime-smoke down --remove-orphans` removed the API/frontend containers and compose network; ports `18010/13001` had no leftover listeners.
  - Red: `npm --prefix frontend run e2e -- --project=chromium-desktop async-and-mobile-depth.spec.ts -g "delayed responses"` failed because `/manual-run` disabled the submit button but had no visible `role=status` progress region for a long-running request.
  - Green: the same focused Playwright command passed after `/manual-run` and `/eval?tab=runs` added visible progress states with disabled duplicate-submit controls, and the DOM audit helper gained an immediate scan path that does not wait for `networkidle`.
  - Green: `npm --prefix frontend run e2e -- --project=chromium-mobile async-and-mobile-depth.spec.ts -g "mobile run detail deep-scroll"` passed, covering a real local `POST /api/runs/manual` seed followed by mobile `/runs/{trace_id}` deep-scroll checks for `提醒建议摘要`, `模型返回摘要`, `证据摘要`, `复核状态摘要`, `后续复盘`, and `通知历史`.
  - Red: `npm --prefix frontend run e2e` initially failed on mobile during the delayed eval pending-state DOM scan because an eval-run table link had a `113x16` click target.
  - Green: the focused mobile delayed-response test passed after `.table-wrap a` gained a `32px` minimum hit target, and the full frontend Playwright suite then passed `44 passed, 4 skipped`.
  - Boundary: this closes no-secret UX/QA proof gaps and the default Docker hosted-runtime smoke only. The Docker smoke is fixture hosted-runtime proof, not production success. Production success still requires the real external `--prod-actionable --fail-on-skip` evidence chain, production-intent hosted config with real readiness, and real exchange-native matured outcome evidence.

---

## 7. Execution Order

Recommended order for the next implementation pass:

1. Run the strict real external prod-actionable gate only after real `BARK_DEVICE_KEY`, public HTTPS OpenAI-compatible endpoint/model/key, real OKX public network, `MACRO_EVENT_PROVIDER=no_active_event`, `MACRO_EVENT_OPERATOR_REF`, `MACRO_EVENT_CONFIRMED_AT`, `MACRO_EVENT_SOURCE_REF`, `MACRO_EVENT_ASSERTION_HORIZON`, unexpired `MACRO_EVENT_VALID_UNTIL`, `DECISION_FINAL_INPUT_MODE=legacy_prompt`, `CANDIDATE_SIDECAR_MODE=disabled`, and `WORKFLOW_EXECUTION_MODE=legacy_baseline` are available.
2. Collect at least one real exchange-native matured outcome with `collect-outcomes`, then prove it through `python3 tools/deployment/smoke_real_outcome_evidence.py --api-base <deployed-api>`; keep mocked outcomes labeled `visibility_only_not_financial_quality`.
3. For any production deployment claim, run hosted-workbench smoke on the target server or equivalent Docker environment with the production-intent env profile: `api` health, frontend render, `POST /api/runs/manual -> /runs/{trace_id}`, `tools/deployment/smoke_hosted_workbench.py --require-prod-config`, and the strict external gate. The 2026-07-09 local Docker retry closed default fixture `hosted-runtime` proof, but it did not close production-intent hosted proof. Do not count hosted smoke as prod-actionable success unless the strict external gate also passes.
4. Decide a separate P1 design for free-form query intent if query text should drive required facts/final input instead of remaining an audit note.
5. Keep per-run replay/outcome visibility as a maintained product contract across API, frontend, and CLI. The remaining blocker is not UI visibility; it is collecting at least one real exchange-native matured outcome and keeping mock/local evidence labeled as non-financial-quality proof.
6. Continue productizing or explicitly diagnostic-gating remaining engineering surfaces. The default `/eval` and eval-run detail are now gated, and raw payload APIs now require `DIAGNOSTIC_ROUTES_ENABLED=true`; non-quality eval tabs and raw/matrix pages still intentionally expose engineering review controls.
7. Only after the above should broader Agent Swarm/candidate/eval platform expansion resume.

The main line is: **user query -> readable manual alert -> safety/readiness proof -> notification -> replay/outcome**, not "more sidecar panels".

Current open checklist:

- [ ] Real external prod-actionable smoke succeeds with real public OpenAI-compatible endpoint, real OKX public data, Bark `sent`, `MACRO_EVENT_PROVIDER=no_active_event` plus complete unexpired operator assertion metadata, `allowed=true`, `decision.final_input_mode=legacy_prompt`, `candidate_sidecar_mode=disabled`, `workflow.execution_mode=legacy_baseline`, `manual_execution_required=true`, and `auto_order_enabled=false`.
- [ ] At least one real exchange-native matured outcome is collected from a real historical window and passes `tools/deployment/smoke_real_outcome_evidence.py`.
- [x] Default fixture Docker/hosted-runtime smoke completes after an actual `docker compose up -d --build api frontend`, not only `docker compose config`.
  - 2026-07-09 first attempt with ECR base images built API/frontend images, but Docker Desktop left API/frontend and a minimal Alpine diagnostic container in `Created`; this was recorded as a container-start runtime blocker, not application proof.
  - 2026-07-09 retry after Docker runtime recovery completed: API/frontend containers reached healthy state on `18010/13001`; `tools/deployment/smoke_hosted_workbench.py` exited `0` with `hosted_runtime_only_not_prod_actionable=true`, `decision_engine=fixture`, and `market_provider=fixture`; strict `--require-prod-config` exited `1` against the same default fixture container, correctly rejecting it as not production-configured.
  - Proof level: `hosted-runtime` only, not `prod-config`, not `prod-actionable`, and not `real-outcome`.
- [ ] Production-intent hosted runtime passes with a filled `.env.production.example` profile, `tools/deployment/smoke_hosted_workbench.py --require-prod-config`, and strict `tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip`.
- [x] Explicit production config-path handling is made fail-fast so a typo in `CONFIG_PATHS` cannot silently fall back to default/fixture behavior.
- [x] `MACRO_EVENT_PROVIDER=no_active_event` is now an auditable operator assertion artifact with operator/source/horizon/validity metadata, and strict prod-actionable readiness fails when the metadata is missing.
- [x] `MACRO_EVENT_VALID_UNTIL` must be timezone-aware, later than `MACRO_EVENT_CONFIRMED_AT`, and still in the future for `MACRO_EVENT_PROVIDER=no_active_event`; stale no-active-event assertions are rejected by config loading and strict local prod-actionable smoke.
- [x] Diagnostic/raw API routes now have an environment boundary: `include_payloads=true`, `mode=judge_openai`, eval run detail, and eval promotion artifacts return `403 diagnostic_routes_disabled` unless `DIAGNOSTIC_ROUTES_ENABLED=true`; default eval run create/list summaries expose only product-safe `financial_quality_gate` metadata.
- [x] Raw/matrix diagnostic UI becomes summary-first and `JsonDetails` gains a defensive redaction layer before any shared-user deployment.
- [x] Manual-run success and run detail summary expose a product-facing generation chain summary: fixture/mock/real model mode, model name/status, provider/interface, duration, token count, finish reason, response summary, and Bark status without raw `request_json` / `response_json`.
- [x] Manual-run success and run detail summary expose product-facing evidence bullets, so users can see what行情/事件/数据 evidence supported the alert without opening raw JSON.
- [x] Notification history keeps latest status consistent with history rows: if the latest projection is `sent` or `failed` but rows are not present, the empty state says `最新状态：Bark 已发送/发送失败，发送明细待同步`.
- [x] Product error states are sanitized with Playwright route-level failure coverage for API 500, invalid envelope, network abort, and eval list failure.
  - 2026-07-09 complete: API 500 / invalid envelope / network abort route-level browser coverage is in place for client-side POST flows, eval diagnostic list/table failure messages are component-covered, and Server Component first-load GET failures for `/eval?tab=runs|cases|quality` are covered through `start_local_stack.py --with-error-internal-api` and the 8013 mock internal fault API.
- [x] Manual-run partial-success responses keep the main flow readable when the core `trace_id` / `plan` / `verdict` is present but the display projection is missing or malformed.
  - 2026-07-09 complete: the frontend renders a clearly labeled fallback alert summary, result-review empty state, notification-not-recorded state, and details link instead of collapsing to a generic failure. Backend current-contract projection gaps still fail loudly in API/CLI tests.
- [x] Run-detail partial-success responses keep the persisted core alert readable when `trace`, `plan_run.parsed_plan`, and `plan_run.verdict` exist but display projections are missing.
  - 2026-07-09 complete: the detail page reuses the manual-run fallback projection and renders `摘要暂不可用`, `核心提醒已返回`, `模型返回摘要`, `证据摘要`, `结果尚未生成`, and notification empty state instead of a generic details load error.
- [x] Fully valid `business_summary` / `result_review` projections and product-visible agent-audit reasons are sanitized before rendering; unsafe paths, trace IDs, payload labels, Bark keys, bearer/API-key fragments, SQLite errors, and stack traces are replaced with safe product copy.
- [x] Eval diagnostic table row content is sanitized before rendering normal data rows; candidate expected/actual behavior, judge reason/evidence, observed/replay action text, and shared error copy hide backend paths, trace/payload labels, Bark/device key hints, bearer/API-key fragments, SQLite errors, and macOS/Linux/Windows file paths.
- [x] Eval diagnostic enum-like row content is product-projected before rendering; candidate category/dataset/severity/status and judge name/type/severity/failure category use closed labels or safe fallback, and ordinary model telemetry such as `321 tokens` is no longer hidden as a false secret.
- [x] `/api/runs` list projection tolerates bad optional `business_summary` / `result_review` values without hiding the run; malformed optional projections are dropped or fallback-rendered rather than collapsing the product history.
- [x] Staging/actionable local proof has a product-visible boundary: incomplete `no_active_event` metadata yields `本地/预发证明，不是生产成功` in persisted API/CLI business summaries, while strict production proof remains gated by complete unexpired event assertion metadata and real external dependencies.
- [x] `business_summary` no longer upgrades config-shaped allowed runs to full `actionable_manual_review` without persisted external proof; missing real LLM success, real OKX evidence, complete unexpired event assertion, Bark `sent`, or strict readiness is shown as `本地/预发证明（人工复核门槛）`, not production success.
- [x] Production/hosted workbench config is verified so `/api/runs/manual` does not silently run fixture defaults when the deployment is being described as production.
  - 2026-07-09 complete: `tools/deployment/smoke_hosted_workbench.py --require-prod-config` rejects default fixture hosted runtimes and requires explicit production-intent config/readiness before submitting the manual run. It now also requires `decision.final_input_mode=legacy_prompt`, so strict hosted smoke cannot validate a candidate-final or decision-input side path as the MVP production final input. Default hosted runtime smoke remains available but is labeled `hosted_runtime_only_not_prod_actionable=true`.
- [ ] Production environment keeps `workflow.execution_mode=legacy_baseline`; `production_candidate_swarm` remains an explicit diagnostic/audit mode and cannot be used as the manual alert main path.
- [ ] Query intent remains honestly labeled as `audit_note`, or a separate P1 design makes it drive facts/final input with tests.
- [x] Mobile run-detail deep-scroll coverage verifies summary, result review, notification history, and review status across top/middle/bottom scroll points.
  - 2026-07-09 complete: `frontend/tests/e2e/async-and-mobile-depth.spec.ts` creates a real local manual run, opens `/runs/{trace_id}` on the mobile project, and scans top/middle/bottom plus summary/review/notification/status modules.
- [x] Long-running manual-run/eval async states have browser coverage for visible progress, disabled duplicate-submit controls, and no layout/DOM defects during delayed responses.
  - 2026-07-09 complete: delayed Playwright route coverage verifies `/manual-run` and `/eval?tab=runs` show `role=status` progress, disable duplicate submits, avoid layout/DOM audit issues during the pending request, and resolve back to normal success states.
