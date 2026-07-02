# Agent 与 Skill 拆分详细设计

## 1. 设计目标

本文是 `crypto-macro-decision` 方法论拆分到项目 Agent/Skill 编排层的详细设计。

`27-轻量自研Workflow与受控Agent层重构建议.md` 记录的是总体方向；本文进一步定义 Agent、Skill、Schema、执行模式、代码门禁和迁移验收，作为后续实现前的设计约束。

核心目标：

- 不再把 `crypto-macro-decision` 当成一整段 prompt 直接交给最终 LLM。
- 将其中的交易思想拆成可编排、可审计、可回放的 Agent/Skill。
- 让实时事实、根因链、市场情绪、拥挤度、场景分叉、反方审查和最终决策各自有明确边界。
- 所有实时判断必须基于当前事实，历史经验只能作为方法论和低权重过程记忆，不能当作当前市场事实。
- 允许系统给出大胆预测，但大胆预测必须来自事实链条，并带有明确证伪条件。
- 交易动作必须唯一、可解析、可被风控门禁阻断或降级。

一句话原则：

```text
Skill 提供专业能力，Agent 负责任务分工和结构化贡献，LeadAgent 负责规整冲突，FinalDecisionAgent 只输出唯一动作，代码 Gate 负责硬边界。
```

## 1.1 开发前必须核对的目标 checklist

每次继续重构前，必须先对照本 checklist，避免把任务退化成“整理文档”或“给旧 pipeline 补字段”。

- 当前改动是否让 Agent / Skill / Policy / Gate 的职责边界更清楚。
- 当前改动是否让 Worker Agent 更像独立运行单元，而不是 `leader_summary` 的一个 key。
- 当前改动是否让 LeadAgent 更能规整冲突、标记缺失 contribution、构建结构化决策输入。
- 当前改动是否让 FinalDecisionAgent 更接近“只消费 `DecisionInput`”，而不是继续直接消费 legacy `prompt_packet`。
- 当前改动是否让完整可回放输入更接近保存 worker artifact、contribution、gate result 和 final raw output。
- 当前改动是否有 runtime harness 或代码 gate 约束，防止非 Final agent 输出可执行交易字段。
- 当前改动是否有 fixture / unit test / regression test 证明不会污染生产 prompt、RiskGate、journal 或 notification。

如果以上问题多数答案是否定，本轮就不是受控 Agent Swarm 重构主线，必须先重新收敛范围。

## 2. 非目标

当前阶段不做：

- 自由聊天式多 Agent swarm。
- 动态发现任意 skill。
- 任意脚本自动注册为工具。
- 自动下单、撤单、提现。
- 让 LLM 修改生产 prompt、规则或 workflow。
- 把历史交易结论默认注入 live decision。
- 用社媒或 search snippet 替代交易所原生执行事实。
- 让 RootCauseSkill 或 reviewer 直接决定最终交易动作。

## 3. 方法论拆解

`crypto-macro-decision` 的核心思想应拆成以下能力：

| 方法论 | 编排落点 | 说明 |
|---|---|---|
| 实时事实防火墙 | `LiveFactSkill` + `FactsGate` | 所有实时决策先刷新事实，缺失/陈旧/冲突不能当作中性 |
| 来源优先级 | `SourcePriorityPolicy` | 代码化，不交给 LLM 自由判断 |
| 会话记忆与事实隔离 | `SessionMemoryManager` + `MemoryFirewall` | 记住用户持仓和追问上下文，但不让旧行情、旧新闻、旧结论污染实时判断 |
| Harness 约束系统 | `HarnessPolicy` + runtime validator | 用 YAML/规则文件显式定义 Agent 能力边界、schema、tool policy、timeout、修复和拦截策略 |
| 根因链 | `RootCauseSkill` | 从事件递归追溯到 durable root driver，并输出证伪条件 |
| 市场情绪与拥挤 | `SentimentCrowdingSkill` | 判断事实是否已定价、仓位是否拥挤、短期是否可能反向 |
| 宏观传导 | `MacroBridgeSkill` | 利率、DXY、VIX、油价、QQQ/NQ 如何传到 BTC/ETH/SOL |
| 衍生品结构 | `DerivativesSweepSkill` | funding、OI、long/short、liquidation、basis、CVD、options |
| 指标扫描 | `IndicatorSweepSkill` | 15 项指标只做异常扫描和 bucket 分类 |
| 场景分叉 | `ScenarioForkSkill` | 重大事件时输出 base/upside/downside，不生成多个动作 |
| 对抗审查 | reviewer agents | 多头、空头、数据质量、执行风险独立贡献 |
| 决策阶梯 | `DecisionLadderSkill` | 主信号投票、分数阶梯、已有仓位规则、event compression |
| 最终动作 | `FinalDecisionAgent` | 只消费 `DecisionInput`，输出 strict JSON |
| 风控门禁 | Parser/Facts/Semantic/Risk Gates | 代码强制执行，优先级高于 LLM |

## 4. 总体 Workflow

采用“串行控制骨架 + 并发研究/审查内核”：

```text
Manual/Scheduled Query
  -> SessionManager
  -> SessionMemoryManager
  -> IntentClassifier
  -> ComplexityRouter
  -> SlotFiller
  -> DecisionRequestBuilder
  -> VersionLock(skill/rule/prompt/model/config)
  -> SkillLoader + ToolPolicy
  -> HarnessPolicyLoader
  -> MarketFactAgent
  -> FactsGate(pre)

  -> LeadAgent.plan_tasks
  -> Parallel Worker Agents
       MarketFactAgent
       DerivativesAgent
       MacroResearchAgent
       FlowEventAgent
       RelativeStrengthAgent
       TechnicalGuardrailAgent
  -> EvidencePacketBuilder
  -> FactsGate(post)
  -> DataQualityGate

  -> RootCauseAgent
  -> MarketSentimentAgent
  -> ScenarioForkAgent(optional)
  -> Reviewer Agents
       BullReviewer
       BearReviewer
       DataQualityAgent
       ExecutionRiskAgent
  -> LeadAgent.synthesize
  -> DecisionInputBuilder
  -> HarnessValidator(pre-final)
  -> FinalDecisionAgent
  -> HarnessValidator(post-final)
  -> ParserGate
  -> PlanSemanticGate
  -> RiskGate
  -> SideEffectGate
  -> FrozenInput / safe audit sidecar
  -> production Journal / plan_runs / notification intent
  -> Bark manual alert or eval/replay no side effect
```

必须串行的环节：

- session / intent / complexity / slots
- version lock
- pre facts gate
- lead synthesis
- decision input build
- final decision
- parser / semantic / risk gates
- side effect gate
- journal / notification

可以并发的环节：

- market facts 补充采集
- macro / flow / event research
- derivatives / relative strength / technical guardrails
- bull / bear / data quality / execution risk reviewers
- eval/replay 旁路测评

### 4.1 当前实现状态

当前代码还不是上面定义的受控 Agent Swarm。

当前实际生产主链仍接近固定 pipeline：

```text
RunExecutor
  -> LegacyPlanRunnerAdapter
  -> PlanRunner / LegacyDecisionWorkflow
  -> fetch market snapshot
  -> load skill text / references
  -> optional research fallback
       -> 并发执行多个 search query
       -> 单个 leader_synthesizer 汇总
          -> 输出 bull_reviewer / bear_reviewer / data_quality_reviewer / execution_risk_reviewer JSON key
  -> final LLM decision
  -> strict parser
  -> risk gate
  -> journal
  -> Bark
```

当前 shadow audit 已具备部分受控 Agent Swarm 骨架，但仍不是生产接管：

- `orchestration.shadow_audit` 是 shadow audit 的 canonical 编排入口，负责 Lead planning、worker registry、`ShadowSwarmRunner` 和失败 envelope。
- `agent_swarm/` 负责 worker、runner、registry、LLM/tool worker；`agent_swarm.shadow_orchestration` 只保留兼容导出。
- shadow audit 已有 `LeadPlan`、`SubTask`、7 个 required shadow workers、`AgentContribution`、worker span、timeout/status/failure_policy 和 harness 校验。
- `LeadAgent.synthesize` 已规整 worker contribution、缺失 worker、dropped contribution 和冲突，并进入 `pre_final_decision_input`、`decision_input_candidate` 与 replay sidecar。
- 上述产物都必须保持 `decision_effect=none`，不写生产 journal/notification，不替换 FinalDecisionAgent 输入。

当前已有价值：

- search query 可以并发执行。
- shadow worker 已能以独立任务和独立 contribution 输出实时事实、衍生品、宏观事件、根因、情绪、数据质量和执行风险审计。
- trace / frozen input / eval 旁路已有基础。
- search_derived 不能替代核心执行事实的约束已有雏形。

当前还缺的关键能力：

- shadow worker 仍默认是本地审计器，不是稳定生产级 LLM/tool Agent。
- 真实实时检索、衍生品、宏观、根因递归、情绪拥挤等 Skill 仍未全部作为受控工具能力接入 worker。
- worker contribution 仍只进入 shadow/candidate/replay 和负向 production control，不是 FinalDecisionAgent 的真实上下文。
- FinalDecisionAgent 仍消费 legacy prompt，不是严格只消费 `DecisionInput`。
- 完整可回放输入仍是 audit sidecar，不替换生产 `FrozenInput`。
- `decision.final_input_mode=decision_input` 仍必须被配置加载拒绝，不能由 readiness 自动打开。

因此本文后续提到的完整 `LeadAgent`、`Worker Agents`、`AgentContribution` 和 `HarnessValidator` 是生产级目标架构，不等于当前 shadow audit 已经接管生产。迁移时不得把当前 shadow/candidate 产物误认为生产 swarm，也不得在 FinalDecisionAgent 仍消费 legacy prompt 时宣称已完成受控 Agent Swarm。

### 4.2 目标形态：受控 Agent Swarm，不是自由聊天式 Swarm

本项目必须从当前固定 pipeline 重构为受控 Agent Swarm。这里反对的是自由聊天式 swarm、Agent 自由 handoff、动态 spawn 和无限 tool loop，不是反对 swarm 本身。原因是本项目输出可能影响真实资金行为，凡是会产生 `open/close/flip/trigger/hold` 类操作建议的请求，都应默认经过多个独立 Worker Agent 的事实、根因、情绪、数据质量和执行风险审查。

目标形态应定义为：

```text
确定性 Workflow 控制主链路
  + LeadAgent 规划任务和规整贡献
  + 多个独立 Worker Agents 并行产生 EvidencePacket / AgentContribution
  + FinalDecisionAgent 只基于 DecisionInput 输出唯一动作
  + Parser/Facts/Semantic/Risk Gates 代码兜底
```

这是 Agent Swarm，但不是自由 swarm：

