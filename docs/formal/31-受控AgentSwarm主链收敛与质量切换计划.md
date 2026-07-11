# 受控 Agent Swarm 主链收敛与质量切换计划

> **当前定位（2026-07-09）**：本文是历史 AgentSwarm 迁移进度记录，不是当前日常执行入口。当前交付执行、P0 证据闭环和 checklist 以 `docs/implementation/2026-07-09-current-delivery-checklist.md` 为准。当前 MVP production main path 仍是 `legacy_baseline + legacy_prompt`；任何 `decision_input` / AgentSwarm 主链切换都需要单独 release review。

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 将当前固定 pipeline、并发 search、单次 leader review 的候选链路，逐步收敛为“轻量自研 Workflow + LeadAgent + 多 Worker Agent + DecisionInput + Gate”的受控 Agent Swarm 主链，同时保留可回放、可审计、可人工切换和可回退的资金安全边界。

**Architecture:** Workflow 只控制顺序、副作用和失败传播；LeadAgent 只负责任务规划与综合；Worker Agents 并行产出结构化证据和 `AgentContribution`；Skill facade 只提供受控工具结果；FinalDecisionAgent 后续只能消费通过前置输入 gate 的 `DecisionInput`。

**Tech Stack:** Python, pytest, YAML harness policy, SQLite journal/eval store, OpenAI-compatible LLM client, structured artifact/hash/replay system.

---

本文是后续重构的唯一执行进度入口。`29-Agent与Skill拆分详细设计.md` 只作为目标架构参考；`30-受控AgentSwarm-MVP实施契约.md` 仍作为当前代码事实、兼容路径和边界契约参考，但不再承载后续执行流水。后续开发必须先更新本文状态，再执行对应小闭环。

## 当前进度快照

| 项目 | 当前状态 |
|---|---|
| 生产主链 | 仍为 `legacy_baseline + legacy_prompt` |
| 当前 checkpoint | Checkpoint 9：主流程与可视化审计收口，已通过本轮验收 |
| 当前小闭环 | 9A-9L 已完成：主流程白盒、query audit_note、trace 显式绑定、controlled_shadow 审计投影、文档事实和 artifact 护栏 |
| 已完成 | Checkpoint 1、2、3、4、5、6、7、8 |
| 未完成 | Checkpoint 9 无剩余项；后续架构优化另立 checkpoint |
| 当前 required shadow workers | 7 个：LiveFactAgent、DerivativesAgent、MacroEventAgent、RootCauseAgent、MarketSentimentAgent、DataQualityAgent、ExecutionRiskAgent |
| 当前硬禁止 | 不自动打开 `decision.final_input_mode=decision_input`；不让 shadow/candidate/eval/replay 产生生产副作用；不把业务 Agent 写进 `agent_swarm/` 或根目录 |

## 当前切换状态

- 默认配置仍为 `workflow.execution_mode=legacy_baseline` 与 `decision.final_input_mode=legacy_prompt`。
- `config/loader.py` 只在 `decision.final_input_mode_switch_review_path` 指向有效 switch review artifact 时接受 `decision.final_input_mode=decision_input`；缺失、格式错误、ref/hash 绑定不完整、回滚计划缺失或安全不变量不满足时继续拒绝。
- 有效 switch review artifact 必须绑定通过的 release gate、config-change approval、manual release decision、config request、candidate input、config hash 和 rollback plan，并保留 `fallback_behavior=legacy_prompt_on_candidate_failure`、`manual_execution_required=true`、`auto_order_enabled=false`。
- 即使配置准入允许 `decision_input`，runtime candidate 未 ready、缺失、validation 失败或 ref/hash 缺失时仍 fallback 到 legacy prompt，并保留 fallback reason 与 blocking reasons。
- shadow/candidate/eval/replay 产物仍只能是 audit/sidecar 语义，不得产生 production journal、notification 或 live order 副作用。

## Worker 命名规则

- Required worker manifest key 必须保持 `MarketSentimentAgent`，不能改成 `SentimentCrowdingAgent`。
- 当前实现类是 `SentimentCrowdingLocalWorker`，`MarketSentimentLocalWorker` 只是兼容 alias。
- 文档中描述业务能力时可以说 sentiment/crowding/reflexivity，但涉及 worker key、LeadPlan、harness policy、tests、DecisionInput refs 时必须使用 `MarketSentimentAgent`。

## 执行规则

- 每个小闭环必须先写失败测试或结构护栏，再实现，再验证。
- 每个小闭环只做当前范围，不顺手扩大到后续任务。
- 小闭环验证必须分层：字段投影、契约和结构边界优先跑对应窄测试；`tests/workflow/test_run_executor.py` 属于 Runner/Journal/Replay/Release gate 深度集成验证，只在 checkpoint 收口或入口边界变化时跑，不作为每个字段变更的默认循环。
- 每完成一个 checkpoint 或小闭环，先更新本文 checkbox 和 `docs/migration/`，再汇报。
- 同一个测试失败、导入边界问题或设计冲突连续失败 3 次，立即暂停。
- 暂停时必须记录失败现象、已尝试方案、当前证据和需要用户决策的点。
- 不允许通过删除测试、跳过结构护栏、扩大范围或改入口径绕过暂停规则。

## 代码归属边界

| 目录 | 职责 |
|---|---|
| `src/crypto_manual_alert/market_agents/` | 加密货币市场业务 Worker Agent 的 canonical owner |
| `src/crypto_manual_alert/agent_swarm/` | runtime、pool、registry、compat exports、LLM/tool worker runtime；不承载市场业务规则 |
| `src/crypto_manual_alert/orchestration/` | shadow audit、failure envelope、pre-final orchestration adapter、contracts 与 harness 的 canonical owner |
| `src/crypto_manual_alert/agent_swarm/contracts.py` | 兼容 re-export；不得新增契约逻辑 |
| `src/crypto_manual_alert/agent_swarm/harness.py` | 兼容 re-export；不得新增 harness 逻辑 |
| `src/crypto_manual_alert/agent_swarm/local_workers/` | 兼容 re-export only；不得新增业务 worker 实现 |
| `src/crypto_manual_alert/lead/` | LeadAgent 任务规划与综合；不 import 具体 market agent 实现 |
| `src/crypto_manual_alert/skills/` | 受控工具能力和结构化工具结果；不返回 `AgentContribution` |
| `src/crypto_manual_alert/decision/` | DecisionInput、candidate final、switch readiness、production control gate；不 import worker runtime |
| `src/crypto_manual_alert/workflow/` | 生产执行顺序、side-effect policy、失败传播 |
| `src/crypto_manual_alert/artifacts/` | EvidencePacket、contribution projection、hash 与 orchestration input artifact；不承载 Agent 编排 |
| `src/crypto_manual_alert/context/` | DecisionRunContext、ArtifactStore 和请求上下文；不承载业务判断 |
| `src/crypto_manual_alert/eval/` | replay runner、release gate、LLMJudge、side-effect proof 和离线质量评估 |
| `src/crypto_manual_alert/storage/` | journal schema、row projection、query repository；不承载决策逻辑 |
| `src/crypto_manual_alert/notification/` | notification sink 与发送边界；不承载决策逻辑 |
| `src/crypto_manual_alert/market/` | market data provider；不混入 Agent 编排或交易动作 |
| `src/crypto_manual_alert/*.py` | 不新增根包业务实现文件 |
| 项目根目录 `.py` | 不新增业务脚本；只允许已登记入口或工具 |
| `tests/` | 不新增根层测试 `.py`；按领域进入 `tests/<domain>/` |

## 总体 Checklist

- [x] Checkpoint 1：冻结当前真实状态，完成根包、测试根层、文档入口和 Git 状态基线。
- [x] Checkpoint 2：Workflow 边界收敛，完成 controlled shadow route、SideEffectGate、legacy baseline/fallback 边界。
- [x] Checkpoint 3：实时事实层补齐，完成 source tier、TTL、fallback、event refresh gate、macro surprise contract 和 DecisionInput 传播。
- [x] Checkpoint 4：Agent/Skill 业务化，完成真正可编排的业务 Worker 与受控 Skill facade。
- [x] Checkpoint 5：DecisionInput 候选 final，候选 FinalDecisionAgent 只消费 `DecisionInput`，并可和 legacy final 对照回放。
- [x] Checkpoint 6：质量门禁与发布审计，建立可证明、可回放、可人工审查的 release gate。
- [x] Checkpoint 7：受控切换与回退，只允许通过人工 config-change review 打开 `DecisionInput` 生产输入。
- [x] Checkpoint 8：Legacy 收敛，legacy prompt 降为 fallback、replay、对照用途。
- [x] Checkpoint 9：主流程与可视化审计收口，让一次 query/manual run 从入口到 Agent 编排、Skill/tool、DecisionInput、Gate、Final、Persistence、Frontend 都可读、可控、可追踪、可运行态验收。

## Checkpoint 4 详细 Checklist

