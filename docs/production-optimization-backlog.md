# Production Optimization Backlog

日期：2026-07-07

本文用于记录结合当前项目状态与生产规范后需要优化的事项。它不是新的 formal 架构总纲，不替代 `docs/formal/34-生产级AgentSwarm优化目标与执行计划.md` 与 `docs/formal/37-真实多Agent对抗审查与交付方向裁决.md`，也不把 audit/candidate 侧路误判为生产主链完成。

## 当前判断

项目目标是 AI 辅助的加密货币人工提醒工作台，不是自动交易系统。生产规范必须继续保持：

- `auto_order_enabled=false`。
- `manual_execution_required=true`。
- 不接入下单、撤单、提现工具。
- eval/replay/candidate/audit 产物默认 `decision_effect=none`。
- search-derived 证据不能满足 mark/index/order_book 等执行事实。
- 生产 FinalDecisionAgent 默认仍走 `decision.final_input_mode=legacy_prompt`，切换到 `decision_input` 必须经过单独人工发布审查。

当前真实生产链路仍是：

```text
API/CLI
  -> RunExecutor
  -> LegacyPlanRunnerAdapter
  -> LegacyDecisionWorkflow
  -> final LLM using legacy prompt
  -> strict parser
  -> production_control/risk gates
  -> journal/notification
```

`agent_swarm/`、`lead/`、`decision_input`、`candidate_final_decision` 与 `src/crypto_manual_alert/skills/` 当前主要是 shadow audit、candidate、replay、eval 和结构化审计侧路，不是默认生产决策输入。

## 命名与边界优化

### P0. 澄清两类 skill 的边界

现状：

- `third_party/skills/crypto-macro-decision/` 是接近标准 Codex skill 的方法论资产，包含 `SKILL.md`、`references/`、`scripts/`。
- `src/crypto_manual_alert/skills/` 是项目内部受控业务工具 facade，包含 `realtime_search`、`root_cause_search`、`market_sentiment`、`macro_event`、`liquidity_order_book`。

问题：

- 两者都叫 skill，容易误解为 `src/.../skills/*` 也应该按标准 `SKILL.md` 目录组织。
- 当前 README 只写了 `skills/ skill runtime 与决策引擎适配`，不足以解释该目录实际是 runtime/tool facade。

优化：

- 在 README 和 docs/configuration 或单独短文档中明确：
  - `third_party/skills` = 外部/标准 skill 资产与规则来源。
  - `src/crypto_manual_alert/skills` = 受控业务工具 runtime，不是标准 skill 包。
- 若后续允许改名，优先考虑将内部包改为 `skill_tools`、`capabilities` 或 `controlled_tools`，避免长期歧义。
- 改名前先补 import compatibility wrapper，避免大面积破坏测试。

验收：

- 新人只看 README 能说清楚两类 skill 的职责。
- `src/crypto_manual_alert/skills` 不再被误认为要补 `SKILL.md`。

### P1. 收敛业务工具 facade 文档

现状：

- `SkillTaskContext`、`SkillToolResult`、`ToolCallArtifact` 已形成结构化契约。
- 但缺一份短文档解释每个内部 skill 的 source_type、是否能满足 execution fact、默认 provider、生产风险。

优化：

- 新增或补充一张表：
  - `realtime_search`: `search_derived`，不能满足 execution fact。
  - `root_cause_search`: `search_derived`，递归因果候选，不能满足 execution fact。
  - `market_sentiment`: `search_derived`，情绪/拥挤度候选。
  - `macro_event`: `official_or_event_pool`，宏观事件候选。
  - `liquidity_order_book`: `exchange_native`，唯一可产出 mark/index/order_book refs 的受控工具。

验收：

- 每个工具的生产含义、默认行为、可满足事实类型有明确文档。

## 真实提醒闭环

### P0. 明确默认配置与真实生产配置的差异

现状：

