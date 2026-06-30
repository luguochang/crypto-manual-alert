# 轻量自研 Workflow 与受控 Agent 层重构建议

## 1. 记录目的

本文记录当前讨论后推荐采用的重构方向：**方案 C：轻量自研 Workflow + 受控 Agent 层**。

本文不是最终实施计划，也不替代 `22-完整Agent业务流程与自进化评估架构设计.md`。它用于暂存当前判断，后续仍需要根据新的设计问题继续修正。

核心背景：

- 当前项目是加密货币趋势预测与手动操作提醒，不是医疗问诊系统。
- 直接照搬医疗领域的 `ConsultationAgent / DiagnosticAgent / ResearchAgent` 分类不合适。
- 当前代码可运行，但主链路仍偏固定 pipeline，Agent 编排价值没有充分落地。
- 项目真正价值不应只是“skill 文档 + 一个 LLM 决策”，而应是受控编排、质量约束、可回放、可评估和可按策略迭代。

## 2. 当前主要问题

### 2.1 Agent 不是一等对象

当前 `bull_reviewer`、`bear_reviewer`、`data_quality_reviewer`、`execution_risk_reviewer` 更像一次 LLM 输出里的多个 JSON key，或者静态 fallback 字典。

它们还不是独立 Worker Agent：

- 没有独立输入契约。
- 没有独立 timeout。
- 没有独立失败状态。
- 没有独立 trace/span。
- 没有独立 `AgentContribution`。
- 不能被 LeadAgent 明确调度、汇总和标记缺失。

### 2.2 Workflow 没有真正接管主链路

当前 `workflow/executor.py` 仍主要是 legacy facade，最终调用 `PlanRunner.run_once(symbol)`。

这意味着文档中的 `DecisionRunContext`、`StepSpec`、`LeadAgent`、`SharedContext`、`SkillRegistry` 还没有成为运行时主干。

### 2.3 编排集中在少数大文件

当前主要复杂度集中在：

- `runner.py`：行情、skill、research、LLM、parser、risk、journal、notifier 都在主流程中串联。
- `research.py`：planner、search adapter、web search、HTML parser、leader synthesizer、evidence synthesis 混在一起。
- `skill_runtime.py`：skill 加载、prompt packet 构建、final decision engine 放在同一层。

这导致可读性差，也让后续多 Agent 编排难以落地。

### 2.4 Skill 仍偏 prompt context，不是一等工具

当前 `SkillRuntime` 主要把 `crypto-macro-decision` 的 `SKILL.md` 和 references 摘要放入 prompt。

更合理的方向是：

```text
SkillLoader
  -> 加载固定 skill 包、计算 hash、读取 references

SkillRegistry
  -> 注册白名单工具

ToolPolicy
  -> 限制哪些工具可被哪个 step/agent 调用

ToolExecutor
  -> 执行工具、记录 trace、返回 ToolResult/EvidencePacket
```

系统不应动态发现任意 skill，也不应注册下单、撤单、提现等真实交易工具。

### 2.5 LeadAgent 职责不够清晰

当前 Lead 更接近“研究总结器”，不是完整的中心协调者。

目标中的 LeadAgent 应该负责：

- 基于 request、facts、gaps 拆解任务。
- 选择需要哪些 researcher/reviewer。
- 汇总 worker 贡献。
- 标记冲突、缺失、降级和置信度上限。
- 构建给 FinalDecisionAgent 的结构化输入。

LeadAgent 不应该：

- 直接给最终交易动作。
- 绕过 FactsGate / ParserGate / RiskGate。
- 触发通知。
- 修改生产 prompt、规则或 workflow。

## 3. 推荐方向：方案 C

推荐采用：

```text
轻量自研 Workflow
  + 受控 Agent 层
  + 白名单 Skill / Tool
  + 强制 Gates
  + Trace / FrozenInput / Eval
```

不建议当前直接做完整 LangGraph / AutoGen / CrewAI 迁移。

原因：