- Worker Agent 不能自行决定下一步全局流程。
- Worker Agent 不能调用未授权工具。
- Worker Agent 不能写最终动作。
- Worker Agent 不能修改 risk verdict。
- Worker Agent 不能触发 Bark、下单、撤单、提现等副作用。
- LeadAgent 不能绕过 FactsGate / RiskGate。
- FinalDecisionAgent 不能调用工具或重新检索事实。

更准确的执行模型是“串行控制骨架 + 并发研究/审查内核”：

```text
串行：session -> request -> facts gate -> lead synthesis -> final decision -> gates -> journal/side effect
并发：fact enrichment / macro research / derivatives review / root cause / sentiment / adversarial reviewers
```

这套设计的价值不是让 Agent 自由聊天，而是让每个关键判断都成为可审计贡献，并能被 LeadAgent 规整、被 Harness 限制、被 Gate 否决、被 Eval 回放。

### 4.3 Swarm 完成定义

以下条件全部满足，才算完成受控 Agent Swarm 重构：

- 7 个 required shadow workers 必须在同一 run 中作为独立运行单元出现：`LiveFactAgent`、`DerivativesAgent`、`MacroEventAgent`、`RootCauseAgent`、`MarketSentimentAgent`、`DataQualityAgent`、`ExecutionRiskAgent`。
- 每个 Worker Agent 有独立 `SubTask`。
- 每个 Worker Agent 有独立 input view、timeout、status、failure_policy、trace span。
- 每个 Worker Agent 输出独立 `AgentContribution` 或 `EvidencePacket`。
- Worker Agent 失败不能伪装成功，LeadAgent 必须显式标记缺失。
- LeadAgent 必须基于 `LeadPlan` 分配任务，而不是把 reviewer 写成一个 LLM JSON key。
- FinalDecisionAgent 只能消费 `DecisionInput`，不能直接消费 `leader_summary`、raw research 或 prompt_packet。
- Eval/FrozenInput 能回放每个 Worker Agent 的输入、输出、失败和被 Lead 采纳/丢弃情况。

只完成以下事项不算 swarm：

- 并发 search query。
- 一个 LLM call 输出多个 reviewer key。
- static fallback 字典里有 bull/bear/data_quality/execution_risk。
- 只把 reviewer key 包装成 `AgentContribution`，但没有独立 Worker Agent runner。
- LeadAgent 只是 summary prompt，没有任务分配和失败传播。

## 5. 核心数据结构

### 5.1 DecisionRequest

描述用户希望系统评估什么，不拉行情、不调用 LLM、不做交易判断。

```json
{
  "run_id": "string",
  "run_type": "manual | scheduled | eval | replay | postmortem",
  "query_text": "string",
  "symbol": "BTC-USDT-SWAP",
  "asset": "BTC",
  "horizon": "now | 1h | 4h | 1d | event_window",
  "position": {
    "side": "unknown | long | short | flat",
    "entry_price": null,
    "leverage": null,
    "liquidation_price": null
  },
  "manual_only": true,
  "session_id": "string|null"
}
```

### 5.2 DecisionRunContext

`DecisionRunContext` 是一轮运行的唯一上下文对象，但不能成为任意模块都能读写的大杂烩。它应按字段分区，并由代码限制写权限。

```json
{
  "run_id": "string",
  "trace_id": "string",
  "request": {},
  "run_mode": "info_only | standard_decision | deep_research",
  "memory_snapshot": {},
  "version_lock": {
    "skill_hashes": {},
    "prompt_hashes": {},
    "rule_hashes": {},
    "model": "string",
    "config_hash": "sha256"
  },
  "lead_plan": {},
  "evidence_store": [],
  "contribution_store": [],
  "lead_synthesis": null,
  "decision_input": null,
  "raw_final_decision": null,
  "gate_results": [],
  "side_effect_policy": {},
  "side_effect_intent": null
}
```

写权限矩阵：

| 字段 | 写入者 | 规则 |
|---|---|---|
| `request` | `DecisionRequestBuilder` | 创建后不可变 |
| `memory_snapshot` | `SessionMemoryManager` | 创建后只读，Agent 不得写 |
| `version_lock` | `WorkflowExecutor` | 创建后不可变 |
| `lead_plan` | `LeadAgent` + Harness | 只能选择枚举任务，不能动态发明任务 |
| `evidence_store` | `ToolExecutor` / `LiveFactSkill` | append-only，禁止 Worker 原地修改或删除 |
| `contribution_store` | `AgentRunner` | append-only，失败也必须写 failed/partial |
| `lead_synthesis` | `LeadAgent` | 必须引用 contribution/evidence，不得丢弃反方证据不留原因 |
| `decision_input` | `DecisionInputBuilder` | 只使用 eligible evidence view 和裁剪后的动作空间 |
| `raw_final_decision` | `FinalDecisionAgent` | 只能写原始输出，不得写 RiskVerdict |
| `gate_results` | Gate 层 | append-only，记录阻断/降级原因 |
| `side_effect_policy` | `WorkflowExecutor` | 由 run_type 决定，eval/replay 必须 no side effect |
| `side_effect_intent` | `SideEffectGate` | gate 通过后才允许生成生产写入/通知意图 |

并发规则：

- Worker Agent 只读 `request`、`memory_snapshot`、eligible evidence view 和分配给自己的 `SubTask`。
- Worker Agent 只能追加 `EvidencePacket` 或 `AgentContribution`。
- Worker Agent 不得写 `lead_synthesis`、`decision_input`、`raw_final_decision`、`gate_results`、`side_effect_intent`。
- 不允许 Agent-to-Agent 直接通信、handoff、动态 spawn。所有协作必须经过 `DecisionRunContext` 的 append-only store 和 `LeadAgent` 汇总。
- 如果两个 Worker 输出冲突，只能追加 conflict，由 `LeadAgent` 和 Gate 处理，不能互相覆盖。

### 5.3 LeadPlan

`LeadAgent.plan_tasks` 不能自由发明任务。它只能从 Harness 配置和代码枚举中选择任务，输出结构化 `LeadPlan`。

```json
{
  "run_mode": "standard_decision",
  "deadline_ms": 900000,
  "max_parallel_workers": 6,
  "max_tool_calls": 16,
  "tasks": [
    {
      "task_id": "task_derivatives",
      "task_type": "market_fact | derivatives | macro | flow_event | relative_strength | technical_guardrail | root_cause | sentiment_crowding | scenario_fork | reviewer",
      "assigned_agent": "DerivativesAgent",
      "required": true,
      "input_refs": [],
      "allowed_tools": [],
      "timeout_seconds": 90,
      "failure_policy": "hard_block | confidence_cap | soft_downgrade | skip"
    }
  ]
}
```

LeadPlan 约束：

- `task_type`、`assigned_agent`、`allowed_tools` 必须来自枚举。
- `max_parallel_workers`、`max_tool_calls`、`deadline_ms` 只能等于或严于 Harness 上限。
- LeadAgent 不得创建下单、撤单、提现、交易所账户读取、密钥读取相关任务。
- LeadAgent 不得把 required task 改成 optional 来绕过失败。
- LeadAgent 不得过滤最强反方链、`DataQualityAgent` 的 hard block、`ExecutionRiskAgent` 的执行阻断。
- LeadAgent 丢弃任何 contribution 时必须记录 `discard_reason`、`discarded_by`、`conflict_refs`。

### 5.4 EvidencePacket

所有工具和研究结果必须统一转成 `EvidencePacket`。原始网页片段、交易所原始 JSON、LLM 原始回答不能直接进入最终 prompt。

```json
{
  "evidence_id": "string",
  "name": "okx_mark_price",
  "symbol": "BTC-USDT-SWAP",
  "data_type": "mark | index | last | order_book | candles | funding | open_interest | liquidation | macro | news | etf_flow | stablecoin | options | sentiment",
  "value": {},
  "unit": "USDT",
  "observed_at": "ISO-8601",
  "retrieved_at": "ISO-8601",
  "age_seconds": 42,
  "source_type": "exchange_native | official_api | official_page | aggregator_api | reputable_news | web_derived | search_derived | social_rumor | fixture",
  "source_tier": 1,
  "source_name": "OKX",
  "source_url": "https://...",
  "freshness_status": "fresh | stale | unknown",
  "can_satisfy_execution_fact": true,
  "confidence_cap": null,
  "claims": [],
  "conflicts": [],
  "tool_latency_ms": 820,
  "trace_ref": "span_id"
}
```

关键规则：

- `exchange_native` 才能满足核心执行事实。
- `search_derived` 只能降低不确定性，不能满足 mark/index/order_book。
- 每个 packet 必须有 source、timestamp、freshness。
- missing/stale/conflict 必须显式写入，不能当中性。

### 5.5 AgentContribution

所有 Agent 输出都要归一为贡献对象，供 LeadAgent 汇总。

```json
{
  "contribution_id": "string",
  "agent_name": "RootCauseAgent",
  "status": "ok | partial | failed | skipped",
  "required": true,
  "summary": "string",
  "claims": [
    {
      "claim": "string",
      "claim_type": "known_fact | consensus | inference | scenario | rumor",
      "side": "bullish | bearish | mixed | neutral",
      "evidence_ids": [],
      "confidence": "high | medium | low",
      "freshness": "fresh | mixed | stale"
    }
  ],
  "constraints": {
    "confidence_cap": null,
    "blocked_actions": [],
    "allowed_action_classes": [],
    "required_confirmations": [],
    "next_review_minutes": null
  },
  "conflicts": [],
  "missing_facts": [],
  "input_ref": "artifact://agent-input/...",
  "output_hash": "sha256",
  "agent_version": "string",
  "prompt_hash": "sha256|null",
  "model": "string|null",
  "repair_attempts": 0,
  "retry_count": 0,
  "failure_policy_applied": "none | confidence_cap | soft_downgrade | hard_block",
  "parent_span_id": "span_id|null",
  "trace_ref": "span_id"
}
```

非 Final agent 的贡献只能表达事实、推理、约束、冲突和缺口，不能输出可执行交易参数。禁止字段包括：

- `main_action`
- `entry_trigger`
- `stop_price`
- `target_1`
- `target_2`
- `leverage`
- `position_size`
- `order_payload`
- `risk_verdict`
- 任何“立即开/平/反手/加仓/减仓”的命令式同义表达

`ExecutionRiskAgent` 只能审查已经存在的 entry/stop/target/RR 是否合理，不能生成新的可执行参数。

### 5.6 DecisionInput

FinalDecisionAgent 只能消费 `DecisionInput`，不能访问工具、原始网页、原始交易所 JSON。