- `config/default.yaml` 是安全本地默认：fixture market、fixture decision、notification disabled、research disabled、shadow local_audit。
- `config/prod.yaml` 开启 openai_compatible、okx_public、Bark、scheduler、LLM research。
- `config/staging.yaml` 额外打开 okx_public 与 `macro_event.provider=no_active_event`，用于验证可执行提醒路径。

问题：

- 默认运行经常会得到被阻断或 fixture 结果，这符合安全默认，但容易被误判为生产不可用或 agent 能力失败。
- 真实可提醒路径需要显式组合配置，文档必须写清楚。

优化：

- 在 README/quickstart/deployment 明确三种运行模式：
  - local fixture smoke：验证结构能跑，不代表真实提醒。
  - staging actionable alert：验证 OKX public execution facts 与宏观事件声明。
  - prod manual alert：真实 LLM + OKX public + Bark，但仍 manual-only。
- 将 `docs/formal/37` 中 H1 提到的阻断陷阱写入公开操作文档：缺 exchange-native execution facts 或 active event 状态时，开仓/触发类动作会被 gate 阻断。

验收：

- 操作者知道何时预期 `allowed=false` 是安全阻断，何时代表需要补配置或数据。

### P0. 打通一次可复现的真实提醒 smoke

目标：

- 用真实 provider 路径跑通一次人工提醒闭环，证明项目交付的是可用提醒工具，而不是只生成 audit 报告。

最小路径：

```text
config/default.yaml
  + config/staging.yaml
  + config/prod.yaml
  + 必需环境变量
```

检查点：

- market data 来自 `okx_public`。
- decision engine 为 `openai_compatible`。
- notification enabled 且 Bark 真正触发。
- 输出 symbol 一致。
- 若计划被阻断，阻断原因必须可解释，并能定位是缺 execution facts、macro event 状态、risk gate 还是 production_control。

验收：

- 记录一次 trace_id。
- Run Detail 能看到计划、阻断/放行原因、关键事实来源与通知状态。

## Agent Swarm 与 Candidate 侧路

### P0. 避免把 audit-only 写成 production-ready

现状：

- shadow/candidate/replay 产物大量存在，但默认不接管生产 final input。
- `LlmToolShadowWorker` 明确不做最终决策、不写 journal、不发通知、不喂给 FinalDecisionAgent。

优化：

- 文档与 UI 文案统一使用：
  - `shadow audit`
  - `candidate sidecar`
  - `pre-final candidate input`
  - `decision_effect=none`
- 避免使用容易误导的表达：
  - “生产级 Agent Swarm 已接管”
  - “production candidate 已可直接发布”
  - “worker 输出即最终决策依据”

验收：

- Run Detail 中的 audit/candidate 面板能明显区分生产主链与旁路审计。
- README 不再给人“Agent Swarm 默认生产可用”的印象。

### P1. 收敛 `controlled_shadow` / `production_candidate_swarm` 状态机

现状：

- `RunExecutor` 允许 `workflow.execution_mode` 选择 controlled adapter。
- 当前很多 candidate 产物仍是 blocked/audit-only，不具备生产提升出口。

优化：

- 给 execution_mode 写清楚状态定义：
  - `legacy_baseline`: 默认生产主链。
  - `controlled_shadow`: 只审计，不生产。
  - `production_candidate_swarm`: 候选验证路径，不自动替换生产 final input。
- 如果未来要从 candidate 进入生产，必须满足：
  - release gate。
  - 手工发布审批。
  - rollback plan。
  - `decision.final_input_mode` 切换审查文件。

验收：

- 配置名、UI 展示、文档说法一致。

## 事实质量与金融质量闭环

### P0. execution facts 可视化与阻断理由前置

现状：

- 代码已有 `analysis.decision_ladder`、production_control、risk gate、tool_calls、fact_refs 等数据。
- 前端若只展示 trace/span/worker，业务用户仍难以判断“能不能信、为什么不能执行、缺什么”。

优化：