- [x] 4A：建立 `market_agents/` canonical owner 和结构护栏。
- [x] 4B：固化 `AgentContribution` 业务契约、harness 禁止字段和 contribution 引用规则。
- [x] 4C：迁移现有本地审查 worker 到 `market_agents/`，保留兼容导出。
- [x] 4D.1：完成 `LiveFactAgent`，只消费已有 snapshot/facts_gate。
- [x] 4D.2：完成 `DerivativesAgent`，只消费已有 snapshot/facts_gate。
- [x] 4D.3：完成 `MacroEventAgent`，只消费已有 snapshot/facts_gate/evidence packets，并加入 7-worker 覆盖。
- [x] 4D.4：升级 `RootCauseAgent` 与 `MarketSentimentAgent`，把根因链、反方链、priced-in/crowding/reflexivity 输出结构化。
- [x] 4D.5：补齐 `DataQualityAgent` 与 `ExecutionRiskAgent` 在 `market_agents/` 下的专项业务测试。
- [x] 4E：实现 Skill facade 与实时信息边界，Skill 只返回结构化工具结果，不返回 `AgentContribution`。
- [x] 4F：Lead/Harness/Runner 接入，business worker contribution 进入 pre-final candidate `DecisionInput`。
- [x] 4G：Checkpoint 4 收口验收，确认 `FlowLiquidityAgent` 是否继续延期，更新 migration 记录并跑完整验收命令。

## 4D.3 完成记录

- [x] 先写 `tests/market_agents/test_macro_event_agent.py` 失败测试。
- [x] red 结果：`ModuleNotFoundError: crypto_manual_alert.market_agents.macro_event`。
- [x] 新增 `src/crypto_manual_alert/market_agents/macro_event.py`，只实现 local audit worker。
- [x] MacroEventAgent 不做 live fetch、不做 web search、不写 journal/notification。
- [x] 输出 `decision_effect=none`，claims 只允许 neutral/audit 语义。
- [x] constraints 包含 `event_status`、`macro_event`、`surprise`、`market_reaction`、`event_compression`、`missing_event_facts`、`missing_macro_facts`、`blocked_action_classes`、`required_confirmations`。
- [x] 缺失或 stale event status 时传播 `missing_event_facts`、`blocked_action_classes` 和 confidence cap。
- [x] 缺失 macro facts 时传播 `missing_macro_facts` 和 confidence cap。
- [x] 更新 `market_agents`、`agent_swarm`、`orchestration/harness.py`、`lead`、`decision/switch_readiness.py` 相关注册和 required worker 数量。
- [x] 同步测试中的 worker count/list，从 6 个 required worker 更新为 7 个 required worker。
- [x] 验证通过：`python -m pytest tests/market_agents/test_macro_event_agent.py tests/market_agents/test_local_workers.py tests/lead/test_agent.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_shadow_swarm.py tests/agent_swarm/test_workers.py tests/workflow/test_pre_final_orchestration.py tests/decision/test_switch_readiness.py -q`。
- [x] 验证通过：`python -m pytest tests/agent_swarm/test_workers.py tests/agent_swarm/test_shadow_orchestration.py tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py tests/decision/test_switch_readiness.py tests/cli/test_runner_cli.py -q -x`。
- [x] 验证通过：`python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/decision/test_switch_readiness.py -q`。
- [x] 验证通过：`python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q`。
- [x] 验证通过：`python -m pytest tests/cli/test_runner_cli.py -q`。
- [x] 验证通过：`python -m pytest tests/structure -q`。

## 4D.4 待执行 Checklist

- [x] 写 `tests/market_agents/test_root_cause_agent.py` 失败测试：要求输出 root cause graph、direct cause、second-order cause、evidence refs、missing facts、confidence cap。
- [x] 写 RootCause 禁止字段测试：不得输出 `main_action`、`entry`、`stop`、`target`、`leverage`、`position_size`、`risk_verdict`。
- [x] 实现 RootCause 结构化输出：把事件、宏观、衍生品、流动性、情绪等影响因素归并为可审计链路。
- [x] 写 `tests/market_agents/test_sentiment_crowding_agent.py` 失败测试：要求 `MarketSentimentAgent` 输出 crowding state、priced-in 判断、reflexivity 风险、counter thesis、required confirmations。
- [x] 实现 Sentiment/Crowding 结构化输出：区分客观事实与短期群体行为偏差，不直接给最终交易动作。
- [x] 保持 `lead/synthesis.py` 现有 counter thesis 与 conflict refs 汇总能力，并更新旧断言以匹配 4D.4 结构化 counter thesis。
- [x] 验证：`python -m pytest tests/market_agents/test_root_cause_agent.py tests/market_agents/test_sentiment_crowding_agent.py -q`。
- [x] 验证：`python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/decision/test_switch_readiness.py -q`。
- [x] 验证：`python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q`。
- [x] 验证：`python -m pytest tests/cli/test_runner_cli.py -vv -x --durations=10`。
- [x] 验证：`python -m pytest tests/structure -q`。
- [x] 更新本文和 `docs/migration/2026-07-03-checkpoint-4-agent-skill-business-slice.md`。

## 4D.4 完成记录

- [x] red 结果：`tests/market_agents/test_root_cause_agent.py` 因缺少 `confidence_cap_reasons`、`root_cause_graph` 等字段失败。
- [x] red 结果：`tests/market_agents/test_sentiment_crowding_agent.py` 因缺少 `crowding_state`、`priced_in_assessment`、`reflexivity_risk` 等字段失败。
- [x] `RootCauseAgent` 输出 `root_cause_graph`、`direct_causes`、`second_order_causes`、`evidence_refs`、`missing_causal_facts`、`confidence_cap`、`required_confirmations`。
- [x] `MarketSentimentAgent` 输出 `crowding_state`、`priced_in_assessment`、`reflexivity_risk`、`counter_thesis`、`missing_sentiment_facts`、`required_confirmations`。
- [x] 两个 worker 仍为 local audit worker，只追加 `AgentContribution`，不写 final decision、journal、notification 或 side-effect intent。
- [x] `MarketSentimentAgent` 保持 worker manifest key；`SentimentCrowdingLocalWorker` 仍为实现类。
- [x] workflow 回归中，structured counter thesis 已进入 candidate/replay/release readback，且仍为 `decision_effect=none`。

## 4D.5 待执行 Checklist

- [x] 写 `tests/market_agents/test_data_quality_agent.py` 失败测试：要求 DataQualityAgent 输出 source quality、execution fact coverage、staleness/conflict details、missing facts、blocked action classes。
- [x] 写 DataQuality 禁止字段测试：不得输出 final decision 或交易动作字段。
- [x] 实现 DataQualityAgent 专项业务输出，避免重复 LiveFactAgent 但能补充质量原因和证据来源。
- [x] 写 `tests/market_agents/test_execution_risk_agent.py` 失败测试：要求 ExecutionRiskAgent 输出 hard block reasons、allowed action class reduction、manual-only reminders、required confirmations。
- [x] 写 ExecutionRisk 禁止字段测试：不得输出 `main_action`、`entry`、`stop`、`target`、`leverage`、`position_size`、`risk_verdict`。
- [x] 实现 ExecutionRiskAgent 专项业务输出，保持只读 audit，不写 production gate verdict。
- [x] 验证：`python -m pytest tests/market_agents/test_data_quality_agent.py tests/market_agents/test_execution_risk_agent.py -q`。
- [x] 验证：`python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/decision/test_switch_readiness.py -q`。
- [x] 验证：`python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q`。
- [x] 验证：`python -m pytest tests/cli/test_runner_cli.py -q -x`。
- [x] 验证：`python -m pytest tests/structure -q`。
- [x] 更新本文和 `docs/migration/2026-07-03-checkpoint-4-agent-skill-business-slice.md`。

## 4D.5 完成记录

- [x] red 结果：`tests/market_agents/test_data_quality_agent.py` 因缺少 `execution_fact_coverage`、`source_quality`、`staleness_details`、`conflicting_fact_details` 等字段失败。
- [x] red 结果：`tests/market_agents/test_execution_risk_agent.py` 因缺少 `allowed_action_class_reduction`、`manual_review_reminders`、clean-path `hard_block` 等字段失败。
- [x] red 结果：subagent 审查发现 `snapshot.unavailable` 非 execution 前缀可能回显 forbidden token；补充 `test_data_quality_agent_does_not_echo_non_execution_unavailable_prefixes` 后先失败再修复。
- [x] `DataQualityAgent` 输出 `execution_fact_coverage`、`source_quality`、`staleness_details`、`conflicting_fact_details`、`missing_execution_facts`、`blocked_action_classes`、`required_confirmations`。
- [x] `DataQualityAgent` 只允许 `mark`、`index`、`order_book` 从 `snapshot.unavailable` 进入 missing execution facts，避免回显非 execution 字段或 forbidden token。
- [x] `ExecutionRiskAgent` 输出 `hard_block`、`hard_block_reasons`、`allowed_action_class_reduction`、`manual_review_reminders`、`required_confirmations`、`execution_risk_summary`。
- [x] 两个 worker 仍为 local audit worker，只追加 `AgentContribution`，不写 final decision、gate verdict、journal、notification 或 side-effect intent。
- [x] 保留原有 `execution_risk_hard_block` 和 `facts_gate:execution_facts_missing` 语义，保证 DecisionInput、production control、release gate 读回路径稳定。