```json
{
  "request": {},
  "eligible_evidence_refs": [],
  "ineligible_evidence_refs": [
    {
      "evidence_id": "string",
      "reason": "stale | missing_source | low_tier | conflict | fixture_in_live | replay_in_live"
    }
  ],
  "facts_gate_result": {},
  "root_cause": {},
  "sentiment_crowding": {},
  "scenario_fork": {},
  "review_contributions": [],
  "lead_synthesis": {
    "primary_signal_vote": {},
    "scorecard": {},
    "strongest_chain": {},
    "strongest_opposite_chain": {},
    "confidence_caps": [],
    "hard_blocks": [],
    "soft_downgrades": [],
    "required_refreshes": []
  },
  "canonical_actions": [
    "open long",
    "open short",
    "hold long",
    "hold short",
    "close long",
    "close short",
    "flip long to short",
    "flip short to long",
    "trigger long",
    "trigger short",
    "no trade"
  ],
  "effective_allowed_actions": [],
  "blocked_actions": [
    {
      "action": "open long",
      "reason": "missing exchange-native mark/index/order_book"
    }
  ],
  "execution_mode": "executable | recheck_only | blocked",
  "confidence_policy": {
    "max_probability": 0.58,
    "cap_reasons": [],
    "cap_applied_by_gate": true
  }
}
```

关键规则：

- `canonical_actions` 只是系统支持的动作全集，不能直接交给 FinalDecisionAgent 当选择空间。
- `effective_allowed_actions` 必须由 `DecisionInputBuilder` 基于 FactsGate、Risk precheck、持仓状态、run mode 和 hard blocks 裁剪后生成。
- 缺核心执行事实时，`open long`、`open short`、`flip long to short`、`flip short to long`、`trigger long`、`trigger short` 都必须从 `effective_allowed_actions` 移除。
- `flip long to short` / `flip short to long` 在当前阶段默认 hard block，除非后续显式增加人工二次确认字段和对应 Gate。
- `trigger long/short` 不是低风险替代动作；带价格、止损、目标的 trigger 仍然是可执行交易建议，必须满足核心事实门禁。
- `no trade` 要区分主动观望与 blocked no-trade。blocked no-trade 必须列出缺失事实，并说明 long/short trigger 需要哪些事实刷新后才可重新评估。
- 多个 confidence cap 取最低值。FinalDecisionAgent 输出概率高于 `max_probability` 时，Parser/Semantic/Risk Gate 必须阻断或降级，不能只做展示修正。

### 5.7 现有数据结构迁移映射与禁止字段

当前代码中的 `MarketSnapshot`、`DataPoint`、`ResearchAudit`、`leader_summary`、`prompt_packet` 需要逐步退化为兼容 adapter，不能继续作为最终 LLM 的直接输入。

迁移映射：

| 当前结构 | 目标结构 | 迁移规则 |
|---|---|---|
| `MarketSnapshot.points.last/mark/index/order_book/candles` | `EvidencePacket[]` | source_type 必须为 `exchange_native`，带 observed_at/retrieved_at/freshness |
| `MarketSnapshot.unavailable` | `FactsGateResult.missing_facts/confidence_caps` | 结构化成 missing/stale/conflict/cap，不能只保留字符串 |
| `SearchResult` | `EvidencePacket` | 只能作为 `news/macro/context` 类证据，source_type 规范为 `search_derived` 或 `web_derived` |
| `ResearchAudit.results` | `EvidenceStore` | 原始 snippet 不进 FinalDecisionAgent，只保留摘要、source_url、retrieved_at、claim refs |
| `ResearchAudit.leader_summary` | `AgentContribution[]` | 每个 reviewer key 转为独立 contribution，带 status、input_ref、output_hash |
| `prompt_packet` | `DecisionInput` | 过渡期只作为 legacy artifact 保存，不能作为最终决策输入长期保留 |

禁止进入 `FinalDecisionAgent` 的字段：

- raw search snippet。
- raw exchange JSON。
- 完整网页正文。
- 完整 `SKILL.md` 文本。
- 未通过 FactsGate 的 `MarketSnapshot`。
- 旧 memory 中的市场事实。
- replay/fixture evidence。
- social rumor 未确认内容，除非明确标为 low-confidence scenario 且不进入 known_fact。

source type canonical enum：

```text
exchange_native
official_api
official_page
aggregator_api
reputable_news
web_derived
search_derived
social_rumor
fixture
replay
```

规范化规则：

- 代码内部统一使用下划线形式，例如 `search_derived`，外部输入的 `search-derived` 只能被规范化为同等低信任类型。
- 未知 `source_type` 默认不可信，在 manual/scheduled run 中触发 hard block 或从 eligible evidence 中剔除。
- `fixture`、`replay` 在 manual/scheduled live run 中禁止作为 live evidence，只能进入 eval/replay sidecar。
- `search_derived`、`web_derived` 永远不能满足 mark/index/order_book。

## 6. 记忆机制与事实隔离

记忆机制需要做，但不能照搬医疗助手的双层记忆。加密货币趋势预测的实时性和资金风险更高，记忆设计必须服务上下文连续性，而不能污染 live decision。

### 6.1 设计结论

当前建议：

```text
短期结构化记忆：必须做
长期过程记忆：谨慎做
Mem0 云向量记忆：不进入第一轮落地
历史市场事实：禁止默认回灌 live decision
```

原因：

- 用户会连续追问，例如“那现在怎么办”“ETH 还拿吗”“刚才那个触发了吗”，系统必须理解上下文。
- 用户持仓、风险偏好、关注资产和操作周期需要在会话内稳定传递给所有 Agent。
- 但交易判断必须基于当前事实，旧价格、旧 funding、旧 OI、旧 ETF 流、旧新闻状态和旧交易结论不能作为当前证据。
- 长期记忆可以保存用户偏好和过程教训，不能保存并召回历史行情作为实时依据。

### 6.2 短期记忆

短期记忆由 `SessionMemoryManager` 管理，写入 `DecisionRunContext`，供 `IntentClassifier`、`SlotFiller`、`LeadAgent` 和 `FinalDecisionAgent` 使用。

短期记忆保存：

- 当前会话最近消息窗口。
- 当前用户持仓槽位：side、entry、leverage、liquidation、stop、target。
- 当前关注资产和周期。
- 上一次系统给出的 trigger、invalidation、next_review_at。
- 本轮和上一轮明确缺失的事实。
- 用户明确偏好，例如更关注短线、只做 BTC、禁止高杠杆。

短期记忆不保存为当前事实：

- 上一次价格。
- 上一次 funding/OI。
- 上一次 ETF 流。
- 上一次新闻状态。
- 上一次宏观数据状态。
- 上一次模型结论。

短期记忆建议 schema：

```json
{
  "session_id": "string",
  "recent_messages": [],
  "conversation_summary": "string",
  "position_slots": {
    "symbol": "ETH-USDT-SWAP",
    "side": "long | short | flat | unknown",
    "entry_price": null,
    "leverage": null,
    "stop_price": null,
    "target": null,
    "updated_at": "ISO-8601",
    "source": "user_stated | inferred | unknown"
  },
  "user_preferences": {
    "default_assets": ["BTC", "ETH", "SOL"],
    "risk_style": "conservative | normal | aggressive | unknown",
    "preferred_horizon": "1h | 4h | 1d | unknown"
  },
  "last_plan_summary": {
    "main_action": "trigger long",
    "trigger": null,
    "invalidation": "string",
    "next_review_at": "ISO-8601",
    "expired": true
  },
  "memory_warnings": [
    "last_plan_summary is context only, not live market evidence"
  ]
}
```

短期记忆压缩：

- 可以对重复消息做 hash 去重。
- 可以把早期对话压缩成结构化摘要。
- 最近消息窗口不建议固定只取最近 5 轮，而应使用“最近窗口 + 结构化槽位 + 当前任务摘要”。
- 压缩不能丢失持仓、杠杆、止损、时间周期和用户显式约束。

### 6.3 长期记忆

长期记忆只做低权重过程记忆，不做实时事实记忆。

允许保存：

- 用户偏好。
- 关注资产。
- 常用周期。
- 风险偏好。
- 过程教训，例如“不要用单一 ETF 流支撑方向”。
- badcase 标签和失败类型。
- 用户明确要求保留的策略约束。

禁止作为 live decision 证据：

- 历史价格。
- 历史资金费率。
- 历史 OI。
- 历史 ETF 流。
- 历史新闻状态。
- 历史模型预测。
- 历史交易盈亏。

长期记忆读取必须经过 `MemoryFirewall`：

```text
long_term_memory
  -> MemoryFirewall
  -> allowed: user preference / process lesson / badcase tag
  -> blocked: old market fact / old decision / old price / old flow / old news
```

### 6.4 Mem0 与向量记忆

第一轮落地不建议引入 Mem0 云服务。

原因：

- 用户持仓、风险偏好和策略记录具有隐私敏感性。
- 向量召回容易把旧市场事实以相似案例形式带回 live decision。
- 云服务增加数据治理、删除、审计和成本复杂度。
- 当前项目更需要结构化 memory 和事实防火墙，而不是相似案例召回。

如果未来引入向量记忆，必须满足：

- 默认本地或可完全关闭。
- 只存用户偏好、过程教训、badcase 标签。
- 每条召回结果必须标注 `memory_type`。
- `market_fact` 类型禁止进入 live `EvidencePacket`。
- 召回只能作为 `context` 或 `lesson`，不能作为 `known_fact`。

### 6.5 与 Agent 编排的关系

记忆只进入以下位置：

- `IntentClassifier`：理解用户追问。
- `SlotFiller`：补全用户持仓、周期和偏好。
- `LeadAgent`：理解本轮任务和用户约束。
- `FinalDecisionAgent`：知道用户当前持仓上下文，但不能把记忆当市场事实。

记忆不能进入：

- `LiveFactSkill` 的事实结果。
- `FactsGate` 的 fresh evidence。
- `RootCauseSkill` 的 `known_fact`。
- `SentimentCrowdingSkill` 的实时拥挤判断。
- `RiskGate` 的行情依据。

### 6.6 与原有记忆设计的结合

原有 `07-记忆与多轮对话.md` 和 `22-完整Agent业务流程与自进化评估架构设计.md` 中的 session memory、event memory、lesson rules、audit journal 仍然保留，但需要重新分流，避免所有历史信息都被叫做“记忆”后混入 live decision。

建议映射如下：

