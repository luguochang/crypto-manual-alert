# Agent-Skill 重构实施计划

## 目标

把当前项目从“服务层直接抓行情再调用模型”的批处理结构，重构为“Agent 编排 Skill”的结构。

首版仍然只做手动操作提醒，不自动下单。系统输出操作计划后，通过 Bark 强提醒用户去交易所手动操作。

## 当前问题

当前实现的主链路是：

```text
PlanRunner
  -> MarketDataProvider.fetch_snapshot()
  -> SkillRuntime.build_prompt_packet(snapshot)
  -> DecisionEngine.run()
  -> parse_decision_plan()
  -> check_plan()
  -> journal + Bark
```

问题在于：

- `runner.py` 在 service 层直接拥有行情 provider。
- `market_data.py` 在 service 层直接写 OKX API 请求。
- `skill_runtime.py` 只把 skill path/hash 包进 prompt，没有真正执行 `crypto-macro-decision` 的 SOP、references、scripts、web search fallback。
- `OpenAICompatibleDecisionEngine` 的 system prompt 是硬编码的，容易和 skill 的真实规则分叉。
- 多 agent 目前不存在，只有单次 LLM 决策。

这不符合目标架构。目标是：行情、衍生品、web search 兜底、事件检查、指标扫描都应该通过 skill/tool 层完成；service 层只做调度、安全边界、风控、通知和记录。

## 目标架构

目标主链路：

```text
Scheduler / CLI
  -> AgentSkillRunner.run_once(symbol)
  -> DecisionWorkflow
       -> SkillLoader 加载 crypto-macro-decision
       -> SkillRegistry 注册可调用工具
       -> MarketFactAgent
       -> MacroEventAgent
       -> DerivativesAgent
       -> BullReviewer
       -> BearReviewer
       -> ExecutionRiskAgent
       -> FinalDecisionAgent
  -> parse_decision_plan()
  -> check_plan()
  -> journal
  -> Bark
```

关键边界：

- Agent 负责任务分工和判断。
- Skill 负责事实获取、SOP、引用资料、工具脚本。
- Workflow 负责并行/顺序编排和证据包聚合。
- Service 负责定时、配置、日志、通知、最终风控。
- LLM 只能输出 `DecisionPlan`，不能下单，不能接触交易密钥。

## 架构选择

参考项目有两种模式：

1. 差旅助手模式：`Skill = Agent 插件`
   - 每个 skill 里直接放 agent 类。
   - 优点是直观。
   - 缺点是容易把 prompt、业务逻辑、工具调用、JSON 清洗都塞进一个大类。

2. 医疗助手模式：`Skill = Tool 函数，Agent = 角色`
   - skill loader 自动发现 skill。
   - skill registry 把函数注册为 OpenAI tools。
   - agent loop 负责 LLM 调工具。
   - 多 agent 通过 coordinator/workflow 编排。

本项目采用第二种。

理由：

- 加密交易需要可测试的小工具函数，不适合大 agent 类。
- OKX/API/web search/fallback 可以作为工具白名单管理。
- 不同 agent 只能访问自己允许的工具，安全边界更清楚。
- 最终交易计划可以继续走现有 parser/risk/notifier 链路。

## 新增目录

计划新增：

```text
src/crypto_manual_alert/
  core/
    skill_loader.py
    skill_registry.py
    agent_loop.py
    llm_client.py

  agents/
    base.py
    market_fact_agent.py
    macro_event_agent.py
    derivatives_agent.py
    bull_reviewer.py
    bear_reviewer.py
    execution_risk_agent.py
    final_decision_agent.py

  workflow/
    evidence_packet.py
    adversarial_review.py
    decision_workflow.py

  constraints/
    agent_constraints.yaml
    decision_constraints.yaml
    validator.py
```

后续可选新增：

```text
src/crypto_manual_alert/skills/
  okx_public_tools.py
  web_search_tools.py
  skill_script_tools.py
```

`skills/` 目录只做 thin wrapper，真正规则来源仍然是 vendored skill：

```text
third_party/skills/crypto-macro-decision/
  SKILL.md
  references/
  scripts/
```

## 保留模块

这些模块应保留，只做适配：

