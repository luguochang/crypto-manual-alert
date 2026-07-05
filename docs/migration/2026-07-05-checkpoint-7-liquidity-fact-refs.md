# Checkpoint 7: liquidity execution fact refs

日期：2026-07-05

## 目标

让 `liquidity_order_book` 不只是声明 `can_satisfy_execution_fact=true`，而是在受控结果里带上 mark/index/order_book 的引用。该切片仍不暴露原始订单簿，不接真实交易所。

## 改动

- `SkillToolResult`
  - 新增 `fact_refs`。
  - 只允许 `mark`、`index`、`order_book` 三类 key。
  - 只允许 `liquidity_order_book` 使用。
- `ToolCallArtifact`
  - 从 skill public result 复制 `fact_refs`。
  - `to_public_dict()` 透出 refs。
- `tool_call_artifact_ref_fields()`
  - allowlist 增加 `fact_refs`。
- `LiquidityOrderBookSkill`
  - 支持注入 `OrderBookProvider`。
  - provider 只返回 refs，不返回原始 order book。
- `build_fixture_skill_registry()`
  - fixture config-only `llm_tool_shadow` 使用 `FixtureOrderBookProvider`。

## 验证

```powershell
python -m pytest tests/skills/test_liquidity_order_book_provider.py -q
python -m pytest tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls -q
python -m pytest tests/skills tests/storage/test_agent_audit_view.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_llm_tool_worker.py tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls -q
```

## 边界

- `FixtureOrderBookProvider` 不是生产交易所 adapter。
- `fact_refs` 是 refs/hash 可观测能力，不是原始数据存储。
- 没有启用订单、通知或生产 final input 切换。
- 真实 exchange adapter 需要后续补充 provider 配置、错误处理、超时和脱敏策略。