| 原有设计 | 新位置 | 用途 | 禁止事项 |
|---|---|---|---|
| session memory | `SessionMemorySnapshot` | 保存追问上下文、用户持仓、周期、风险偏好、上一轮计划摘要 | 不保存旧行情为当前事实 |
| event memory / event pool | `EventContext` + fresh `EvidencePacket` | 维护事件窗口和未解决反应，进入本轮前必须刷新或标 stale | 不能把过期事件状态当作当前新闻 |
| lesson rules | long-term process memory | 保存过程教训和 badcase 类型，作为检查清单或 eval case 来源 | 不能作为方向证据 |
| audit journal | `Journal` / `FrozenInput` / `Trace` | 用于复盘、回放、评估和发布前审查 | 默认不回灌 live prompt |
| badcase | eval dataset / candidate improvement | 生成离线测试和候选规则 | 不能在线自改生产策略 |

新链路中，记忆读取应发生在事实刷新之前，但只能写入 `DecisionRunContext.memory_snapshot`：

```text
SessionManager
  -> SessionMemoryManager.load_snapshot
  -> MemoryFirewall
  -> DecisionRunContext.memory_snapshot
  -> IntentClassifier / SlotFiller / LeadAgent

MarketFactAgent
  -> LiveFactSkill
  -> EvidencePacket
  -> FactsGate
```

这意味着“用户刚才说持有 ETH 多单”可以进入本轮请求，“上一轮 ETH funding 是多少”“上一轮模型判断偏多”不能进入本轮事实层。FinalDecisionAgent 可以看到用户持仓和上一轮计划摘要，但每个行情、资金费率、OI、ETF 流、新闻状态都必须由本轮 `EvidencePacket` 重新提供。

短期记忆不建议实现成无边界的全局单例。可以有会话级单一来源，但每次运行应生成不可变的 `SessionMemorySnapshot`，Agent 只读 snapshot，只有 `SessionMemoryManager` 在本轮结束后根据结构化结果写回。这样既能保证多 Agent 共享同一上下文，又不会让 Worker Agent 在执行中互相污染状态。

“熵管理器”可以保留为压缩手段，但作用域只限于对话文本：

- 可以对重复用户消息和重复系统摘要做 hash 去重。
- 可以把早期对话压缩为结构化摘要。
- 不能压缩、合并或改写 `EvidencePacket`。
- 不能把多个过期市场事实合成为一个“当前事实”。

## 7. Agent 分层设计

| Agent | 职责 | 输入 | 输出 | 能否调用工具 | 能否给最终动作 |
|---|---|---|---|---:|---:|
| `DecisionLeadAgent` | 规划任务、汇总贡献、处理冲突、构建 DecisionInput | request, facts gate, contributions | lead synthesis | 否或只读 registry | 否 |
| `MarketFactAgent` | 拉交易所原生执行事实 | symbol, requirements | EvidencePacket[] | 是 | 否 |
| `DerivativesAgent` | 整理 funding/OI/liquidation/basis/CVD/options | market facts | AgentContribution | 是或只读 | 否 |
| `MacroResearchAgent` | 查宏观、利率、DXY、VIX、油价、事件 | request, facts | AgentContribution | 是 | 否 |
| `FlowEventAgent` | 查 ETF、stablecoin、事件池、突发新闻 | request, event context | AgentContribution | 是 | 否 |
| `RelativeStrengthAgent` | 比较 BTC/ETH/SOL 强弱 | candles, price pairs | AgentContribution | 否或只读 | 否 |
| `TechnicalGuardrailAgent` | 执行质量：结构、ATR、RR、支撑阻力 | evidence packets | AgentContribution | 否或只读 | 否 |
| `RootCauseAgent` | 递归根因链和可证伪路径 | evidence, seed events | CausalEvidenceGraph | 通过受控事实请求 | 否 |
| `MarketSentimentAgent` | 情绪、拥挤、已定价、反身性 | facts, candidate direction | AgentContribution | 否或只读 | 否 |
| `ScenarioForkAgent` | base/upside/downside 场景 | event facts, consensus | ScenarioSummary | 否或只读 | 否 |
| `BullReviewer` | 最强多头链 | decision draft input | ReviewContribution | 否 | 否 |
| `BearReviewer` | 最强空头链 | decision draft input | ReviewContribution | 否 | 否 |
| `DataQualityAgent` | 来源、新鲜度、冲突、cap | packets, facts gate | AgentContribution | 否 | 否 |
| `ExecutionRiskAgent` | entry/stop/target/RR/滑点/事件 | decision input draft | AgentContribution | 否 | 否 |
| `FinalDecisionAgent` | 生成唯一 strict JSON DecisionPlan | DecisionInput | DecisionPlan raw JSON | 否 | 是，且必须过 gate |

## 8. Skill 拆分设计

| Skill | 职责 | 输入 | 输出 | 工具权限 |
|---|---|---|---|---|
| `request-normalization-skill` | 意图、symbol、horizon、仓位槽位标准化 | raw query, session | DecisionRequest draft | 无 |
| `live-fact-skill` | 实时事实总入口 | LiveFactRequest | LiveFactResponse | 行情/API/search 白名单 |
| `news-search-skill` | 固定 search lanes，结构化实时消息 | search plan | EvidencePacket[] | web_search |
| `derivatives-sweep-skill` | funding/OI/liquidation/long-short/basis/options | market facts | derivatives contribution | 行情/聚合数据 |
| `macro-bridge-skill` | rates/DXY/VIX/oil/QQQ/Fed path 传导 | macro facts | macro contribution | web/API |
| `flow-event-skill` | ETF/stablecoin/交易所流入流出/事件池 | event context | flow contribution | web/API |
| `indicator-sweep-skill` | 15 项指标 bucket 扫描 | evidence packets | bucket state table | 只读 |
| `root-cause-skill` | 递归因果检索和最大可能路径 | facts, seed event | CausalEvidenceGraph | 受控事实请求 |
| `sentiment-crowding-skill` | 已定价、拥挤、反身性、短期偏离 | objective facts, market facts | constraints contribution | 只读 |
| `scenario-fork-skill` | 重大事件路径分叉 | event window, consensus, facts | ScenarioSummary | 只读 |
| `adversarial-review-skill` | 多头/空头/数据/执行审查模板 | DecisionInput draft | ReviewContribution[] | 无 |
| `decision-ladder-skill` | 主信号投票、分数阶梯、已有仓位规则 | contributions | ladder result | 无 |
| `final-plan-skill` | strict JSON 决策计划 | DecisionInput | DecisionPlan raw JSON | 无 |
| `risk-gate-skill` | 风控 rule hit 文案模板 | plan, snapshot, gate result | risk explanation | 代码调用 |
| `eval-replay-skill` | frozen input 回放和候选评估 | frozen input, candidate | eval report | 只读 |

Skill 可以包含：

- prompt 片段
- 输入输出 schema
- tool policy
- 质量规则
- fallback 策略
- trace 记录规范

Skill 不应该：

- 自由注册工具
- 绕过 workflow
- 直接修改生产规则
- 直接产生副作用
- 动态发现未知脚本

## 9. LiveFactSkill / NewsSearchSkill / SourcePriorityPolicy

### 9.1 LiveFactSkill

职责：

- 作为实时事实总入口。
- 编排交易所 API、宏观/ETF/新闻覆盖、事实新鲜度检查。
- 输出覆盖率、缺口、冲突、confidence cap 和 hard block。

输入：

```json
{
  "run_id": "string",
  "symbol": "BTC-USDT-SWAP",
  "asset": "BTC",
  "run_mode": "info_only | standard_decision | deep_research",
  "horizon": "now | intraday | event_window | swing",
  "as_of": "ISO-8601",
  "deadline_ms": 90000,
  "allow_web_search": true,
  "required_domains": [
    "execution_price",
    "derivatives",
    "btc_anchor",
    "macro",
    "breaking_news",
    "events"
  ],
  "requirements": [
    {
      "fact_id": "mark_price",
      "data_type": "mark",
      "required": true,
      "max_age_seconds": 120,
      "acceptable_source_types": ["exchange_native"],
      "can_be_satisfied_by_search": false
    }
  ]
}
```

输出：

```json
{
  "status": "ok | partial | blocked",
  "packets": [],
  "coverage": {
    "required": [],
    "covered": [],
    "missing": [],
    "stale": []
  },
  "hard_blocks": [],
  "soft_downgrades": [],
  "confidence_caps": [],
  "conflicts": [],
  "next_recheck_at": "ISO-8601"
}
```

### 9.2 NewsSearchSkill

职责：

- 执行固定 search lanes。
- 返回结构化来源证据。
- 不做交易判断。

典型 search lanes：

- Fed / rates / data expectations
- CPI / PPI / PCE / NFP / FOMC
- ETF flows
- stablecoin / exchange flows
- CoinGlass / Coinalyze / Velo / Laevitas
- Deribit options
- exchange / chain status
- Reuters / AP / Bloomberg / CNBC breaking news
- official issuer / regulator announcements

### 9.3 SourcePriorityPolicy

不建议做成 LLM Skill，应做成代码化规则。

优先级：

1. 交易执行事实：OKX/Binance/Bybit/Deribit 原生 API。
2. 全市场衍生品：CoinGlass / Coinalyze / Velo / Laevitas。
3. 宏观实际值：BLS / BEA / Fed / Treasury / Cboe / FRED。
4. 新闻：官方声明 > Reuters/AP/Bloomberg > CNBC/WSJ/FT > social。
5. 社媒：只作为 rumor risk，不能作为 confirmed fact。

硬规则：

- `search_derived` 不能满足 mark/index/order_book。
- 执行事实冲突时不取平均，必须二次验证；无法验证则 hard block/cap。
- 地缘新闻冲突时标为 `unconfirmed scenario`。
- ETF flows 必须看 total，不允许只看单一基金。

## 10. RootCauseSkill

### 10.1 定位

`RootCauseSkill` 是“递归因果检索与可证伪路径生成器”，不是最终交易决策器。

它围绕一个事件或异常市场事实递归追问：

- 为什么它发生？
- 它会通过哪些通道影响 BTC/ETH/SOL？
- 这些通道又受哪些更深层因素驱动？
- 哪条路径是当前事实下最大可能路径？
- 什么事实会证伪这条路径？

### 10.2 因果链格式

```text
observable fact
  -> prior expectation / positioning
  -> immediate cause
  -> deeper driver
  -> market transmission
  -> confirmation trigger
  -> trade implication
```

`SentimentCrowdingSkill` 参与后，链条必须显式包含：

```text
market interpretation / crowding distortion
```

### 10.3 输出

```json
{
  "skill": "RootCauseSkill",
  "status": "complete | partial | hard_blocked",
  "data_quality": {
    "freshness": "fresh | mixed | stale",
    "source_tiers_used": [],
    "missing_critical_facts": [],
    "confidence_cap": "none | <=58 | <=55 | no_directional_score"
  },
  "root_cause_graph": {
    "seed_event": "string",
    "nodes": []
  },
  "ranked_chains": [],
  "maximum_likelihood_path": {
    "summary": "string",
    "why_this_path_wins": [],
    "bold_falsifiable_prediction": "string",
    "falsifiers": []
  },
  "opposite_chain": {
    "summary": "string",
    "what_would_make_it_take_control": []
  }
}
```