- `config.py`：继续负责配置加载、安全检查、禁止交易密钥。
- `cli.py`：命令不大改，避免部署文档失效。
- `scheduler.py`：保留定时和 SQLite lock。
- `journal.py`：保留 SQLite 记录，扩展 payload。
- `notifier.py`：保留 Bark。
- `plan_parser.py`：保留严格 JSON 解析。
- `risk.py`：保留最终安全闸门，但输入从 `MarketSnapshot` 逐步迁移到 `EvidencePacket` / `DataQuality`。
- `domain.py`：保留 `DecisionPlan` 等核心对象，必要时新增证据包对象。
- `Dockerfile` / `docker-compose.yml`：保持外部启动方式不变。

## 降级或迁移模块

这些模块需要调整：

- `market_data.py`
  - 不再由 `PlanRunner` 直接调用。
  - 里面 OKX public 代码可以迁移成 skill tool，或包装调用 `crypto-macro-decision/scripts/okx_snapshot.py`。
  - 保留 fixture 只用于测试。

- `skill_runtime.py`
  - 不再只构造 prompt packet。
  - 应改为 skill metadata/reference/script 的加载入口，或被 `core/skill_loader.py` 替代。

- `runner.py`
  - 新增或改为 `AgentSkillRunner`。
  - `PlanRunner` 可暂时保留为 legacy。
  - 默认生产路径切到 agent-skill 后，再决定是否删除旧路径。

- `config/default.yaml`
  - `market_data.provider` 降级为 legacy。
  - 新增 `agent_workflow`、`skills`、`tools`、`web_search` 等配置段。

## Agent 分工

### MarketFactAgent

职责：

- 获取 last/mark/index。
- 获取 1H/4H candles。
- 获取 order book。
- 获取 funding/OI。
- 标注 timestamp、source、freshness。
- API 失败时调用 fallback。

输出：

```json
{
  "agent": "market_fact",
  "facts": {},
  "sources": [],
  "unavailable": [],
  "stale": [],
  "confidence_cap": null
}
```

### MacroEventAgent

职责：

- 读取 `event-pool.md` active/current 部分。
- 按 `data-sources.md` 进行宏观、新闻、地缘、ETF、稳定币等搜索。
- 区分 known fact、inference、scenario。

输出：

```json
{
  "agent": "macro_event",
  "events": [],
  "root_cause_chains": [],
  "hard_blocks": [],
  "soft_downgrades": []
}
```

### DerivativesAgent

职责：

- 按 `exchange-derivatives.md` 检查 minimum tradable data pack。
- 审计 funding、OI、long/short、liquidation、CVD、basis、options。
- 数据不足时明确 confidence cap。

输出：

```json
{
  "agent": "derivatives",
  "confirmation": {},
  "crowding_audit": {},
  "unavailable": [],
  "confidence_cap": 0.58
}
```

### BullReviewer

职责：

- 只提出做多链路。
- 指出多头触发价、确认信号、失效条件。
- 不输出最终结论。

### BearReviewer

职责：

- 只提出做空链路。
- 指出空头触发价、确认信号、失效条件。
- 不输出最终结论。

### ExecutionRiskAgent

职责：

- 检查 entry/stop/T1/T2 是否可执行。
- 检查 RR、滑点、order book、数据过期、事件压缩。
- 检查是否适合手动执行。

### FinalDecisionAgent

职责：

- 只能输出一个 `DecisionPlan`。
- `main_action` 必须是 skill 定义的 enum。
- 必须写 `why_not_opposite`。
- 必须输出 stop、target、有效期、置信度、不可用数据。
- 不能输出下单命令，不能输出真实仓位数量。

## 多 Agent 审查方式

不做自由聊天式辩论。

采用一轮结构化审查：

```text
Fact Agents 并行收集事实
  -> EvidencePacket
Review Agents 并行提出多/空/执行风险意见
  -> AdversarialReview
FinalDecisionAgent 合成唯一 DecisionPlan
```

这样更容易测试，也更适合生产。

## Skill / Tool 合约

Skill loader 必须支持：

- 读取 `SKILL.md` frontmatter。
- 计算 skill hash。
- 读取 required references。
- 允许按 agent 选择需要的 reference。
- 加载 `scripts/okx_snapshot.py` 这类脚本为受控工具。

Skill registry 必须支持：

- 注册工具函数。
- 工具参数 schema。
- 工具超时。
- 工具输出结构化。
- 按 agent 白名单限制工具。
- 记录每次 tool call 的输入摘要、输出摘要、耗时、错误。

首版工具建议：

```text
okx_snapshot
read_skill_reference
read_event_pool_active
web_search_crypto_market
web_search_macro_events
web_search_derivatives_fallback
```

其中 `web_search_*` 首版可以先做接口和 fixture，后续再接真实搜索源。

## 配置计划

新增配置段建议：

