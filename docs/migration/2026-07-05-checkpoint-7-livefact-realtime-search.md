# Checkpoint 7: LiveFactAgent realtime_search tool artifact

日期：2026-07-05

## 目标

让 `llm_tool_shadow` 模式下的 `LiveFactAgent` 也进入受控 Worker -> SkillExecutor -> ToolCallArtifact 链路，避免实时事实层仍停留在 local audit。该切片仍然是 audit-only，不启用外部网络，不改变默认生产 final input。

## 改动

- `src/crypto_manual_alert/skills/realtime_search/providers.py`
  - 增加 `SearchProviderRequest`。
  - 增加 `SearchProvider` 协议。
- `src/crypto_manual_alert/skills/realtime_search/skill.py`
  - 支持注入 provider。
  - 没有 provider 时仍使用 `input_view.search_results` 作为 fixture fallback。
- `src/crypto_manual_alert/agent_swarm/registry.py`
  - `llm_tool_shadow` 模式下将 `LiveFactAgent` 注册为 `LlmToolShadowWorker`。
- `src/crypto_manual_alert/agent_swarm/shadow_llm_client.py`
  - fixture `LiveFactAgent` 请求 `realtime_search`。
- `tests/api/test_runs_routes.py`
  - 主 API 链路测试要求 `tool_calls[]` 包含 `realtime_search`。

## 验证

```powershell
python -m pytest tests/skills/test_realtime_search_provider.py -q
python -m pytest tests/agent_swarm/test_registry.py tests/agent_swarm/test_llm_tool_worker.py tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls tests/skills -q
```

临时主链路 smoke：

```json
{
  "trace_id": "24a64472c5d343269b060a06f06563df",
  "workers": 7,
  "tool_calls": [
    "realtime_search",
    "root_cause_search",
    "market_sentiment",
    "liquidity_order_book"
  ],
  "worker_tool_counts": {
    "LiveFactAgent": 1,
    "DerivativesAgent": 0,
    "MacroEventAgent": 0,
    "RootCauseAgent": 1,
    "MarketSentimentAgent": 1,
    "DataQualityAgent": 0,
    "ExecutionRiskAgent": 1
  },
  "execution_fact_tool_calls": [
    "liquidity_order_book"
  ]
}
```

## 边界

- 默认 `shadow.worker_mode=local_audit` 未改变。
- 默认 `decision.final_input_mode=legacy_prompt` 未改变。
- 当前 provider 边界只支持注入；默认未接外部 web search。
- 该切片证明 `realtime_search` 可进入主 API/audit projection，不证明实时数据质量已经生产可用。