- Run Detail 首屏突出：
  - action/probability。
  - entry/stop/target。
  - allowed/blocking。
  - blocking rule hits。
  - missing execution facts。
  - source freshness。
  - strongest counter thesis。
- manual-run 成功页继续强化价位、概率、阻断原因、人工执行提醒。

验收：

- 管理者 5 秒内能判断：是否允许、为什么、缺哪些关键事实。

### P1. outcome collector 进入稳定使用

现状：

- outcome collector 与 OutcomeStore 已有路径，但金融质量样本积累仍是交付风险。

优化：

- 将 `collect-outcomes` 纳入日常操作文档。
- 明确 horizon 成熟后如何采集 exchange-native K 线。
- 至少积累一条真实 outcome，证明金融质量闭环不是空壳。
- 后续再做 legacy/candidate/no-trade baseline 对照。

验收：

- Eval 页面能展示真实 outcome 样本。
- Financial quality gate 的 `not_enough_samples` 是真实样本不足，而不是管道未接通。

## 测试与发布规范

### P0. 测试状态不得红着交付

优化：

- 交付前至少跑：

```powershell
python -m pytest
```

- 如果存在非 MVP 阻塞失败，必须在 README 或 release note 中显式列出：
  - 失败测试名。
  - 是否影响真实提醒闭环。
  - 临时处置。
  - 后续修复 owner/方向。

验收：

- 不能用“结构已完成”替代测试通过。

### P1. 配置安全检查保持 fail closed

必须保持：

- 禁止 `decision.engine=command` 绕过受控链路。
- 禁止 trade/withdraw key。
- `final_input_mode=decision_input` 必须要求 switch review 文件。
- `shadow.worker_mode=llm_tool_shadow` 真实模式必须显式 provider 与 LLM client，不得默认偷开。

验收：

- 配置 loader 对不安全配置继续 fail closed。
- 文档不鼓励用户用环境变量绕开安全边界。

## 文档治理

### P0. 停止新增 formal 总纲文档

现状：

- `docs/formal/` 已有大量设计文档，且 `docs/formal/37` 明确要求交付闭环跑通前不要继续新增 formal 总纲。

优化：

- 后续只允许：
  - 修改 README/quickstart/deployment 等面向操作的文档。
  - 写 migration/checkpoint 记录真实代码变更。
  - 写短小 backlog/decision record。
- 不再新增 `docs/formal/38-*` 这类总纲。

验收：

- 文档数量增长服务于交付，不再替代交付。

### P1. 建立当前状态页

优化：

- 新增或补充一页“当前生产状态”：
  - 默认链路是什么。
  - 哪些模块是 production。
  - 哪些模块是 shadow/candidate/eval。
  - 哪些配置打开后才会调用真实外部 provider。
  - 哪些能力明确不做。

验收：

- 任何 reviewer 不需要翻 30 篇 formal 文档就能判断项目当前形态。

## 建议执行顺序

1. P0 文档澄清：README/quickstart/deployment 写清默认、本地、staging、prod 差异。
2. P0 真实提醒 smoke：跑通一次真实路径，记录 trace_id 和结果。
3. P0 UI/Run Detail 首屏聚焦：让业务用户能看懂允许/阻断与缺失事实。
4. P0 测试全绿或显式 descoping。
5. P1 outcome collector 日常化。
6. P1 内部 `skills` 命名去歧义，必要时再做包名迁移。
7. P1 candidate/swarm 状态机文档与配置名收敛。

## 暂不做

- 不把 `src/crypto_manual_alert/skills/*` 改成标准 `SKILL.md` 包。
- 不默认启用 `decision.final_input_mode=decision_input`。
- 不默认启用 `shadow.worker_mode=llm_tool_shadow`。
- 不接自动下单/撤单/提现。
- 不接 Langfuse/DeepEval 等外部平台作为交付前优先项，除非真实提醒闭环、测试与 outcome 管道已经稳定。