- 当前真实缺口是业务语义边界、证据隔离、门禁、trace/eval，不是缺一个大框架。
- 交易提醒涉及真实资金风险，自由 swarm 容易流程漂移、成本膨胀、难回放。
- 外部框架不能天然理解本项目的 hard safety rule，例如 manual-only、search-derived 不能替代 mark/index/order_book。
- 当前项目规模仍适合先做轻量自研骨架，后续当分支、恢复和人机中断复杂到难维护时，再评估引入框架。

## 4. 目标架构

一句话目标：

```text
把当前项目从几个大文件串起来的 LLM 决策 pipeline，
重构成以 DecisionRunContext 为中心、
由 WorkflowExecutor 编排、
多个受控 Agent 贡献证据和审查、
LeadAgent 规整、
FinalDecisionAgent 输出、
Gate 强制兜底的交易提醒系统。
```

目标主链路：

```text
DecisionRequest
  -> DecisionRunContext
  -> WorkflowExecutor
  -> MarketFactStep
  -> FactsGate
  -> ResearchPlanningStep
  -> ParallelResearchWorkers
  -> ReviewerWorkers
  -> LeadSynthesisStep
  -> DecisionInputBuilder
  -> FinalDecisionAgent
  -> ParserGate
  -> PlanSemanticGate
  -> RiskGate
  -> Journal / Notification
```

关键原则：

- 一轮运行只有一个 `DecisionRunContext`。
- 每个 step 只读写声明过的字段。
- 并发 worker 只能追加 `EvidencePacket` 或 `AgentContribution`。
- 并发 worker 不能直接改 final decision、risk verdict、notification。
- FinalDecisionAgent 只能消费 `DecisionInput`，不能调用工具。
- 代码层 gates 决定是否允许、阻断、降置信或通知。

## 5. Agent 分层建议

### 5.1 Agent 角色

| Agent | 职责 | 能否调用工具 | 能否给最终交易动作 |
|---|---|---:|---:|
| `DecisionLeadAgent` | 拆任务、汇总贡献、处理冲突、构建决策输入 | 否或只读 registry | 否 |
| `MarketFactAgent` | 拉交易所原生事实 | 是，白名单行情工具 | 否 |
| `MacroResearchAgent` | 查宏观、ETF、事件、新闻 | 是，白名单 search 工具 | 否 |
| `DerivativesAgent` | 审查 funding、OI、order book、liquidation、crowding | 是或只读 facts | 否 |
| `BullReviewer` | 构造最强多头根因链和确认条件 | 否 | 否 |
| `BearReviewer` | 构造最强空头根因链和确认条件 | 否 | 否 |
| `DataQualityReviewer` | 审计来源、新鲜度、冲突和置信度上限 | 否 | 否 |
| `ExecutionRiskReviewer` | 审计入场、止损、流动性、杠杆和执行风险 | 否 | 否 |
| `FinalDecisionAgent` | 基于规整后的输入生成一个 `DecisionPlan` | 否 | 是，但必须过 gate |

### 5.2 与医疗架构的差异

医疗助手适合按业务语义拆成健康咨询、症状诊断、医学研究等 Agent。

本项目更适合按交易提醒链路拆：

```text
事实层
  -> 研究层
  -> 对抗审查层
  -> Lead 规整层
  -> 最终决策层
  -> 风控门禁层
```

因此这里的多 Agent 不是为了角色扮演，而是为了让每个判断都有独立贡献、独立失败边界和独立审计记录。

## 6. 目录重构建议

建议逐步演进到以下结构：

```text
src/crypto_manual_alert/
  workflow/
    executor.py
    steps.py
    context.py
    result.py

  agents/
    lead_agent.py
    final_decision_agent.py
    research_planner.py
    reviewers.py

  skills/
    loader.py
    registry.py
    tool_policy.py
    tool_executor.py

  evidence/
    packet.py
    facts_gate.py
    synthesis.py

  gates/
    parser_gate.py
    semantic_gate.py
    risk_gate.py
```

迁移时不要一次性重写全部代码。旧文件可以先作为 facade 保留：

