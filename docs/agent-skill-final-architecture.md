# Agent-Skill 最终架构

## 核心结论

`crypto-macro-decision` 负责规则和规范层。
项目代码负责执行和编排层。

也就是说：

- `SKILL.md` 定义流程、数据源优先级、根因链要求、输出格式和审查要求。
- `scripts/` 提供可调用的数据采集脚本和兜底脚本。
- 编排代码真正负责启动多个 agent、运行工具、收集证据、强制反方审查，并产出唯一的 `DecisionPlan`。
- Hermes 如果保留，只能作为外壳入口，不能作为控制平面。

## 为什么必须这样拆

仅靠 prompt 不能真的执行：

- 在 prompt 里写“启动多个 agent”，并不会真的创建多个 agent。
- 在 prompt 里写“做深层根因链”，并不能保证模型真的追到更深层。
- 在 prompt 里写“缺数据时降低置信度”，并不能形成硬约束。
- 在 prompt 里写“审查反方观点”，也不会自动产生独立的反方分析。

所以代码必须把这些要求做成工作流，而不是愿望。

## 最终分层架构

```text
Hermes / CLI / Scheduler
  -> AgentSkillRunner
       -> SkillLoader
       -> SkillRegistry
       -> 事实采集 Agent
       -> 审查 Agent
       -> FinalDecisionAgent
  -> plan_parser
  -> risk gate
  -> journal
  -> Bark / 飞书
```

### 规范层

- `third_party/skills/crypto-macro-decision/SKILL.md`
- `third_party/skills/crypto-macro-decision/references/*`
- `third_party/skills/crypto-macro-decision/scripts/*`

### 编排层

- `core/skill_loader.py`
- `core/skill_registry.py`
- `workflow/decision_workflow.py`
- `workflow/adversarial_review.py`
- `workflow/evidence_packet.py`

### 事实层

- `MarketFactAgent`
- `MacroEventAgent`
- `DerivativesAgent`

### 审查层

- `BullReviewer`
- `BearReviewer`
- `ExecutionRiskAgent`

### 决策层

- `FinalDecisionAgent`
- `DecisionPlan`

### 闸门层

- `plan_parser`
- `risk.py`
- freshness / confidence cap
- schema validation

### 交付层

- `journal.py`
- `notifier.py`
- `scheduler.py`
- `cli.py`

## 责任边界

- skill 文件负责策略规范。
- 代码负责真实执行。
- workflow 负责 agent 协调。
- guardrail 负责拒绝、降级和拦截。
- delivery 负责通知和持久化。

## 先保留的旧路径

- `PlanRunner`
- `market_data.py`
- 当前直接 prompt 决策路径

这些先保留为 legacy，等新编排路径稳定后再清理。

## v1 最小版本

第一版只保留以下能力：

- 事实采集
- 根因链抽取
- 1 个 bull reviewer
- 1 个 bear reviewer
- 1 个 execution-risk reviewer
- 1 个 finalizer
- 严格 plan 解析
- 严格 risk gate
- journal + Bark

不做自动下单。
不接 trade / withdraw key。
不做自由聊天式辩论。