## 4E Skill Facade 设计 Checklist

- [x] 定义 skill facade protocol：输入为受控 task context，输出为结构化 tool result。
- [x] Skill 不得返回 `AgentContribution`，不得生成 final decision，不能写 side effect。
- [x] 设计实时检索 skill：支持 web searched 实时信息，但必须进入 evidence/facts gate。
- [x] 设计根因检索 skill：支持事件影响因素递归展开，但必须限制深度、证据来源和超时。
- [x] 设计市场情绪 skill：区分客观事实、舆情拥挤、priced-in、短期 reflexivity。
- [x] 设计宏观事件 skill：围绕事件状态、预期差、实际值、市场反应、滞后确认输出结构化结果。
- [x] 设计流动性/盘口 skill：只接受交易所原生事实源，不允许 search-derived 满足核心执行事实。
- [x] 写结构测试确保 skill facade 不 import `market_agents`、`agent_swarm`、final decision runtime 或 workflow。
- [x] 验证：`python -m pytest tests/skills/test_facade_contract.py tests/structure/test_skill_runtime_boundaries.py -q`。
- [x] 验证：`python -m pytest tests/skills -q`。
- [x] 验证：`python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/decision/test_switch_readiness.py -q`。
- [x] 验证：`python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q`。
- [x] 验证：`python -m pytest tests/cli/test_runner_cli.py -q -x`。
- [x] 验证：`python -m pytest tests/structure -q`。

## 4E 完成记录

- [x] red 结果：`tests/skills/test_facade_contract.py` 因缺少 `crypto_manual_alert.skills.facade` 失败。
- [x] red 结果：`skills.__init__` 未导出 facade 协议对象，包入口测试失败。
- [x] 新增 `SkillTaskContext` 和 `SkillToolResult`，形成受控输入与结构化工具结果边界。
- [x] 新增 `RealtimeSearchSkill`、`RootCauseSearchSkill`、`MarketSentimentSkill`、`MacroEventSkill`、`LiquidityOrderBookSkill`。
- [x] Search-derived skill 结果默认 `can_satisfy_execution_fact=false`，必须进入 facts gate；Liquidity/盘口 skill 只允许 `exchange_native` 满足 execution fact。
- [x] Root cause skill 带 `recursive_factor_search`、`max_depth`、`timeout_seconds` 和 allowed factor types。
- [x] Market sentiment skill 明确输出 crowding、priced-in、reflexivity，且区分客观事实与拥挤行为。
- [x] Macro event skill 明确 event status、actual、consensus、surprise、market reaction、lagged_confirmation、released_at 等必需字段。
- [x] 结构护栏确认 skill facade 不 import business agents、swarm runtime、final decision runtime 或 workflow，也不引用 worker contribution 类型。
- [x] 补充结构护栏：`skills.runtime` 只允许 legacy final-engine allowlist 导出；skill facade 禁止动态导入绕过。
- [x] `SkillToolResult` 已从开放 `dict/list` 输出收敛为白名单、不可变、不可携带 final/side-effect 语义的结构化结果模型。

## 4E 边界收敛补充记录

- [x] 已修复：`RealtimeSearchSkill.run()` 收敛为 `run(self, context)`，搜索候选只从 `SkillTaskContext.input_view["search_results"]` 读取。
- [x] 已修复：所有 realtime/search-derived evidence candidate 强制 `source_type=search_derived`，不能伪装为 `exchange_native`。
- [x] 已修复：`MacroEventSkill` 必需字段补齐 `lagged_confirmation`。
- [x] 已修复：`SkillToolResult` 增加 `decision_effect`、`result_type`、`source_type`、execution fact source、公开字段类型和 forbidden semantic value 校验。
- [x] 已修复：结构测试改为 AST import 检查，并补充 runtime legacy allowlist 与 dynamic import 守卫。
- [x] 新增 `EvidenceCandidate`、`SkillConstraints` typed/frozen value objects；`SkillToolResult` 不再接受开放 `dict/list` payload。
- [x] `to_public_dict()` 只从白名单 typed fields 组装新 dict/list，返回值突变、输入 `search_results` 突变、构造后外部 payload 突变均不会污染后续输出。
- [x] 增加 per-skill contract matrix：skill_name、task_id、result_type、source_type、execution fact、constraints 必须成套匹配，不允许跨 skill extra constraints。
- [x] 复审通过：结构/契约复审 Approved；安全边界复审 Approved。

## 4F 待执行 Checklist

- [x] 写失败测试：Lead/Harness/Runner 能把 business worker contribution 稳定写入 pre-final candidate `DecisionInput`，且 contribution refs 包含 7 个 required workers。
- [x] 写失败测试：Skill facade tool result 只能作为 evidence/tool result 被 worker 消费；禁止把原始 `SkillToolResult` 对象或 public dict 嵌入 `AgentContribution` 或 final decision。
- [x] 检查 `run_pre_final_orchestration`、`ShadowSwarmRunner`、`LeadAgent`、`DecisionInput` 当前接入路径，移除重复/旁路引用。
- [x] 确认 worker contribution 进入 pre-final candidate `DecisionInput` 的字段完整：task_id、evidence_ids、confidence_cap、confidence_cap_reasons、blocked_actions、hard_block、hard_block_reasons、manual_review_reminders、allowed_action_class_reduction、required_confirmations、trace_ref、output_hash。
- [x] 确认 shadow/candidate/eval/replay 仍无生产 journal、notification、live order 副作用。
- [x] 验证：`python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py tests/decision/test_decision_input.py -q`。
- [x] 验证：`python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/skills -q`。
- [x] 验证：`python -m pytest tests/structure -q`。
- [x] 更新本文和 `docs/migration/2026-07-03-checkpoint-4-agent-skill-business-slice.md`。

## 4F 完成记录

- [x] red 结果：`tests/decision/test_decision_input.py::test_pre_final_decision_input_contribution_refs_include_required_workers_and_safety_fields` 因 pre-final `contribution_refs` 缺少 `confidence_cap_reasons` 等安全字段失败。
- [x] red 结果：`tests/agent_swarm/test_harness_validation.py::test_harness_validation_rejects_raw_skill_tool_result_payload_inside_contribution` 初始未能拦截嵌入 `AgentContribution.constraints` 的 raw `SkillToolResult` public dict。
- [x] red 结果：`tests/decision/test_decision_input.py::test_pre_final_decision_input_fails_when_required_worker_refs_are_missing_without_drop_record` 初始未能把 pre-final required worker refs 缺失标记为 hard fail。
- [x] red 结果：`tests/context/test_run_context.py::test_decision_run_context_contribution_refs_include_pre_final_safety_fields` 初始 artifact summary 未投影 4F 安全字段。
- [x] `DecisionInput` pre-final contribution refs 已投影 7 个 required workers，并保留 task_id、evidence_ids、confidence cap、hard block、manual review、action class reduction、required confirmations、trace_ref 和 output_hash。
- [x] `DecisionInput` pre-final validation 对缺失 required worker refs 输出 `decision_input.required_worker_refs_missing` hard fail；普通 candidate helper 路径不扩大该行为。
- [x] `DecisionRunContext.to_artifact_summary()` 已输出安全 contribution refs，不泄漏 raw contribution payload，同时保留 4F 必要安全字段。
- [x] `confidence_cap` 在 contribution refs 中总是显式投影；无 cap 时为 `None`，避免实际 pre-final 路径中部分 worker 缺字段。
- [x] `artifacts.contributions.contribution_safety_ref_fields()` 成为 4F 安全字段投影的共享 helper，避免 `DecisionInput` 与 `RunContext` 各自维护一份字段规则。
- [x] Harness 增加 raw `SkillToolResult` public dict 和真实 `SkillToolResult` 对象嵌入检测，避免 skill facade 结果绕过 evidence/tool-result 边界直接进入 `AgentContribution`。
- [x] 对抗审查处理：规格审查发现的 `confidence_cap` 缺字段与 raw `SkillToolResult` 对象漏检已修复；Harness required-agent 覆盖、forbidden-field 文本误报和 `cap_applied_by_gate` 命名作为后续硬化项记录，不在 4F 默认语义里扩大行为面。
- [x] 验证分层记录：字段和 artifact 投影用 `tests/decision/test_decision_input.py`、`tests/context/test_run_context.py`、`tests/agent_swarm/test_harness_validation.py`；pre-final 边界用 `tests/workflow/test_pre_final_orchestration.py`；`tests/workflow/test_run_executor.py` 只在 4F 收口验证跑一次。
- [x] 验证通过：`python -m pytest tests/artifacts/test_artifacts_package_structure.py tests/artifacts/test_contributions.py -q`。
- [x] 验证通过：`python -m pytest tests/decision/test_decision_input.py tests/context/test_run_context.py -q`。
- [x] 验证通过：`python -m pytest tests/agent_swarm/test_harness_validation.py tests/workflow/test_pre_final_orchestration.py -q`。
- [x] 验证通过：`python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py tests/decision/test_decision_input.py -q`。
- [x] 验证通过：`python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/skills -q`。
- [x] 验证通过：`python -m pytest tests/structure -q`。

