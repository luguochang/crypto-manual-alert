# Checkpoint 2: SkillExecutor 与 ToolCallArtifact 后端闭环

日期：2026-07-04

## 范围

本次完成的是后端受控 Skill/Artifact 主通道的小闭环，不切换生产最终输入，不开启自动交易，不声称真实市场预测质量已经提升。

## 完成项

- 新增默认 Skill registry，统一注册 `realtime_search`、`root_cause_search`、`market_sentiment`、`macro_event`、`liquidity_order_book`。
- `SkillExecutor` 输出 `ToolCallArtifact`，worker 只能拿到 ref/hash/source/freshness 等字段，不能直接把 raw skill result 写入 contribution。
- Harness/LeadPlan 的 llm tool shadow allowlist 从 `web_search` 切到业务 Skill 名称。
- LLM worker 只支持 `skill_requests`，旧 `tool_requests` 会硬拒绝；artifact refs 写入 `AgentContribution.tool_call_artifact_refs`。
- replay manifest、eval replay summary 和 API projection 不再投影旧 `tool_audit_result_refs/tool_audit_results`。
- `ToolCallArtifact.to_public_dict()` 不再输出 raw `error`，后续失败信息只能走 `error_type/error_hash` 这类脱敏字段。
- `ToolCallArtifact` 已贯穿到 `DecisionInput`、pre-final gate、replay manifest、RunContext artifact summary 和 agent audit projection。
- `pre_final_orchestration` 增加显式 `tool_executor` 注入入口；llm tool worker registry 未显式传 executor 时默认使用 `SkillExecutor(build_default_skill_registry())`。
- 统一 `tool_call_artifact_refs` 的安全投影函数，减少白名单漂移。

## 安全边界

- production final input 仍默认使用 legacy prompt。
- candidate/swarm 输出仍是 `decision_effect=none`。
- Skill 不写 journal、不发通知、不下单。
- search-derived artifact 不能满足 execution fact。
- API/replay/context 只投影 artifact refs，不投影 raw snippet、raw payload、request_json、response_json、error_message 或 raw worker error。
- `FixtureShadowToolExecutor(web_search)` 只保留为隔离兼容对象，不接 `LlmToolShadowWorker` 主通道。

## 验证命令

```powershell
python -m pytest tests/skills tests/agent_swarm/test_registry.py tests/agent_swarm/test_harness_validation.py tests/agent_swarm/test_llm_tool_worker.py tests/agent_swarm/test_shadow_orchestration.py tests/lead/test_agent.py tests/workflow/test_pre_final_orchestration.py tests/decision/test_decision_input.py tests/decision/test_pre_final_input_gate.py tests/decision/test_replayable_input.py tests/storage/test_agent_audit_view.py tests/context/test_run_context.py -q
```

结果：通过。

补充验证：

```powershell
python -m pytest tests/agent_swarm tests/skills tests/lead tests/workflow/test_pre_final_orchestration.py tests/decision/test_replayable_input.py tests/decision/test_decision_input.py tests/decision/test_pre_final_input_gate.py tests/storage/test_agent_audit_view.py tests/context/test_run_context.py tests/structure/test_skill_executor_boundaries.py -q
python -m pytest tests/eval/test_replayable_input_summary.py tests/eval/test_replay_llmjudge.py tests/eval/test_candidate_artifact_validation.py -q
```

结果：通过。

## 未完成边界

- `RootCauseSearchSkill` 还没有真实递归 web searched 检索实现。
- `RealtimeSearchSkill` 还没有直接触发大模型 web search 或外部实时搜索。
- 前端还没有消费 canonical `tool_call_artifact_refs`。
- 后端 projection 还没有一等 `tool_calls[]`、`source_freshness[]`、`root_cause_graph`、`conflict_edges[]`、`input_lineage`、`release_eval_gate`。
- 金融预测质量评测仍未开始。