### 10.4 循环停止条件

- 达到 `max_depth`，默认 4。
- 达到 `max_nodes`，默认 24。
- 当前链已落到 durable root driver。
- 新一层检索没有增加独立事实。
- 当前节点与交易 horizon 无关。
- 证据只能来自 rumor/social 且无法确认。
- 关键事实缺失导致方向无法评分。
- 来源冲突无法裁决。
- 触发 timeout 或 tool budget。

### 10.5 质量规则

- 每个 `known_fact` 必须绑定 evidence。
- 没有 evidence 的 claim 降级为 `scenario`。
- Rumor/social 不能成为主链根因。
- 每条 ranked chain 必须有 confirmation trigger 和 invalidation。
- 必须输出 strongest opposite chain。
- 最大可能路径必须有 price/event/derivatives/time 四类证伪条件。
- RootCauseSkill 禁止输出最终交易 enum。

## 11. SentimentCrowdingSkill

### 11.1 定位

`SentimentCrowdingSkill` 解决“事实正确但短期价格可能反向”的问题。

它回答：

- 市场是否已经充分定价某个事实？
- 多头/空头是否拥挤？
- 新信息是否还能带来边际买盘/卖盘？
- 清算、期权 gamma、社媒叙事、ETF 预期是否在扭曲传导？
- 当前方向应加分、降权、限制为 trigger，还是禁止追价？

它不输出交易动作，只输出约束和贡献。

### 11.2 需要分析的数据

- funding：当前值、年化、7d/30d percentile、跨交易所差异、下一次 funding。
- OI：1h/4h/24h 变化、价格/OI 组合、OI/volume、跨交易所集中度。
- long/short：账户比、持仓比、大户比。
- liquidation：1h/4h/24h/7d 清算簇。
- basis/perp premium：现货推动还是合约追涨。
- taker flow/CVD：主动买卖、吸收、背离。
- options skew：25-delta skew、put/call OI、IV、max pain、gamma zone。
- ETF flows：总净流入/流出和连续性。
- stablecoin/liquidity：稳定币供给、交易所 stablecoin 余额。
- fear/greed：只作为情绪温度计。
- social/news heat：新闻热度、叙事拥挤、KOL 一致性。
- cross-asset sentiment：VIX、DXY、收益率、QQQ/NQ、油价。

### 11.3 输出

```json
{
  "skill": "SentimentCrowdingSkill",
  "status": "ok | partial | unavailable | conflict",
  "crowding_state": "not_crowded | mildly_crowded | crowded_but_trending | dangerously_crowded",
  "priced_in_state": "not_priced_in | partly_priced_in | mostly_priced_in | overpriced",
  "reflexivity_state": {
    "direction": "upward | downward | two_way | none",
    "strength": "low | medium | high",
    "mechanism": "string"
  },
  "short_term_distortion": {
    "risk": "low | medium | high",
    "likely_against_objective_fact": true,
    "expected_window": "minutes | 1h | 4h | 1d",
    "reason": "string"
  },
  "constraints": {
    "max_confidence": 58,
    "max_position_size": "none | tiny | small | normal",
    "allowed_action_classes": [],
    "blocked_actions": [],
    "required_confirmations": [],
    "next_review_minutes": 30
  }
}
```

### 11.4 典型解释

好消息不等于做多：

```text
好消息
  -> 是否早已预期
  -> funding 是否极高
  -> OI 是否继续上升
  -> 多头清算簇是否密集在下方
  -> 是否只能等待突破接受或回踩确认
```

坏消息不等于做空：

```text
坏消息
  -> 空头是否拥挤
  -> funding 是否负
  -> 价格是否不再创新低
  -> 是否存在轧空风险
```

ETF 流入不等于上涨：

```text
ETF 总流入
  -> 是否连续
  -> 价格是否已提前反应
  -> 现货买盘是否被卖盘吸收
  -> BTC 结构是否确认
```

### 11.5 门禁规则

- 缺 funding 或 OI 时，杠杆方向置信度不得高于 60%。
- 单一 fear/greed、社媒热度、KOL 观点不能作为主方向依据。
- `search_derived` 不能替代 exchange_native mark/index/funding/OI。
- funding 极端同向 + OI 上升 + 价格接近阻力/支撑时，禁止追同向 market entry。
- ETF flows 必须看总净流量和连续性。
- 新闻热度高但价格不跟随，必须标记 `priced_in` 或 `absorption`。
- 数据窗口必须匹配交易周期。
- 多源衍生品冲突时输出 `conflict` 并触发 cap。
- 重大宏观事件或期权到期附近，options/gamma/liquidation 缺失必须降级。

## 12. Reviewer 设计

Reviewer 不是角色扮演，而是独立审查贡献。

| Reviewer | 必须回答 |
|---|---|
| `BullReviewer` | 最强多头根因链、确认条件、失效条件、为什么可以超过空头 |
| `BearReviewer` | 最强空头根因链、确认条件、失效条件、为什么可以超过多头 |
| `DataQualityAgent` | 哪些事实 fresh/stale/missing/conflict，哪些 search_derived 不能用 |
| `ExecutionRiskAgent` | entry/stop/T1/T2/RR、盘口、滑点、清算簇、事件窗口、是否只能 trigger |

每个 reviewer 必须：

- 有独立 span。
- 有 timeout。
- 有 status。
- 失败时写 `failed` 或 `partial`，不能伪装成功。
- required reviewer 失败会触发 hard block 或 confidence cap。
- optional reviewer 失败只写 unavailable。

Reviewer 独立性分级：

| 等级 | 说明 | 适用 |
|---|---|---|
| `compact_structured` | 同一次 LLM call 输出 bull/bear/data-quality/execution-risk 四类结构化 review | `standard_decision` 低复杂场景的最低要求 |
| `independent_parallel` | 每个 reviewer 独立 LLM call、独立 span、独立 timeout、独立 status | 资金风险较高、持仓复杂、事实冲突明显 |
| `deep_independent` | reviewer 可基于同一 eligible evidence view 独立构造反方链和执行风险审查，但仍不能调用未授权工具 | `deep_research` |

`compact_structured` 不是 swarm，也不能被实现或宣传为独立多 Agent。无论采用哪一级，输出都必须转为独立 `AgentContribution`，便于 Lead 汇总、Eval 归因和 reviewer 命中率统计。

required reviewer 失败的确定性处理：

| Reviewer | 失败默认处理 |
|---|---|
| `DataQualityAgent` | hard block，除非 DataQualityGate 已经给出同等或更严结果 |
| `ExecutionRiskAgent` | hard block 可执行入场/反手/trigger，允许输出 blocked no-trade |
| `BullReviewer` | confidence cap，不得阻断空头审查 |
| `BearReviewer` | confidence cap，不得阻断多头审查 |

Reviewer effectiveness 必须进入 eval：

- confirmed badcase hit rate。
- false negative rate。
- false positive rate。
- failure taxonomy 覆盖率。
- compact vs independent 的效果差异。
- reviewer 输出被 Lead 丢弃的比例和原因。

没有命中率和漏报率统计的 reviewer 只算格式完整，不算质量已验证。

## 13. LeadAgent 设计

LeadAgent 是中心协调者，但不是交易决策者。

职责：

- 根据 request、facts gate、复杂度决定需要哪些 Agent/Skill。
- 汇总 `EvidencePacket` 和 `AgentContribution`。
- 标记冲突、缺失、降级、confidence cap。
- 生成主信号投票材料。
- 生成 scorecard。
- 选择可进入 FinalDecisionAgent 的 root-cause chains。
- 构建 `DecisionInput`。

LeadAgent 不做：

- 不直接输出 `main_action`。
- 不绕过 gates。
- 不调用下单/通知工具。
- 不修改生产规则。
- 不把历史结论当当前事实。
- 不过滤最强反方链。
- 不删除 `DataQualityAgent` / `ExecutionRiskAgent` 的 hard block。
- 不放宽 confidence cap。
- 不把 `canonical_actions` 当作 FinalDecisionAgent 的有效动作空间。

LeadAgent 必须记录：

- 每个 contribution 是否进入 `DecisionInput`。
- 未进入的 contribution 的 `discard_reason`。
- 与主方向冲突的 evidence/contribution refs。
- 最强反方链和为什么没有胜出。
- 所有 hard block、soft downgrade、confidence cap 的来源和传播结果。

LeadAgent 只能生成 `lead_synthesis` 和 `DecisionInput` 草案，不能生成最终交易动作。若 Lead 的 `primary_signal_vote` 与 reviewer 或 gate 冲突，冲突必须进入 `DecisionInput.lead_synthesis.conflicts`，不能静默裁剪。

## 14. FinalDecisionAgent 设计

FinalDecisionAgent 只消费 `DecisionInput`，输出 strict JSON `DecisionPlan`。

要求：

- `main_action` 必须且只能是一个合法枚举。
- 必须包含 entry/trigger、stop、T1/T2、invalidation、next review time。
- 必须解释 why-not-opposite。
- 必须体现 confidence cap 和 hard block。
- 不能调用工具。
- 不能搜索。
- 不能发通知。
- 不能修改 RiskVerdict。

允许动作：

```text
open long
open short
hold long
hold short
close long
close short
flip long to short
flip short to long
trigger long
trigger short
no trade
```

## 15. 执行模式

交易相关请求的默认模式不应是单 Agent 路由。只要本轮输出会影响 `open long`、`open short`、`close`、`flip`、`hold`、`trigger`、`no trade` 等操作判断，就至少进入 `standard_decision`。轻量路径只能用于不产生交易动作的解释、配置、普通状态查询，或明确低风险的提醒生成。

### 15.1 info_only

适用：

- 解释系统规则、配置、文档。
- 查询历史 trace/eval/journal，不形成当前交易建议。
- 用户只要求说明某个指标含义。
- 不输出任何交易动作、价格触发、止损止盈或仓位建议。

链路：

```text
request
  -> optional memory context
  -> answer / documentation / trace query
  -> no DecisionPlan
```

策略：

- 不允许输出 `main_action`。
- 不调用 `FinalDecisionAgent`。
- 不触发 Bark 交易提醒。
- 如果用户追问“那我该怎么做”“现在能不能开/平/反手”，必须升级到 `standard_decision`。

### 15.2 standard_decision

适用：

- 普通交易判断，默认模式。
- 有仓位、杠杆、止损止盈。
- 无极端事件，但需要覆盖 research。
- 用户追问“那现在怎么办”“还能拿吗”“要不要开/平/反手”。

链路：