## 4G 完成记录

- [x] `FlowLiquidityAgent` 继续延期：当前 Checkpoint 4 已由 `LiveFactAgent`、`DataQualityAgent`、`ExecutionRiskAgent` 和 `LiquidityOrderBookSkill` 覆盖执行事实、盘口质量与交易所原生 order book skill 边界；尚未为独立 flow/liquidity worker 定义单独验收标准，不能在收口阶段顺手新增第 8 个 required worker。
- [x] Checkpoint 4 保持 7 个 required shadow workers，不扩大 worker manifest：LiveFactAgent、DerivativesAgent、MacroEventAgent、RootCauseAgent、MarketSentimentAgent、DataQualityAgent、ExecutionRiskAgent。
- [x] Checkpoint 4 收口后生产主链仍为 `legacy_baseline + legacy_prompt`，`decision.final_input_mode=decision_input` 仍由 config loader 硬拒绝。
- [x] shadow/candidate/eval/replay 仍保持 audit/sidecar 语义，不写生产 journal、notification 或 live order。
- [x] 已记录后续硬化项：Harness required-agent 覆盖、forbidden-field 自然语言误报、`cap_applied_by_gate` 命名语义。
- [x] 验收通过：`python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py tests/decision/test_decision_input.py -q`。
- [x] 验收通过：`python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/skills -q`。
- [x] 验收通过：`python -m pytest tests/structure -q`。

## Checkpoint 5-8 预留 Checklist

Gate 分层必须保持清楚：

- FinalDecisionAgent 前置输入 gate：`DecisionInput` schema/readback、required worker refs、execution fact source、hard block propagation、side-effect guard。
- FinalDecisionAgent 后置输出 gate：parser、semantic、risk、release gate、production switch readiness。

- [x] Checkpoint 5A：定义 `DecisionInput` 最小可生产候选 schema 与前置输入 gate。
- [x] Checkpoint 5B：隔离 candidate FinalDecisionAgent，候选 final 只消费通过前置输入 gate 的 `DecisionInput`，只写 sidecar，不改生产 final。
- [x] Checkpoint 5C：建立 legacy 与 candidate final 对照回放。
- [x] Checkpoint 6A：release gate 硬门禁，覆盖 eval coverage、schema-valid rate、side-effect guard、manual execution、badcase severity、candidate business gates、execution fact source violations、candidate replay、worker manifest consistency、context artifact consistency、artifact snapshot consistency、complete replay refs、span tree parent completeness、worker hard blocks、counter-conflict coverage 和 final switch readiness。
- [x] Checkpoint 6B：发布样本与 badcase 覆盖。
- [x] Checkpoint 6C：无生产副作用证明。
- [x] Checkpoint 6D：记忆与事实隔离回归。
- [x] Checkpoint 7A：人工 config-change review artifact。
- [x] Checkpoint 7B：candidate 故障到 legacy fallback，但不得覆盖事实缺失或风险阻断。
- [x] Checkpoint 7C：回滚计划。
- [x] Checkpoint 8A：legacy prompt 用途降级。
- [x] Checkpoint 8B：兼容 wrapper 生命周期表。
- [x] Checkpoint 8C：文档与全量验收。

Checkpoint 5 验收命令：

```powershell
python -m pytest tests/decision -q
python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q
python -m pytest tests/eval/test_shadow_final_comparison.py tests/eval/test_replayable_input_summary.py -q
python -m pytest tests/structure -q
```

## 5A 完成记录

- [x] red 结果：`tests/decision/test_pre_final_input_gate.py` 因缺少 `crypto_manual_alert.decision.pre_final_input_gate` 失败。
- [x] red 结果：`tests/decision/test_pre_final_switch_readiness.py` 仍按旧结构断言 readiness，未包含 pre-final input gate 结果。
- [x] 新增 `evaluate_pre_final_input_gate()`，定义 pre-final `DecisionInput` 最小候选输入 gate。
- [x] gate 覆盖 schema_version/mode/decision_effect、required worker refs、validation passed、execution fact source、worker hard block 和 side-effect 字段。
- [x] `build_pre_final_switch_readiness()` 已消费 input gate，但仍保持 `ready=false`，只解释为何当前不能切换生产 final input。
- [x] 生产主链仍为 `legacy_baseline + legacy_prompt`，本小闭环没有启用 candidate FinalDecisionAgent。
- [x] 验证通过：`python -m pytest tests/decision -q`。
- [x] 验证通过：`python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q`。
- [x] 验证通过：`python -m pytest tests/structure -q`。

## 5B 完成记录

- [x] red 结果：`tests/decision/test_candidate_final_decision.py` 因缺少 `crypto_manual_alert.decision.candidate_final_decision` 失败。
- [x] red 结果：`tests/workflow/test_persistence_payload.py::test_build_plan_payload_mirrors_candidate_final_sidecar_in_audit_only_namespace` 因 `audit_only` 未镜像 `candidate_final_decision` 失败。
- [x] 新增 `run_candidate_final_decision_sidecar()`，只消费通过前置输入 gate 的 pre-final `DecisionInput`，传给候选 engine 的输入固定为 `mode=candidate_final_input`、`decision_effect=none`。
- [x] candidate final sidecar 输出固定为 `artifact_type=candidate_final_decision`、`mode=candidate_final_sidecar`、`decision_effect=none`、`production_final_input=false`；输入 gate 失败或候选 engine 异常时只写 sidecar error，不影响生产 final。
- [x] `build_candidate_audit_payload()` 可接收并安全携带 candidate final sidecar；不满足 audit-only 边界的 sidecar 会降级为 invalid sidecar error。
- [x] `DecisionRunContext` artifact summary、`record_orchestration_artifacts()` 和 persistence `audit_only` namespace 均可审计 candidate final sidecar refs。
- [x] 生产主链仍为 `legacy_baseline + legacy_prompt`，本小闭环没有接入 `workflow/executor.py` 自动调用 candidate engine，也没有启用 `decision.final_input_mode=decision_input`。
- [x] 验证通过：`python -m pytest tests/decision/test_candidate_final_decision.py tests/decision/test_candidate_audit.py tests/context/test_artifacts.py tests/workflow/test_persistence_payload.py -q`。
- [x] 验证通过：`python -m pytest tests/decision -q`。
- [x] 验证通过：`python -m pytest tests/structure -q`。
- [x] 本小闭环未运行 `tests/workflow/test_run_executor.py`：5B 没有修改 Runner/Journal/Replay/Release gate 入口边界，深度集成验证保留到 Checkpoint 5 收口或 5C 入口变化时执行。

## 5C 完成记录

- [x] red 结果：`tests/eval/test_shadow_final_comparison.py::test_candidate_final_legacy_comparison_reports_safe_action_diff_without_raw_payload` 因缺少 `build_candidate_final_legacy_comparison()` 失败。
- [x] red 结果：`tests/eval/test_case_builder_candidate_audit.py::test_candidate_audit_summary_preserves_safe_candidate_final_sidecar_summary` 因 case summary 未保留 `candidate_final_decision` 安全摘要失败。
- [x] red 结果：`tests/eval/test_replay_llmjudge.py::test_candidate_decision_replay_compares_persisted_candidate_final_sidecar` 因 replay output 未生成 `candidate_final_legacy_comparison` 失败。
- [x] 新增 `build_candidate_final_legacy_comparison()`，支持从 5B sidecar 或安全 summary 生成 legacy-vs-candidate 对照，只输出 `main_action`、`probability`、`instrument` 等安全摘要。
- [x] `EvalCaseBuilder` 的 candidate audit summary 会保留 `candidate_final_decision` 的安全摘要、input refs、gate 状态和 `candidate_final_output_hash`，不保留 `raw_candidate_decision`。
- [x] `ReplayRunner` 的 `candidate_decision` 模式在 sidecar 存在时输出 `candidate_final_legacy_comparison`，且不写生产 journal、notification 或 live order。
- [x] Checkpoint 5 收口验证通过：`python -m pytest tests/decision -q`。
- [x] Checkpoint 5 收口验证通过：`python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q`。
- [x] Checkpoint 5 收口验证通过：`python -m pytest tests/eval/test_shadow_final_comparison.py tests/eval/test_replayable_input_summary.py -q`。
- [x] Checkpoint 5 收口验证通过：`python -m pytest tests/structure -q`。
- [x] 补充 5C 窄范围验证通过：`python -m pytest tests/eval/test_shadow_final_comparison.py tests/eval/test_case_builder_candidate_audit.py tests/eval/test_replay_llmjudge.py::test_candidate_decision_replay_compares_persisted_candidate_final_sidecar -q`。

