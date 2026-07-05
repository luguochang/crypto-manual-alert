# Checkpoint 7: root_cause controlled recursion provider

日期：2026-07-05

## 目标

让 `root_cause_search` 不再只是声明递归约束，而是具备受控递归 provider 边界。该切片只实现 provider 注入、depth/branch 控制、去重和脱敏输出，不接真实外部 web search。

## 改动

- `src/crypto_manual_alert/skills/root_cause/providers.py`
  - 新增 `RootCauseSearchRequest`。
  - 新增 `RootCauseProvider` 协议。
- `src/crypto_manual_alert/skills/root_cause/skill.py`
  - 支持注入 provider。
  - 使用 `context.max_depth` 控制递归深度。
  - 使用 `max_branch_count` 控制每层展开数量。
  - 只接受 `ALLOWED_FACTOR_TYPES` 中的因素类型。
  - 输出仍为 `EvidenceCandidate`，不引入开放 payload。
- `tests/skills/test_root_cause_recursion.py`
  - 验证 depth、branch 和 request 传递。

## 验证

```powershell
python -m pytest tests/skills/test_root_cause_recursion.py -q
python -m pytest tests/skills tests/structure/test_skill_runtime_boundaries.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_llm_tool_worker.py tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls -q
```

临时主链路 smoke：

```json
{
  "trace_id": "bd00ff24406e4ec9b4da151aaa9a6510",
  "workers": 7,
  "tool_calls": [
    "realtime_search",
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

- 未接入真实 web search provider。
- 未把 root-cause 图结构作为开放 payload 返回。
- 默认主链路没有 provider 时仍返回空 evidence candidates，但 tool artifact 仍可被审计。
- 递归结果不能直接产生交易动作、风险结论、通知或订单。