```text
full core fact pack
  -> derivatives / macro / flow coverage
  -> root-cause compact
  -> sentiment/crowding
  -> compact reviewers
  -> Lead synthesis
  -> FinalDecision
  -> gates
```

策略：

- 总耗时可到 900 秒。
- research 最多 180 秒。
- 缺关键事实不强行输出方向。
- reviewer 可以 compact，但必须有结构化 `AgentContribution` 和独立 status。
- 至少包含 data-quality 与 execution-risk 审查；bull/bear 可以合并为一个 adversarial compact call，但输出必须分开。
- 若用户有实盘仓位或杠杆，缺核心执行事实时只能 `trigger` / `no trade` / `close` 类保守动作，不能高置信开仓或反手。

### 15.3 deep_research

适用：

- CPI/FOMC/NFP。
- ETF 异常。
- 地缘冲突。
- 暴涨暴跌。
- 爆仓链。
- 用户明确要求多 Agent、根因链、大胆预测。

链路：

```text
complete fact pack
  -> full macro/flow/derivatives/event research
  -> RootCauseSkill recursive graph
  -> SentimentCrowdingSkill
  -> ScenarioForkSkill
  -> independent reviewers
  -> Lead conflict resolution
  -> FinalDecision
  -> strict gates
```

策略：

- 总耗时可到 1800 秒。
- 必须标明不是极速短线提醒。
- reviewer 独立 span/timeout。
- 必须输出 strongest opposite chain。
- 必须标注 confidence cap 和 missing facts。
- 重大事件 6-24h 内优先 trigger/hold-to-near-target。
- 最终仍只允许一个 `main_action`。

## 16. Harness Engineering 约束系统

Harness 系统是多 Agent 编排的基础设施，优先级高于“记忆系统”。它负责把 Agent 能力边界、工具权限、输出 schema、timeout、retry、fallback、自动修复和阻断策略显式化。

### 16.1 设计结论

必须做 Harness/YAML 约束系统。

原因：

- 当前项目最大风险不是“Agent 不够多”，而是“Agent 输出质量不可控、边界不清、事实和推理混在一起”。
- 如果没有显式约束，多 Agent 最终会退化成 prompt 堆叠。
- Harness 可以让每个 Agent 的能力、输入、输出、工具权限和失败策略在运行时被验证。

### 16.2 配置边界

适合 YAML 配置：

- Agent 名称和启用模式。
- 每个 Agent 的 tool policy。
- 每个 Agent 的 input/output schema 名称。
- timeout、retry、required/optional。
- run mode 下启用哪些 Agent。
- confidence cap 规则参数，但只能收紧代码硬边界。
- source freshness 阈值，但只能收紧代码硬边界。
- reviewer 是否 compact 或 independent。
- 自动修复允许范围。

必须代码硬编码：

- 禁止自动下单、撤单、提现。
- `manual_execution_required=true`。
- `search_derived` 不能满足 mark/index/order_book。
- FinalDecisionAgent 不能调用工具。
- eval/replay 不发 Bark。
- action enum 唯一性。
- JSON schema 和字段类型。
- 风控 hard block。
- secret 环境变量禁止读取。

### 16.3 YAML 示例

```yaml
agents:
  RootCauseAgent:
    required: true
    can_call_tools: false
    input_schema: RootCauseRequest
    output_schema: CausalEvidenceGraph
    timeout_seconds:
      info_only: 0
      standard_decision: 90
      deep_research: 300
    failure_policy: confidence_cap
    allowed_claim_types:
      - known_fact
      - consensus
      - inference
      - scenario
      - rumor
    forbidden_outputs:
      - main_action
      - risk_verdict

  MarketSentimentAgent:
    required: true
    can_call_tools: false
    input_schema: SentimentCrowdingRequest
    output_schema: SentimentCrowdingContribution
    timeout_seconds:
      info_only: 0
      standard_decision: 90
      deep_research: 180
    failure_policy: soft_downgrade

  FinalDecisionAgent:
    required: true
    can_call_tools: false
    input_schema: DecisionInput
    output_schema: DecisionPlan
    timeout_seconds:
      info_only: 0
      standard_decision: 180
      deep_research: 240
    allowed_actions:
      - open long
      - open short
      - hold long
      - hold short
      - close long
      - close short
      - flip long to short
      - flip short to long
      - trigger long
      - trigger short
      - no trade

facts:
  execution_facts:
    mark:
      required_for:
        - open long
        - open short
        - flip long to short
        - flip short to long
      acceptable_source_types:
        - exchange_native
      can_be_satisfied_by_search: false
      max_age_seconds: 120
    order_book:
      required_for:
        - open long
        - open short
      acceptable_source_types:
        - exchange_native
      can_be_satisfied_by_search: false

repair:
  allowed:
    - strip_markdown_fence
    - parse_json_object_from_text
    - normalize_action_enum_case
    - coerce_numeric_string
    - fill_optional_empty_arrays
  forbidden:
    - invent_missing_fact
    - choose_between_two_main_actions
    - convert_search_derived_to_exchange_native
    - remove_hard_block_reason
```

### 16.4 Runtime Validator

每个 Agent 执行前后都要过 Harness 校验。

执行前：

- 校验 Agent 是否在当前 run mode 启用。
- 校验是否拥有工具权限。
- 校验 input schema。
- 校验 required facts 是否已满足。
- 校验 timeout/deadline。

执行后：

- 校验 output schema。
- 校验 forbidden outputs。
- 校验 claim 是否绑定 evidence。
- 校验 source type 是否满足要求。
- 校验 missing/stale/conflict 是否显式输出。
- 校验 confidence cap 和 blocked actions 是否一致。

### 16.5 自动修复机制

自动修复只允许修格式，不允许修语义。

允许自动修复：

- 去掉 markdown code fence。
- 从文本中提取唯一 JSON object。
- 字段名别名映射。
- enum 大小写/空格规范化。
- 数字字符串转数字。
- 缺省可为空字段补空数组。

禁止自动修复：

- LLM 输出两个 `main_action` 时替它选择一个。
- 缺核心执行事实却建议开仓时替它补事实。
- 把 `search_derived` 改成 `exchange_native`。
- 删除 hard block reason。
- 根据历史记忆补当前行情。
- 根据模型解释生成缺失来源。

不能修复时：

```text
repair failed
  -> retry once with structured error
  -> still failed: mark agent failed/partial
  -> required agent failure: hard block or confidence cap
  -> optional agent failure: unavailable
```

### 16.6 与现有 Gate 的关系

Harness 不替代代码 Gate。

```text
HarnessValidator
  -> 保证 Agent 输入输出和权限正确

FactsGate / ParserGate / PlanSemanticGate / RiskGate
  -> 保证业务事实、动作、语义和风控正确
```

Harness 更靠近编排层，Gate 更靠近业务安全层。

### 16.7 与原有 Workflow / Gate / Eval 的结合

原有 `22-完整Agent业务流程与自进化评估架构设计.md` 和 `27-轻量自研Workflow与受控Agent层重构建议.md` 已经定义了主链路、Gate、Trace、Eval 和人工发布边界。Harness 不推翻这些设计，而是补上“Agent 怎么被受控调用”的运行时合约层。

结合方式如下：

```text
WorkflowExecutor
  -> StepSpec / run mode
  -> HarnessPolicyLoader
  -> HarnessValidator.pre_agent
  -> AgentRunner
  -> HarnessValidator.post_agent
  -> ContributionStore / EvidenceStore
  -> Business Gates
  -> FrozenInput / Eval
```

边界分工：

| 层 | 负责什么 | 不负责什么 |
|---|---|---|
| `WorkflowExecutor` | 串行/并发顺序、deadline、step 状态、失败传播 | 判断市场方向 |
| `HarnessPolicy` | Agent 权限、schema、timeout、retry、required/optional、repair 范围 | 业务风控最终裁决 |
| `ToolPolicy` | 工具白名单、source type、可调用渠道 | 根据工具结果给最终动作 |
| `HarnessValidator` | Agent 前后置合约校验、格式修复、越权阻断 | 补事实、改语义、替 Agent 做交易判断 |
| `Business Gates` | Facts/Parser/Semantic/Risk 的业务硬门禁 | 管理 Agent timeout 和 prompt 权限 |
| `Eval/Replay` | 用 FrozenInput 复现、对比候选规则、人工审批 | 触发实时行情、Bark 或生产副作用 |

落到现有重构方案中，Harness 应该随 Agent 编排骨架一起落地，而不是等到所有 Agent 写完以后再补。原因是多 Agent 混乱的根源不是“Agent 数量不够”，而是每个 Agent 的输入、输出、权限和失败状态没有运行时边界。

第一轮 Harness 配置只建议覆盖三类内容：

1. Agent 合约：`input_schema`、`output_schema`、`can_call_tools`、`required`、`timeout_seconds`、`failure_policy`。
2. 工具权限：哪些 Agent 可以用 exchange-native、official API、web search、aggregator fallback。
3. 修复策略：只允许 JSON/字段/enum 的格式修复，禁止语义修复和事实补全。

暂时不建议把所有业务策略都 YAML 化。以下规则仍应硬编码在代码 Gate 中：

- `manual_execution_required=true`。
- 禁止下单、撤单、提现工具。
- `FinalDecisionAgent` 永远不能调用工具。
- `search_derived` 永远不能满足 mark/index/order_book。
- eval/replay 永远不发 Bark。
- hard block 不能被 LLM 或 YAML 覆盖。

这样可以避免 YAML 变成第二套难以审查的业务逻辑。YAML 管“谁能做什么、输出长什么样、失败怎么办”，代码 Gate 管“什么绝对不能发生”。

Harness 配置单调性：

- YAML 可以收紧 timeout，不能放宽代码默认 deadline。
- YAML 可以收紧 source freshness，不能让 stale 数据变 fresh。
- YAML 可以降低 confidence cap，不能提高代码 Gate 给出的 cap。
- YAML 可以禁用 Agent 或工具，不能启用代码禁止的工具。
- YAML 可以把 optional 改 required，不能把 hard required 改 optional。
- YAML 不能允许 handoff、spawn、Agent-to-Agent 直接通信。

### 16.8 Harness MVP 接口签名

第一轮不需要完整平台，但需要最小运行时接口，避免 Harness 停留在 YAML 文档。

```python
class HarnessPolicyLoader:
    def load(self, run_mode: str) -> HarnessPolicy: ...

class HarnessValidator:
    def pre_agent(self, context: DecisionRunContext, task: SubTask, policy: HarnessPolicy) -> ValidationResult: ...
    def post_agent(self, context: DecisionRunContext, task: SubTask, contribution: AgentContribution, policy: HarnessPolicy) -> ValidationResult: ...
    def repair_format(self, raw_output: str, schema_name: str, policy: HarnessPolicy) -> RepairResult: ...
    def apply_failure_policy(self, task: SubTask, error: Exception, policy: HarnessPolicy) -> AgentContribution: ...
```