Checkpoint 6 验收命令：

```powershell
python -m pytest tests/eval -q
python -m pytest tests/decision/test_switch_readiness.py tests/decision/test_pre_final_switch_readiness.py -q
python -m pytest tests/structure -q
```

## 6A 完成记录

- [x] red 结果：`tests/eval/test_release_gate.py::test_release_gate_rejects_candidate_final_comparison_decision_effect_violation` 初始失败，release gate 未拒绝 `candidate_final_legacy_comparison.decision_effect=production_final_input`。
- [x] `release_gate` 的 candidate replay side-effect guard 已覆盖 5C 新增的 `candidate_final_legacy_comparison`。
- [x] 同时防御性检查 `candidate_final_decision` sidecar 如出现在 replay output 中不得带 `decision_effect != none` 或 `production_final_input=true`。
- [x] 验证通过：`python -m pytest tests/eval/test_release_gate.py -q`。
- [x] 验证通过：`python -m pytest tests/eval/test_promotion_review.py tests/eval/test_promotion_artifacts.py tests/eval/test_promotion_artifact_validation.py -q`。
- [x] 验证通过：`python -m pytest tests/eval/test_candidate_audit_rules.py tests/eval/test_counter_conflict_coverage.py tests/eval/test_complete_replay_refs.py -q`。
- [x] red 结果：`tests/eval/test_release_gate.py::test_release_gate_requires_current_seven_required_worker_artifacts` 初始失败，4-worker candidate replay 可被 release gate 接受。
- [x] red 结果：`tests/eval/test_release_gate.py::test_release_gate_blocks_when_required_candidate_replay_evidence_is_missing` 初始失败，缺失 worker/context/counter 证据时 release gate 仍可 ready。
- [x] red 结果：`tests/eval/test_release_gate.py::test_release_gate_blocks_when_complete_replay_refs_are_false_even_if_missing_list_is_empty` 初始失败，release gate 信任 missing list 而未从 refs map 反算缺失项。
- [x] red 结果：`tests/eval/test_release_gate.py::test_release_gate_blocks_when_span_tree_parent_evidence_is_missing` 初始失败，缺失 span parent 完整性证据时 release gate 仍可 ready。
- [x] red 结果：`tests/eval/test_promotion_review.py::test_upsert_promotion_review_artifacts_preserves_required_badcase_severity_gate` 初始失败，promotion recompute 路径未接收 required badcase severity 配置。
- [x] release gate 和 promotion review 的 worker 阈值已从 4 更新为当前 7 个 required shadow workers。
- [x] worker manifest consistency、context artifact consistency、counter-conflict coverage、complete replay refs、span tree parent completeness 已收敛为缺证即阻断。
- [x] promotion recompute 路径已传递存储中的 cases 和 required badcase severity 配置。
- [x] 验证通过：`python -m pytest tests/eval/test_release_gate.py -q`。
- [x] 验证通过：`python -m pytest tests/eval/test_promotion_review.py tests/eval/test_promotion_artifacts.py tests/eval/test_promotion_artifact_validation.py -q`。
- [x] 验证通过：`python -m pytest tests/eval/test_replay_llmjudge.py::test_eval_runner_uses_configured_release_gate_thresholds_without_prod_side_effects tests/eval/test_replay_llmjudge.py::test_candidate_decision_replay_can_run_injected_decision_input_shadow_final tests/eval/test_replay_llmjudge.py::test_candidate_decision_replay_compares_persisted_candidate_final_sidecar -q`。
- [x] 验证通过：`python -m pytest tests/eval/test_context_artifact_readback.py tests/eval/test_candidate_artifact_validation.py tests/eval/test_promotion_artifact_store.py -q`。
- [x] 验证通过：`python -m pytest tests/structure -q`。

## 6B 完成记录

- [x] red 结果：默认 release gate 配置仍偏弱，未体现发布级样本与 badcase 覆盖要求。
- [x] `config/default.yaml` 与 `EvalReleaseGateConfig` 默认值已收敛为发布级门槛：`minimum_case_count=20`、`schema_valid_rate_threshold=0.95`、`required_badcase_severities=["high", "critical"]`。
- [x] `tests/config/test_config.py` 已覆盖默认配置、可接受阈值、非法阈值和未知 badcase severity。
- [x] 6B 没有修改 workflow/runner/journal/side-effect 入口边界，因此没有运行 `tests/workflow/test_run_executor.py`；深度集成验证保留到 checkpoint 收口或入口边界变化时执行。
- [x] 验证通过：`python -m pytest tests/config/test_config.py::test_default_config_disables_auto_ordering tests/config/test_config.py::test_config_accepts_release_gate_thresholds tests/config/test_config.py::test_config_rejects_invalid_release_gate_thresholds tests/config/test_config.py::test_config_rejects_unknown_release_gate_badcase_severity -q`。
- [x] 验证通过：`python -m pytest tests/config -q`。
- [x] 验证通过：`python -m pytest tests/eval/test_replay_llmjudge.py::test_eval_runner_uses_configured_release_gate_thresholds_without_prod_side_effects tests/eval/test_promotion_review.py tests/eval/test_release_gate.py -q`。

## 6C 完成记录

- [x] red 结果：`tests/eval/test_side_effect_proof.py` 初始失败，缺少 `no_production_side_effect_proof` artifact builder。
- [x] red 结果：`tests/eval/test_replay_llmjudge.py::test_eval_runner_uses_configured_release_gate_thresholds_without_prod_side_effects` 初始失败，EvalRunner metadata 未携带无生产副作用证明。
- [x] red 结果：`tests/eval/test_release_gate.py::test_release_gate_requires_no_production_side_effect_proof_for_promotion_material` 初始失败，release hard gate 可在缺少 proof 时通过。
- [x] red 结果：subagent 对抗审查指出 proof 校验会把缺失 delta 当 0、缺少 fingerprint 证明、nested `notification_input/live_order_input/production_final_input` 未完整拦截；已补对应失败测试。
- [x] 新增 `src/crypto_manual_alert/eval/side_effect_proof.py`，生成 `no_production_side_effect_proof`，覆盖生产 journal 相关表 count、fingerprint、delta、无副作用 flags 和阻断原因。
- [x] EvalRunner 在 eval/replay 运行前后采样生产表 count 与 stable fingerprint，并把 proof 写入 `promotion_artifacts`；仍不写生产 plan_runs、notifications、manual_outcomes、traces、trace_spans 或 llm_interactions。
- [x] release gate 新增 `hard_gate_results.no_production_side_effect_proof`，当存在 `eval_run_id` 时缺失、失败或 malformed proof 均会 hard block。
- [x] promotion review 仍要求 `no_production_side_effect_proof` 作为发布材料，manual release decision 的 `required_artifact_refs` 必须覆盖该 proof。
- [x] candidate replay side-effect guard 已扩展到 nested `production_final_input`、`notification_input`、`live_order_input`。
- [x] 6C 没有修改 workflow executor、journal 写入口、notification 发送入口或生产切换入口，因此没有运行 `tests/workflow/test_run_executor.py`；深度集成验证保留到 Checkpoint 6 收口或入口边界变化时执行。
- [x] 验证通过：`python -m pytest tests/eval/test_side_effect_proof.py tests/eval/test_release_gate.py tests/eval/test_promotion_review.py tests/eval/test_promotion_artifacts.py tests/eval/test_promotion_artifact_validation.py tests/eval/test_replay_llmjudge.py::test_eval_runner_uses_configured_release_gate_thresholds_without_prod_side_effects -q`。
- [x] 验证通过：`python -m pytest tests/eval -q`。
- [x] 验证通过：`python -m pytest tests/structure -q`。

## 6D 完成记录

