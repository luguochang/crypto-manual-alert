# Checkpoint: 修绿失败测试 + 配置文档对齐（Phase 0.2 / 0.3）

日期：2026-07-06
对应：`docs/formal/37` §5.2 H7（测试红）、M6（配置文档落差）
计划：`.tmp/optimization-plan.md` Phase 0.2 / 0.3

## Phase 0.2 修绿 6 个失败测试

6 个失败全是夹具漂移（测试断言旧契约，生产行为已正确演进），不是生产 bug。逐个更新断言匹配当前契约，保留测试意图，不改生产行为。

### test_shadow_orchestration.py（2 个）

- `test_run_shadow_swarm_audit_returns_failed_payload_when_llm_worker_mode_has_no_client`：`llm_tool_shadow` + 无 client + **fixture** engine 现在回退到 fixture shadow client（不再 fail）。为保留"misconfiguration 必须 fail-closed"的意图，改用 `openai_compatible` engine（非 fixture）+ 无 client → registry 抛 `WorkerRegistryConfigurationError` → failed payload。
- `test_run_shadow_swarm_audit_runs_llm_tool_workers_with_explicit_client_factory`：`LiveFactAgent` 现在也是 LLM tool shadow worker（不再用 local_audit）。`requested_agents` 更新为 `[LiveFactAgent, RootCauseAgent, MarketSentimentAgent, DataQualityAgent, ExecutionRiskAgent]`（5 个 LLM worker）；`by_agent` 中仅 `DerivativesAgent`/`MacroEventAgent` 保持 `shadow_swarm`，其余为 `llm_tool_shadow_worker`。

### test_artifacts.py（1 个）

- `test_record_orchestration_artifacts_writes_only_controlled_context_sections`：`gate_result_refs.candidate_final_decision` 现在含 `production_final_input: False` 字段（`_input_ref` 提取该键）。expected 补该字段；hash 仍为 `stable_hash(candidate_audit["candidate_final_decision"])`，核对一致。

### test_replayable_input.py（1 个）

- `test_replayable_input_candidate_records_telemetry_refs_without_raw_payloads`：`span_refs` 现在为有 `input_summary` 的 span 附带 `span_input_hash` + `input_refs`（`_span_refs` 演进）。exact-match 改为保意图的结构断言：基础 6 字段 + `span_input_hash` 存在 + raw prompt 不泄露。raw-payload 泄露断言（`str(candidate)` 不含 raw prompt/secret/model text）保持不变。

### test_scripts.py（local_stack，2 个）

- `test_local_smoke_asserts_agent_audit_view_contract`：mock audit 补齐 `_assert_agent_audit_view` 现在要求的字段：`tool_calls`/`evidence_sources`/`source_freshness`/`conflict_edges`（list）+ `root_cause_graph`（nodes/edges）+ `input_lineage`（`production_final_input_mode=legacy_prompt`）+ `release_eval_gate`（`financial_quality_gate.status=not_configured`）。
- `test_local_smoke_asserts_frontend_agent_audit_text`：body 字符串补齐 `_assert_frontend_agent_audit_html` 检查的全部 14 个 token（原 body 缺 `Worker Matrix`/`Skill Tool Calls`/`Source Freshness`/`Root Cause Graph`/`Conflict Matrix`/`Candidate Comparison`/`Input Lineage`/`Release And Gates`）。负例用 `full_body.replace(...)` 移除单 token 验证报错。

## Phase 0.3 配置与文档对齐

- `.env.example`：`SCHEDULER_ENABLED=false`（与 `default.yaml:54` 一致；scheduler 仅经 CLI 子命令运行，API 服务不内置）；新增 `MACRO_EVENT_PROVIDER=disabled`。
- `docs/deployment.md`：新增"风控门禁与可执行提醒（facts_gate）"章节，说明执行事实（mark/index/order_book 需 exchange_native）+ 事件事实（active_event_status 需 event_pool/official）两道门，以及 default/staging/prod 三种配置的放行行为。
- `config/loader.py`：`MACRO_EVENT_PROVIDER` env 覆盖（与文档一致）。

## 改动文件

- `tests/agent_swarm/test_shadow_orchestration.py`
- `tests/context/test_artifacts.py`
- `tests/decision/test_replayable_input.py`
- `tests/local_stack/test_scripts.py`
- `.env.example`
- `docs/deployment.md`（Phase 0.1 已改，0.3 复用）
- `src/crypto_manual_alert/config/loader.py`（MACRO_EVENT_PROVIDER env）

## 验收

```powershell
python -m pytest -q --ignore=tests/local_stack   # 全绿，exit_code 0
python -m pytest tests/local_stack/test_scripts.py -q   # 全绿
```

全量套件（除 local_stack 需服务器部分）通过，无回归。6 个原失败全部转绿，且 diff 只含测试夹具 + 配置/文档，未改生产行为（除 0.1 的 provider 注入与 event_status 已在前一个 checkpoint 完成）。

## 不变约束维持

- 未为让测试通过而关闭任何 gate。
- 未默认启用真实 provider/LLM。
- 生产行为未为迁就旧测试而回退。

## 剩余

- Phase 1.1：manual-run 成功页直显 entry/stop/target/probability。
- Phase 1.2：Run Detail 首屏决策摘要卡。
- Phase 2.1：outcome collector。
