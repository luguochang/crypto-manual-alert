# Checkpoint 7: llm_tool_shadow skill artifact slice

日期：2026-07-05

## 目标

让 `shadow.worker_mode=llm_tool_shadow` 在本地 fixture 决策引擎下可走通主 API 链路，并产出可由页面/API 观察到的真实 `ToolCallArtifact`。该切片只验证 Worker -> SkillExecutor -> ToolCallArtifact -> agent_audit_view，不启用生产外部 LLM，不切换生产 final input。

## 改动

- `src/crypto_manual_alert/agent_swarm/shadow_llm_client.py`
  - 增加 deterministic fixture shadow client factory。
  - fixture worker 响应通过 `skill_requests` 请求业务 skill。
- `src/crypto_manual_alert/agent_swarm/registry.py`
  - 显式 `llm_client_factory` 仍然优先。
  - 没有显式 factory 时，仅 `decision.engine=fixture` 可自动使用 fixture shadow client。
  - 非 fixture 引擎继续拒绝 config-only `llm_tool_shadow`，避免误开外部 LLM。
- `tests/api/test_runs_routes.py`
  - 增加 API 主链路测试，验证 `/api/runs/manual` 后 `agent_audit_view.tool_calls[]` 投影出业务 skill。

## 验证

```powershell
python -m pytest tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls -q
python -m pytest tests/api/test_runs_routes.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_llm_tool_worker.py -q
```

结果：

- 聚焦 API 测试通过。
- 小范围回归：30 passed。

临时主链路 smoke：

```json
{
  "trace_id": "9c65bdc62c40485c81d21f9a60569700",
  "workers": 7,
  "tool_calls": [
    "root_cause_search",
    "market_sentiment",
    "liquidity_order_book"
  ],
  "execution_fact_tool_calls": [
    "liquidity_order_book"
  ]
}
```

## 边界

- 默认 `config/default.yaml` 仍为 `shadow.worker_mode=local_audit`。
- 默认 `decision.final_input_mode` 未改成 `decision_input`。
- 该切片没有接入真实 web search provider。
- 该切片没有接入真实外部 LLM。
- `liquidity_order_book` 当前仍走 fixture/adapter 层，但已经通过 `SkillExecutor` 形成 execution fact 类型的 artifact。

## 后续

- 按业务能力拆分 `skills/facade.py` 到 skill package。
- 为 `root_cause_search` 增加受控递归策略。
- 为 `realtime_search` 增加可注入 web search provider。
- 为 `liquidity_order_book` 增加真实 exchange-native provider 或明确的 exchange fixture adapter 边界。