- [x] red 结果：`tests/context/test_run_context.py::test_decision_run_context_quarantines_market_fact_like_memory_fields` 初始失败，`DecisionRunContext.memory_snapshot.allowed_fields` 会保留旧 `mark/funding/open_interest/order_book/news_status/macro_event_status/last_model_conclusion/previous_final_action`。
- [x] red 结果：`tests/decision/test_replayable_input.py::test_replayable_input_candidate_quarantines_memory_market_facts` 初始失败，直接从 observed artifacts 构造 replayable input 时也会保留记忆里的旧市场事实。
- [x] 新增 `src/crypto_manual_alert/context/memory_firewall.py`，把可进入 `memory_snapshot.allowed_fields` 的字段收敛到用户偏好、持仓槽位、关注资产、周期、语言、过程约束和上一轮计划上下文等白名单。
- [x] `DecisionRunContext.set_memory_snapshot()` 已复用 memory firewall；旧行情、旧新闻状态、旧宏观状态、旧模型结论和旧 final action 会进入 `quarantined_fields`，不会进入 `allowed_fields`。
- [x] `replay_observed_refs` 已复用同一套 memory firewall，避免 replayable input 直接消费 observed artifacts 时绕过 context sanitizer。
- [x] `replayable_input_summary` 会保留 `quarantined_fields` 与 `memory_warnings` 作为审计元数据，但不保留被隔离字段的原始值。
- [x] 6D 没有修改 workflow executor、journal 写入口、notification 发送入口、CLI 入口或生产切换入口，因此没有运行 `tests/workflow/test_run_executor.py`；深度集成验证仍只在入口边界变化时运行。
- [x] 验证通过：`python -m pytest tests/context/test_run_context.py -q`。
- [x] 验证通过：`python -m pytest tests/context -q`。
- [x] 验证通过：`python -m pytest tests/decision/test_replayable_input.py -q`。
- [x] 验证通过：`python -m pytest tests/eval/test_replayable_input_summary.py -q`。
- [x] Checkpoint 6 收口验证通过：`python -m pytest tests/eval -q --durations=10`。
- [x] Checkpoint 6 收口验证通过：`python -m pytest tests/decision/test_switch_readiness.py tests/decision/test_pre_final_switch_readiness.py -q`。
- [x] Checkpoint 6 收口验证通过：`python -m pytest tests/structure -q`。
- [x] 备注：首次 `python -m pytest tests/eval -q` 使用 120 秒上限时超时，随后使用 300 秒上限重跑通过；慢点集中在 `tests/eval/test_replay_llmjudge.py` 的 replay fixture，不是断言失败或循环卡死。

Checkpoint 7 验收命令：

```powershell
python -m pytest tests/config tests/decision tests/workflow tests/cli -q
python -m pytest tests/eval/test_release_gate.py tests/eval/test_promotion_review.py -q
python -m pytest tests/structure -q
```

## 7A 完成记录

- [x] red 结果：`tests/eval/test_promotion_artifacts.py::test_config_change_review_approval_records_no_side_effect_human_review` 初始导入失败，缺少 `build_config_change_review_approval()`。
- [x] red 结果：`tests/eval/test_promotion_review.py::test_upsert_promotion_review_artifacts_recomputes_release_gate_without_approving` 初始导入失败，promotion review 不能识别人工 config-change approval artifact。
- [x] 新增 `build_config_change_review_approval()`，记录 reviewer、config review request、manual release decision、candidate input、config hash 和 rollback plan ref。
- [x] `config_change_review_approval` 固定 `decision_effect=none`、`allowed_to_change_production_final_input=false`、`runtime_switch_gate_required=true`，只记录人工审批，不直接修改生产配置。
- [x] `release_promotion_review` 在有效 manual release decision 与 config-change request 后识别 approval，状态推进到 `config_change_review_approved`，但 `promotion_approved` 仍为 false。
- [x] `promotion_artifact_validation` 已注册并校验 `config_change_review_approval`，拒绝带生产切换许可的 approval。
- [x] `config/loader.py` 仍拒绝 `decision.final_input_mode=decision_input`；7A 没有放开生产 final input。
- [x] 验证通过：`python -m pytest tests/eval/test_promotion_artifacts.py tests/eval/test_promotion_artifact_validation.py tests/eval/test_promotion_review.py -q`。
- [x] 验证通过：`python -m pytest tests/config -q`。
- [x] 验证通过：`python -m pytest tests/eval/test_release_gate.py -q`。
- [x] 验证通过：`python -m pytest tests/structure -q`。
- [x] 7A 未运行 `tests/workflow/test_run_executor.py`：本小闭环没有修改 workflow executor、journal、notification、CLI 或生产切换入口。

## 7B 完成记录

- [x] red 结果：`tests/decision/test_final_input.py` 初始失败，`decision_input` 模式在 switch readiness 不 ready 或 candidate validation 失败时仍抛异常，不能受控 fallback 到 legacy prompt。
- [x] `select_final_input()` 已支持 candidate failure fallback：当未来 `final_input_mode=decision_input` 但候选输入未 ready、缺失、validation 失败或 ref/hash 缺失时，返回 `legacy_prompt` selection。
- [x] fallback selection 会保留 `fallback_reason`、`fallback_from_mode=decision_input`、`fallback_blocking_reasons`、`candidate_input_ref` 和 `candidate_input_hash`，方便后续审计和回放。
- [x] fallback 不会覆盖事实缺失或风险阻断：`production_control_gate` 的 worker hard block 回归测试已带 fallback final_input_selection 元数据，并仍会阻断可执行动作。
- [x] 生产配置仍未放开；`config/loader.py` 仍拒绝 `decision.final_input_mode=decision_input`。
- [x] 验证通过：`python -m pytest tests/decision/test_final_input.py -q`。
- [x] 验证通过：`python -m pytest tests/decision/test_final_decision_step.py tests/decision/test_production_control_gate.py -q`。
- [x] 验证通过：`python -m pytest tests/workflow/test_decision_control_step.py tests/workflow/test_persistence_payload.py -q`。
- [x] 验证通过：`python -m pytest tests/decision -q`。
- [x] 验证通过：`python -m pytest tests/structure -q`。
- [x] 7B 未运行 `tests/workflow/test_run_executor.py`：本小闭环没有修改 workflow executor、journal、notification、CLI 或生产切换入口。

## 7C 完成记录

- [x] red 结果：`tests/config/test_config.py::test_config_accepts_decision_input_only_with_runtime_switch_review_artifact` 初始失败，`DecisionConfig` 不支持 `final_input_mode_switch_review_path`。
- [x] red 结果：`tests/config/test_config.py::test_config_rejects_decision_input_when_runtime_switch_review_lacks_ref_hash_bindings` 初始失败，switch review artifact 缺少 ref/hash 绑定仍可通过。
- [x] 新增 `src/crypto_manual_alert/config/final_input_switch_review.py`，作为 `decision.final_input_mode=decision_input` 的配置准入 gate。
- [x] loader 只在 `final_input_mode_switch_review_path` 指向有效 JSON artifact 时接受 `decision_input`；否则继续拒绝或报错。
- [x] switch review artifact 必须绑定 `artifact_ref`、`eval_run_id`、release gate ref/hash、promotion/config approval/manual release/config request ref/hash、candidate input ref/hash、config hash、rollback plan ref/hash、rollback target/steps。
- [x] switch review artifact 必须保留安全不变量：`fallback_behavior=legacy_prompt_on_candidate_failure`、`manual_execution_required=true`、`auto_order_enabled=false`。
- [x] 新增 workflow smoke：即使配置准入允许 `decision_input`，当前 runtime readiness 不 ready 时仍 fallback 到 legacy prompt，并保留 candidate ref/hash 与 fallback blocking reasons。
- [x] 验证通过：`python -m pytest tests/config -q`。
- [x] 验证通过：`python -m pytest tests/workflow/test_run_executor.py::test_run_executor_falls_back_to_legacy_when_decision_input_mode_is_approved_but_runtime_not_ready -q`。
- [x] Checkpoint 7 收口验证通过：`python -m pytest tests/config tests/decision tests/workflow tests/cli -q`。
- [x] Checkpoint 7 收口验证通过：`python -m pytest tests/eval/test_release_gate.py tests/eval/test_promotion_review.py -q`。
- [x] Checkpoint 7 收口验证通过：`python -m pytest tests/structure -q`。

Checkpoint 8 验收命令：

```powershell
python -m pytest tests/structure -q
python -m pytest
```

## 8A 完成记录

- [x] red 结果：`tests/workflow/test_persistence_payload.py` 初始失败，plan payload 没有 `legacy_prompt_lifecycle`，无法区分 legacy prompt 当前用途。
- [x] `build_plan_payload()` 新增 `legacy_prompt_lifecycle`，把 legacy prompt 明确分类为 `legacy_primary_until_switch_review`、`decision_input_fallback` 或 `replay_and_comparison_only`。
- [x] 当 `final_input_selection.mode=decision_input` 时，legacy prompt 标记为只允许 `replay_baseline` 与 `legacy_comparison`。
- [x] 当 `decision_input` runtime 不 ready 回落 legacy 时，legacy prompt 标记为 `decision_input_fallback`，并保留 fallback reason 和 blocking reasons。
- [x] 当前默认 legacy 路径仍被标记为 `legacy_primary_until_switch_review`，明确它只是 switch review 前的过渡主路径。
- [x] 完整 runner 已覆盖默认 legacy lifecycle 与 decision_input-approved-but-runtime-not-ready fallback lifecycle。
- [x] 验证通过：`python -m pytest tests/workflow/test_persistence_payload.py -q`。
- [x] 验证通过：`python -m pytest tests/workflow/test_run_executor.py::test_run_executor_full_legacy_chain_feeds_candidate_replay_and_release_gate tests/workflow/test_run_executor.py::test_run_executor_falls_back_to_legacy_when_decision_input_mode_is_approved_but_runtime_not_ready -q`。
- [x] 验证通过：`python -m pytest tests/structure -q`。