MVP 验收：

- 未在 Harness 中启用的 Agent 不能运行。
- Agent 输出缺 schema 字段时进入 repair；repair 失败必须 failed/partial。
- 非 Final agent 输出 `main_action`、entry、stop、target、leverage、position size 时必须失败。
- FinalDecisionAgent 请求工具时必须失败。
- run mode 为 `info_only` 时，FinalDecisionAgent、RiskGate、Bark 均不得执行。
- eval/replay run_type 下，任何 side effect sink 必须为 noop。

## 17. 代码 Gate

以下必须由代码强制，不能交给 LLM：

- action enum 唯一性和合法性。
- strict JSON 和字段类型。
- `manual_execution_required=true`。
- eval/replay 不发 Bark、不写生产副作用。
- 禁止自动下单、撤单、提现。
- 禁止读取交易密钥。
- `search_derived` / `web_derived` 不能满足 mark/index/order_book。
- 核心执行事实缺失时阻断开仓、反手、trigger、高杠杆入场。
- stale data 检查和 confidence cap。
- allowed symbols。
- max leverage。
- risk_pct。
- plan TTL。
- entry/stop/target 顺序。
- RR 下限。
- action-position 合法性。
- FinalDecisionAgent 不允许调用工具。
- RootCauseSkill 和 reviewers 不允许输出最终交易动作或可执行交易参数。
- `fixture` / `replay` evidence 不允许进入 manual/scheduled live decision。
- Journal/FrozenInput/trace hash 缺失时不得发送生产通知。
- 生产 plan_runs、生产通知记录、前端可执行计划展示必须在 SideEffectGate 通过后发生。

LLM 可以判断但必须结构化输出并被 gate 约束：

- 宏观事件如何传导到 BTC/ETH/SOL。
- 根因链质量。
- 最强反方论点。
- 新闻是否可能已定价。
- 拥挤程度的定性解释。
- 场景分叉。
- 主观概率说明。
- 为什么不用相反方向。
- 哪些证据会改变动作。

### 17.1 SideEffectGate 与人工执行通知边界

SideEffectGate 必须位于所有生产副作用之前。

生产副作用包括：

- 写入生产 `plan_runs`。
- 写入生产 notification 记录。
- 发送 Bark/飞书/其他外部通知。
- 在前端展示为“当前可执行计划”。
- 写入任何会被 scheduler 或 live UI 读取为当前计划的表。

安全审计写入包括：

- eval/replay sidecar。
- FrozenInput artifact。
- sanitized trace。
- candidate report。

安全审计写入可以在生产 SideEffectGate 前发生，但必须不能被 live UI 当作当前计划执行。

通知边界：

- 通知必须包含 `manual_execution_required=true`。
- 通知不得包含一键下单链接。
- 通知不得包含交易所 order payload。
- 通知不得包含自动化脚本命令。
- 通知不得包含 API key、account id、withdraw/transfer 相关信息。
- blocked plan 的通知必须明确“禁止按本次结果交易”。

eval/replay 隔离：

```text
eval/replay entry
  -> NoopNotificationSink
  -> read-only production source
  -> eval sidecar store
  -> no live market fetch
  -> no live web search
  -> no production plan_runs write
  -> assert prod_plan_runs_delta == 0
  -> assert prod_notifications_delta == 0
  -> assert bark_sent == 0
```

ReplayRunner 不得调用生产 `PlanRunner.run_once()`、OKX live fetch、web search、Bark 或生产 trace/LLM 表写入。candidate 只能在 frozen input 上重放和比较。

## 18. Trace / Eval / FrozenInput / Replay / ReleaseGate

每个 step、tool、agent、reviewer 都要有独立 trace span：

```text
workflow.session
workflow.intent
workflow.complexity
skill.load
tool.market.fetch
tool.news.search
gate.facts.pre
agent.macro_research
agent.root_cause
agent.sentiment_crowding
review.bull
review.bear
review.data_quality
review.execution_risk
agent.lead_synthesis
decision.input.build
decision.final
gate.parser
gate.semantic
gate.risk
journal.write
side_effect.notification
```

### 18.1 完整可回放输入

完整可回放输入不能只保存摘要，必须保存可回放 artifact refs 和 hash，使系统能回答“当时看到了什么、哪些 Agent 产出了什么、版本是什么、最终输出和风控结果是什么”。

FrozenInput 必须保存：

- request。
- memory_snapshot hash 和允许进入决策的字段。
- 完整规范化 `EvidencePacket` 或 artifact refs。
- FactsGateResult / DataQualityGateResult。
- 每个 Agent 的 input_ref、output_hash、status、repair_attempts、retry_count、failure_policy_applied。
- 每个 tool call 的输入摘要、source、retrieved_at、latency、status、output_hash。
- AgentContribution 完整结构。
- LeadPlan。
- Lead synthesis 和丢弃 contribution 的原因。
- DecisionInput。
- FinalDecisionAgent raw output。
- ParserGate / PlanSemanticGate / RiskGate result。
- SideEffectGate result 和 side-effect counters。
- config/rule/prompt/model/skill hash。
- span tree、parent_span_id、token/cost/latency。
- redaction policy。

FrozenInput 不保存隐藏推理链，但必须保存足够的结构化理由、证据引用和 gate 结果，支持 replay 与人工复核。

### 18.2 ReplayRunner 模式

ReplayRunner 只允许三种模式：

| 模式 | 说明 | 禁止 |
|---|---|---|
| `frozen_observed` | 复现当时 observed output、gate、side effect counters | live fetch/search |
| `candidate_decision` | 在同一 FrozenInput 上运行候选 prompt/rule/model | 生产 PlanRunner、Bark、生产写入 |
| `judge_only` | 对 observed/candidate 做 RuleJudge/LLMJudge/HumanReview | 修改生产规则 |

ReplayRunner 默认禁止：

- OKX live fetch。
- web search。
- Bark/飞书通知。
- 写生产 plan_runs。
- 写生产 trace/LLM 表。
- 读取交易密钥。

### 18.3 LLMJudge 合约

LLMJudge 只做语义评估，不做交易裁决，初期为 advisory，人工校准后才允许进入 release gate。

首批 rubric：

- evidence grounding：结论是否绑定证据。
- counter thesis：是否保留最强反方链。
- data gap honesty：是否诚实暴露缺失/陈旧/冲突事实。
- execution clarity：动作、触发、失效、下一次复查是否清楚。
- overconfidence：是否在缺事实或冲突时过度自信。

LLMJudge 必须：

- strict JSON schema。
- 固定 judge prompt hash。
- 固定 model/version/temperature。
- 输出 `score`、`severity`、`reasons`、`evidence_refs`。
- 非法 JSON 记为 judge failure，不自动改语义。
- 与 RuleJudge 冲突时进入 HumanReview。

### 18.4 Badcase 生命周期与 Reviewer Metrics

badcase 生命周期：

```text
recorded
  -> triaged
  -> confirmed | rejected
  -> eval_case
  -> golden_set
  -> regression
  -> candidate_fix
  -> human_approval
  -> release_gate
```

badcase 标签只能作为 checklist、eval case 和 failure taxonomy，不能作为方向性先验：

- 不得生成 `known_fact`。
- 不得进入 `EvidencePacket`。
- 不得影响多空方向分数。
- 不得回灌 live prompt。

Reviewer metrics：

- confirmed badcase hit rate。
- false negative / false positive。
- failure taxonomy coverage。
- compact_structured vs independent_parallel 对比。
- reviewer failure rate。
- Lead 丢弃 reviewer contribution 的比例和原因。

### 18.5 Release Gate 与 Candidate Promotion

候选 prompt/rule/workflow/model 进入生产前必须通过 release gate。

Hard gate：

- critical RuleJudge fail = 0。
- schema valid rate 达到阈值。
- `manual_execution_required=true` 覆盖率 100%。
- search_derived 未被用于 mark/index/order_book。
- eval/replay side-effect counters 全为 0。
- high/critical badcase 不复发。
- blocked action 不被 candidate 放行。

Advisory gate：

- LLMJudge 平均分。
- reviewer hit rate 改善。
- overconfidence 下降。
- evidence grounding 改善。
- compact vs independent 差异可解释。

HumanReview 必须处理：

- high/critical badcase。
- RuleJudge 与 LLMJudge 冲突。
- release gate hard fail。
- 人工 override。

任何 candidate 发布都必须记录 baseline/candidate 对比、审批人、发布时间、可回滚版本和影响范围。

Eval 只评：

- 事实覆盖是否完整。
- 来源使用是否正确。
- search_derived 是否被错误用于执行事实。
- 根因链是否完整。
- 反方链是否存在。
- confidence cap 是否正确。
- action enum 是否唯一。
- 风控 gate 是否阻断该阻断的动作。

Eval 不评：

- 交易是否赚钱。
- 是否应该绕过 RiskGate。
- 是否自动发布候选。

## 19. 迁移阶段

### 19.0 阶段退出标准

每个阶段都必须有可运行 fixture 和禁止项检查，不能只以“代码写完”为完成标准。

通用退出标准：

- 有 schema/dataclass/Pydantic 约束。
- 有 trace span。
- 有 journal 或 sidecar 可观察结果。
- 有至少一个成功 fixture 和一个失败 fixture。
- 有禁止字段断言。
- 有 eval/replay 无副作用断言。

### 设计冻结

内容：

- 本文档确认。
- 明确 schema。
- 明确 gate 优先级。
- 明确 info_only / standard_decision / deep_research。
- 明确 memory firewall。
- 明确 Harness/YAML 约束边界。

验收：

- 产出 schema 文件或等价 Python dataclass/Pydantic 模型草案。
- 产出 gate 优先级表。
- 产出 run mode 枚举：`info_only | standard_decision | deep_research`。
- 产出禁止字段清单：raw snippet、raw exchange JSON、完整 skill text、fixture/replay live evidence。
- 产出至少 5 个 fixture 验收用例：缺 mark/index/order_book、search_derived 冒充执行事实、reviewer 输出 main_action、eval/replay 触发 Bark、FinalDecisionAgent 请求工具。

### 入口上下文与贡献对象

内容：

- 新增 `DecisionRunContext`。
- 新增 `LeadPlan`。
- 新增 `EvidencePacket`。
- 新增 `AgentContribution`。
- 新增 `DecisionInput`。
- 新增 `SessionMemorySnapshot`。
- `RunExecutor` 创建 context，不再把 `DecisionRequest` 直接缩成 `symbol`。
- `PlanRunner` 暂时降级为 legacy adapter 或内部 step，不再作为长期主编排入口。