- `runner.py` 逐步变成 legacy facade。
- `research.py` 逐步拆成 planner、executor、adapters、lead synthesizer。
- `skill_runtime.py` 逐步拆成 skill loader、registry、decision input builder、final decision engine。

## 7. 第一阶段建议

第一阶段不要追求完整多 Agent，先把架构落点做出来。

建议第一刀：

```text
新增 DecisionRunContext
新增 WorkflowStep / StepResult
新增 EvidencePacket
新增 AgentContribution
让 RunExecutor 创建 context
让 PlanRunner 暂时作为 legacy step 或 facade
```

验收目标：

- 主入口不再只传 `symbol`，而是以 `DecisionRequest` 为输入。
- 一轮运行的中间状态能在 `DecisionRunContext` 中被追踪。
- research/reviewer 的输出可以表示为 contribution，而不是混在 summary JSON 中。
- trace 能看到 step 级状态，而不仅是固定 pipeline 的若干 span。

## 8. 第二阶段建议

第二阶段再迁移受控 Agent：

```text
ResearchPlannerAgent
  -> 生成 research tasks

ParallelResearchWorkers
  -> 并发执行 search/tool
  -> 输出 EvidencePacket

ReviewerWorkers
  -> bull/bear/data-quality/execution-risk 独立执行
  -> 输出 AgentContribution

LeadAgent
  -> 汇总 contribution
  -> 标记冲突和缺失
  -> 输出 DecisionInput
```

验收目标：

- 单个 reviewer 失败不会伪装成成功。
- LeadAgent 能明确标记缺失 reviewer。
- required worker 失败触发 hard block 或 confidence cap。
- optional worker 失败只写 unavailable，不能静默吞掉。
- 每个 worker 有独立 span、timeout、status、fallback_reason。

## 9. 第三阶段建议

第三阶段再强化 Skill / Tool 和 Eval：

```text
SkillLoader / SkillRegistry / ToolPolicy
  -> 工具白名单
  -> 工具调用审计
  -> search-derived 与 exchange-native 证据隔离

DecisionInputBuilder
  -> FinalDecisionAgent 只消费结构化输入

Eval / Replay
  -> frozen input
  -> baseline vs candidate
  -> release gate
  -> 人工审批
```

验收目标：

- search-derived 不能满足 mark/index/order_book。
- 开仓、反手类动作缺核心执行事实时 100% 阻断。
- FinalDecisionAgent 不能调用工具、不能发通知、不能改 RiskVerdict。
- badcase 只能生成 eval case 或候选改进，不能作为 live prompt 事实回灌。

## 10. 非目标

当前阶段不做：

- 完整通用 Agent 平台。
- 自由聊天式 swarm。
- 动态发现任意 skill。
- 任意脚本自动注册为工具。
- 自动交易。
- 下单、撤单、提现工具。
- 在线自我修改生产 prompt/rule/workflow。
- 把历史交易结论直接注入 live decision。

## 11. 保留问题

当前设计仍需要继续讨论的问题：

- `DecisionRunContext` 的字段边界如何定义，避免变成新的大杂烩对象。
- `AgentContribution` 应该多结构化，哪些字段必须由代码校验。
- LeadAgent 是 LLM、规则代码，还是二者组合。
- reviewer 默认 compact 模式还是 independent LLM call。
- 哪些 worker 是 required，哪些是 optional。
- `reasoning_mode` 如何版本化和进入 eval。
- 是否需要引入轻量 StepSpec 配置，还是先用代码显式编排。
- 何时才有必要引入 LangGraph 或 OpenAI Agents SDK。

## 12. 当前结论

当前推荐方向仍是：

```text
串行控制骨架 + 并发研究/审查内核
```

也就是：

- Session、intent、slot、facts gate、lead synthesis、final decision、parser、risk、journal、notification 必须串行。
- facts、research、review、eval 可以并发。
- Agent 负责提出可审查的判断。
- 代码负责边界、门禁、状态、trace、eval 和发布控制。

这是本项目区别于“直接写一个 skill 接 Codex”的核心价值。