```yaml
agent_workflow:
  enabled: true
  mode: structured_review
  max_iterations: 4
  max_tool_calls_per_agent: 4
  total_timeout_seconds: 900
  fact_collection_timeout_seconds: 180
  review_timeout_seconds: 240
  finalization_timeout_seconds: 180

skills:
  crypto_macro_decision_path: third_party/skills/crypto-macro-decision
  allowed_skill_names:
    - crypto-macro-decision

tools:
  okx_snapshot_enabled: true
  web_search_enabled: false
  command_tools_enabled: true
  command_timeout_seconds: 30

web_search:
  provider: disabled
  timeout_seconds: 20
  max_results: 8

decision:
  engine: agent_skill
```

保留：

```yaml
trading:
  auto_order_enabled: false
  manual_execution_required: true
```

必须继续禁止：

```yaml
security:
  forbid_trade_keys: true
```

## 数据结构

新增 `EvidencePacket`：

```json
{
  "symbol": "ETH-USDT-SWAP",
  "created_at": "2026-06-24T00:00:00Z",
  "skill": {
    "name": "crypto-macro-decision",
    "path": "third_party/skills/crypto-macro-decision",
    "sha256": "..."
  },
  "facts": {},
  "sources": [],
  "unavailable": [],
  "stale": [],
  "agent_outputs": [],
  "data_quality": {
    "core_execution_complete": true,
    "minimum_pack_complete": false,
    "confidence_cap": 0.58,
    "cap_reasons": []
  }
}
```

`DecisionPlan` 继续使用现有 schema，不在第一阶段大改。

## 分阶段实施

### Phase 0: 冻结外部契约

目标：保证重构不破坏当前可用功能。

动作：

- 保留 CLI 命令。
- 保留 Bark 行为。
- 保留 SQLite journal。
- 保留 Docker Compose 启动方式。
- 保留 `DecisionPlan` JSON schema。
- 保留 `AUTO_ORDER_ENABLED=false` 和交易 key 禁用。

验收：

- 现有测试继续通过。
- fixture run-once 仍可跑通。

### Phase 1: 新增 skill loader 和 registry

目标：工程能加载 vendored skill，而不是只把 path 塞进 prompt。

新增：

- `core/skill_loader.py`
- `core/skill_registry.py`
- 对应测试。

验收：

- 能读取 `third_party/skills/crypto-macro-decision/SKILL.md`。
- 能计算 hash。
- 能读取指定 reference。
- 能注册和执行一个 fixture tool。
- 工具不存在、超时、异常时 fail closed。

### Phase 2: 新增 EvidencePacket 和 Agent 基类

目标：建立 agent 输出和证据包标准。

新增：

- `workflow/evidence_packet.py`
- `agents/base.py`
- `constraints/agent_constraints.yaml`
- `constraints/validator.py`

验收：

- agent 输出不符合 schema 会被拒绝。
- 未授权工具调用会被拒绝。
- evidence packet 可序列化进 journal。

### Phase 3: 接入 crypto skill 的 OKX snapshot

目标：行情事实由 skill/tool 层获取。

动作：

- 包装调用 `third_party/skills/crypto-macro-decision/scripts/okx_snapshot.py`。
- 或把现有 `OkxPublicMarketDataProvider` 移到 skill tool 边界。
- `PlanRunner` 不再直接调用它。

验收：

- `MarketFactAgent` 可以获得 last/mark/index/funding/OI/candles/books。
- OKX 不可达时，结果进入 `unavailable`，不抛出未处理异常。
- 数据时间戳和来源进入 evidence packet。

### Phase 4: 实现结构化多 agent review

目标：实现一轮多/空/执行风险审查。

新增：

- `agents/market_fact_agent.py`
- `agents/macro_event_agent.py`
- `agents/derivatives_agent.py`
- `agents/bull_reviewer.py`
- `agents/bear_reviewer.py`
- `agents/execution_risk_agent.py`
- `workflow/adversarial_review.py`

验收：

- bull/bear/risk reviewer 输出固定 JSON。
- 任一 reviewer 失败不会导致系统盲目给交易结论，必须降级或 block。
- finalizer 能看到 opposing view。

### Phase 5: 实现 FinalDecisionAgent 和 AgentSkillRunner

目标：完整替代旧的直接 prompt 决策路径。

新增/修改：

- `agents/final_decision_agent.py`
- `workflow/decision_workflow.py`
- `runner.py` 新增 `AgentSkillRunner`
- `build_decision_engine` 或新工厂支持 `decision.engine=agent_skill`