验收：

- 主入口不再只传 symbol。
- 一轮运行有唯一 context。
- research/reviewer 输出可以记录为 contribution。
- 用户追问可以通过结构化短期记忆补全上下文。
- 旧市场事实不会进入 EvidencePacket。
- `DecisionRequest -> DecisionRunContext -> legacy adapter` 有 trace span。
- `run_type=eval/replay` 不进入生产 PlanRunner。

### 实时事实与 FactsGate

内容：

- 实现 `LiveFactSkill`。
- 实现 `SourcePriorityPolicy`。
- 实现 `FactsGate`。
- 将当前 market/research 结果转 EvidencePacket。
- 定义 `MarketSnapshot/DataPoint -> EvidencePacket` 映射。
- 定义 `SearchResult/ResearchAudit -> EvidencePacket` 映射。
- 定义 `leader_summary -> AgentContribution[]` 映射。
- 建立 `EvidenceStore` 和 `FactsGateResult`。

验收：

- `search_derived` / `web_derived` 不能满足 mark/index/order_book。
- raw search snippet 不进入 FinalDecisionAgent。
- raw exchange JSON 不进入 FinalDecisionAgent。
- `fixture` / `replay` evidence 在 manual/scheduled live run 被剔除或 hard block。
- 缺核心执行事实时开仓/反手/trigger 被阻断。

### Contribution 兼容封装

定位：

- 这是从当前伪多 Agent 迁移到受控 Agent Swarm 的过渡层。
- Contribution 兼容封装不是 swarm 完成点，不能作为最终架构停留。

内容：

- 不急于拆独立 Agent，先把当前 `leader_summary`、static reviewer、LLM reviewer 输出封装为 `AgentContribution[]`。
- 每个 contribution 带 status、input_ref、output_hash、failure_policy_applied、trace_ref。
- compact reviewer 也必须拆成四个 contribution。

验收：

- 当前 reviewer JSON key 不再直接混在 summary 中。
- 单个 reviewer 缺失或非法时能标记 failed/partial。
- Lead 能看到 contribution 缺失和冲突。
- 验收报告必须标明“仍未完成 Agent Swarm”，直到独立 Worker Agent 并发执行通过。

### Harness 运行约束骨架

内容：

- 实现 HarnessPolicyLoader。
- 实现 HarnessValidator pre/post。
- 实现格式 repair 和 failure_policy。
- 禁止非 Final agent 输出动作和可执行参数。

验收：

- Agent 工具权限和输出 schema 可 runtime 校验。
- run mode 为 `info_only` 时 FinalDecisionAgent 不运行。
- YAML 只能收紧，不能放宽代码硬边界。

### 受控 Agent Swarm 最小实现

内容：

- 实现 LeadAgent planning/synthesis。
- 实现枚举化 `LeadPlan`。
- 实现 `AgentRunner`，让 Worker Agent 作为独立运行单元并发执行。
- 最小实现必须覆盖 7 个 required shadow workers：`LiveFactAgent`、`DerivativesAgent`、`MacroEventAgent`、`RootCauseAgent`、`MarketSentimentAgent`、`DataQualityAgent`、`ExecutionRiskAgent`。
- reviewer 独立 span/status/timeout。
- 禁止 Agent-to-Agent 直接通信、handoff、动态 spawn。

验收：

- 至少 4 个 Worker Agent 在同一 run 中产生独立 trace span。
- 每个 Worker Agent 有独立 `SubTask`、input_ref、output_hash、status、timeout 和 failure_policy。
- 每个 Worker Agent 输出独立 `AgentContribution` 或 `EvidencePacket`。
- 单个 reviewer 失败不会伪装成功。
- LeadAgent 能标记缺失 reviewer。
- contribution 可回放。
- Worker 只能 append EvidencePacket/AgentContribution。
- LeadPlan 不能创建枚举外任务。
- `leader_summary` 多 key 输出不再作为 swarm 证据，只能作为 legacy fallback。
- 如果 Worker Agent 未独立运行，本阶段不通过。

### 根因链与情绪拥挤分析

内容：

- 实现根因递归图。
- 实现拥挤/已定价/反身性约束。
- 接入 DecisionInput。

验收：

- 每条根因链有证据、确认、失效。
- 情绪拥挤能限制 fresh market entry。

### 最终决策与业务门禁

内容：

- FinalDecisionAgent 只消费 DecisionInput。
- ParserGate / PlanSemanticGate / RiskGate 完整接管。
- `DecisionInputBuilder` 生成 `effective_allowed_actions`、`blocked_actions`、`execution_mode`、`confidence_policy`。

验收：

- FinalDecisionAgent 无工具权限。
- 输出唯一动作。
- gate 可阻断或降级。
- FinalDecisionAgent 不能看到未裁剪的全量动作空间。
- 缺核心执行事实时 `trigger long/short` 不在 `effective_allowed_actions`。
- `flip long to short` / `flip short to long` 当前阶段默认 hard block。

### Eval / Replay 闭环

内容：

- 完整可回放输入覆盖完整链路。
- badcase 变成 eval case。
- candidate 只走离线评估和人工审批。
- ReplayRunner 支持 `frozen_observed`、`candidate_decision`、`judge_only`。
- LLMJudge 首批五个 rubric。
- release gate 和 HumanReview 队列。

验收：

- eval/replay 无 Bark。
- badcase 不污染 live decision。
- live fetch/search 计数为 0。
- production plan_runs / notifications delta 为 0。
- critical RuleJudge fail = 0 才允许候选发布。
- high/critical badcase 不复发。

### 长期记忆与候选治理

内容：

- 实现长期过程记忆。
- 保存用户偏好、过程教训、badcase 标签。
- 如需向量记忆，先做本地可关闭方案。

验收：

- 长期记忆不能生成 live `known_fact`。
- 旧行情、旧资金费率、旧新闻不能进入实时证据。
- badcase 只能进入 eval/candidate，不进入 live prompt。

## 20. 对抗审查采纳项

本轮按四个独立视角对本文档做了只读对抗审查：架构边界、资金风控、实现迁移、Eval/Trace/Release。以下问题已在本文中补充为设计约束。

### 20.1 架构边界审查采纳项

- 明确当前代码不是 agent swarm，而是固定 pipeline + 并发 search + 单次 leader review。
- 明确目标必须是受控 Agent Swarm，不是自由聊天式 swarm，也不是继续保留固定 pipeline。
- 新增 `DecisionRunContext` 字段分区和写权限矩阵。
- 新增 `LeadPlan` schema，限制 LeadAgent 只能选择枚举任务。
- 禁止 Agent-to-Agent 直接通信、handoff、动态 spawn。
- 明确 LeadAgent 不得过滤最强反方链、不得放宽 confidence cap、不得删除 hard block。
- 明确 YAML 只能收紧代码硬边界，不能放宽。

### 20.2 资金风控审查采纳项

- `trigger long/short` 纳入核心执行事实缺失时的阻断范围。
- `FinalDecisionAgent` 不再消费全量动作枚举，而是消费 `effective_allowed_actions`。
- `flip long to short` / `flip short to long` 当前阶段默认 hard block。
- RootCause/reviewer 禁止输出 entry、stop、target、leverage、position size 等可执行交易参数。
- 统一 source type 为下划线 canonical enum，例如 `search_derived`。
- manual/scheduled live run 禁止 `fixture` / `replay` evidence。
- confidence cap 统一为数值 `max_probability`，多 cap 取最低。
- SideEffectGate 必须在生产写入和通知前执行。

### 20.3 实现迁移审查采纳项

- 入口上下文阶段明确 `RunExecutor` 创建 `DecisionRunContext`，不再长期只传 `symbol`。
- `PlanRunner` 过渡为 legacy adapter 或内部 step，而不是长期主编排入口。
- 实时事实阶段增加 `MarketSnapshot/DataPoint -> EvidencePacket`、`SearchResult/ResearchAudit -> EvidencePacket`、`leader_summary -> AgentContribution[]` 的迁移映射。
- Agent 编排骨架拆成 Contribution 兼容封装、Harness 运行约束骨架、AgentRunner 并发执行三步。
- 明确 raw snippet、raw exchange JSON、完整 skill text、未过 FactsGate 的 snapshot 不得进入 FinalDecisionAgent。
- 增加 Harness MVP 接口签名。

### 20.4 Eval / Trace / Release 审查采纳项

- FrozenInput 升级为完整可回放输入，保存完整规范化 artifact refs，而不是只保存 summaries。
- ReplayRunner 定义 `frozen_observed`、`candidate_decision`、`judge_only` 三种模式。
- eval/replay 入口必须 Noop sinks、只读生产源、eval sidecar，并断言生产表 delta 为 0。
- LLMJudge 定义五个首批 rubric：evidence grounding、counter thesis、data gap honesty、execution clarity、overconfidence。
- 增加 badcase 生命周期。
- 增加 reviewer hit rate、false negative、false positive、failure taxonomy coverage 等有效性指标。
- 增加 Release Gate 与 Candidate Promotion。

## 21. 待确认问题

- RootCauseSkill 默认最大深度是否为 4，deep_research 是否允许提高到 5。
- standard_decision 是否默认跳过 ScenarioForkSkill，还是只在重大事件窗口跳过。
- SentimentCrowdingSkill 是独立 LLM call，还是先规则化 + compact LLM。
- standard_decision 默认 reviewer independence level 是 `compact_structured`，哪些条件升级到 `independent_parallel`。
- NewsSearchSkill 是否优先使用 OpenAI web_search，再 fallback DuckDuckGo HTML。
- deep_research 最大运行时间是否接受 1800 秒。
- FinalDecisionAgent 的 prompt/version 是否独立于 skill version。
- `SourcePriorityPolicy` 第一轮硬编码后，是否允许 YAML 仅做收紧型覆盖。
- 短期记忆窗口大小是否按 token budget 动态调整。
- 长期记忆是否第一轮只做 SQLite，不接 Mem0。
- Harness YAML 第一轮是否覆盖 reviewer independence level 的升级条件。
- 自动修复失败后 retry 次数是否固定为 1，还是按 Agent required/optional 分级。

## 22. 当前结论

本项目的核心价值不是“写一个 skill 给 Codex 调”，而是把交易判断拆成可控链路：

```text
实时事实
  -> 受控检索
  -> 短期结构化记忆补上下文
  -> MemoryFirewall 隔离旧事实
  -> 根因递归
  -> 情绪/拥挤约束
  -> 对抗审查
  -> Harness 约束 Agent 权限和输出
  -> Lead 规整
  -> 唯一动作
  -> 代码门禁
  -> trace/eval 回放
```

只有这样，系统才能在实时消息高度敏感的加密货币市场里，既允许大胆预测，又避免无依据的方向判断。
