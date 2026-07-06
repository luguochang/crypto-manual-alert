# Checkpoint 7: skill provider config boundary

日期：2026-07-06

## 目标

为 Skill provider 增加显式配置边界，让 fixture/disabled/真实 provider 的启用可审查、可测试。该切片不启用真实外部搜索或交易所 adapter。

## 改动

- `config/models.py`
  - 新增 `SkillProvidersConfig`。
  - 默认 `realtime_search=disabled`、`root_cause=disabled`、`liquidity_order_book=fixture`。
- `config/loader.py`
  - 解析 `skill_providers`。
  - 校验 provider mode allowlist。
- `skills/realtime_search/providers.py`
  - 新增 `FixtureSearchProvider`。
- `skills/root_cause/providers.py`
  - 新增 `FixtureRootCauseProvider`。
  - 新增 `RealtimeBackedRootCauseProvider`，把 realtime search result 转成受控 root-cause factor candidate。
- `skills/registry.py`
  - 新增 `build_skill_registry_from_config()`。
  - 支持 `skill_providers.root_cause=realtime_search` 复用 `realtime_search` provider。
  - 对未实现的真实 provider mode 执行 fail closed。
- `agent_swarm/registry.py`
  - fixture config-only `llm_tool_shadow` 分支改为使用 config-aware skill registry。
- `skills/executor.py`
  - skill/provider 异常转换为 failed `ToolCallArtifact`。
  - 公开 `error_type/error_hash`，不公开原始错误消息。

## 验证

```powershell
python -m pytest tests/config/test_config.py::test_config_accepts_skill_provider_modes tests/config/test_config.py::test_config_rejects_unknown_skill_provider_mode tests/skills/test_skill_registry.py tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls tests/agent_swarm/test_registry.py -q
python -m pytest tests/skills tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls tests/config/test_config.py::test_config_accepts_skill_provider_modes tests/config/test_config.py::test_config_rejects_unknown_skill_provider_mode -q
python -m pytest tests/skills tests/agent_swarm/test_llm_tool_worker.py -q
python -m pytest tests/skills/test_skill_registry.py -q
```

## 边界

- `responses_web_search` 只是配置 allowlist，真实 provider 尚未实现。
- `exchange_native` 只是配置 allowlist，真实 exchange adapter 尚未实现。
- 默认不启用真实外部 provider。
- 默认不改变 `shadow.worker_mode`、`workflow.execution_mode`、`decision.final_input_mode`。
