# Checkpoint 7: business skill package split

日期：2026-07-05

## 目标

把集中在 `skills/facade.py` 的业务 Skill 拆成按能力命名的 package，降低单文件复杂度，并让后续新增 root cause、sentiment、macro、liquidity 等能力时有清晰目录边界。该切片不改变 Skill 行为，不接入外部实时源。

## 新结构

```text
src/crypto_manual_alert/skills/
  _shared.py
  facade.py
  registry.py
  realtime_search/
    __init__.py
    skill.py
  root_cause/
    __init__.py
    skill.py
  sentiment_crowding/
    __init__.py
    skill.py
  macro_event/
    __init__.py
    skill.py
  liquidity_order_book/
    __init__.py
    skill.py
```

## 改动

- `facade.py` 只保留稳定兼容导出。
- `registry.py` 改为从业务 skill package 导入实现。
- `_shared.py` 承载共同的 `SkillToolResult` 构造、约束构造、search result 清理和 missing input 逻辑。
- 结构测试新增 package 约束，防止后续又把所有业务 Skill 塞回一个 facade 文件。

## 验证

```powershell
python -m pytest tests/structure/test_skill_runtime_boundaries.py::test_business_skills_are_packaged_by_capability -q
python -m pytest tests/skills tests/structure/test_skill_runtime_boundaries.py tests/agent_swarm/test_registry.py tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls -q
```

临时主链路 smoke：

```json
{
  "trace_id": "441a805597b54459aeef8aaa34bbe974",
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

- 未改变默认 `shadow.worker_mode=local_audit`。
- 未改变 `decision.final_input_mode=legacy_prompt`。
- 未接入真实 web search。
- 未接入真实交易所 order book。
- `root_cause_search` 当前仍只是受控结构化输出，不是递归因果检索实现。