## 8B 完成记录

- [x] red 结果：`tests/structure/test_compatibility_wrapper_lifecycle.py` 初始失败，缺少 `docs/formal/33-compatibility-wrapper-lifecycle.md`，且本文与 checkpoint 8 migration 记录未引用该生命周期表。
- [x] 新增 `docs/formal/33-compatibility-wrapper-lifecycle.md`，登记当前 compatibility wrapper、canonical owner、allowed usage、no-new-logic rule、removal condition 和 current guard。
- [x] 生命周期表覆盖 `agent_swarm/contracts.py`、`agent_swarm/harness.py`、`agent_swarm/default_lead_plan.py`、`agent_swarm/shadow_orchestration.py`、`agent_swarm/shadow_failure.py`、`agent_swarm/workers.py`、`agent_swarm/local_workers/` 和 `skills/runtime.py`。
- [x] 生命周期表单独标出 `agent_swarm/registry.py`、`runtime.py`、`pool_runner.py`、`llm_tool_worker.py`、`tool_executor.py`、`shadow_runner.py`、`shadow_inputs.py` 和 `shadow_worker_failures.py` 不是当前 removable wrapper，避免误删仍有职责的 runtime 模块。
- [x] 8B 是文档/结构护栏小闭环，没有修改 workflow executor、journal、notification、CLI、release gate 或生产切换入口，因此没有运行 `tests/workflow/test_run_executor.py`。
- [x] 验证通过：`python -m pytest tests/structure/test_compatibility_wrapper_lifecycle.py -q`。

## 8C 完成记录

- [x] 结构验收通过：`python -m pytest tests/structure -q`。
- [x] 首次全量验收 `python -m pytest` 失败 6 个用例，根因不是生产链路变更，而是 `tests/api/test_api_package_structure.py` 的 `_without_modules()` 只恢复 `sys.modules`，没有恢复父包上的子模块属性，导致后续 monkeypatch 打到临时导入模块。
- [x] 已修复测试 helper：恢复 `sys.modules` 后同步恢复或删除父包属性，避免 `crypto_manual_alert.workflow`、`storage`、`eval` 等包属性残留临时模块对象。
- [x] 最小复现验证通过：`python -m pytest tests/api/test_api_package_structure.py tests/cli/test_runner_cli.py::test_runner_records_shadow_swarm_failure_without_changing_verdict -q`。
- [x] 失败用例集合验证通过：`python -m pytest tests/cli/test_runner_cli.py::test_runner_records_shadow_swarm_failure_without_changing_verdict tests/cli/test_runner_cli.py::test_runner_sends_notification_even_when_shadow_swarm_fails tests/workflow/test_legacy_adapter.py::test_legacy_plan_runner_adapter_passes_full_context_to_plan_runner tests/workflow/test_pre_final_orchestration.py::test_pre_final_orchestration_passes_config_to_shadow_worker_registry tests/workflow/test_pre_final_orchestration.py::test_pre_final_orchestration_builds_single_audit_payload_source tests/workflow/test_run_executor.py::test_run_executor_passes_pre_final_decision_input_to_final_step_boundary -q`。
- [x] 全量验收通过：`python -m pytest`，最终结果 `775 passed in 352.27s`。
- [x] 全量验收后修正本文顶部“当前切换状态”为 Checkpoint 7/8 后的真实状态，并将乱码化文档结构断言收敛为 ASCII 关键字段断言。
- [x] 文档后置结构验收通过：`python -m pytest tests/structure -q`。
- [x] Checkpoint 8 收口后，生产默认链路仍为 `legacy_baseline + legacy_prompt`；`DecisionInput` 生产输入仍只允许通过人工 switch review artifact 打开，且 candidate failure 会 fallback 到 legacy prompt。

## Checkpoint 9 主流程与可视化审计收口 Checklist

Checkpoint 9 是对抗审查后新增的未完成主线。它的目标不是继续堆 sidecar artifact，而是让一次 query/manual run 的主流程白盒化，并能在前端被直接审查。

### Checkpoint 9 当前真实主流程白盒图

当前 `query/manual run` 的真实链路必须按下列 owner 审查，不能再把后端看成黑盒：

```text
POST /api/runs/manual
  -> DecisionRequest
  -> DecisionRunContext
  -> RunExecutor
  -> LegacyPlanRunnerAdapter
  -> PlanRunner.run_once
  -> LegacyDecisionWorkflow
  -> pre_final_orchestration
  -> shadow audit: LeadPlan + 7 required Worker Agents
  -> pre_final DecisionInput / decision_input_candidate / replayable_input_candidate
  -> legacy FinalDecisionAgent
  -> production_control_gate / risk gate
  -> persistence: traces + spans + plan_runs.payload_json
  -> API projection: plan_run.agent_audit_view
  -> frontend view: /runs/{trace_id} Agent Swarm Audit
  -> runtime smoke assertion
```

关键事实：

- 默认生产 final input 仍是 `legacy_prompt`，不是 `DecisionInput`；`DecisionInput` 仍是候选、审计、回放和后续切换评估输入。
- `query_text` 固定为 `audit_note`：保留为操作员审计备注，不驱动 LeadPlan、worker selection、tool budget、facts requirement 或 final input。后续如果要升级为受控 intent，必须新增 IntentClassifier、结构化 intent schema、LeadPlan/worker/tool/facts/DecisionInput 消费路径和反向测试。
- 7 个 required shadow workers 是 `LiveFactAgent`、`DerivativesAgent`、`MacroEventAgent`、`RootCauseAgent`、`MarketSentimentAgent`、`DataQualityAgent`、`ExecutionRiskAgent`，当前均为 shadow audit，不是生产最终决策者。
- 当前已有 5 个 skill facade 和 `SkillToolResult` 边界，但未真实接入默认生产主链；`llm_tool_shadow` 是显式实验路径，不代表默认 Tool loop 已完成。
- `LeadAgent` 当前只做 shadow planning/synthesis；生产默认仍由 legacy final 链路给出计划，再由 production control gate 阻断不安全动作。
- 新增 sidecar/artifact 前必须同时交付 `producer -> persistence -> API projection -> frontend view -> runtime smoke assertion`，并写清 raw/secret/redaction/ref/hash 策略；缺任一环不得合并。运行态护栏入口是 `tools/local_stack/smoke_local_stack.py`。

- [x] 9A：补齐真实主流程文档和代码入口注释，明确 `POST /api/runs/manual -> DecisionRequest -> DecisionRunContext -> RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner.run_once -> LegacyDecisionWorkflow -> pre_final_orchestration -> shadow audit -> pre_final DecisionInput -> legacy FinalDecisionAgent -> production_control_gate/risk -> persistence -> agent_audit_view -> frontend` 的 owner、输入、输出、trace ref 和失败策略；默认 final input 仍是 `legacy_prompt`。
- [x] 9B：修正 `query_text` 语义。当前固定为 `audit_note`，只作为审计备注；API projection、前端页面和 local smoke 都必须显示它不驱动 final input。
- [x] 9C：修正 trace 绑定。`RunExecutor` 不得通过最近 traces 反查当前 `trace_id`；runner/adapter 必须显式返回本次 trace_id，且空 trace_id 必须失败，避免并发或 controlled_shadow 路径错配。
- [x] 9D：明确 sidecar/audit 与 production-blocking gate 的关系。pre-final 不喂 final decision，但 candidate audit 会影响 `production_control_gate`；文档、payload 字段和前端展示必须避免误导。
- [x] 9E：修正 `controlled_shadow` 可追踪性。该模式保留为 audit-only，必须 start/finish trace、persist plan_run，在 API/UI/eval 中暴露安全版 `controlled_shadow` 标记，并保持 `production_final_input=false`、`notification_input=false`。
- [x] 9F：补齐 Agent/Skill 主链差距说明和下一步策略。当前 7 个 Worker 是 shadow audit，5 个 skill facade 没有真实接入默认主链，LeadAgent 只是 shadow/audit 协调者；后续任何“Agent 系统完成”判断都必须先满足可审计主候选链路。
- [x] 9G：新增脱敏 `agent_audit_view` API 投影。`GET /api/runs/{trace_id}` 必须能返回 LeadPlan、7 个 worker result、Lead synthesis、harness validation、facts gate、evidence packets、pre-final DecisionInput、decision_input_candidate、gate_candidate、final_input_selection、production_control_gate 和 replay refs。
- [x] 9H：补齐前端 Agent 可视化审计页。`/runs/{trace_id}` 不能只显示 span 列表和 JSON；必须用一等 UI 展示 worker 状态矩阵、LeadPlan、并发执行关系、每个 Agent 贡献、冲突和缺失事实、Skill/tool 调用、DecisionInput、Gate 和最终输入选择。
- [x] 9I：补齐运行态验收。必须启动 API 和 frontend，用一次新生成 trace 验证 Network 响应和页面都能看到 `shadow_swarm_audit.worker_results`、`lead_synthesis`、`DecisionInput`、`gate_candidate`、`final_decision_switch_readiness`、`production_control_gate`。
- [x] 9J：补齐 local stack smoke 断言。不能只检查页面存在和 trace_id 匹配，必须断言 API/页面出现 `LeadPlan`、`ExecutionRiskAgent`、`DecisionInput`、`production_control_gate` 等关键审计内容。
- [x] 9K：同步修正文档事实。`29`、`30` 的当前事实段落必须统一为：7 required worker，业务实现归 `market_agents/`，`agent_swarm/local_workers/` 是兼容 re-export，不能再使用旧 worker 数量或旧 owner 口径。
- [x] 9L：补充结构护栏：新增 sidecar/artifact 前必须同时明确 producer、persistence、API projection、frontend view、runtime smoke assertion，否则不得合并；对应结构测试必须扫描 29/30/31、API projection、前端 schema/page 和 `tools/local_stack/smoke_local_stack.py`。