验收：

- finalizer 只输出一个 `DecisionPlan`。
- `parse_decision_plan()` 能解析。
- `check_plan()` 能校验。
- journal 写入 evidence、agent outputs、sources、skill hash。
- Bark 能正常发送最终人工操作提醒。

### Phase 6: Web search fallback 接口预留

目标：先把接口和审计链路做出来，真实搜索源可后续接。

新增：

- `skills/web_search_tools.py`
- `web_search.provider` 配置。
- fixture/mock provider。

验收：

- OKX/API 失败时 workflow 会尝试 fallback。
- 如果 provider disabled，必须明确写入 `web_search_disabled`。
- 不允许把 search-derived 数据伪装成 exchange-native。

### Phase 7: 切换默认路径并清理 legacy

目标：生产默认使用 agent-skill。

动作：

- `config/prod.yaml` 切到 `decision.engine=agent_skill`。
- 文档更新为 agent-skill 流程。
- `market_data.provider` 标为 legacy。
- 旧 `PlanRunner` 保留一段时间后再删除。

验收：

- `pytest -q` 通过。
- `crypto-alert show-config` 通过。
- fixture 模式通过。
- 本地真实 LLM + Bark 可跑完整链路。
- 海外服务器再测 OKX 真实 public API。

## 测试计划

新增测试：

```text
tests/test_skill_loader.py
tests/test_skill_registry.py
tests/test_agent_constraints.py
tests/test_evidence_packet.py
tests/test_agent_workflow_fixture.py
tests/test_agent_skill_runner.py
tests/test_web_search_fallback.py
```

重点测试：

- skill path 不存在。
- `SKILL.md` 读取失败。
- reference 不存在。
- 工具超时。
- 工具异常。
- agent 调用未授权工具。
- reviewer 输出非法 JSON。
- finalizer 输出多个 main_action。
- missing stop 被 risk gate 拒绝。
- stale data 触发 confidence cap。
- Bark 通知失败不影响 journal 记录。

## Journal 扩展

`plan_runs.payload_json` 建议增加：

```json
{
  "plan": {},
  "verdict": {},
  "evidence_packet": {},
  "agent_outputs": [],
  "tool_calls": [],
  "sources": [],
  "unavailable": [],
  "stale": [],
  "skill": {
    "name": "crypto-macro-decision",
    "sha256": "..."
  }
}
```

不要把密钥、完整 API token、完整 Bark key 写入 journal。

## 安全边界

首版必须保持：

- 不自动下单。
- 不申请 OKX trade key。
- 不读取 withdraw key。
- 不把任何 key 放进 prompt。
- 不把历史 journal 当成实时市场事实。
- 不允许 LLM 决定仓位数量。
- 不允许 LLM 解除熔断。
- 不允许没有止损的新开仓计划通过。
- 不允许过期计划通过。

## 部署影响

Docker Compose 外部形态不变：

- 不固定 container_name。
- 不暴露 host port。
- 使用环境变量注入 Bark 和 LLM key。
- 使用 `./data:/app/data` 持久化。

新增配置后，部署文档需要更新：

- 如何启用 `decision.engine=agent_skill`。
- 如何设置 agent workflow 超时。
- 如何启用/禁用 web search fallback。
- 如何查看 journal 中的 evidence。
- 如何判断某次结论是数据不足还是模型判断。

## 风险和取舍

### 不直接引入 LangChain / CrewAI / AutoGen

理由：

- 当前项目很小。
- 首版只需要 supervisor + specialist agents + tool registry。
- 引入大框架会增加部署、调试、版本兼容成本。

后续如果 workflow 复杂度明显上升，再评估 LangGraph。

### 不做自由辩论

理由：

- 自由辩论不可控。
- 交易场景需要可审计和可测试。
- 一轮结构化多空审查已经能覆盖主要反方观点。

### 不立刻删除旧路径

理由：

- 当前 fixture/openai/Bark 流程已跑通过。
- 分阶段迁移能降低风险。
- 新路径稳定后再清理 legacy。

## 你需要确认的问题

1. 是否同意采用“Skill = Tool 函数，Agent = 角色”的模式？
2. 是否同意第一版只做一轮结构化多 agent review，不做自由聊天辩论？
3. 是否同意暂时保留旧 `PlanRunner` 作为 legacy，等新路径稳定后再删？
4. 是否同意 web search 先做 provider 接口和 fixture，真实搜索源后续再接？
5. 是否同意首版仍严格禁止自动下单，只做强提醒和手动操作计划？

