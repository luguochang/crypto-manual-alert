# Checkpoint 7 - Realtime Responses Web Search Provider

日期：2026-07-06

## 目标

补齐 `realtime_search` 的显式真实 web search provider 边界，让 `skill_providers.realtime_search=responses_web_search` 可以构建 OpenAI-compatible Responses web_search provider，同时保持默认 `disabled`、fixture、本地 audit-only 主链路不变。

## 变更

- `src/crypto_manual_alert/skills/realtime_search/providers.py`
  - 新增 `ResponsesWebSearchProvider`。
  - 调用 `/v1/responses`，payload 必须包含 `tools=[{"type":"web_search"}]`。
  - 校验响应中实际 `web_search` usage 大于 0。
  - 校验响应文本非空。
  - Skill public result 只返回 `responses://web_search` 与 `snippet_sha256` 引用，不返回原始 search text。
  - `api_key` 只用于 Authorization header，dataclass `repr` 不显示 key。
- `src/crypto_manual_alert/skills/realtime_search/__init__.py`
  - 导出 `ResponsesWebSearchProvider`。
- `src/crypto_manual_alert/skills/registry.py`
  - `skill_providers.realtime_search=responses_web_search` 显式构建 `ResponsesWebSearchProvider.from_config(config)`。
  - 默认 `disabled` 与 `fixture` 行为不变。
- `tests/skills/test_realtime_search_provider.py`
  - 覆盖 Responses web_search 请求、refs-only 输出、零 web_search usage 失败、缺 key 失败、repr 不泄露 key。
- `tests/skills/test_skill_registry.py`
  - 覆盖显式 `responses_web_search` provider wiring。
- `docs/formal/35-剩余主缺口对抗审查与执行清单.md`
  - 更新 Phase 2 执行记录与验收说明。

## 验证

RED：

```powershell
python -m pytest tests/skills/test_realtime_search_provider.py tests/skills/test_skill_registry.py -q
```

失败点：

- `ResponsesWebSearchProvider` 尚不存在。
- registry 对 `responses_web_search` 仍然 fail closed。
- dataclass repr 会暴露 `api_key`。

GREEN：

```powershell
python -m pytest tests/skills/test_realtime_search_provider.py tests/skills/test_skill_registry.py -q
python -m pytest tests/config/test_config.py tests/skills tests/agent_swarm/test_llm_tool_worker.py tests/api/test_runs_routes.py -q
```

结果：通过。

## 安全边界

- 没有修改默认 `workflow.execution_mode=legacy_baseline`。
- 没有修改默认 `decision.final_input_mode=legacy_prompt`。
- 没有修改默认 `shadow.worker_mode=local_audit`。
- 没有默认启用真实 web search provider。
- 没有新增下单、撤单、提现或交易通知能力。
- `realtime_search` 仍然输出 `search_derived`，不能满足 `mark/index/order_book` execution facts。

## 剩余缺口

- 还需要用真实 trace 做显式 provider 的运行时 smoke；当前测试使用 `httpx.MockTransport`，没有访问真实网络。
- `root_cause=realtime_search` 在真实 provider 模式下仍需要端到端 smoke 验证。
- Phase 3 还需要浏览器截图验证 Run Detail 移动端无文本重叠。