Checkpoint 9 当前已验证命令：

```powershell
python -m pytest tests/workflow/test_run_executor.py::test_run_executor_rejects_empty_adapter_trace_id tests/workflow/test_controlled_adapter.py::test_controlled_swarm_audit_adapter_persists_traceable_audit_only_run tests/storage/test_agent_audit_view.py::test_agent_audit_view_projects_controlled_shadow_without_raw_payloads tests/eval/test_case_builder_candidate_audit.py::test_candidate_audit_summary_preserves_controlled_shadow_audit_only_marker tests/structure/test_formal_docs_current_state.py::test_query_semantics_is_asserted_across_api_frontend_and_runtime_smoke -q
python -m pytest tests/structure/test_formal_docs_current_state.py::test_formal_docs_do_not_reintroduce_stale_worker_count_or_owner_facts tests/structure/test_formal_docs_current_state.py::test_checkpoint_9_records_artifact_full_chain_guard tests/structure/test_formal_docs_current_state.py::test_query_semantics_is_asserted_across_api_frontend_and_runtime_smoke -q
python -m pytest tests/storage/test_agent_audit_view.py tests/storage/test_query_repository.py tests/api/test_runs_routes.py tests/local_stack/test_scripts.py -q
python -m pytest -q
cd frontend; npm run typecheck; npm run build
python tools/local_stack/smoke_local_stack.py
```

## 9A/9B/9C/9E/9F/9K/9L 完成记录

- [x] red 结果：`tests/workflow/test_run_executor.py::test_run_executor_rejects_empty_adapter_trace_id` 初始失败，`RunExecutor` 接受了空 `trace_id`。
- [x] `DecisionStepResult` 保持 adapter 结果契约，`RunExecutor` 和 `LegacyPlanRunnerAdapter` 在执行边界要求 `require_trace_id=True`，避免最近 trace 反查。
- [x] red 结果：`tests/workflow/test_controlled_adapter.py::test_controlled_swarm_audit_adapter_persists_traceable_audit_only_run` 初始失败，`audit_only.controlled_shadow` 缺失。
- [x] `ControlledSwarmAuditAdapter` 写入完整 trace、`journal.write` span、blocked plan_run，并在顶层和 `audit_only` 命名空间同时暴露 safe `controlled_shadow`。
- [x] red 结果：`tests/eval/test_case_builder_candidate_audit.py::test_candidate_audit_summary_preserves_controlled_shadow_audit_only_marker` 初始失败，eval summary 丢失 controlled shadow 标记。
- [x] Eval case builder 只保留 `mode/audit_only/production_final_input/notification_input/reason`，不暴露 raw 字段。
- [x] `query_text` 明确为 `audit_note`，后端 `agent_audit_view`、前端 schema/page 和 local smoke 都有 `query_semantics` 护栏。
- [x] `29`、`30`、`31` 已修正旧 worker 数量和 canonical owner 事实：7 required worker，`market_agents/` 为业务 worker owner，`agent_swarm/local_workers/` 为兼容 re-export only。
- [x] 新增 migration 记录：`docs/migration/2026-07-04-checkpoint-9-main-flow-trace-query.md`。
- [x] 全量 pytest 通过：`python -m pytest -q`。
- [x] 前端类型检查和生产构建通过：`npm run typecheck`、`npm run build`。
- [x] 本地栈 smoke 通过：`python tools/local_stack/smoke_local_stack.py`。
- [x] 本地栈已重新启动并生成运行态审计页面：`http://127.0.0.1:3001/runs/72fdbdd9789d4b3985d95a6f4d5ddcf3`。

## 9D/9G/9H/9I/9J 完成记录

- [x] red 结果：`tests/storage/test_agent_audit_view.py` 初始导入失败，缺少 `crypto_manual_alert.storage.agent_audit_view`。
- [x] red 结果：`tests/api/test_runs_routes.py::test_run_detail_exposes_sanitized_agent_audit_view` 初始缺少 `plan_run.agent_audit_view`。
- [x] 新增 `src/crypto_manual_alert/storage/agent_audit_view.py`，从完整 `plan_runs.payload_json` 中投影 UI/API 安全视图，只暴露 ref、hash、summary、counts、gate 结果和 runtime flow。
- [x] `journal_rows.plan_run_row()` 已返回 `agent_audit_view`；`JournalQueryRepository.get_run_detail()` 和 `/api/runs/{trace_id}` 默认可见该投影，不依赖 `include_payloads=true`。
- [x] `agent_audit_view` 明确 `decision_effect=audit_only_input_production_blocking_gate`，避免把 shadow/candidate 误解为 production final input，同时承认其会影响 `production_control_gate`。
- [x] 投影过滤 `raw_decision`、`frozen_input`、完整 prompt/completion 和 raw/frozen refs；LLM `include_payloads=true` 仍只属于受控复盘通道。
- [x] 前端 `frontend/src/lib/schemas/runs.ts` 已建模 `agent_audit_view` 并保留 passthrough，避免后端新增字段被 Zod 静默剥离。
- [x] `/runs/{trace_id}` 新增 `Agent Swarm Audit` 一等 UI，展示 LeadPlan、Worker Agent Matrix、DecisionInput、Gates、Runtime Flow、ExecutionRiskAgent 和 `production_control_gate`。
- [x] `tools/local_stack/smoke_local_stack.py` 已从“页面存在”升级为 API/页面双断言：必须看到 `LeadPlan`、`ExecutionRiskAgent`、`DecisionInput`、`production_control_gate`。
- [x] 首次运行态 smoke 失败：端口 `8010` 被旧本地 `uvicorn crypto_manual_alert.api.app` 进程占用；确认 PID 37728 后停止该本项目进程并重跑。
- [x] 运行态 smoke 重跑通过：`python tools/local_stack/smoke_local_stack.py` 返回 `ok=true`，API `http://127.0.0.1:8010`，frontend `http://127.0.0.1:3001`，notification disabled。

## 每个小闭环完成定义

- 必须先写失败测试或结构护栏，并记录 red 结果。
- 实现只覆盖当前小闭环，不借机扩大到后续小闭环。
- 新增文件归属明确，且被 registry、factory、harness、workflow 或 tests 引用。
- Worker 有独立 `SubTask`、input view、status、trace ref、output hash 和 failure policy。
- Worker 输出只追加 contribution/evidence，不写 final decision、gate verdict、journal、notification 或 side-effect intent。
- LeadAgent 只规划和综合，不绕过 FactsGate/RiskGate，不生成最终交易动作。
- DecisionInput/candidate/eval/replay 仍保持 audit/sidecar 语义，生产 final 不切换。
- 相关窄范围测试、结构测试和必要 workflow/CLI smoke 必须通过。
- 本文 checkbox、任务队列和 `docs/migration/` 实施记录必须同步更新。

## 验收命令清单

小闭环窄范围验证：

```powershell
python -m pytest tests/market_agents -q
python -m pytest tests/agent_swarm tests/lead tests/decision/test_switch_readiness.py -q
python -m pytest tests/workflow/test_pre_final_orchestration.py -q
python -m pytest tests/cli/test_runner_cli.py -q
```

入口边界或 checkpoint 收口深度验证：

```powershell
python -m pytest tests/workflow/test_run_executor.py -q
```

结构验证：

```powershell
python -m pytest tests/structure -q
```

全量验证：

```powershell
python -m pytest
```

## 汇报模板

```text
当前 checkpoint:
当前小闭环:
完成项:
修改文件:
失败测试/结构护栏是否先写:
新增文件归属:
是否有未接入/重复实现:
生产默认链路是否仍为 legacy_baseline + legacy_prompt:
验证命令:
结果:
未完成项:
是否触发暂停条件:
下一步:
```
