# 受控 Agent Swarm MVP 实施契约

## 1. 目的

本文是 `29-Agent与Skill拆分详细设计.md` 的落地契约，约束接下来代码重构的第一批模块、退出标准和禁止宣称完成的条件。

当前目标不是一次性重写完整系统，而是在现有仓库内新建清晰的编排内核边界，让旧 `PlanRunner` 逐步降级为 legacy adapter，同时保留 API、Journal、Trace、Eval/Replay、前端和现有风控回归资产。

一句话结论：

```text
同仓渐进重构：新 Workflow/Context/Adapter 骨架先接管入口，旧 PlanRunner 只作为兼容执行步骤；当前已落地 shadow_swarm_audit 和 pre-final 结构化输入审计，但不能宣称已经替换生产决策链。
```

## 2. 当前实现事实

当前代码事实必须明确记录，避免后续评审误判：

- 当前生产决策链仍不是完整 agent swarm。
- 当前生产链仍是固定 pipeline：`RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner.run_once(symbol)`。
- `research.py` 里多头、空头、数据质量、执行风险只是 `leader_summary` 的多个 key，不是独立 Worker Agent。
- 当前已经新增 `shadow_swarm_audit`：它有 `LeadPlan`、`SubTask`、并发 `ShadowSwarmRunner` 和 7 个 required shadow worker span，但 `decision_effect=none`，只写审计 payload。
- 当前生产路径已在 `decision.final` 之前运行 7 个 required shadow workers：`LiveFactAgent`、`DerivativesAgent`、`MacroEventAgent`、`RootCauseAgent`、`MarketSentimentAgent`、`DataQualityAgent`、`ExecutionRiskAgent`。它们只读隔离后的 safe/redacted `snapshot/research/facts_gate/evidence_packets`，生成 `AgentContribution`，不读取最终 `plan/verdict`，默认不调用 LLM，不检索实时信息，不写 journal/通知，不修改主链路。
- 当前已经在 `decision.final` 前生成 `pre_final_decision_input`：它只包含证据引用、worker contribution 引用、Lead synthesis、动作裁剪和 confidence policy，不包含 legacy plan、risk verdict、raw evidence 或 raw snippet；`decision_effect=none`，只写 payload 审计。`pre_final_orchestration.py` 当前只生成一次 `audit_payload`，并把同一份 artifact 传给 shadow worker 输入和 pre-final DecisionInput，避免 worker 所见证据与候选输入证据漂移；Lead synthesis 由 `LeadAgent.synthesize` 基于 shadow `LeadPlan` 和 worker contribution 统一生成，`DecisionInput` builder 只消费该结果，不再自行构造 synthesis。
- 当前已有受控 Skill facade 和 `SkillToolResult` 边界，但它们尚未真实接入默认生产主链；默认主链仍以 legacy prompt 与 shadow audit payload 为主，不能把 Skill facade 误判为生产 Tool loop 已完成。
- Final LLM 当前消费 legacy `prompt_packet`，不是 `DecisionInput`。
- FrozenInput 当前冻结 legacy prompt packet，不是完整 swarm artifact。

这些事实不代表已有工作没有价值。现有 API、Journal、Trace、FrozenInput、Eval sidecar、RuleJudge、RiskGate 和前端 schema 都是迁移时必须保护的资产。

## 2.1 当前态索引与历史记录解释规则

本文后半部分包含追加式执行记录。旧执行记录只作为历史参考，不代表当前代码状态。当前代码事实以本节、重构进度 checklist 和结构测试为准；当历史段落与当前态索引冲突时，以当前态索引为准。

当前 canonical 路径：

- 生产主链入口：`workflow/executor.py`、`workflow/legacy_adapter.py`、`workflow/legacy_plan_runner.py`、`workflow/legacy_decision_workflow.py`。
- pre-final 编排入口：`workflow/pre_final_orchestration.py`。
- shadow audit 编排入口：`orchestration/shadow_audit.py`；shadow audit 失败 envelope：`orchestration/shadow_failure.py`。
- 默认 shadow LeadPlan canonical builder：`lead/default_plan.py`；真实规划归属是 `lead/agent.py` 的 `LeadAgent.plan_tasks(...)`，`agent_swarm/default_lead_plan.py` 只保留兼容导出，`agent_swarm/shadow_runner.py` 不再内联默认任务规划。
- shadow worker 失败/超时/未配置/preflight reject envelope：`agent_swarm/shadow_worker_failures.py`；`agent_swarm/shadow_runner.py` 不再内联失败 contribution/hash 细节。
- worker/runner/registry/tool worker：`agent_swarm/`；加密货币市场业务 worker canonical owner：`market_agents/`。`agent_swarm/local_workers/`、`agent_swarm/workers.py`、`agent_swarm/shadow_orchestration.py` 和 `agent_swarm/shadow_failure.py` 只保留兼容导出。
- 编排中立契约：`orchestration/contracts.py`、`orchestration/runtime.py`、`orchestration/harness.py`。
- replayable input 入口：`decision/replayable_input.py`；生产链观察引用：`decision/replay_observed_refs.py`；worker manifest/ref：`decision/replay_worker_refs.py`；replay hash/raw 字段剥离：`decision/replay_sanitization.py`。
- DecisionInput 规则策略：`decision/decision_input_policy.py`；`decision/decision_input.py` 不再内联 missing facts、conflict、blocked action、confidence cap、required worker drop 或 worker hard block validation 规则。
- artifact 稳定哈希：`artifacts/hashing.py`；`decision/frozen_input.py` 继续兼容导出 `stable_hash`，但 `context/` 不得依赖 `decision/`。
- skill 加载与 prompt context：`skills/context_loader.py`、`skills/prompt_context.py`；`skills/runtime.py` 只保留兼容导出。
- final decision engine：`decision/final_engine.py`；pre-final canonical bundle：`decision/pre_final_bundle.py`；pre-final switch readiness envelope：`decision/pre_final_switch_readiness.py`；生产链构造 final engine 时不得再从 `skills.runtime` 取实现。
- research pipeline search adapter：`research_pipeline/search_adapters.py`；leader synthesis：`research_pipeline/leader_synthesizers.py`；共享 LLM 配置/耗时/chat completion helper：`research_pipeline/llm_support.py`；共享 prompt 常量：`research_pipeline/prompts.py`；`research_pipeline/core.py` 不再内联搜索适配器、DuckDuckGo HTML parser 或 leader synthesis。
- storage journal schema/migration/index 初始化：`storage/journal_schema.py`；storage journal row/JSON 投影：`storage/journal_rows.py`；`storage/journal.py` 不再内联 SQLite DDL、迁移 helper 或查询结果投影 helper。
- eval case builder 候选 artifact snapshot/ref 汇总：`eval/candidate_artifact_snapshots.py`；`eval/case_builder.py` 不再内联该组 hash/ref 细节。
- eval case builder context artifact refs 汇总：`eval/context_artifact_summary.py`；`eval/case_builder.py` 不再内联 context artifact refs 投影规则。
- eval case builder replayable input 安全摘要：`eval/replayable_input_summary.py`；`eval/case_builder.py` 不再内联 replayable coverage 与 artifact refs 白名单投影规则。
- eval replay 候选 artifact snapshot 一致性检查：`eval/candidate_artifact_consistency.py`；`eval/replay.py` 不再内联 candidate artifact sidecar hash/ref 对账规则。
- eval candidate artifact 校验：`eval/candidate_artifact_validation.py`；`eval/store.py` 不再内联 candidate artifact snapshot/ref 校验，`eval/candidate_artifact_consistency.py` 复用同一 artifact type 列表。
- eval replay worker manifest 一致性检查：`eval/worker_manifest_consistency.py`；`eval/replay.py` 不再内联 worker manifest、Lead synthesis drop 对账和相关 helper。
- eval replay context artifact 一致性检查：`eval/context_artifact_consistency.py`；`eval/replay.py` 不再内联 context artifact refs/hash 对账规则。
- eval replay 完整回放引用覆盖：`eval/complete_replay_refs.py`；`eval/replay.py` 不再内联 complete replay refs key map 或 missing refs 计算。
- eval replay 反方/冲突覆盖：`eval/counter_conflict_coverage.py`；`eval/replay.py` 不再内联 counter thesis、conflict refs 与 lead synthesis artifact gap 计算。
- eval replay shadow final 对照：`eval/shadow_final_comparison.py`；`eval/replay.py` 不再内联 DecisionInput shadow final 与 legacy observed output 的安全 diff 计算。
- eval release gate promotion review 状态机：`eval/release_promotion_review.py`；`eval/release_gate.py` 不再内联 promotion material/manual release/config review artifact 校验。
- eval promotion artifact 校验：`eval/promotion_artifact_validation.py`；`eval/store.py` 不再内联 promotion artifact 的业务校验，只保留 SQLite CRUD 与写入委托。
- eval store row/JSON 转换：`eval/store_rows.py`；`eval/store.py` 不再内联 JSON dump/load、row-to-schema 转换和 no-replay fallback。
- 根包结构护栏：`tests/structure/test_root_package_structure.py`；完整 runner 入口测试：`tests/workflow/test_run_executor.py`。
- 边界护栏：`tests/structure/test_context_boundaries.py`、`tests/structure/test_skill_runtime_boundaries.py`、`tests/structure/test_eval_case_builder_boundaries.py`、`tests/structure/test_eval_replay_boundaries.py`、`tests/structure/test_release_gate_boundaries.py`、`tests/structure/test_eval_store_boundaries.py`、`tests/structure/test_shadow_swarm_boundaries.py`；pre-final bundle/readiness 契约测试：`tests/decision/test_pre_final_bundle.py`、`tests/decision/test_pre_final_switch_readiness.py`。
- 编排 ownership 护栏：`tests/structure/test_orchestration_contract_boundaries.py`；内部源码不得依赖 `agent_swarm.contracts`、`agent_swarm.harness` 或 `agent_swarm.shadow_failure` 兼容路径。

当前物理目录事实：

- `src/crypto_manual_alert/*.py` 当前只允许 `__init__.py`。`cli`、`config`、`domain` 已经子包化，不能再写回根包 `.py` 文件。
- `tests/` 根层不再直接放测试 `.py` 或本地脚本；业务测试进入 `tests/<domain>/`，跨包结构约束进入 `tests/structure/`，本地脚本进入 `tools/local_stack/`。
- 历史记录中出现的 `tests/test_*.py`、根目录 wrapper 或 `agent_swarm.shadow_orchestration` 作为真实实现入口的描述，均属于当时迁移状态；当前实现和新增测试必须使用上面的 canonical 路径。

## 3. 渐进重构分层

### 入口上下文与 Legacy Adapter

这一层只做外壳重构，不改变交易行为。

必须实现：

- `DecisionRunContext`：一轮运行唯一上下文。
- `SideEffectPolicy`：由 `run_type` 派生副作用策略。
- `RunExecutor`：创建 `DecisionRunContext`，不再长期只把请求压缩成 `symbol`。
- `LegacyPlanRunnerAdapter`：短期调用旧 `PlanRunner`，并明确它是 legacy 兼容步骤。

这一层不做：

- 不拆独立 Worker Agent。
- 不改变最终 LLM prompt。
- 不替换 `RiskGate`。
- 不改前端 API 响应结构。
- 不迁移历史 SQLite 表。

退出标准：

- `RunExecutor.submit(request)` 创建 `DecisionRunContext`。
- `RunResult` 能暴露本次运行的 context 摘要，供测试和后续 trace 使用。
- `run_type=eval/replay/postmortem` 仍不能进入生产 `PlanRunner`。
- 现有手动运行 API、Journal、Trace、通知测试保持兼容。
- 新增测试证明 legacy adapter 收到的是 context，而不是由入口层直接绕过 context。

### 结构化证据与 Facts 边界

这一层仍不宣称完成 swarm，目标是把事实和检索结果从 prompt packet 迁移到结构化证据。

必须实现：

- `EvidencePacket`。
- `FactsGateResult`。
- `MarketSnapshot/DataPoint -> EvidencePacket` 映射。
- `SearchResult/ResearchAudit -> EvidencePacket` 映射。
- `leader_summary -> AgentContribution[]` 兼容映射。

退出标准：

- `search_derived` 不能满足 mark/index/order_book 等执行事实。
- raw search snippet、raw exchange JSON、完整 skill text 不能直接进入 FinalDecisionAgent。
- 缺核心执行事实时，opening/trigger/flip 类动作在进入最终动作空间前被裁剪或标记阻断。

### Contribution 兼容封装

这是过渡层，不是 swarm 完成点。

必须实现：

- 当前 compact reviewer 输出拆成多个 `AgentContribution`。
- 每个 contribution 有 `status`、`input_ref`、`output_hash`、`failure_policy_applied`、`trace_ref`。
- 单个 reviewer 缺失或非法时能标记 `failed/partial`。

禁止宣称：

- 只要没有独立 Worker Agent runner，就不能宣称完成 agent swarm。

### Harness 运行约束骨架

必须实现：

- `HarnessPolicy` / `load_harness_policy`。
- `validate_agent_run_request` / `validate_agent_contributions`。
- Agent 输入输出 schema 校验。
- Tool policy 校验。
- 非 Final agent 禁止输出可执行交易字段。

硬边界：

- YAML 只能收紧代码硬边界，不能放宽。
- FinalDecisionAgent 不能调用工具。
- Worker Agent 不能写最终动作、risk verdict、journal 或通知。

### Shadow Swarm 审计骨架

当前 shadow swarm 不接管生产决策。它证明“独立 worker 并发执行 + 失败显式入审计 + 不污染 prompt/frozen input/risk/notification”的运行骨架。

shadow 审计骨架必须实现：

- 枚举化 `LeadPlan`。
- `ShadowSwarmRunner` 并发运行独立 Worker Agent。
- 7 个 required shadow workers 在同一 run 中执行：`LiveFactAgent`、`DerivativesAgent`、`MacroEventAgent`、`RootCauseAgent`、`MarketSentimentAgent`、`DataQualityAgent`、`ExecutionRiskAgent`。
- 每个 Worker Agent 有独立 `SubTask`、input view、timeout、status、failure_policy、trace span。
- 每个 Worker Agent 输出独立 `AgentContribution`。
- Worker 失败必须显式进入 `shadow_swarm_audit.failed_workers`，不能伪装成功。
- `shadow_swarm_audit.decision_effect` 必须恒为 `none`。
- preflight 失败的 worker 不得执行。
- worker timeout 必须转为 failed audit，不得阻塞生产 plan 持久化和通知。

退出标准：

- 测试能证明 7 个 required shadow workers 产生独立 span。
- 测试能证明 Worker 只能 append evidence/contribution。
- 测试能证明 LeadPlan 不能创建枚举外任务。
- 测试能证明 shadow swarm 不进入 `prompt_packet`、FrozenInput、FinalDecisionAgent 输入和 notification。
- 测试能证明 shadow swarm 自身失败不会改变最终 `plan`，但会通过 `production_control_gate` 阻断可执行动作。

完整受控 Agent Swarm 仍未完成：

- FinalDecisionAgent 仍未切换到 `DecisionInput`。
- 完整可回放输入仍未保存完整 worker artifact。
- LeadAgent synthesis 已由 `LeadAgent.synthesize` 进入 `shadow_swarm_audit`、`pre_final_decision_input` 和候选审计，但仍未进入 FinalDecisionAgent 输入。
- Worker contribution 尚未成为 FinalDecisionAgent 的真实上下文，但已经通过 `DecisionInputCandidate` 和 `production_control_gate` 参与最终动作空间裁剪、confidence cap 与可执行动作阻断。

## 4. 第一层目标模块

第一层只允许新增和小改这些位置：

```text
src/crypto_manual_alert/context/request.py          # 已有 DecisionRequest
src/crypto_manual_alert/context/run_context.py      # 新增 DecisionRunContext / SideEffectPolicy
src/crypto_manual_alert/workflow/executor.py        # 修改为创建 context 的主入口
src/crypto_manual_alert/workflow/legacy_adapter.py  # 新增 legacy PlanRunner 适配器
tests/test_run_context.py                           # 新增 context 契约测试
tests/test_workflow_run_executor.py                 # 修改入口契约测试
```

第一层不得改动：

- `risk.py` 的既有判定语义。
- `runner.py` 的实际交易链路行为。
- `storage/journal.py` 的表结构。
- API 响应结构。
- 前端 schema。
- eval/replay 的旁路隔离语义。

## 4.1 代码目录分层约束

后续不得继续把新业务实现平铺到 `src/crypto_manual_alert/*.py` 根目录。当前根包物理 `.py` 只允许保留 `__init__.py`；`cli`、`config`、`domain` 已经子包化。新增或迁移的实现必须按业务域进入包目录：

- `agent_swarm/`：受控 Agent 编排契约、worker runtime、pool runner、shadow runner、worker registry、本地 worker、LLM/tool worker、shadow tool/client。
- `workflow/`：生产执行入口、legacy adapter、legacy workflow 步骤顺序、market/research/pre-final/control/persistence 步骤、未来 production executor 适配层。
- `context/`：运行上下文、side-effect policy、artifact store、orchestration artifact 写回。
- `eval/`：case、replay、judge、release gate、promotion/config-review sidecar。
- `decision/`：候选 DecisionInput、final input 选择、legacy prompt freeze、final 决策调用、计划解析、候选门禁、production control、switch readiness。
- `lead/`：LeadAgent 规划、Lead synthesis 候选聚合、Lead synthesis replay artifact。
- `artifacts/`：结构化证据、FactsGate、AgentContribution、legacy reviewer contribution adapter 和审计输入构造。
- `skills/`：skill 加载、skill context 构造、最终模型所需的 skill prompt packet 与决策引擎适配器。
- `telemetry/`：LLM 调用 telemetry payload 解析、token/cost/finish reason 等观测字段归一化。
- `market/`：行情数据 provider、交易所公开行情适配器、fixture 行情数据源。
- 后续再按风险较低顺序拆出 `gates/` 等包；迁移期可以短暂保留旧 import wrapper，但调用方和测试全部切到新路径后必须删除，不能长期留在根目录。

迁移原则：

- 先迁移无副作用、边界清晰的模块，再迁移生产 workflow 模块。
- 如迁移期临时保留 wrapper，只能 re-export，不得继续承载业务逻辑；完成调用方迁移后必须删除。
- 项目内部新代码必须使用业务子包 canonical 路径，不得继续引入根目录业务 wrapper。
- 包 `__init__.py` 不得 eager import 重型 workflow/runner 依赖；如需保留包级导出，使用轻量 namespace 或 lazy export，避免循环导入。
- 每次目录迁移必须有结构测试和核心行为回归测试，证明 JSON payload、`decision_effect=none`、生产 final input mode 与 journal/notification 副作用均未变化。

根目录 `.py` 文件归类口径：

- 当前可以长期保留的根包物理 `.py` 仅限包元信息 `__init__.py`。稳定入口或基础设施通过 `cli/`、`config/`、`domain/` 子包承载。
- Agent Swarm、Decision、Workflow step、Lead、Artifacts、Skill runtime、Telemetry、Notification、Market provider、Storage journal、Research pipeline 等业务实现均必须位于对应业务子包内，根目录不再保留这些业务 wrapper。
- `tests/structure/test_root_package_structure.py` 已把根目录白名单收紧为 `__init__.py`，防止业务 `.py` 文件重新散落到根包。
- 业务子包的 `__init__.py` 也不能成为隐形大入口。包级导出必须轻量，优先使用 lazy export；单纯 `import crypto_manual_alert.agent_swarm`、`import crypto_manual_alert.decision`、`import crypto_manual_alert.lead`、`import crypto_manual_alert.artifacts` 不得提前加载内部实现模块。
- 后续新增 Agent、Skill、Workflow step、Decision gate、Market provider、Telemetry sink 时，必须先选择清晰的业务子包和文件名。除稳定入口或兼容 wrapper 外，不允许新增 `src/crypto_manual_alert/*.py` 根包实现文件。

## 5. 命名约束

命名必须让代码评审者能直接看出职责：

- 用 `DecisionRunContext`，不用 `Context`、`SharedState`、`Blackboard`。
- 用 `SideEffectPolicy`，不用 `EffectConfig`。
- 用 `LegacyPlanRunnerAdapter`，不用 `RunnerWrapper`。
- 用 `AgentContribution`，不用 `ReviewResult`。
- 用 `EvidencePacket`，不用 `Fact` 或 `DataItem`。
- 用 `LeadPlan` 和 `SubTask`，不用 `TaskPlan`、`Job`、`Step` 混用。

所有新模块的 docstring 必须说明：

- 这个对象做什么。
- 它不做什么。
- 它属于哪个重构阶段。

## 6. 重构顺序

必须按以下顺序推进：

1. 补文档权威关系：`00` 指向 `29` 和本文。
2. 写失败测试：先证明入口需要 context 和 legacy adapter。
3. 新增 `DecisionRunContext` / `SideEffectPolicy`。
4. 新增 `LegacyPlanRunnerAdapter`。
5. 修改 `RunExecutor`。
6. 跑聚焦测试。
7. 跑相关 API/runner 回归测试。
8. 再进入结构化证据与 Facts 边界阶段。

## 7. 入口上下文阶段验收测试

入口上下文阶段至少需要这些测试：

- `DecisionRunContext` 保留完整 `DecisionRequest`，包括 `query_text`、`horizon`、`session_id`。
- manual/scheduled 的 `SideEffectPolicy` 允许生产 journal 和通知意图。
- eval/replay/postmortem 的 `SideEffectPolicy` 禁止生产 journal 和通知意图。
- 缺少 `run_context_summary.side_effect_policy` 的直接持久化调用默认禁止生产 journal 和通知意图；生产副作用必须显式来自 `DecisionRunContext` 或等价的 manual/scheduled policy，不得靠旧 `PlanRunner.run_once(symbol)` 默认放行。
- `RunExecutor` 返回的 `RunResult` 带有本次 context。
- `LegacyPlanRunnerAdapter` 只能从 context 读取 symbol 调用 legacy runner。
- `RunExecutor` 仍拒绝 eval/replay/postmortem 进入生产执行。

## 8. 禁止宣称完成的条件

出现以下任一情况，不能宣称已完成受控 Agent Swarm：

- 只新增了 `DecisionRunContext`。
- 只把 `leader_summary` 包装成 `AgentContribution`。
- 只有并发 search query。
- 一个 LLM call 输出多个 reviewer key。
- 没有独立 Worker Agent runner。
- 没有 Worker 级 timeout/status/failure_policy/trace span。
- FinalDecisionAgent 仍直接消费 legacy `prompt_packet`。

## 9. 当前执行状态

当前代码已完成以下基础落地：

- 入口上下文层：`DecisionRunContext`、`SideEffectPolicy`、`LegacyPlanRunnerAdapter`、`RunExecutor` 入口边界。
- CLI `run-once` 与 `scheduler` 已改为通过 `RunExecutor` 创建 `DecisionRunContext`，不再直接实例化 `PlanRunner`。
- 结构化证据层：`EvidencePacket`、`FactsGateResult`，并区分 `exchange_native` 与 `search_derived` 执行事实。
- Contribution 兼容封装：`AgentContribution` legacy wrapper。
- Harness 运行约束骨架：内置 `HarnessPolicy`、run request tool policy、contribution schema 与非 Final 可执行字段校验。
- Shadow Swarm 审计骨架：`LeadPlan`、`SubTask`、`ShadowSwarmRunner`、7 个 required shadow workers 并发执行、worker span、失败审计、runner payload 集成。
- Shadow Swarm 审计已前移到 `decision.final` 之前执行，worker input view 只允许读取 final 前的 `snapshot/research/facts_gate/evidence_packets`，不得读取最终 `plan/verdict`。
- 业务门禁候选已补充 `PlanSemanticGate`：审计 entry/stop/target 顺序和基础风险回报结构，当前只进入 payload/Eval，不替换现有 `RiskGate`。
- 当前 worker 是本地审计器，不是 LLM Agent，也不是实时工具 Agent；不得宣称已经完成生产级独立分析 Agent。

当前仍不能宣称“生产链已完成受控 Agent Swarm”。更准确的说法是：

```text
生产决策链仍是 legacy PlanRunner；
受控 Agent Swarm 已有 shadow audit 骨架；
下一步要把结构化决策输入、完整可回放输入、Lead 规整结果和业务门禁接入主链路。
```

## 10. 重构进度 checklist

每次继续开发前，先更新本表。不得只凭记忆判断进度。

当前代码目录事实优先级高于早期阶段记录：根目录业务 wrapper 已删除，`src/crypto_manual_alert/*.py` 当前只允许 `__init__.py`。本表和后续历史记录中若仍出现“旧根目录 wrapper 保留”或 `tests/test_*.py` 的历史措辞，只表示迁移过程中的早期状态，不代表当前代码状态；当前 import 和测试必须使用业务子包 canonical 路径。

| 模块 | 当前状态 | 完成口径 | 下一步 |
|---|---|---|---|
| 入口上下文 | 已接入并承载最小 artifact store；artifact 写回实现已迁入 `context/` 包 | `RunExecutor` 创建 `DecisionRunContext`，legacy adapter 把完整 context 传给 `PlanRunner`；API、CLI run-once、scheduler 均走该入口；`run_context` 摘要已写入 plan payload 与 trace metadata；evidence、worker contribution、LeadPlan、pre-final input、pre-final bundle、decision input candidate、candidate gate、replayable input candidate 和 production control gate result 已写回 context artifact store；`to_artifact_summary()` 已输出安全的 evidence/contribution refs、lead_plan_ref、pre-final `decision_input_ref`、pre-final bundle gate ref 和各 candidate gate refs，不暴露 raw payload/snippet；`set_lead_plan`、`set_decision_input`、`set_gate_result` 公开写入口已要求显式授权角色，worker 不能绕过 `write_section` 写 LeadPlan、DecisionInput 或 gate result；`context.artifacts` 承载 orchestration artifact 写回，旧根目录 `context_artifacts.py` 只保留兼容 wrapper；旧生产步骤顺序已抽到 `workflow.legacy_decision_workflow`，`runner.py` 不再直接导入 market/research/pre-final/final/parser/control 等 step 细节，并已改为从 `workflow.*` canonical 路径读取 legacy workflow 与 run persistence；`tests/test_workflow_run_executor.py` 已覆盖从真实 `RunExecutor.submit()` 到 journal payload、EvalCaseBuilder、EvalStore sidecar、`ReplayRunner(candidate_decision)` 和 release gate 的完整入口级 fixture | 继续让 `DecisionRunContext` 从承载 artifact 过渡到生产 workflow 的可替换执行上下文，但不得直接切换 FinalDecisionAgent 输入 |
| 结构化证据 | 已接入审计输入构造，核心实现已迁入 `artifacts/` 包 | `artifacts.evidence` 承载 `EvidencePacket` / `FactsGateResult`，能区分 `exchange_native` 和 `search_derived`；`artifacts.orchestration_inputs` 负责构建 evidence、facts gate、legacy contribution 和 harness validation；旧根目录 `evidence.py` 与 `orchestration_inputs.py` 只保留兼容 wrapper | 继续让 eligible evidence 明确进入可切换的最终决策输入 |
| Contribution 封装 | 已接入兼容层，核心实现已迁入 `artifacts/` 包 | `artifacts.contributions` 承载 `AgentContribution` 与 legacy reviewer adapter；legacy reviewer 可转成 `AgentContribution`；`harness.py` 与 `agent_swarm/*` 已切到 `artifacts.contributions`；旧根目录 `contributions.py` 只保留兼容 wrapper | 让 worker 原生输出 contribution，而不是从 summary 二次包装 |
| Harness 约束 | 已有骨架 | 能校验 agent、tool policy、schema、非 Final 可执行字段 | 接入真实 worker run request 和 final 前置校验 |
| Shadow Swarm 审计 | 已接入 shadow，已前移到 FinalDecision 前，并抽出独立 orchestration 入口；核心实现已迁入 `agent_swarm/` 包 | 4 个本地 worker 并发执行，`decision_effect=none`，不污染 prompt/frozen/notification；worker input view 不含最终 `plan/verdict`，且使用 safe/redacted 视图，raw search snippet 不进入 worker 输入；pre-final `audit_payload` 已成为 shadow 与 DecisionInput 候选的单一 artifact 来源；harness 失败会被生产控制门禁用于阻断可执行动作；worker span 与异常 envelope 已下沉到 `agent_swarm.runtime.AgentRunner`；preflight、并发限制、单 worker timeout、全局 `LeadPlan.deadline_ms` 和顺序聚合已下沉到 `agent_swarm.pool_runner.ControlledAgentPoolRunner`；`SubTask`、`LeadPlan`、`WorkerResult`、`ShadowSwarmAudit` 已迁入 `agent_swarm.contracts`；本地 worker 已通过 `agent_swarm.registry.WorkerImplementationRegistry` 显式注册；`shadow.worker_mode` 已从 `runner.py -> pre_final_orchestration.py -> shadow_orchestration.py` 传入 worker registry，默认 `local_audit`；`llm_tool_shadow` 缺少显式 LLM client factory 时会 hard fail into shadow audit，不影响生产决策；显式传入 `llm_client_factory` 时可注册并执行 4 个 `LlmToolShadowWorker`，但仍只产出 `AgentContribution` 且 `decision_effect=none`；`LlmToolShadowWorker` 默认拒绝 `tool_requests`，并会把 worker request timeout 下沉给 LLM client 与 tool executor；`FixtureShadowToolExecutor` 已提供离线 `web_search` 审计执行器，只有显式注入 `tool_executor` 且 SubTask 已请求该工具时才执行，并且只把 `result_ref/result_refs/result_count/source_type` 等审计结果写入 contribution constraints，不返回 raw snippet；`LeadAgent.plan_tasks(worker_mode="llm_tool_shadow")` 只为 harness 允许的 RootCauseAgent/MarketSentimentAgent 显式请求 `web_search`；`agent_swarm.shadow_llm_client` 已提供 fixture client 与显式 OpenAI-compatible shadow client factory，OpenAI-compatible client 支持 per-request timeout override，但不会因配置自动联网；`shadow_orchestration.py` 负责 LeadPlan、worker registry、ShadowSwarmRunner、tool executor 注入和失败 envelope，`runner.py` 只调用审计入口；旧根目录 `agent_runtime.py`、`agent_pool_runner.py`、`controlled_swarm_contracts.py`、`shadow_swarm.py`、`worker_registry.py`、`shadow_workers.py`、`llm_tool_shadow_worker.py`、`shadow_llm_client.py`、`shadow_tool_executor.py` 只保留兼容 re-export wrapper；`AgentRunResult` 已记录 `input_view_hash` 和 `agent_run_request_hash`，用于证明 worker 所见 safe/redacted 输入 | 继续保持 shadow/candidate `decision_effect=none` 与 sidecar readback 门禁；随后继续把 candidate/decision/gate 相关根目录模块按业务包迁移，不得继续在根目录新增实现文件 |
| LeadAgent | 已接入 shadow 规划和候选 synthesis，核心实现已迁入 `lead/` 包，未生产接管 | `LeadAgent.plan_tasks` 受 Harness 枚举约束，非法 worker 被拒，required worker 不得静默缺失；`LeadAgent.synthesize` 基于 shadow `LeadPlan` 和 worker contribution 生成 `shadow_swarm_audit.lead_synthesis`，pre-final input 与 candidate audit 只消费该单一来源；冲突、缺失 worker 和 dropped contribution reason 不再由 `decision_input.py` 自行构造；`lead.agent`、`lead.synthesis`、`lead.synthesis_artifact` 承载真实实现，旧根目录 `lead_agent.py`、`lead_synthesis.py`、`lead_synthesis_artifact.py` 只保留 re-export wrapper；生产 `shadow_orchestration.py` 与 `decision.candidate_audit` 已切到新包路径；仍不得误称为生产级 FinalDecisionAgent 上下文 | 扩展为生产级 synthesis 前继续做 shadow 对照，并让 synthesis 进入完整可回放 DecisionInput，随后再做受控切换实验 |
| DecisionInput | 已接入 pre-final 审计输入和事后候选，未接入最终模型输入；候选输入、门禁、final input 选择与解析步骤已迁入 `decision/` 包 | `pre_final_orchestration.py` 负责在 `decision.final` 前生成单一 `audit_payload`、shadow audit、`pre_final_decision_input` 和 `pre_final_bundle`，并写回 `DecisionRunContext`；`decision.pre_final_bundle` 以 refs/hash 绑定 FactsGate、harness validation、LeadPlan、worker manifest 和 pre-final DecisionInput，`decision_effect=none`，`production_final_input=false`，不复制 final plan/verdict/raw snippet；`decision.decision_input` 只接收 `lead_synthesis`，不再导入或调用 Lead synthesis 构造规则；`decision.candidate_audit`、`decision.gate_candidate`、`decision.plan_semantic_candidate`、`decision.switch_readiness`、`decision.production_control_gate` 和 `decision.replayable_input` 承载候选审计、业务门禁、切换准备度和可回放输入实现；`decision.pre_final_input`、`decision.final_input`、`decision.final_prompt`、`decision.final_decision_step`、`decision.legacy_final_input_step` 和 `decision.plan_parse_step` 承载 final 输入选择、legacy prompt 冻结和 final 输出解析边界；旧根目录同名模块只保留兼容 wrapper，`tests/test_decision_package_structure.py` 必须用对象身份断言防止新旧路径分叉；`validation` 不再只表示构建成功，会在 facts gate hard fail、required worker 缺失/失败或 missing facts 存在时显式记录 violation；Final LLM 当前仍消费 legacy `prompt_packet`，`decision_input_candidate` 只进入 payload audit 和生产控制门禁 | 继续让完整 worker artifact replay 稳定后，再做受控切换实验 |
| FinalDecisionAgent | 未切换，已有输入选择器和切换条件审计 | `final_input_selection` 当前锁定 `legacy_prompt`，`final_decision_switch_readiness` 只判断是否具备切换条件 | 只有候选 gate、worker artifact、完整可回放输入都稳定后才允许切换实验 |
| 完整可回放输入 | 已接入审计候选和 eval sidecar，未替换现有 FrozenInput | `replayable_input_candidate` 记录稳定 `input_ref`、legacy frozen hash、DecisionInput candidate refs、shadow worker artifact refs、worker result manifest、worker `input_view_hash`、`agent_run_request_hash`、agent_run_result 摘要和 tool_audit_result_refs；同一 `input_ref` 下 safe/redacted worker input view 变化会导致 manifest input hash 变化；Eval case/replay 会保留安全的 candidate replay 摘要与 coverage，不复制 raw payload；`ReplayRunner` 会检查 coverage、worker refs 和 manifest 的数量/哈希自洽，输出 `worker_manifest_consistency`；同时会对照 `run_context.artifacts` 的安全 refs/hash，输出 `context_artifact_consistency`；`EvalStore` 已新增 `eval_candidate_artifacts` sidecar，`upsert_cases()` 会同步保存 7 类 candidate artifact snapshot：`decision_input_candidate`、`replayable_input_candidate`、`lead_synthesis`、`worker_result_manifest`、`gate_candidate`、`plan_semantic_candidate`、`final_decision_switch_readiness`；candidate artifact snapshot 顶层必须 `decision_effect=none`、`production_final_input=false`、`notification_input=false`，每个子 artifact 也必须显式 `decision_effect=none`；`ReplayRunner` 会优先从 eval store 读回 case 与 candidate artifact sidecar，校验 JSON 内 `artifact_hash` 与 sidecar 表列 `artifact_hash` 一致，并输出 `artifact_snapshot_consistency` | 继续保持 replay 不调用生产 runner/LLM/tool；下一步基于完整 readback 进入生产级 synthesis 与 DecisionInput 切换实验的人工评审前置条件 |
| 业务门禁 | 已接入生产阻断层，仍保留现有 RiskGate | `decision_control_step.py` 负责生成 candidate audit、运行 `production_control_gate`、调用 legacy RiskGate 并合并 verdict；`production_control_gate` 仍在 `parser.strict_json` 后、`risk.check` 前生效 | 继续扩展 RR 下限、事件窗口、滑点等语义门，并把 release gate 指标纳入上线条件 |
| Eval 闭环 | 已能读取候选审计摘要并生成 release gate 硬门禁评审对象 | Eval case summary 会带 `candidate_audit`，RuleJudge 会评分 candidate gate、plan semantic candidate 与 switch readiness；`EvalRunner.metadata.release_gate` 会汇总失败 score、schema valid rate、candidate replay 覆盖、candidate blocked action/missing facts 摘要、search_derived/web_derived 执行事实误用、worker artifact 数、worker manifest 完整性、worker manifest 自洽性、context artifact 自洽性、candidate artifact sidecar readback 自洽性、最小 eval 覆盖和 switch readiness 阻断原因，并输出 `hard_gate_results`、`hard_gates_passed`、`promotion_review` 与 `promotion_approved=false`；candidate gate 失败但缺少 `blocked_actions` 或 `missing_facts` 证据时会以 `candidate_block_evidence_incomplete` 阻断；manifest 数量或 hash 自洽失败会以 `worker_manifest_consistency_failed` 阻断；context artifact refs/hash 对照失败会以 `context_artifact_consistency_failed` 阻断；candidate artifact sidecar 缺失、不一致、字段缺失或格式错误都会以 `artifact_snapshot_readback_failed` 阻断；`ReplayRunner(candidate_decision)` 在显式注入 DecisionInput shadow final adapter 时，会生成 `shadow_legacy_comparison`，只比较 legacy observed parsed plan 与 shadow final 的安全动作/概率摘要；`shadow_candidate_comparison` 作为人工切换评审材料时，必须为每个可用 case 同时带 completed/no-effect `decision_input_shadow_final` 安全摘要和 `shadow_legacy_comparison`，否则该 comparison 视为缺失；`minimum_case_count` 与 `schema_valid_rate_threshold` 已接入 `eval.release_gate` 配置，默认值保持本地 eval 行为不变；该结果只用于发布评审，不会自动切换 FinalDecisionAgent 输入 | 后续补齐高/critical badcase 复发、人审审批 artifact、回滚版本和影响范围；发布配置只能收紧评审门槛，不能打开生产切换 |

## 11. 下一步实施入口

当前已经越过“只写候选 payload”的阶段。下一步不是继续清理文档，也不是直接让 shadow worker 接管生产决策，而是在保持 FinalDecisionAgent 继续消费 legacy prompt 的前提下，把受控编排产物逐步纳入生产控制门禁：

```text
EvidencePacket / FactsGateResult
  + shadow worker AgentContribution
  -> pre_final_decision_input audit
  -> legacy FinalDecisionAgent
  -> PlanRunner legacy output
  + EvidencePacket / FactsGateResult
  + shadow worker AgentContribution
  -> DecisionInputBuilder candidate
  -> Lead synthesis candidate
  -> candidate audit payload
  -> production_control_gate
  -> legacy RiskGate
```

硬约束：

- candidate 不进入 `prompt_packet`。
- candidate 不直接改变 `plan`。
- candidate 不进入 FinalDecisionAgent 输入。
- `pre_final_decision_input` 必须在 `decision.final` 前生成，但仍不能进入 FinalDecisionAgent 输入、FrozenInput 或 notification。
- `production_control_gate` 可以读取 candidate audit，并在 legacy `RiskGate` 前阻断可执行动作。
- candidate 不改变 journal schema 和 notification。
- candidate 必须记录 hash、input refs、dropped contribution reason、missing facts 和 conflict。
- candidate 必须有测试证明：legacy frozen input hash 不变，shadow/candidate 失败不影响生产通知。

退出标准：

- `DecisionInputBuilder` 有独立测试，覆盖 eligible evidence、blocked actions、confidence cap、missing facts。
- `Lead synthesis candidate` 有独立测试，覆盖冲突保留、缺失 worker 标记、反方链不被静默删除。
- runner payload 中能看到 `pre_final_decision_input` 和 candidate audit；生产 prompt/frozen/notification 不读取它们；生产控制门禁可以读取 candidate audit 并转成 RuleHit。
- 文档和测试都继续明确：此时仍未完成生产级受控 Agent Swarm。

当前代码已完成本节的最小候选层：`pre_final_decision_input` 会在 `decision.final` 前写入 plan payload，证明结构化输入可以脱离 legacy plan/verdict 生成；`shadow_swarm_audit.lead_synthesis` 由 `LeadAgent.synthesize` 生成，并被 `pre_final_decision_input` 与 `decision_input_candidate` 复用来记录冲突、缺失 worker 和 dropped contribution reason；`replayable_input_candidate` 会记录 legacy frozen hash、DecisionInput candidate refs 和 shadow worker artifact refs；`gate_candidate` 会审计 legacy action 是否落在 candidate allowed actions 内，并检查 confidence cap；`final_decision_switch_readiness` 会判断是否具备切换 FinalDecisionAgent 输入的条件。它们仍不进入 `prompt_packet`、legacy frozen payload、journal schema 或 notification，也不是 FinalDecisionAgent 的真实输入。但 `production_control_gate` 已经可以读取这些候选审计结果，并把 action clipping、confidence cap、semantic failure、shadow harness failure 和 required worker 缺失转成生产 `RiskVerdict` 阻断。
`DecisionInput.validation` 当前用于候选链路和 readiness，不代表生产 FinalDecisionAgent 已切换；它会把 facts gate hard fail、required worker 缺失/失败和 missing facts 记录为结构化 violation，并且只把 `missing_required_contribution` 或 required contribution 失败归类为 required worker failure，optional worker drop 不会误触发 hard fail；这样避免评审把“候选 payload 构建成功”误读为“决策输入已满足上线条件”。

market/skill 上下文入口是 `workflow.market_context_step`，负责当前市场快照和 skill context 加载。研究降级编排入口是 `workflow.research_orchestration`，负责 research plan、并发 search、search evidence 合成和 leader review。编排输入构造入口是 `artifacts.orchestration_inputs`。final 前受控编排入口是 `workflow.pre_final_orchestration`，负责生成单一 `audit_payload`、shadow audit、pre-final input、pre-final bundle 和 context 写回。`decision.pre_final_bundle` 是 final 前 canonical 审计锚点，只输出安全 refs/hash 与 worker manifest，不进入 final prompt、FrozenInput 或 notification。候选审计聚合入口是 `decision.candidate_audit`。决策控制入口是 `workflow.decision_control_step`，负责 candidate audit、production control gate 和 legacy RiskGate 合并。context artifact 写回入口是 `context.artifacts`。legacy final input 构造入口是 `decision.legacy_final_input_step`，负责 final-safe prompt packet 和 FrozenInput。计划解析入口是 `decision.plan_parse_step`，负责 legacy final raw JSON 到 `DecisionPlan` 的边界。运行持久化入口是 `workflow.run_persistence_step`，负责 plan payload、journal、trace finish 和 notification audit，并硬校验 `SideEffectPolicy`；缺少 side-effect policy 时默认跳过生产 `plan_runs` 和 `notifications`，避免 eval/replay/postmortem 或旧直调绕过入口写生产 plan 或通知。plan payload 组装入口是 `workflow.persistence_payload`。legacy 生产步骤顺序入口是 `workflow.legacy_decision_workflow`，负责串联当前 legacy prompt 链路，`workflow.legacy_plan_runner` 负责启动 trace、调用该 workflow、处理成功/失败持久化，不能继续堆积 market fetch、skill load、Evidence/Facts、DecisionInput、Lead synthesis、ReplayableInput、Gate readiness、risk merge、legacy prompt freeze、parser、payload、journal/notification 或 context 写入细节。
Shadow 编排入口当前是 `orchestration.shadow_audit`。LeadPlan 构造、本地 worker registry、`ShadowSwarmRunner` 调用和 shadow 失败归一化都放在这里，避免 legacy runner 或 `agent_swarm/` worker 包继续混入 Lead 编排细节；`agent_swarm.shadow_orchestration` 只保留兼容导出。
Legacy final prompt 构造入口是 `decision.final_prompt`。它负责构造当前 legacy prompt 的 final-safe research/snapshot 视图，保证 raw search snippet 不进入 `decision.final` 输入。`decision.legacy_final_input_step` 再把该 prompt packet 冻结为当前生产 FinalDecisionAgent 使用的 exact FrozenInput。

配置层当前显式使用 `decision.final_input_mode=legacy_prompt`。任何 `decision_input` 切换值都会被配置校验拒绝，直到候选链路的 readiness 结果、回放覆盖率和人工验收全部达标。

最终模型输入选择入口是 `decision.final_input`。`FinalInputSelector` 已具备受控 `DecisionInput` 渲染能力：只有 `switch_readiness.ready=true`、候选 `validation.passed=true` 且存在 `input_ref/input_hash` 时，才会把候选输入复制为 `production_final_input` payload，并保留 `source_candidate_ref/source_candidate_hash`。这只是切换前置能力，不代表生产配置已允许切换。
最终决策执行入口是 `decision.final_decision_step`。它封装 final input selection 和 legacy decision engine 调用；当前生产配置仍锁定 `legacy_prompt`，但 `workflow.legacy_decision_workflow` 已在 final step 调用边界显式传入 `pre_final_decision_input` 和 `decision.pre_final_switch_readiness` 生成的 pre-final readiness envelope。该 envelope 的 `stage=pre_final`、`decision_effect=none`、`ready=false`，并显式列出尚未生成的 post-final gates：`decision_input_candidate`、`replayable_input_candidate`、`gate_candidate`、`plan_semantic_candidate`、`production_control_gate`；它只说明 legacy final 前不能切换输入，不替代 post-final `final_decision_switch_readiness`。最终审计 payload 组装入口是 `workflow.persistence_payload`，legacy runner 不再内联 redaction、analysis summary 或 candidate audit 默认构造。`decision.plan_parse_step` 封装 `parser.strict_json` 的解析边界；`workflow.run_persistence_step` 封装成功与失败路径的 payload、journal、trace finish 和 notification audit，通知失败仍不得改变 `RiskVerdict`。

Eval 侧已能读取 candidate audit 摘要。`EvalCaseBuilder` 只提取 gate/semantic/readiness/input_ref/hash 等安全摘要，不复制 raw prompt、raw snippet 或完整 contribution；`RuleJudge` 会对 candidate gate、plan semantic candidate 和 switch readiness 做旁路评分。
`ReplayRunner` 已在 sidecar output 中加入 `candidate_replay` 摘要，记录 DecisionInput ref/hash、ReplayableInput ref/hash、worker artifact count 和 switch blocking reasons；`replayable_input_candidate` 自身已包含 worker result manifest（task、agent、status、input_ref、input_hash、agent_run_request_hash、output_hash、trace_ref、failure_policy、agent_run_result、tool_audit_result_refs、error）。其中 `input_hash` 优先来自 `AgentRunResult.input_view_hash`，覆盖 safe/redacted worker input view；`agent_run_request_hash` 覆盖 worker run request envelope；`worker_manifest_consistency` 会检查 coverage 声称的 worker 数、manifest 数、worker refs 数和 manifest 内 hash 是否一致；`context_artifact_consistency` 会把 candidate refs/hash 与 `run_context.artifacts` 中的 `decision_input_candidate` gate ref、`replayable_input_candidate` ref、evidence/contribution refs 数量进行对照；`run_context.artifacts.decision_input_ref` 仍表示 final 前 `pre_final_decision_input`，不得与 post-final candidate input 混用。Replay mode 已显式区分 `frozen_observed`、`judge_only` 和 `candidate_decision`；`candidate_decision` 当前只做基于 candidate audit artifact 的只读 replay，输出 `decision_effect=none` 的审计结果，不调用生产 runner、真实 LLM 或真实工具。
`EvalRunner` 已在 metadata 中加入 `release_gate` 硬门禁评审对象，统一汇总 eval score 失败、schema valid rate 不达标、manual-only 失败、side-effect guard 失败、critical rule 失败、candidate gate/semantic gate 失败、candidate blocked action 证据缺失、search_derived/web_derived 冒充 mark/index/order_book 执行事实、candidate replay 缺失、worker artifact 覆盖不足、worker manifest 缺字段、worker manifest 自洽失败、context artifact 自洽失败、candidate artifact readback 失败、最小 eval 覆盖不足和 final switch readiness 未就绪。该对象会输出 `hard_gate_results`、`hard_gates_passed`、`promotion_review` 和 `promotion_approved=false`；`minimum_case_count` 与 `schema_valid_rate_threshold` 已通过 `eval.release_gate` 配置注入，默认值保持原本本地 eval 行为；即使 `hard_gates_passed=true`，也只表示候选具备进入人工发布评审的条件，不代表允许自动切换 `decision.final_input_mode`，不会写生产 journal。

Release gate 的 `promotion_review` 当前已经显式声明发布前必需 artifact：`manual_approval`、`rollback_plan`、`impact_scope`、`shadow_candidate_comparison`。在这些 artifact 尚未写入并通过人工验收前，`required_artifacts.*.present` 必须保持 `false`，`missing_artifacts` 必须列出缺失项，`approval_artifact_ref` 必须保持 `None`，`allowed_to_change_production_final_input` 必须保持 `false`。这表示“可以进入人工发布评审”，不是“可以自动发布候选”。

当前已定义四类 promotion artifact 的只读 schema：`manual_approval`、`rollback_plan`、`impact_scope` 和 `shadow_candidate_comparison`。这些 artifact 的 `decision_effect` 必须恒为 `none`，只能作为发布评审材料，不得写生产 journal，不得发送通知，不得改变 `decision.final_input_mode`。

当前另有两类可选的配置变更审查 artifact：`manual_release_decision` 和 `config_change_review_request`。`manual_release_decision` 必须绑定同一个 `eval_run_id`，引用四类必需 artifact 的 artifact_ref，记录 baseline/target final input mode、candidate input ref/hash 和 config hash；它只表示“可以进入单独的配置变更审查”，不表示允许自动修改生产配置。`config_change_review_request` 必须绑定合法 `manual_release_decision_ref` 和同一组 candidate input ref/hash，只表示“已经提交人工配置变更审查申请”。两者都必须保持 `decision_effect=none` 和 `allowed_to_change_production_final_input=false`。

`EvalRunner` 会自动生成 `promotion_artifacts.shadow_candidate_comparison`。它只汇总 replay 输出里的 `DecisionInput` ref/hash、ReplayableInput ref/hash、worker 覆盖数量、自洽校验结果、blocked actions、missing facts 和 switch readiness，不复制 raw prompt、raw snippet 或完整 worker payload。`manual_approval`、`rollback_plan`、`impact_scope`、`manual_release_decision` 和 `config_change_review_request` 则必须由发布流程显式提供。

Eval store 当前已新增 `eval_promotion_artifacts` sidecar 存储。`EvalRunner` 写入 run 时会把 metadata 中的 promotion artifacts 同步写入该 sidecar；手工补充的 promotion artifacts 也必须通过该入口写入，并校验 `eval_run_id`、`artifact_type`、`artifact_ref` 绑定当前 run、`schema_version` 和 `decision_effect=none`。这一步仍是 eval sidecar，不写生产 journal，不发送通知。

Release gate 识别 promotion artifact 时必须传入并绑定当前 `eval_run_id`，缺少 `eval_run_id` 时所有 promotion artifact 都按无效处理；同时校验 artifact_ref 形状和最小内容完整性。`manual_approval` 必须有审批人和 `approved_for_manual_promotion` 决定；`rollback_plan` 必须有回滚目标和步骤；`impact_scope` 必须有受影响组件和排除组件；`shadow_candidate_comparison` 必须无缺失 replay、所有 case 都 switch ready、worker/context 自洽均通过且 worker 覆盖达标，并且每个 available case 必须包含 `decision_input_shadow_final.status=completed`、`decision_effect=none`、`artifact_ref/hash`、`source_decision_input_ref/hash` 和安全 `main_action` 摘要。缺少 shadow final、shadow final 失败、source 信息缺失或 effectful shadow final 都不能作为人工切换评审材料。硬门禁通过但材料不齐时，`promotion_review.status=blocked_missing_artifacts`；材料齐全时只进入 `ready_for_manual_release_decision`，仍保持 `promotion_approved=false` 和 `allowed_to_change_production_final_input=false`。如果再提供合法的 `manual_release_decision`，`promotion_review.status` 只能提升到 `ready_for_config_change_review`；如果再提供合法的 `config_change_review_request`，状态只能提升到 `config_change_review_requested`。这些状态都必须保持 `promotion_approved=false` 和 `allowed_to_change_production_final_input=false`。真正发布仍需要后续单独的人工配置变更流程，不能由 release gate 或 artifact 自动修改生产配置。

## 12. 当前最新落地状态

本节用于防止后续开发忘记当前边界。

- `shadow_swarm_audit` 已经从 `risk.check` 之后前移到 `decision.final` 之前，后续 `DecisionInputCandidate` 可以消费 final 前 worker contribution，而不是事后补审计。
- 前移不代表生产链切换：`shadow_swarm_audit.decision_effect` 仍必须恒为 `none`，不得改变 `plan/verdict/status/RiskGate/notification`。
- `pre_final_decision_input` 已经在 `decision.final` 前生成并持久化，`decision_effect=none`，不包含 `legacy_decision_ref`，也不进入 legacy frozen payload。
- `pre_final_input.py` 已作为 pre-final 结构化输入构造入口：runner 不再内联 worker contribution 选择、LeadPlan 提取和失败归一化。`pre_final_orchestration.py` 已作为 final 前受控编排入口：runner 不再直接调用 `shadow_orchestration.py`、`orchestration_inputs.py` 或 `pre_final_input.py` 的内部细节。
- `research_orchestration.py` 已作为研究降级编排入口：runner 不再直接管理 fallback 判断、research plan、并发 search、search evidence 合成和 leader review。
- `market_context_step.py` 已作为 market/skill 上下文入口：runner 不再直接调用 market provider 的 `fetch_snapshot` 或 `SkillRuntime.load_context`。
- legacy `FinalDecisionAgent` 当前仍消费 legacy prompt，但 prompt 侧已通过 `final_prompt.py` 使用 research/snapshot 脱敏视图：raw search snippet 不进入 final prompt，只保留 title/url/source 和 snippet_ref；完整 snippet 只留在审计 payload。
- `legacy_final_input_step.py` 已作为 legacy final input 构造入口：runner 不再直接构造 final prompt 或调用 `freeze_decision_prompt_packet`，但最终模型输入仍是 legacy prompt，不是 `DecisionInput`。
- worker input view 已做 deep-copy 隔离与 safe/redacted 脱敏：误写嵌套 `snapshot/research/facts_gate/evidence_packets` 不得污染原始 snapshot、后续 `risk.check` 或通知；raw search snippet 不进入 shadow worker 输入，只保留 `snippet_ref` 或 redacted ref。
- `ShadowSwarmRunner` 当前仍运行本地审计 worker，不是 LLM Agent，也不是实时工具 Agent。
- `PlanSemanticGate` 当前模块名是 `plan_semantic_candidate.py`，只做审计候选：多头 stop 必须低于 entry、target 必须高于 entry、target_2 顺序必须合理；空字段不崩溃，非开仓动作不误伤。
- `PlanSemanticGate` 对 opening/trigger/flip 还会检查 entry、stop、target_1、invalidation 是否存在；空字段会阻断候选 readiness。
- `final_decision_switch_readiness` 已把 `plan_semantic_candidate` 与 `shadow_swarm_audit.harness_validation` 纳入切换阻断条件。语义候选失败或 shadow harness 失败时，不允许切换到 `decision_input`。
- `decision_control_step.py` 已经接入主链路：在 `parser.strict_json` 后、legacy `risk.check` 前生成 candidate audit、运行 `production_control_gate`，再与 legacy RiskGate 合并 verdict。默认 fixture 因执行事实来源不是 `exchange_native`，`trigger long` 会被 `production_control.candidate.action_not_allowed` 阻断。
- `legacy_decision_workflow.py` 已作为旧生产链路步骤顺序入口：market/skill、research、legacy final input、pre-final orchestration、final decision、parser、production control 和 risk check 的串联已从 `runner.py` 移出；`runner.py` 仍是 legacy shell，不是生产级 Agent Swarm 入口。
- `plan_parse_step.py` 已作为计划解析入口：runner 不再直接导入或调用 `parse_decision_plan`。
- `run_persistence_step.py` 已作为运行持久化入口：runner 不再直接调用 `build_plan_payload`、`append_plan_run`、`finish_trace` 或 `append_notification`；成功/失败路径的 payload、trace 和通知审计都由该 step 统一处理；该 step 现在会读取 `run_context_summary.side_effect_policy`，当 production journal 或 notification intent 被禁止时硬跳过生产写入/通知；当 side-effect policy 缺失时也默认跳过生产写入/通知，即使有人直接调用 `PlanRunner.run_once(..., run_context=eval_context)` 或无 context 旧入口，也不会写 `plan_runs` 或 `notifications`。
- 无 `DecisionRunContext` 或 `run_context_summary` 的 `PlanRunner.run_once()` 直调会在 trace metadata 中标记 `legacy_direct_invocation`，并因缺少 side-effect policy 默认跳过生产 `plan_runs` 和 `notifications`。生产手动/定时入口必须继续走 `RunExecutor`。
- `plan_payload.py` 已新增 `audit_only` 命名空间，集中声明 evidence、facts gate、worker contribution、shadow swarm、pre-final input 和 candidate audit 均为 `decision_effect=none`、`production_final_input=false`、`notification_input=false`。旧顶层字段暂时保留作为兼容镜像，但 `EvalCaseBuilder` 会优先读取 `audit_only`，避免把生产 journal 顶层字段误当作生产事实来源。
- `EvalCaseBuilder`、`ReplayRunner`、`RuleJudge` 和 `EvalRunner.release_gate` 已能读取并评分候选审计摘要，Eval sidecar 会记录 `candidate_replay` 覆盖情况，release gate 当前已输出受控切换前的硬门禁评审对象，但仍不是生产切换开关；`EvalStore` 已有 `eval_candidate_artifacts` sidecar，`upsert_cases()` 会同步保存 candidate artifact snapshot，且要求 snapshot 顶层和子 artifact 都显式 `decision_effect=none`；`ReplayRunner` 会从 eval store 读回 case 与 candidate artifact sidecar 并输出 `artifact_snapshot_consistency`，缺失、不一致、字段缺失或格式错误都会进入 release gate 阻断；`promotion_artifacts.py` 已定义人工审批、回滚方案、影响范围、shadow/candidate 对照报告和人工发布决策的只读 artifact schema；`EvalStore` 已有 promotion artifact sidecar 读写；`promotion_approved` 固定为 `false`，缺少任一必需 artifact 时不得进入发布评审，即使四类 artifact 和 `manual_release_decision` 都齐也不得自动发布候选。

下一批必须优先补的不是更多 payload 字段，而是生产级编排边界：

- `DecisionRunContext` 已具备最小 append-only artifact store：`append_evidence`、`append_contribution`、`set_lead_plan`、`set_decision_input`、`set_gate_result`；append 写入必须显式声明 `writer_role`，当前只允许 `workflow/tool/worker` 写 evidence 或 contribution store，`final/external/unknown` 会被拒绝；worker 写 `final_decision/risk_verdict/journal/notification` 会被拒绝，公开访问器只返回深拷贝，避免外部误改内部 artifact。
- `context_artifacts.py` 已把主链生成的 evidence、worker contribution、LeadPlan、pre-final input、candidate gate、replayable input candidate 和 production control gate 写回 `DecisionRunContext`，`RunExecutor` 返回 artifact summary，且 summary 已包含安全 refs/hash，便于后续评审确认编排产物没有只停留在 payload，也不会泄漏 raw payload/snippet。
- `workflow.persistence_payload` 已作为 plan payload 组装入口，runner 不再内联 analysis/redaction/evidence-to-claims/candidate audit 默认构造；根目录 `plan_payload.py` 只保留兼容 wrapper；`plan_parse_step.py` 和 `run_persistence_step.py` 已补齐 parser、journal、trace 与 notification 边界。
- 但 `DecisionRunContext` 仍未替代旧 `PlanRunner` 编排：当前只是承载主链 artifact；market-context、research、legacy-final-input、pre-final、decision-control、final-decision、parser、payload、persistence 和 legacy step sequence 已拆成可替换边界，shadow timeout/并发调度已收敛到 `ControlledAgentPoolRunner`，本地 worker 已通过 `WorkerImplementationRegistry` 显式注册，`shadow.worker_mode` 已能从主链传到 registry，`LlmToolShadowWorker` 也已提供真实 LLM/tool worker adapter 契约；当前已支持注入式 `llm_client_factory` 作为 shadow 实验入口，并支持显式注入 `FixtureShadowToolExecutor` 做离线 `web_search` 审计 fixture；工具结果只进入 `tool_audit_results`，不进入 FinalDecisionAgent、journal 或 notification。后续要把 artifact store readback 从 candidate input/replayable input 扩展到 lead synthesis、worker manifest 和 gate result，再接生产级 synthesis 与 DecisionInput 切换实验。
- `AgentRunRequest` / `AgentRunResult` 已有轻量契约模块 `agent_runtime.py`，能表达 worker input view、tool policy、timeout、status、failure_policy、trace ref 和 output hash，并复用 Harness preflight；`AgentRunResult` 会记录 `input_view_hash` 和 `agent_run_request_hash`，用于 replay manifest 证明 worker 当时看到的 safe/redacted 输入。
- `ShadowSwarmRunner` 已经能从 `SubTask` 生成 `AgentRunRequest`，并在 worker result 中导出 `AgentRunResult` 摘要。
- `AgentRunner` 已抽出最小单 worker 执行内核：负责调用 worker、把异常规范化为 failed contribution/result，并支持在 trace span 内保留异常状态；`ShadowSwarmRunner` 不再自己打开 worker span。
- `ControlledAgentPoolRunner` 已抽出受控并发调度边界：负责 preflight、max_parallel_workers、单 worker timeout、全局 deadline、取消慢 worker 和按 LeadPlan 任务顺序聚合结果；`ShadowSwarmRunner` 不再直接持有线程池、preflight 判断、timeout 或 deadline 细节。
- `ControlledAgentPoolRunner` 的 timeout 当前是审计结果边界：超时 worker 会返回 failed audit envelope，`error.cancellation_scope=audit_result_only`；Python 线程中已经开始的 LLM/tool 调用不能被该层保证强制中断。`LlmToolShadowWorker` 已把 `AgentRunRequest.timeout_seconds` 作为 per-request timeout 传给 LLM client 和 tool executor；OpenAI-compatible shadow client 会使用该 timeout 覆盖单次 HTTP 请求。后续接更多真实工具执行器时，仍必须逐个验证其客户端是否真正支持请求级 timeout 或取消，不能把当前 `future.cancel()` 误认为外部调用取消。
- `AgentRunner` 会校验 worker 返回的 `AgentContribution` 是否与 `AgentRunRequest` 的 `agent_name/input_ref/trace_ref` 一致；不一致会转成 failed contribution，防止 worker 误报或伪装其他 Agent。
- `DecisionRunContext.write_section` 和公开 setter 已收紧写权限：`set_lead_plan` 只接受 `lead`，`set_decision_input` 只接受 `decision_input_builder`，`set_gate_result` 只接受 `gate`；worker 不能写 LeadPlan、DecisionInput、任何 gate result 或 reserved section，只能通过 append evidence/contribution 记录自己的产物。
- `WorkerImplementationRegistry` 已作为 worker implementation 注册入口：当前默认注册 `local_audit` worker，`decision_effect=none`；`build_shadow_worker_registry(config)` 会读取 `shadow.worker_mode`，无配置时仍默认 `local_audit`，`llm_tool_shadow` 在缺少显式 client factory 时返回可审计失败；传入 `llm_client_factory` 时会为 4 个 shadow worker 注册 `LlmToolShadowWorker`，传入 `tool_executor` 时才允许 LLM shadow worker 执行已请求且已通过 harness 的工具。
- `LlmToolShadowWorker` 已作为真实 LLM/tool worker adapter 契约：它只能生成 `AgentContribution`，默认不进入 FinalDecisionAgent、不写 journal/notification；非法 JSON 会被 `AgentRunner` 包装为 failed contribution，非 Final agent 泄漏 `main_action` 等可执行字段会继续被 Harness 拦截；当前 client 必须显式注入，配置本身不会默认访问真实网络或 LLM；LLM 输出 `tool_requests` 时默认失败为 `tool execution is disabled`，只有显式注入 `tool_executor` 且 `SubTask.requested_tools` 允许时才执行，结果只进入 `tool_audit_results` 审计字段；`FixtureShadowToolExecutor` 当前只做离线 fixture，不接真实 web search。
- `shadow_orchestration.py` 已作为 shadow swarm 的单一入口：生产 runner 不再直接依赖 `LeadAgent`、`ShadowSwarmRunner` 或本地 worker builder。
- `LeadPlan` 已显式携带 `resource_limits`（max_parallel_workers、deadline_ms、max_tool_calls），来源于 `HarnessPolicy`；`ShadowSwarmRunner` 会按 `max_parallel_workers` 限制并发，并把 `deadline_ms` 传给 `ControlledAgentPoolRunner` 作为全局调度硬约束，而不是按任务数无限扩展或只展示 deadline。
- 默认本地 shadow worker 不请求工具；`HarnessPolicy.allowed_tools` 是能力上限，不会被自动当成 `requested_tools`。只有 `worker_mode=llm_tool_shadow` 时，`LeadAgent.plan_tasks` 才会把 allowed tool 转成 RootCauseAgent/MarketSentimentAgent 的显式 `requested_tools`，并继续受 preflight 校验。
- 下一步仍不是 FinalDecisionAgent 生产接管，而是进入生产级 synthesis / DecisionInput 切换实验的前置准备：先定义人工审批 artifact、回滚版本、影响范围和 shadow/candidate 对照报告；同时继续保持 shadow 对照和 `decision_effect=none`。
- `LeadAgent` 已从固定 `build_default_lead_plan` 的直接调用中抽出：`runner.py` 通过 shadow orchestration 入口使用 `LeadAgent.plan_tasks` 生成 shadow `LeadPlan`，非法 task 会被拒，required task 不得静默降级；shadow 失败兜底也通过 `LeadAgent.plan_tasks` + `LeadAgent.synthesize` 生成 `lead_plan` 与 `lead_synthesis`，不再手工构造 synthesis；`LeadAgent.synthesize` 已成为 `shadow_swarm_audit.lead_synthesis` 的单一生成入口，并被 pre-final/candidate DecisionInput 复用；但生产级 synthesis 还没有进入 FinalDecision 输入。
- `FinalDecisionAgent` 在 readiness、回放覆盖率和人工验收达标前继续锁定 `legacy_prompt`；任何 `decision_input` 切换只能作为受控实验入口，不得默认打开。

## 13. 2026-06-30 P0 执行记录：候选发布门禁与 readback 收紧

本轮只完成受控切换前的 P0 防错门禁，不代表生产链已经切换为受控 Agent Swarm。

当前事实必须继续按以下口径描述：

- 生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`。
- `FinalDecisionAgent` 仍消费 legacy prompt；`decision.final_input_mode=decision_input` 仍被 `config.py` 拒绝。`final_input.py` 只提供受控渲染能力，不提供生产配置开关。
- `ControlledSwarmAuditAdapter` 只是 audit-only 骨架；即使显式注入 `RunExecutor`，也只能返回 blocked/no-trade，不能写生产 journal、不能发通知、不能接管生产 final input。
- `shadow_swarm_audit`、`pre_final_decision_input`、`decision_input_candidate`、`replayable_input_candidate`、`gate_candidate`、`plan_semantic_candidate`、`final_decision_switch_readiness` 都必须保持 `decision_effect=none`。
- `production_control_gate` 可以读取候选审计结果做负向阻断，但这不是候选决策接管生产；它只能收紧，不得放宽 legacy RiskGate。

本轮已落地的 P0 约束：

- `ReplayRunner(candidate_decision)` 必须从 eval sidecar 读回 candidate artifacts，并输出 `metadata.source=eval.candidate_decision_replay`、`decision_effect=none`。
- `ReleaseGate` 不再信任任意 `candidate_replay` 摘要；只有 `status=completed`、`mode=candidate_decision`、metadata 明确为 no-side-effect candidate readback 的 replay output 才能作为发布评审证据。
- 当没有有效 candidate replay 时，release gate 只报告 candidate replay/readback 问题，不再派生误导性的 worker 覆盖或 switch readiness 二次原因。
- `EvalRunner` 仍保留 `frozen_observed` 给 judge 使用，但 promotion artifact 和 release gate 必须使用 `candidate_decision` replay outputs。
- `EvalStore.eval_candidate_artifacts.artifact_hash` 改为存储层对 artifact payload 重新计算的 hash；payload 内自报的 `artifact_hash` 仍保留为 candidate artifact 自身 hash，但不能作为 store readback hash。
- `ReplayRunner.artifact_snapshot_consistency` 会对比存储行 hash 与读回 JSON 重算 hash，能发现 sidecar JSON 被篡改。
- `context_artifact_consistency` 已扩展到 `lead_synthesis_artifact`、`gate_candidate`、`plan_semantic_candidate`、`final_decision_switch_readiness` 的 context ref/hash 对照；sidecar 有候选 artifact 但 context summary 缺 ref 时必须 hard fail。
- `DecisionRunContext.to_artifact_summary()` 对无 `input_ref/artifact_ref` 的 gate result 至少输出安全 `artifact_hash`，使 `production_control_gate` 的阻断也能被审计。
- `manual_release_decision` 必须绑定同一 `shadow_candidate_comparison` 中真实出现的 `decision_input_ref/hash`；格式正确但引用 stale candidate hash 时，只能停留在 `ready_for_manual_release_decision`，不能进入 `ready_for_config_change_review`。
- 即使 release gate hard gates 通过、四类 promotion artifacts 齐全、再提供合法 `manual_release_decision`，`promotion_approved` 和 `allowed_to_change_production_final_input` 仍必须保持 `false`，只能进入单独配置变更审查。

本轮新增/加固的测试约束包括：

- `tests/test_eval_context_artifact_readback.py`：覆盖 context 中 lead/gate/semantic/readiness artifact ref/hash 缺失或不一致。
- `tests/test_eval_release_gate.py`：覆盖 failed replay、非 candidate_decision replay、缺 no-side-effect metadata、stale manual release candidate hash、badcase severity 覆盖门槛。
- `tests/test_eval_promotion_artifact_store.py`：覆盖 candidate artifact store hash 必须由存储层重算。
- `tests/test_eval_replay_llmjudge.py`：覆盖 EvalRunner 使用 candidate_decision replay 作为 promotion/release gate 证据，同时保持 judge 侧无生产副作用。
- `tests/test_controlled_swarm_adapter.py`：覆盖 controlled adapter 即使被显式注入也仍是 blocked audit-only。
- `tests/test_context_artifacts.py`：覆盖 production control gate 也写入 context artifact summary 的安全 hash。

下一步不能继续堆 payload 字段，必须优先补生产级编排边界：

- Lead synthesis 仍需继续走 shadow/candidate 对照，但 required worker 失败/缺失、optional worker 失败、冲突保留、dropped contribution reason 已有基础单元测试与 replay readback；下一步重点是把最强反方链、数据质量 hard block 和执行风险 hard block 的验收样例补齐。
- Worker result manifest 已扩展到 required/failure_policy readback：不仅校验数量和 input hash，也会校验 required worker 失败是否被 Lead synthesis dropped_contributions 正确传播；下一步继续补 optional worker soft_downgrade 与多 worker 冲突样例。
- `DecisionInput` 仍只能做 shadow/candidate 实验；切换前必须有独立 release/config-change 入口，不能让 `switch_readiness.ready=true` 单独驱动生产配置。

## 14. 2026-06-30 P0 执行记录：Lead synthesis 与 worker manifest 合约收紧

本轮只收紧 shadow/candidate 的编排合约和 eval readback，不代表生产链已经切换为受控 Agent Swarm。

本轮已落地：

- `LeadAgent.synthesize` / `build_lead_synthesis_candidate` 不再完全信任 worker contribution 自报的 `required`；当 agent 在 LeadPlan required 列表内时，失败 contribution 会按 required worker 处理。
- `AgentRunResult` 和 `WorkerResult` 明确携带 `required`，使 required/optional 由运行请求和 LeadPlan 向下传播，而不是依赖 worker 自己声明。
- `replayable_input_candidate.worker_result_manifest` 记录 `required`，并继续记录 `input_hash`、`agent_run_request_hash`、`failure_policy_applied`、`agent_run_result` 和 tool audit refs。
- `ReplayRunner(candidate_decision)` 的 `worker_manifest_consistency` 增加 required/failure_policy readback：manifest 与 `agent_run_result` 的 required 或 failure policy 不一致会阻断。
- `ReplayRunner(candidate_decision)` 会检查 failed/skipped required worker 是否出现在 Lead synthesis 的 `dropped_contributions` 中，并校验 `failure_policy_applied` 与 `required=true` 是否被正确传播。
- `DecisionInput.validation` 和 `final_decision_switch_readiness` 会识别 dropped contribution 自身携带的 `required=true` 或 `failure_policy_applied=hard_block`；即使 `contribution_refs` 缺失，也不能把 required hard failure 误判为 optional。
- `ReleaseGate` 的 manifest consistency violation 安全白名单允许透传 `failure_policy_applied`，但仍过滤 raw payload/snippet。

新增/加固测试包括：

- `tests/test_lead_synthesis_candidate.py`：覆盖 required worker 即使 contribution 自报 optional，也必须按 LeadPlan required 处理。
- `tests/test_replayable_input_candidate.py`：覆盖 worker manifest 记录 required，并从 result envelope 优先读取 required。
- `tests/test_eval_context_artifact_readback.py`：覆盖 failed required worker 未传播到 Lead synthesis dropped_contributions 时，candidate replay 必须 hard fail。
- `tests/test_eval_release_gate.py`：覆盖 release gate 保留 `failure_policy_applied` 审计字段，同时继续过滤 raw 字段。
- `tests/test_decision_input_candidate.py` 和 `tests/test_switch_readiness.py`：覆盖 required hard failure 在 contribution refs 缺失时仍阻断，optional soft_downgrade 不误阻断。

下一步仍不是生产 FinalDecisionAgent 接管。下一步优先补：

- 最强反方链和冲突样例：确保 Lead synthesis 不会因为主方向明确而删除 bear/counter thesis。
- optional worker soft_downgrade 样例：optional 失败应可审计，但不能误触发 required hard block。
- 数据质量和执行风险 hard block 样例：DataQualityAgent / ExecutionRiskAgent 的 hard failure 必须稳定进入 DecisionInput validation、switch readiness 和 release gate。
- 独立 release/config-change 入口：即使所有 readiness 为 true，也不能由 `switch_readiness.ready=true` 自动打开 `decision.final_input_mode=decision_input`。

## 15. 2026-06-30 P0 执行记录：反方链、optional worker 与 hard block 样例收紧

本轮仍只收紧 shadow/candidate 合约和 eval readback，不代表生产 FinalDecisionAgent 已切换到 `DecisionInput`，也不代表生产链已经完成受控 Agent Swarm 接管。

本轮已落地：

- `LeadSynthesisCandidate` 新增 `counter_thesis_refs`、`strongest_counter_thesis_ref` 和 `conflict_refs`。`counter_thesis` / `conflicts` 旧字段继续保留兼容；新增 refs 用于追溯反方论点和冲突来自哪个 worker contribution、哪些 evidence refs，避免 Lead 在主方向明确时静默删除 bear/counter thesis。
- `LeadSynthesisArtifact` 同步输出 `counter_thesis_refs`、`strongest_counter_thesis_ref` 和 `conflict_refs`，并继续过滤 `raw_payload`、`raw_snippet`、`raw_prompt` 等字段，保证 sidecar/replay 能看到反方链来源但不复制 raw 内容。
- `ReplayRunner(candidate_decision)` 的 `worker_manifest_consistency` 新增稳定 `advisories` 字段。optional worker `soft_downgrade` 未被 Lead dropped 记录时只生成 advisory，不会把 optional failure 升级为 release hard fail；required worker failed/skipped 仍必须进入 `dropped_contributions`，否则 hard fail。
- `DecisionInput.validation`、`final_decision_switch_readiness`、`production_control_gate` 和 `release_gate` 增补 DataQualityAgent / ExecutionRiskAgent hard block 样例。required hard failure 必须稳定进入 candidate validation、switch readiness 阻断、可执行动作的 production control 阻断，以及 release gate 的 blocking reasons。
- `config.py` 的生产切换硬边界继续保持：即使 release gate 到达 `ready_for_config_change_review`，`decision.final_input_mode=decision_input` 仍被配置加载拒绝；环境变量也不能打开该模式；伪造 `manual_release_decision` 声称允许生产切换会被 release gate 拒绝。

本轮新增/加固测试包括：

- `tests/test_lead_synthesis_candidate.py`：覆盖结构化 counter refs、strongest counter thesis、conflict refs，以及 raw 字段不进入 public dict。
- `tests/test_lead_synthesis_artifact.py`：覆盖 lead synthesis sidecar 对 counter/strongest/conflict refs 的保留和 raw 字段过滤。
- `tests/test_eval_context_artifact_readback.py`：覆盖 optional worker soft_downgrade advisory 与 required worker missing drop hard fail 的区别。
- `tests/test_decision_input_candidate.py`、`tests/test_switch_readiness.py`、`tests/test_production_control_gate.py`：覆盖 DataQualityAgent / ExecutionRiskAgent hard block 在候选输入、切换准备度和生产控制门禁中的传播。
- `tests/test_eval_release_gate.py`：覆盖 required worker hard block 从 candidate replay blocking reasons 进入 release gate，并覆盖伪造 manual release decision 不得打开生产切换。
- `tests/test_config.py`、`tests/test_final_input_selector.py`：继续锁定生产 final input 只能是 `legacy_prompt`。

本轮通过的验证：

- `python -m pytest tests/test_lead_synthesis_candidate.py tests/test_lead_synthesis_artifact.py tests/test_decision_input_candidate.py tests/test_switch_readiness.py tests/test_production_control_gate.py tests/test_replayable_input_candidate.py -q`
- `python -m pytest tests/test_eval_context_artifact_readback.py tests/test_eval_release_gate.py tests/test_eval_replay_llmjudge.py tests/test_eval_promotion_review.py tests/test_config.py tests/test_final_input_selector.py -q`

本轮后下一步仍不是生产接管。下一步优先补：

- counter/conflict coverage readback 已在第 17 节收紧；后续继续保持 release gate 能明确报告 counter/conflict refs 是否缺失或被 sidecar/context 漏记，而不仅是 artifact hash 自洽。
- local shadow worker 样例：MarketSentimentAgent / ExecutionRiskAgent 应有稳定 fixture 产出 bearish counter claim 和 execution hard block 场景，避免只有手写测试能覆盖反方链。
- 真实 LLM/tool worker 的请求级 timeout 和取消边界：`LlmToolShadowWorker` 已把 worker request timeout 下沉到 LLM client 和 tool executor，OpenAI-compatible shadow client 已支持 per-request HTTP timeout；但 `ControlledAgentPoolRunner` timeout 仍只是 audit envelope 边界，不能误认为已经能强制中断所有外部 LLM/tool 调用。
- 生产级 `DecisionInput` 切换实验入口：必须继续保持 `decision_effect=none` 和独立人工配置变更审查，不得由 `switch_readiness.ready=true` 自动修改生产配置。

## 16. 2026-06-30 P0 执行记录：worker 反方与硬阻断 readback 收紧

本轮仍只收紧 shadow/candidate/eval 合约，不代表生产 FinalDecisionAgent 已切换到 `DecisionInput`，也不代表生产链已经完成受控 Agent Swarm 接管。

当前事实必须继续保持：

- 生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`。
- `FinalDecisionAgent` 仍消费 legacy prompt。
- `decision.final_input_mode=decision_input` 仍被配置加载拒绝；final input selector 只能在测试/受控调用中基于 readiness 和候选 validation 渲染结构化输入。
- `shadow_swarm_audit`、`pre_final_decision_input`、`decision_input_candidate`、`replayable_input_candidate`、`candidate_decision` replay 和 release gate 产物都必须保持 `decision_effect=none`。

本轮已落地：

- `MarketSentimentAgent` 本地 shadow worker 在发现 funding/leverage/crowded longs 等拥挤迹象时，会输出 `side=bearish` 的 counter claim，并携带 evidence ref 与显式 strength。`LeadSynthesisCandidate` 能从真实本地 worker contribution 中生成 `counter_thesis_refs` 与 `strongest_counter_thesis_ref`，不再只依赖手写 synthesis payload 测试。
- `ExecutionRiskAgent` 本地 shadow worker 在 facts gate 或 missing execution facts 表明可执行动作应阻断时，会输出 `constraints.hard_block=true`、`hard_block_reasons` 和 `execution_risk_hard_block` conflict。该字段表示 worker 成功运行后的审计结论，不等同于 worker 运行失败、超时或 dropped contribution。
- `DecisionInput` 的 `contribution_refs` 只保留安全 hard block 摘要，不复制完整 constraints 或 raw payload；`DecisionInput.validation` 会把 `worker_hard_block` 作为独立 hard fail violation。
- `final_decision_switch_readiness` 会把 worker hard block 转成 `worker_hard_block` 阻断原因；这仍只是切换准备度审计，不会驱动生产配置变更。
- `production_control_gate` 会在 legacy final 后、legacy RiskGate 前读取 worker hard block，对可执行动作生成 `production_control.worker_hard_block` 阻断；该门禁只能收紧 legacy RiskGate，不能放宽。
- `ReplayRunner(candidate_decision)` 会把 `worker_hard_blocks` 作为只读 readback 摘要输出，同时继续输出 `counter_conflict_coverage`；两者都不调用生产 runner、真实 LLM、真实 tool、journal 或 notification。
- `ReleaseGate` 新增独立 `worker_hard_blocks` hard gate。只要 candidate replay 读到 worker hard block，即使 switch readiness 漏掉对应 blocking reason，release gate 也必须以 `worker_hard_block` 阻断；输出会过滤 `raw_payload` 等 raw 字段。

本轮新增/加固测试包括：

- `tests/test_shadow_workers.py`：覆盖本地 `MarketSentimentAgent` 产出 bearish counter claim，并通过真实 worker contribution 进入 Lead synthesis strongest counter ref；覆盖 `ExecutionRiskAgent` 产出 hard block 审计约束。
- `tests/test_decision_input_candidate.py`：覆盖 worker hard block constraint 进入安全 contribution refs 与 validation hard fail。
- `tests/test_switch_readiness.py`：覆盖 worker hard block constraint 阻断 FinalDecisionAgent 输入切换准备度。
- `tests/test_production_control_gate.py`：覆盖 worker hard block constraint 对可执行动作生成生产控制阻断。
- `tests/test_eval_context_artifact_readback.py`：覆盖 candidate replay 读回 worker hard block 摘要并过滤 raw 字段。
- `tests/test_eval_release_gate.py`：覆盖 release gate 独立阻断 worker hard block，包括 switch readiness reason 缺失时的防漏场景。
- `tests/test_eval_replay_llmjudge.py`：同步 candidate replay 和 candidate_decision 的安全 readback 字段，保持无生产副作用。
- `tests/test_pre_final_orchestration.py`：覆盖从 `run_pre_final_orchestration()` 入口触发的本地 worker counter thesis 与 hard block 链路，证明它们能进入 pre-final DecisionInput 和 context artifact，而不是只在单 worker 单测中成立。
- `tests/test_workflow_run_executor.py`：新增完整 runner 入口级 fixture，从真实 `RunExecutor.submit()` 触发 legacy 主链，随后经 journal payload、EvalCaseBuilder、EvalStore sidecar、`ReplayRunner(candidate_decision)` 和 release gate 读回，证明 worker hard block、sidecar、context artifact 和 release gate 在完整主链上自洽，且 final input selection 仍是 `legacy_prompt`。
- `tests/test_agent_pool_runner.py`：覆盖 pool timeout 只是 audit envelope 边界；超时结果可以先返回，但已启动的慢外部调用仍可能继续执行，不能宣称已具备请求级强制取消能力。
- `tests/test_llm_tool_shadow_worker.py`、`tests/test_shadow_llm_client.py`、`tests/test_shadow_orchestration.py`：覆盖 `LlmToolShadowWorker` 从 `AgentRunRequest` / `SubTask` 下沉 per-request timeout 到 LLM client 和 tool executor，OpenAI-compatible shadow client 使用 per-call timeout，且 llm_tool_shadow 编排仍保持 `decision_effect=none`。

本轮同时修正了两个 readback 边界：

- `DecisionRunContext` 继续保留 final 前 `pre_final_decision_input` 的 `decision_input_ref`，并额外在 gate refs 中记录 post-final `decision_input_candidate` 的安全 ref/hash，避免 replay 把两种不同阶段的输入误判为 context 不一致。
- `EvalCaseBuilder` 对 `decision_input_candidate.contribution_refs` 只保留安全摘要，尤其保留 `hard_block` 与 `hard_block_reasons`，使 `ReplayRunner(candidate_decision)` 和 release gate 能读回 `ExecutionRiskAgent` 的 worker hard block，但不会复制完整 constraints 或 raw payload。

本轮后仍未完成生产接管。下一步优先项：

- 继续为未来接入的真实工具执行器逐个补请求级 timeout / cancellation fixture；当前 OpenAI-compatible shadow client 与工具 executor 协议已有 per-request timeout，下层新工具仍需各自证明可中断或可超时。
- 生产级 `DecisionInput` 切换实验必须继续设计成独立 no-side-effect 实验入口，不能由配置或 release gate 自动打开。

## 17. 2026-06-30 P0 执行记录：counter/conflict sidecar readback 收紧

本轮仍只收紧 shadow/candidate/eval 合约，不代表生产 FinalDecisionAgent 已切换到 `DecisionInput`，也不代表生产链已经完成受控 Agent Swarm 接管。

当前事实必须继续保持：

- 生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`。
- `FinalDecisionAgent` 仍消费 legacy prompt。
- `decision.final_input_mode=decision_input` 仍被配置加载拒绝；final input selector 已不再无条件拒绝，但必须满足 readiness 与候选 validation。
- `shadow_swarm_audit`、`pre_final_decision_input`、`decision_input_candidate`、`replayable_input_candidate`、`candidate_decision` replay、promotion artifact 和 release gate 产物都必须保持 `decision_effect=none`。

本轮已落地：

- `LeadSynthesisArtifact` 新增 `counter_thesis_count` 和 `conflict_count` 安全计数字段。计数来自结构化 `counter_thesis` / `conflicts`，缺少显式冲突列表时可由安全 refs 兜底，避免 sidecar 低估反方链或冲突覆盖。
- `EvalCaseBuilder` 在 candidate artifact sidecar 中保留 `lead_synthesis` 的安全 counter/conflict refs、strongest counter ref 和计数字段，同时用白名单过滤 raw 字段名和值，避免 `raw_payload`、`raw_snippet` 等进入 eval sidecar。
- `ReplayRunner(candidate_decision)` 的 `counter_conflict_coverage` 不再只看 `decision_input_candidate.lead_synthesis` 内部 payload；它同时读取 `eval_candidate_artifacts.lead_synthesis` sidecar 顶层审计字段，并能报告 `lead_synthesis_artifact_counter_thesis_refs_missing`、`lead_synthesis_artifact_strongest_counter_missing`、`lead_synthesis_artifact_conflict_refs_missing`。
- `ReleaseGate` 继续通过 `counter_conflict_coverage_failed` 汇总新增 readback violation，并使用 `_safe_violation` 白名单过滤输出，避免 raw payload/snippet 被带入 release summary。
- `build_shadow_candidate_comparison` 只在 candidate replay 真的产出 `decision_input_shadow_final` 安全摘要时才写入该字段；缺少 shadow final 摘要时不再输出 `decision_input_shadow_final: None`，减少 promotion artifact 噪音。

本轮新增/加固测试包括：

- `tests/test_lead_synthesis_artifact.py`：覆盖 `LeadSynthesisArtifact` 的 counter/conflict 计数与 raw 字段过滤。
- `tests/test_eval_replay_llmjudge.py`：覆盖 `EvalCaseBuilder` 从真实 plan payload 的 `lead_synthesis_artifact` 保留安全 counter/conflict refs，并过滤 raw 字段。
- `tests/test_eval_context_artifact_readback.py`：覆盖 candidate replay 能发现 lead synthesis 内部 refs 完整、但 sidecar 顶层 counter/conflict refs 被漏记的场景。
- `tests/test_eval_release_gate.py`：继续覆盖 `counter_conflict_coverage_failed` 进入 release gate hard gate，并保持输出字段脱敏。
- `tests/test_promotion_artifacts.py`：覆盖缺少 shadow final summary 时不输出空字段；存在 shadow final summary 时只保留安全摘要，不复制 raw。

本轮通过的验证：

- `python -m pytest tests/test_promotion_artifacts.py tests/test_decision_input_experiment.py tests/test_eval_replay_llmjudge.py tests/test_eval_release_gate.py tests/test_eval_context_artifact_readback.py tests/test_lead_synthesis_artifact.py -q`

本轮后仍未完成生产接管。下一步优先项：

- 继续为未来接入的真实工具执行器逐个补请求级 timeout / cancellation fixture；当前 OpenAI-compatible shadow client 与工具 executor 协议已有 per-request timeout，下层新工具仍需各自证明可中断或可超时。
- 生产级 `DecisionInput` 切换实验的配置变更审查申请已在第 18 节收紧；后续继续保持它只是 eval sidecar，不得由配置或 release gate 自动打开。
- 在保持 legacy 主链的前提下，继续补 full runner 级 fixture，覆盖更多 worker conflict、required failure 与 release gate readback 组合。

## 18. 2026-06-30 P0 执行记录：配置变更审查申请边界收紧

本轮仍只收紧 promotion/release/config-review 的 eval sidecar 合约，不代表生产 FinalDecisionAgent 已切换到 `DecisionInput`，也不代表生产链已经完成受控 Agent Swarm 接管。

当前事实必须继续保持：

- 生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`。
- `FinalDecisionAgent` 仍消费 legacy prompt。
- `decision.final_input_mode=decision_input` 仍被配置加载拒绝；final input selector 的 `DecisionInput` 路径只作为受控切换前置能力存在。
- `shadow_swarm_audit`、`pre_final_decision_input`、`decision_input_candidate`、`replayable_input_candidate`、`candidate_decision` replay、promotion artifact、release gate 和 config review request 产物都必须保持 `decision_effect=none`。

本轮已落地：

- 新增 `build_config_change_review_request`，用于生成 `config_change_review_request` artifact。它必须绑定 `manual_release_decision_ref`、baseline `legacy_prompt`、requested `decision_input`、candidate input ref/hash，并显式写入 `config_change_review_required=true` 与 `allowed_to_change_production_final_input=false`。
- `EvalStore` 已允许持久化 `config_change_review_request` 的 requester 后缀型 artifact_ref，同时继续校验 `eval_run_id`、`artifact_type`、`schema_version`、`decision_effect=none` 和 artifact_ref 形状；伪造生产副作用的 request 会被拒绝。
- `EvalStore` 对 `config_change_review_request` 增加类型特定校验：`allowed_to_change_production_final_input` 必须为 `false`，`config_change_review_required` 必须为 `true`，baseline/requested mode、`manual_release_decision_ref` 和 candidate input ref/hash 都必须存在且合法。
- `ReleaseGate` 在合法 `manual_release_decision` 之后可以识别合法 `config_change_review_request`，并把 `promotion_review.status` 从 `ready_for_config_change_review` 提升为 `config_change_review_requested`。该状态仍只表示人工配置审查请求已提交，不表示允许修改生产配置。
- `ReleaseGate` 验证 `manual_release_decision` 时不只检查它和 `shadow_candidate_comparison` 自洽，还必须要求 candidate input ref/hash 存在于当前传入的 `candidate_decision` replay outputs；这样旧 comparison、旧 release decision 和旧 config request 即使三者相互一致，也不能越过当前 replay readback。
- `ReleaseGate` 会拒绝 candidate hash 过期、未绑定合法 `manual_release_decision_ref` 或自称允许生产切换的 `config_change_review_request`；被拒时不会暴露 `config_change_review_request_ref`，且仍保持 `allowed_to_change_production_final_input=false`。
- `upsert_promotion_review_artifacts` 可以把该 request 作为 eval promotion artifact 持久化并重新计算 release gate；返回结果仍保持 `promotion_approved=false`，不会写生产 journal、通知或配置。
- `LlmToolShadowWorker` 的 tool loop 已从“每个工具拿完整 worker timeout”收紧为请求级 deadline：LLM call 后每个工具只拿剩余预算，预算耗尽时停止后续工具调用并返回审计型 worker error。该能力仍只在 shadow worker 层，不表示 `ControlledAgentPoolRunner` 能强制取消所有外部调用。

本轮新增/加固测试包括：

- `tests/test_promotion_artifacts.py`：覆盖 `config_change_review_request` 的 no-side-effect schema、缺 requester、错误 baseline/target mode 和缺 candidate hash。
- `tests/test_eval_promotion_artifact_store.py`：覆盖 eval sidecar 持久化 `config_change_review_request`，以及拒绝带生产副作用的 request。
- `tests/test_eval_release_gate.py`：覆盖合法 request 只能进入 `config_change_review_requested`，不能打开生产切换；覆盖 stale candidate hash、当前 replay ref/hash 不匹配与伪造生产切换 request 被拒绝。
- `tests/test_eval_promotion_review.py`：覆盖 promotion review workflow 持久化 request 后的 readback，仍保持 `promotion_approved=false` 与 `allowed_to_change_production_final_input=false`。
- `tests/test_llm_tool_shadow_worker.py`：覆盖多个 tool request 逐次使用剩余请求预算，以及 LLM call 后 deadline 已耗尽时不会继续调用 tool executor。

本轮通过的验证：

- `python -m pytest tests/test_promotion_artifacts.py tests/test_eval_promotion_artifact_store.py tests/test_eval_promotion_review.py tests/test_eval_release_gate.py tests/test_decision_input_experiment.py -q`
- `python -m pytest tests/test_llm_tool_shadow_worker.py tests/test_shadow_llm_client.py tests/test_shadow_tool_executor.py tests/test_shadow_orchestration.py tests/test_agent_pool_runner.py -q`

本轮后仍未完成生产接管。下一步优先项：

- 继续为未来接入的真实工具执行器逐个补请求级 timeout / cancellation fixture；当前 OpenAI-compatible shadow client、fixture tool executor 协议和 shadow worker tool loop 已有 per-request timeout/deadline，下层新真实工具仍需各自证明可中断或可超时。
- 在保持 legacy 主链的前提下，继续补 full runner 级 fixture，覆盖更多 worker conflict、required failure、counter/conflict sidecar 和 release gate readback 组合。
- 继续推进完整可回放输入 readback，但不得替换 legacy FrozenInput，也不得让 `DecisionInput` 成为生产 FinalDecisionAgent 输入。

## 19. 2026-06-30 P0 执行记录：full runner readback 与 LLM/tool worker 边界收紧

本轮仍只收紧 shadow/candidate/eval 合约和生产控制边界，不代表生产 FinalDecisionAgent 已切换到 `DecisionInput`，也不代表生产链已经完成受控 Agent Swarm 接管。

当前事实必须继续保持：

- 生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`。
- `FinalDecisionAgent` 仍消费 legacy prompt。
- `decision.final_input_mode=decision_input` 仍被配置加载拒绝；final input selector 的 `DecisionInput` 路径必须由显式 readiness/candidate validation 共同约束。
- `shadow_swarm_audit`、`pre_final_decision_input`、`decision_input_candidate`、`replayable_input_candidate`、`candidate_decision` replay、promotion artifact、release gate 和 config review request 产物都必须保持 `decision_effect=none`。

本轮已落地：

- 默认 full runner fixture 不再强行要求 counter thesis。默认 `research.enabled=false` 时，`MarketSentimentAgent` 没有 research 证据，允许 `counter_thesis_count=0`；该 fixture 只要求 conflict sidecar、worker hard block、context artifact、candidate replay 和 release gate readback 完整。
- 新增显式 research fixture 的 `RunExecutor` 入口级测试：启用离线 research fallback 并注入 funding/leverage/crowded longs 证据时，`MarketSentimentAgent` 必须产出 bearish counter thesis，且该 counter ref 必须进入 `lead_synthesis` sidecar、candidate replay 和 release gate readback；同时 search-derived evidence 仍不能替代 mark/index/order_book 执行事实，worker hard block 仍保持阻断。
- `ReplayRunner(candidate_decision)` 的 `counter_conflict_coverage` 摘要现在会把 `decision_input_candidate.lead_synthesis` 与 `eval_candidate_artifacts.lead_synthesis` 顶层 sidecar 计数合并展示，避免 sidecar 已读到 counter/conflict 但 coverage 摘要显示 0 的误导；violation 规则没有放松。
- `ReleaseGate` 对 `shadow_candidate_comparison` 不再只做 artifact 自洽校验；comparison 中的 available candidate input ref/hash 必须存在于当前传入的 `candidate_decision` replay outputs。旧 comparison 即使自身结构合法，也会在 required artifact 阶段被视为缺失，不能让 promotion material 看起来 complete。
- full runner readback 增加 context gate refs 与 eval candidate artifact sidecar 的绑定断言：`decision_input_candidate`、`lead_synthesis`、`gate_candidate`、`plan_semantic_candidate`、`final_decision_switch_readiness` 必须 hash 对齐；`replayable_input_candidate` 因 context 记录完整 payload hash、eval sidecar 记录安全摘要 hash，只断言 input ref/hash 和 `decision_effect` 对齐。
- `LlmToolShadowWorker` 不再允许 LLM 输出的 `constraints.decision_effect` 覆盖 `none`；Harness 也新增 contribution 级 `constraints.decision_effect == none` 校验。
- `LlmToolShadowWorker` 新增 `max_tool_calls` 预算并在执行任何 tool 前校验请求数量；shadow harness 当前给 LLM/tool worker 一个小的显式上限，只有显式注入 `tool_executor`、SubTask 已请求该工具且请求数量未超预算时才执行，工具结果仍只进入 `tool_audit_results`，不进入 FinalDecisionAgent、journal 或 notification。
- LLM/tool shadow worker 输出的 `constraints.hard_block=true` 仍保留在 `DecisionInput`、switch readiness 和 replay 的审计信号里，但 `production_control_gate` 不再把 `migration_stage=llm_tool_shadow_worker` 的 hard block 提升为生产 `RiskVerdict` 阻断。当前只有本地确定性 worker 的 hard block 可以通过 production control 收紧 legacy RiskGate。
- `ControlledAgentPoolRunner` 的全局 deadline 语义已收紧：聚合结果时先检查 `future.done()`，再判断剩余 deadline，避免全局 deadline 耗尽后把已完成 worker 误标为 timeout；该 timeout 仍只是 audit result boundary，不是外部线程或外部工具调用的强制取消能力。
- `ReleaseGate` 不再只依赖 replay metadata 的 `decision_effect=none`。`candidate_replay`、`candidate_decision` 和 `decision_input_shadow_final` 等 nested artifact 一旦带有非 `none` 的 `decision_effect`，会以 `candidate_replay_decision_effect_violation` 阻断，不能进入 release evidence。
- 新增 `agent_swarm/` 包并迁移受控 Agent 编排核心实现：`contracts`、`runtime`、`pool_runner`、`shadow_runner`、`registry`、`workers`、`llm_tool_worker`、`shadow_llm_client`、`tool_executor`。旧根目录同名模块只保留 re-export wrapper，项目内部导入已切到新包路径，避免后续继续在根目录堆 Agent 相关实现。
- 新增 `decision/` 包并迁移候选输入与候选门禁实现：`decision_input`、`candidate_audit`、`gate_candidate`、`plan_semantic_candidate`、`switch_readiness`、`production_control_gate`、`replayable_input`。生产内部调用已切到新包路径；旧根目录模块只保留 import 兼容 wrapper，`candidate_audit.py` 已从重复实现收敛为 re-export wrapper。
- `LegacyDecisionWorkflow` 的异常持久化中间态从松散 `dict[str, Any]` 改为 `LegacyDecisionWorkflowState` dataclass。runner 异常路径不再通过 magic key 读取 `workflow_state[...]`，而是通过 typed attribute 读取已完成的 snapshot、legacy prompt、pre-final audit、candidate audit 和 production control verdict；生产步骤顺序和持久化 payload 不变。
- `decision/` 包继续承接 final 输入与输出边界：`pre_final_input`、`final_input`、`final_prompt`、`final_decision_step`、`legacy_final_input_step`、`plan_parse_step` 已迁入新包；生产内部调用已切到 `decision.*`，旧根目录模块保留 re-export wrapper 或兼容门面。
- `workflow/` 包继续承接 legacy 生产步骤顺序和 workflow step 实现：`legacy_decision_workflow`、`market_context_step`、`research_orchestration`、`pre_final_orchestration`、`decision_control_step`、`run_persistence_step` 已迁入新包；`runner.py` 和 `workflow.controlled_adapter` 已切到 `workflow.*` canonical 路径；旧根目录同名模块只保留兼容 wrapper，`tests/test_workflow_package_structure.py` 覆盖 wrapper identity；`workflow.__init__` 改为 lazy export，避免包初始化触发 runner 级循环导入。
- `lead/` 包承接 LeadAgent 规划、Lead synthesis 候选聚合与 Lead synthesis artifact 实现：`lead.agent`、`lead.synthesis`、`lead.synthesis_artifact` 已成为 canonical 路径；旧根目录同名模块只保留兼容 wrapper；`shadow_orchestration.py` 和 `decision.candidate_audit` 已切到新包路径，避免根目录继续承载 Agent 编排业务逻辑。
- `artifacts/` 包承接结构化证据、贡献封装与审计输入构造实现：`artifacts.evidence`、`artifacts.contributions`、`artifacts.orchestration_inputs` 已成为 canonical 路径；旧根目录 `evidence.py`、`contributions.py`、`orchestration_inputs.py` 只保留兼容 wrapper；`workflow.pre_final_orchestration`、`workflow.persistence_payload`、`shadow_orchestration.py`、`harness.py` 和 `agent_swarm/*` 已切到新包路径，避免根目录继续承载 artifact 业务逻辑。
- `context/` 包承接 orchestration artifact 写回实现：`context.artifacts` 已成为 canonical 路径；旧根目录 `context_artifacts.py` 只保留兼容 wrapper；`workflow.pre_final_orchestration`、`workflow.legacy_decision_workflow` 和 `workflow.controlled_adapter` 已切到新包路径，避免根目录继续承载 context 写回逻辑。

本轮新增/加固测试包括：

- `tests/test_workflow_run_executor.py`：覆盖默认 full runner 的 conflict/readback 口径、显式 research fixture 的 counter thesis 入口级 readback，以及 context gate refs 与 eval sidecar artifact 绑定。
- `tests/test_eval_release_gate.py`：覆盖 stale `shadow_candidate_comparison` 在 required artifact 阶段即被视为缺失，旧 release/config request 不能越过当前 replay readback；同时覆盖 nested candidate replay artifact 的非 `none` `decision_effect` 被本地 release gate 阻断。
- `tests/test_agent_pool_runner.py`：覆盖全局 deadline 耗尽后已完成 worker 仍保留真实结果，不被误标为 timeout；同时继续覆盖 pool timeout 只是 audit envelope 边界。
- `tests/test_controlled_swarm_contracts.py`：覆盖新 `agent_swarm` 包路径可用、旧根目录 import wrapper 仍兼容、SubTask 生成的 worker request 继续保持 `decision_effect=none`。
- `tests/test_decision_package_structure.py`：覆盖新 `decision` 包路径可用、旧根目录 import wrapper 仍兼容、DecisionInput candidate 继续保持 `decision_effect=none`。
- `tests/test_runner_boundaries.py`：覆盖 runner 与 legacy workflow 使用 typed `LegacyDecisionWorkflowState`，不再用裸 dict magic keys 承接异常持久化中间态。
- `tests/test_workflow_package_structure.py`：覆盖 workflow 新包路径可用、旧根目录 wrapper 仍兼容、包级 lazy export 不破坏 `RunExecutor` 入口。
- `tests/test_lead_package_structure.py`：覆盖 lead 新包路径可用、旧根目录 wrapper 仍兼容、包级导出与子模块导出对象一致。
- `tests/test_artifacts_package_structure.py`：覆盖 artifacts 新包路径可用、旧根目录 wrapper 仍兼容、包级导出与子模块导出对象一致。
- `tests/test_context_artifacts.py`：覆盖 context artifact 写回行为不变，并断言旧根目录 wrapper 与 `context.artifacts` canonical 对象一致。
- `tests/test_final_input_selector.py`、`tests/test_final_decision_step.py`、`tests/test_final_prompt.py`、`tests/test_legacy_final_input_step.py`、`tests/test_plan_parse_step.py`、`tests/test_pre_final_input.py`：覆盖 final/pre-final/parse 迁移后旧路径兼容和生产 final input 仍锁定 legacy prompt。
- `tests/test_llm_tool_shadow_worker.py`：覆盖 `decision_effect` 不可被 LLM constraints 覆盖、tool request 数量预算、剩余 deadline 下沉和工具失败只进入 audit 结果。
- `tests/test_harness_validation.py`：覆盖 contribution constraints 中非 `none` 的 `decision_effect` 被 Harness 拦截。
- `tests/test_decision_input_candidate.py` 与 `tests/test_production_control_gate.py`：覆盖 LLM/tool worker hard block 保留为 audit/readiness 信号，但不进入生产 RiskVerdict；本地确定性 `ExecutionRiskAgent` hard block 仍可收紧生产控制。

本轮通过的验证：

- `python -m pytest tests/test_workflow_run_executor.py::test_run_executor_full_legacy_chain_feeds_candidate_replay_and_release_gate tests/test_workflow_run_executor.py::test_run_executor_research_fixture_feeds_counter_thesis_into_replay_and_release_gate -q`
- `python -m pytest tests/test_eval_release_gate.py::test_release_gate_rejects_shadow_candidate_comparison_when_current_replay_hash_differs tests/test_eval_release_gate.py::test_release_gate_rejects_release_and_config_request_when_current_replay_hash_differs -q`
- `python -m pytest tests/test_eval_release_gate.py::test_release_gate_rejects_candidate_replay_with_nested_decision_effect_violation tests/test_agent_pool_runner.py::test_controlled_agent_pool_runner_keeps_done_result_after_deadline_is_spent -q`
- `python -m pytest tests/test_llm_tool_shadow_worker.py tests/test_harness_validation.py tests/test_decision_input_candidate.py tests/test_production_control_gate.py -q`
- `python -m pytest tests/test_worker_implementation_registry.py tests/test_shadow_orchestration.py tests/test_shadow_tool_executor.py -q`
- `python -m pytest tests/test_controlled_swarm_contracts.py tests/test_agent_runtime.py tests/test_agent_pool_runner.py tests/test_shadow_swarm.py tests/test_shadow_orchestration.py tests/test_shadow_workers.py tests/test_llm_tool_shadow_worker.py tests/test_worker_implementation_registry.py tests/test_shadow_llm_client.py tests/test_shadow_tool_executor.py -q`
- `python -m pytest tests/test_decision_package_structure.py tests/test_decision_input_candidate.py tests/test_candidate_audit.py tests/test_decision_control_step.py tests/test_gate_candidate.py tests/test_plan_semantic_candidate.py tests/test_switch_readiness.py tests/test_production_control_gate.py tests/test_replayable_input_candidate.py tests/test_plan_payload.py tests/test_controlled_swarm_adapter.py -q`
- `python -m pytest tests/test_runner_boundaries.py tests/test_runner_cli.py tests/test_workflow_run_executor.py -q`
- `python -m pytest tests/test_final_input_selector.py tests/test_final_decision_step.py tests/test_final_prompt.py tests/test_legacy_final_input_step.py tests/test_plan_parse_step.py tests/test_pre_final_input.py tests/test_pre_final_orchestration.py -q`
- `python -m pytest tests/test_workflow_package_structure.py tests/test_market_context_step.py tests/test_research_orchestration.py tests/test_decision_control_step.py tests/test_run_persistence_step.py tests/test_pre_final_orchestration.py tests/test_runner_boundaries.py tests/test_runner_cli.py tests/test_workflow_run_executor.py -q`
- `python -m pytest tests/test_lead_package_structure.py tests/test_lead_agent.py tests/test_lead_synthesis_candidate.py tests/test_lead_synthesis_artifact.py tests/test_shadow_workers.py tests/test_candidate_audit.py tests/test_decision_input_candidate.py tests/test_shadow_orchestration.py -q`
- `python -m pytest tests/test_artifacts_package_structure.py tests/test_evidence_packets.py tests/test_agent_contributions.py tests/test_orchestration_inputs.py tests/test_harness_validation.py -q`
- `python -m pytest tests/test_agent_runtime.py tests/test_agent_pool_runner.py tests/test_shadow_swarm.py tests/test_shadow_workers.py tests/test_llm_tool_shadow_worker.py tests/test_worker_implementation_registry.py tests/test_shadow_orchestration.py -q`
- `python -m pytest tests/test_context_artifacts.py tests/test_run_context.py tests/test_pre_final_orchestration.py tests/test_controlled_swarm_adapter.py tests/test_workflow_package_structure.py tests/test_workflow_run_executor.py -q`
- `python -m pytest tests/test_runner_cli.py tests/test_workflow_run_executor.py tests/test_shadow_orchestration.py tests/test_controlled_swarm_adapter.py -q`
- `python -m pytest tests/test_eval_replay_llmjudge.py tests/test_eval_context_artifact_readback.py tests/test_eval_release_gate.py tests/test_eval_case_builder_candidate_audit.py -q`

本轮后仍未完成生产接管。下一步优先项：

- 在保持 legacy 主链的前提下，继续补 required worker failure、optional soft downgrade、多 worker conflict 的 full runner 级 fixture。
- 继续做不改变生产效果的目录分层重构：`research.py` 已拆到 `research_pipeline/`，`skill_runtime.py` 已拆到 `skills/runtime.py`；后续基础设施拆分仍必须每次只迁移一个业务包，保留 wrapper 和 import 兼容测试，避免生产 legacy path 与 audit-only swarm path 混在根目录平铺文件里。

## 20. 目录分层收敛记录

本轮只收敛代码结构和兼容边界，不代表生产决策链已经由受控 Agent Swarm 接管。以下事实必须继续保持：

- 生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`。
- `FinalDecisionAgent` 仍消费 legacy prompt。
- `decision.final_input_mode=decision_input` 仍必须被配置加载拒绝；selector 层允许的受控渲染不得被解释为生产开关已打开。
- `shadow_swarm_audit`、`pre_final_decision_input`、`decision_input_candidate`、`replayable_input_candidate`、eval/replay/promotion/config-review 相关产物仍必须保持 `decision_effect=none`。
- `production_control_gate` 只能收紧 legacy `RiskGate`，不能放宽它。

本轮已经完成的目录分层：

- `research_pipeline/` 继续拆分：`models.py` 承接研究数据结构，`protocols.py` 承接 planner/search/synthesizer 协议，`redaction.py` 承接 prompt 脱敏，`evidence.py` 承接缺失/陈旧行情判断与 search-derived evidence 合成，`executor.py` 承接并发 research query 执行，`factory.py` 承接 planner/search/synthesizer 构造函数。`core.py` 继续保留 planner、search adapter、leader synthesizer 和 LLM/HTML 解析主体类。
- 根目录 `research.py` 继续作为兼容 facade，包级 `research_pipeline` 导出从新模块聚合，旧路径和新路径对象保持同一性。
- 根目录 `pre_final_input.py` 已从重复实现收敛为 `decision.pre_final_input` 的兼容 wrapper，项目内部测试改为优先使用 canonical 路径。
- 新增 `tests/test_root_package_structure.py`：对已经完成迁移的根目录兼容 wrapper 做 AST 约束，只允许 import、`__all__` 和模块说明，禁止这些 wrapper 重新长出业务函数或类。

下一批目录分层优先级：

- `shadow_orchestration.py`：迁入 `agent_swarm/shadow_orchestration.py`，根目录保留 wrapper；`workflow.pre_final_orchestration` 后续应调用 canonical 路径。
- `harness.py`：迁入 `agent_swarm/harness.py` 或明确的 harness 子模块，根目录保留 wrapper；所有 `agent_swarm/*`、`lead/*`、`artifacts/*` 内部导入后续应切到 canonical 路径。
- `plan_parser.py`、`frozen_input.py`、`risk.py`：按 decision 归属继续迁移，但必须先补 wrapper identity 测试和生产 final input 锁定测试。
- `plan_payload.py`：真实实现已迁入 `workflow.persistence_payload`，根目录只保留兼容 wrapper；后续如继续拆分，只能在 `workflow/`、`decision/` 或 `artifacts/` 包内按职责拆，不得回到根目录。
- `skill_runtime.py`：真实实现已迁入 `skills/runtime.py`，根目录只保留兼容 wrapper；项目内部代码应使用 `skills.runtime` canonical 路径。

本轮新增/加固测试：

- `tests/test_research_pipeline_package_structure.py`：覆盖 `research_pipeline.evidence`、`research_pipeline.executor`、`research_pipeline.factory` 与包级/旧根路径导出的对象同一性。
- `tests/test_decision_package_structure.py`：覆盖 `pre_final_input` 旧路径与 `decision.pre_final_input` canonical 路径同一性。
- `tests/test_pre_final_input.py`：改为 patch canonical `decision.pre_final_input`，避免后续测试继续依赖旧 wrapper 内部实现。
- `tests/test_root_package_structure.py`：防止已迁移 wrapper 重新承载业务实现。

本轮通过的验证：

- `python -m pytest tests/test_research_pipeline_package_structure.py -q`
- `python -m pytest tests/test_research_fallback.py tests/test_research_orchestration.py tests/test_evidence_packets.py tests/test_final_prompt.py tests/test_legacy_final_input_step.py tests/test_pre_final_orchestration.py tests/test_orchestration_inputs.py -q`
- `python -m pytest tests/test_runner_cli.py tests/test_workflow_run_executor.py tests/test_shadow_orchestration.py tests/test_shadow_tool_executor.py tests/test_controlled_swarm_adapter.py -q`
- `python -m pytest tests/test_decision_package_structure.py tests/test_pre_final_input.py tests/test_pre_final_orchestration.py tests/test_final_input_selector.py tests/test_final_prompt.py -q`
- `python -m pytest tests/test_root_package_structure.py -q`

### 目录分层补充记录：agent 编排边界

本次补充继续只做目录分层，不改变生产决策语义：生产主链、legacy final prompt、`decision_effect=none` 约束和 `production_control_gate` 只收紧不放宽的边界均保持不变。

已完成：

- `harness.py` 的真实实现迁入 `agent_swarm/harness.py`，根目录 `harness.py` 只保留兼容 wrapper。
- `shadow_orchestration.py` 的真实实现迁入 `agent_swarm/shadow_orchestration.py`，根目录 `shadow_orchestration.py` 只保留兼容 wrapper。
- `agent_swarm/*`、`lead/*`、`artifacts/*`、`workflow.pre_final_orchestration` 的内部导入已切到 canonical `agent_swarm` 路径。
- `tests/test_root_package_structure.py` 已把 `harness.py` 和 `shadow_orchestration.py` 纳入根目录纯 wrapper 护栏。
- 普通测试导入已优先使用 canonical 路径，旧根路径只保留在兼容 identity 测试中。

仍未完成：

- `plan_parser.py`、`frozen_input.py`、`risk.py` 仍在根目录承载真实实现，后续按 decision 归属迁移。
- `plan_payload.py` 真实实现已迁入 `workflow.persistence_payload`，根目录只保留兼容 wrapper。
- `skill_runtime.py` 真实实现已迁入 `skills/runtime.py`，根目录只保留兼容 wrapper；legacy 生产链仍使用同一组对象，不改变技能加载和 final prompt 行为。

本次通过的验证：

- `python -m pytest tests/test_controlled_swarm_contracts.py tests/test_harness_validation.py tests/test_agent_runtime.py tests/test_agent_pool_runner.py tests/test_shadow_swarm.py tests/test_llm_tool_shadow_worker.py tests/test_lead_agent.py tests/test_root_package_structure.py -q`
- `python -m pytest tests/test_controlled_swarm_contracts.py tests/test_harness_validation.py tests/test_shadow_orchestration.py tests/test_shadow_orchestration_boundaries.py tests/test_pre_final_orchestration.py tests/test_runner_cli.py tests/test_workflow_run_executor.py tests/test_root_package_structure.py -q`

### 目录分层补充记录：decision 输入与风险边界

本次补充仍只做目录分层，不改变生产决策语义，也不放宽任何风控规则。

已完成：

- `plan_parser.py` 的真实实现迁入 `decision/plan_parser.py`，根目录 `plan_parser.py` 只保留兼容 wrapper。
- `frozen_input.py` 的真实实现迁入 `decision/frozen_input.py`，根目录 `frozen_input.py` 只保留兼容 wrapper。
- `risk.py` 的真实实现迁入 `decision/risk.py`，根目录 `risk.py` 只保留兼容 wrapper。
- 内部调用已切到 `decision.plan_parser`、`decision.frozen_input`、`decision.risk`，旧根路径只保留给外部兼容和 identity 测试。
- `tests/test_root_package_structure.py` 已把 `plan_parser.py`、`frozen_input.py`、`risk.py` 纳入根目录纯 wrapper 护栏。

边界说明：

- `decision.risk.check_plan` 的规则 ID、`RiskVerdict` 结构、`RuleHit` 结构和阻断/警告语义必须保持兼容。
- `decision.frozen_input.stable_hash` 与冻结输入 payload 语义必须保持兼容，仍用于 legacy prompt replay 和 eval replay。
- `decision.plan_parser.parse_decision_plan` 仍只接受严格 JSON，不接受 markdown fence 或额外文本。
- 这次迁移不代表 `DecisionInput` 已进入生产 final input；生产 final input 仍锁定 legacy prompt。

本次通过的验证：

- `python -m pytest tests/test_decision_package_structure.py tests/test_plan_parser_and_risk.py tests/test_plan_parse_step.py tests/test_legacy_final_input_step.py tests/test_final_input_selector.py tests/test_root_package_structure.py -q`
- `python -m pytest tests/test_decision_control_step.py tests/test_run_persistence_step.py tests/test_context_artifacts.py tests/test_run_context.py tests/test_runner_cli.py tests/test_workflow_run_executor.py tests/test_eval_promotion_artifact_store.py tests/test_eval_replay_llmjudge.py -q`

### Directory Layering Addendum: Workflow Persistence Payload

This addendum is directory layering only. It does not change production decision semantics and does not mean the production chain has been taken over by controlled Agent Swarm.

Completed:

- Real implementation of `plan_payload.py` moved to `workflow/persistence_payload.py`; root `plan_payload.py` is now only a compatibility wrapper.
- Internal production imports in `workflow.run_persistence_step` and `runner.py` now use `workflow.persistence_payload`.
- `tests/test_workflow_package_structure.py` covers identity between the legacy root import and the canonical workflow package import.
- `tests/test_root_package_structure.py` now includes `plan_payload.py` in the pure wrapper guard.

Boundaries:

- `workflow.persistence_payload.build_plan_payload` still only assembles audit/persistence payload. It does not mutate `RiskVerdict`, send notifications, or write journal rows.
- `audit_only`, candidate audit, pre-final input, replayable input, and release/promotion/config-review artifacts must keep `decision_effect=none`.
- Production final input remains locked to legacy prompt; `decision.final_input_mode=decision_input` remains disabled.

Verification:

- `python -m pytest tests/test_root_package_structure.py tests/test_workflow_package_structure.py tests/test_plan_payload.py -q`

### 完整可回放输入补充记录：生产链观察引用覆盖

本次补充只增强 candidate replay 和 release gate 的审计闭环，不改变生产决策语义，也不让 `DecisionInput` 进入生产 `FinalDecisionAgent`。

已完成：

- `replayable_input_candidate.coverage` 已记录并暴露生产链观察引用覆盖：`has_lead_synthesis_artifact`、`has_final_decision_output`、`has_final_input_selection`、`has_parsed_plan`、`has_production_control_gate`、`has_risk_gate_result`、`has_side_effect_policy`、`has_context_artifact_summary`、`has_version_lock`、`has_telemetry_refs`、`has_evidence_snapshot_refs`、`has_memory_snapshot_refs`、`has_span_tree_refs`，并记录 `span_tree_parent_complete` 与 `span_tree_missing_parent_count`。
- `ReplayRunner` 的 `candidate_replay` 和 `candidate_decision` 输出新增 `complete_replay_refs` 与 `complete_replay_missing_refs`，只输出布尔覆盖率和缺失引用名，不复制 raw decision、raw prompt、raw payload 或完整 worker 输出。
- `release_gate` 新增硬门禁 `complete_replay_input`。任一 candidate replay 缺少上述生产链观察引用时，阻断原因固定为 `complete_replay_input_incomplete`，并按 case 输出安全的 `missing_refs`。
- `release_gate` 会单独检查 span tree 的 `parent_span_id` 完整性；如果 span tree ref 存在但 parent 链缺失，阻断原因为 `span_tree_parent_incomplete`。
- `EvalCaseBuilder` 对 replayable observed-run refs 只保留存在的安全 ref/hash，缺失项不写入 `None` 占位，避免 sidecar 摘要膨胀和误读；同时保留上述 `has_*` coverage 位，避免真实 journal -> eval case 路径丢失完整回放覆盖信息。
- `LegacyDecisionWorkflow` 会在 candidate audit 的 run context summary 中生成 `version_lock`：包含 `config_hash`、`skill_hashes`、`prompt_hashes`、`model`、`rule_hashes` 和 `redaction_policy_hash`。这些字段只保存 hash/ref，不保存完整 config、完整 skill 文本、raw prompt、密钥或 raw completion。

边界：

- 这仍不是生产级完整 replay。当前补齐的是 final/control/risk/side-effect/context 观察引用、首批 version lock 覆盖、安全 telemetry refs 覆盖、不复制 raw evidence 的 evidence snapshot refs/hash、安全 memory snapshot refs/hash，以及不复制 span input/output summary 的 span tree refs/hash。
- `FrozenInput` 仍是 legacy prompt replay 资产；`replayable_input_candidate` 仍是 audit sidecar，不替换生产 `FrozenInput`。
- 缺完整可回放引用时，系统只能阻断 candidate promotion；不得因此修改生产 plan、risk verdict、journal 或 notification。

本次通过的验证：

- `python -m pytest tests/test_eval_context_artifact_readback.py::test_candidate_replay_reports_complete_replay_ref_coverage tests/test_eval_release_gate.py::test_release_gate_blocks_when_complete_replay_refs_are_missing tests/test_eval_case_builder_candidate_audit.py::test_candidate_audit_summary_preserves_safe_replayable_observed_run_refs -q`
- `python -m pytest tests/test_eval_replay_llmjudge.py tests/test_eval_case_builder_candidate_audit.py -q`
- `python -m pytest tests/test_eval_context_artifact_readback.py tests/test_eval_release_gate.py tests/test_eval_case_builder_candidate_audit.py tests/test_eval_replay_llmjudge.py -q`
- `python -m pytest tests/test_replayable_input_candidate.py tests/test_candidate_audit.py tests/test_decision_control_step.py tests/test_plan_payload.py tests/test_root_package_structure.py tests/test_workflow_package_structure.py -q`
- `python -m pytest tests/test_replayable_input_candidate.py tests/test_eval_context_artifact_readback.py tests/test_eval_release_gate.py tests/test_eval_case_builder_candidate_audit.py tests/test_decision_control_step.py tests/test_plan_payload.py tests/test_workflow_run_executor.py -q`

### 目录分层补充记录：根包白名单

本次补充把“根目录不再堆业务实现”从文档约定提升为结构测试约束。

已完成：

- `tests/test_root_package_structure.py` 新增根包 `.py` 显式分类测试：根包文件必须属于纯兼容 wrapper 或少量允许保留真实实现的入口/基础设施模块。
- 已迁移的 Agent Swarm、Decision、Workflow、Lead、Artifacts、Context 相关根文件必须继续保持纯 wrapper，只允许 import、`__all__` 和模块说明。
- 当前允许保留真实实现的根包模块仅限稳定入口或基础设施，例如 `cli.py`、`config.py`、`domain.py`。已迁移的 `journal.py`、`runner.py`、`market_data.py`、`notifier.py`、`observability.py`、`scheduler.py`、`skill_runtime.py` 只允许保留纯 wrapper；新增业务模块不得平铺到 `src/crypto_manual_alert/*.py`。

后续迁移原则：

- Agent 编排实现继续进入 `agent_swarm/`，不得回流根包。
- 生产 workflow 步骤进入 `workflow/`，decision 输入、解析、风控和 final 输入进入 `decision/`，证据和贡献进入 `artifacts/`，Lead 规划与汇总进入 `lead/`。
- `skill_runtime.py` 已迁入 `skills/` 包；当前 canonical 实现是 `skills/context_loader.py` 和 `skills/prompt_context.py`，`skills/runtime.py` 只保留兼容导出；后续 skill 相关扩展必须继续进入 `skills/` 或更细的 skill 子模块，不得回流根包。
- `runner.py` 可继续作为 legacy 外壳，但不得继续堆积 market fetch、skill load、Evidence/Facts、DecisionInput、Lead synthesis、ReplayableInput、gate readiness、risk merge、legacy prompt freeze、parser、payload、journal/notification 或 context 写入细节。

本次通过的验证：

- `python -m pytest tests/test_root_package_structure.py -q`

### 目录分层补充记录：Skill Runtime 收敛

本次补充仍只做目录分层，不改变生产决策语义，也不放宽任何风控规则。生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`，最终模型输入仍锁定 legacy prompt。

已完成：

- `skill_runtime.py` 的真实实现先迁入 `skills/runtime.py`，随后进一步拆到 `skills/context_loader.py`、`skills/prompt_context.py` 和 `decision/final_engine.py`。
- 根目录 `skill_runtime.py` 已删除；`skills/runtime.py` 只保留兼容导出，旧 import 路径导出的 `SkillRuntime`、`DecisionEngine`、`OpenAICompatibleDecisionEngine` 等对象与当前 canonical 模块保持同一性。
- `workflow.legacy_plan_runner` 已从 `decision.final_engine` 构造 final decision engine；`workflow.market_context_step`、`workflow.legacy_decision_workflow`、`decision.legacy_final_input_step` 已切到 `skills.context_loader`。
- `tests/structure/test_root_package_structure.py` 约束根包不得重新出现业务 `.py`；`tests/structure/test_skill_runtime_boundaries.py` 约束 `skills/runtime.py` 只能做兼容导出，内部生产代码不得继续依赖该兼容层。
- `tests/skills/test_runtime_contract.py` 保留旧兼容路径与 canonical 路径对象同一性测试，继续覆盖 skill context 加载、压缩 prompt context、缺失 reference/script 和 skill 名称校验。

后续原则：

- 后续 skill 设计、tool 化 skill、实时检索 skill、根因链 skill、市场情绪 skill 等实现必须进入 `skills/` 或更细的业务子模块，不能再平铺到根目录或塞回 `skills/runtime.py`。
- 兼容导出只承担迁移期兼容，不得写业务逻辑；项目内部新代码必须使用 canonical 包路径。

本次通过的验证：

- `python -m pytest tests/test_root_package_structure.py tests/test_skill_runtime_contract.py tests/test_openai_compatible.py tests/test_workflow_package_structure.py tests/test_decision_package_structure.py tests/test_final_input_selector.py tests/test_config.py -q`
- `python -m pytest tests/test_market_context_step.py tests/test_legacy_final_input_step.py tests/test_final_prompt.py tests/test_workflow_run_executor.py -q`
- `rg -n "\bv1\b|\bv2\b" README.md docs/deployment.md docs/formal/30-受控AgentSwarm-MVP实施契约.md`

### 目录分层补充记录：LLM Telemetry 收敛

本次补充仍只做目录分层，不改变 LLM 调用语义、成本统计语义、生产决策语义或任何风控规则。

已完成：

- `llm_telemetry.py` 的真实实现迁入 `telemetry/llm.py`，新增 `telemetry/` 包作为 LLM telemetry payload 解析的 canonical 路径。
- 根目录 `llm_telemetry.py` 只保留兼容 wrapper，旧路径导出的 `LlmTelemetry`、`extract_chat_completion_telemetry`、`extract_responses_telemetry` 与 `telemetry.llm` 保持同一性。
- `skills.runtime`、`research_pipeline.core`、`eval.judges.llm` 已切到 `telemetry.llm` canonical 路径。
- `telemetry/__init__.py` 使用 lazy export，避免包级 import 提前加载 LLM telemetry 实现。
- `tests/test_root_package_structure.py` 已把 `llm_telemetry.py` 纳入纯 wrapper 护栏，`tests/test_telemetry_package_structure.py` 覆盖旧路径兼容和 telemetry 包 lazy import。

后续原则：

- 观测、token、cost、latency、span tree 等通用 telemetry 逻辑后续进入 `telemetry/` 或更细的观测子模块，不得继续平铺根目录。
- 根目录 `observability.py` 仍是基础设施实现，后续如拆分必须单独做兼容 wrapper、结构测试和 trace/journal 回归。

本次通过的验证：

- `python -m pytest tests/test_telemetry_package_structure.py tests/test_root_package_structure.py tests/test_openai_compatible.py -q`
- `python -m pytest tests/test_research_fallback.py tests/test_eval_replay_llmjudge.py -q`

### 目录分层补充记录：Notification 收敛

本次补充仍只做目录分层，不改变 Bark 通知语义、生产 journal 写入语义、side-effect policy 或任何风控规则。生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`。

已完成：

- `notifier.py` 的真实实现迁入 `notification/sinks.py`，新增 `notification/` 包作为通知 sink 的 canonical 路径。
- 根目录 `notifier.py` 只保留兼容 wrapper，旧路径导出的 `NotificationSink`、`NoopNotificationSink`、`BarkNotificationSink`、`redact` 与 `notification.sinks` 保持同一性。
- `runner.py`、`cli.py`、`workflow.run_persistence_step` 已切到 `notification.sinks` canonical 路径。
- `notification/__init__.py` 使用 lazy export，避免包级 import 提前加载通知实现。
- `tests/test_root_package_structure.py` 已把 `notifier.py` 纳入纯 wrapper 护栏，并新增内部源码不得继续依赖根目录 `notifier.py` 的结构约束。
- `tests/test_notification_package_structure.py` 覆盖旧路径兼容和 notification 包导出。

后续原则：

- 后续 Bark、飞书、邮件或其他通知 sink 必须进入 `notification/` 或更细的通知子模块，不能再平铺到根目录。
- 根目录 `notifier.py` 只承担迁移期兼容，不得写通知业务逻辑；项目内部新代码必须使用 canonical 包路径。

本次通过的验证：

- `python -m pytest tests/test_root_package_structure.py tests/test_notification_package_structure.py tests/test_notifier.py -q`

### 目录分层补充记录：Market Provider 收敛

本次补充仍只做目录分层，不改变 OKX 公共行情请求语义、fixture 行情语义、market/skill 上下文加载语义、生产决策语义或任何风控规则。生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`。

已完成：

- `market_data.py` 的真实实现迁入 `market/providers.py`，新增 `market/` 包作为行情 provider 的 canonical 路径。
- 根目录 `market_data.py` 只保留兼容 wrapper，旧路径导出的 `MarketDataProvider`、`FixtureMarketDataProvider`、`OkxPublicMarketDataProvider` 与 `market.providers` 保持同一性。
- `runner.py` 与内部测试已切到 `market.providers` canonical 路径；旧根目录 import 只保留在兼容 identity 测试中。
- `market/__init__.py` 使用 lazy export，避免包级 import 提前加载 provider 实现。
- `tests/test_root_package_structure.py` 已把 `market_data.py` 纳入纯 wrapper 护栏，并新增内部源码不得继续依赖根目录 `market_data.py` 的结构约束。
- `tests/test_market_package_structure.py` 覆盖旧路径兼容、canonical 路径对象同一性和 market 包 lazy import。

后续原则：

- 后续交易所适配器、行情缓存、行情质量校验、实时行情 fallback 等实现必须进入 `market/` 或更细的市场数据子模块，不能再平铺到根目录。
- 根目录 `market_data.py` 只承担迁移期兼容，不得写行情业务逻辑；项目内部新代码必须使用 canonical 包路径。

本次通过的验证：

- `python -m pytest tests/test_root_package_structure.py tests/test_market_package_structure.py -q`
- `python -m pytest tests/test_plan_parser_and_risk.py tests/test_skill_runtime_contract.py tests/test_runner_cli.py tests/test_workflow_run_executor.py -q`

### 目录分层补充记录：Observability 收敛

本次补充仍只做目录分层，不改变 trace、span、LLM interaction 记录语义，不改变 payload 脱敏和截断语义，不改变生产决策语义或任何风控规则。

已完成：

- `observability.py` 的真实实现迁入 `telemetry/observability.py`，`telemetry/` 包同时承载 LLM telemetry payload 解析与 trace/span 记录边界。
- 根目录 `observability.py` 只保留兼容 wrapper，旧路径导出的 `ObservabilityRecorder`、`SpanHandle`、`use_observability`、`record_llm_interaction` 与 `telemetry.observability` 保持同一性。
- 生产源码已切到 `telemetry.observability` canonical 路径；普通测试也优先使用 canonical 路径，旧根目录 import 只保留在兼容 identity 测试中。
- `telemetry/__init__.py` 继续使用 lazy export，避免包级 import 提前加载 LLM telemetry 或 observability 实现。
- `tests/test_root_package_structure.py` 已把 `observability.py` 纳入纯 wrapper 护栏，并新增内部源码不得继续依赖根目录 `observability.py` 的结构约束。

后续原则：

- 后续 trace、span tree、cost、latency、token 与 LLM 交互观测扩展必须进入 `telemetry/` 或更细的观测子模块，不能再平铺到根目录。
- 根目录 `observability.py` 只承担迁移期兼容，不得写观测业务逻辑；项目内部新代码必须使用 canonical 包路径。

本次通过的验证：

- `python -m pytest tests/test_root_package_structure.py tests/test_telemetry_package_structure.py -q`
- `python -m pytest tests/test_root_package_structure.py tests/test_telemetry_package_structure.py tests/test_journal_scheduler.py tests/test_openai_compatible.py tests/test_run_persistence_step.py tests/test_workflow_run_executor.py -q`

### 目录分层补充记录：Scheduler 收敛

本次补充仍只做目录分层，不改变 job lock 表语义、定时循环异常处理语义、CLI scheduler 行为、生产决策语义或任何风控规则。

已完成：

- `scheduler.py` 的真实实现迁入 `workflow/scheduler.py`，`workflow/` 包作为 CLI 定时生产入口调度逻辑的 canonical 路径。
- 根目录 `scheduler.py` 只保留兼容 wrapper，旧路径导出的 `JobLock` 与 `run_scheduler` 和 `workflow.scheduler` 保持同一性。
- `cli.py` 与普通 scheduler 测试已切到 `workflow.scheduler` canonical 路径；旧根目录 import 只保留在兼容 identity 测试中。
- `workflow/__init__.py` 继续使用 lazy export，并补充 `JobLock`、`run_scheduler` 和测试 monkeypatch 所需的子模块 lazy access。
- `tests/test_root_package_structure.py` 已把 `scheduler.py` 纳入纯 wrapper 护栏，并新增内部源码不得继续依赖根目录 `scheduler.py` 的结构约束。

后续原则：

- 后续调度、任务锁、运行入口协调等实现必须进入 `workflow/` 或更细的 workflow 子模块，不能再平铺到根目录。
- 根目录 `scheduler.py` 只承担迁移期兼容，不得写调度业务逻辑；项目内部新代码必须使用 canonical 包路径。

本次通过的验证：

- `python -m pytest tests/test_root_package_structure.py tests/test_workflow_package_structure.py tests/test_journal_scheduler.py tests/test_runner_cli.py -q`

### 目录分层补充记录：业务子包轻量入口

本次补充仍只做目录分层，不改变生产决策语义，不切换 FinalDecisionAgent 输入，也不放宽任何风控规则。

已完成：

- `agent_swarm/__init__.py` 改为 lazy export，保留 `from crypto_manual_alert.agent_swarm import ShadowSwarmRunner` 等兼容导出，但单纯导入包名不会提前加载 `contracts`、`pool_runner`、`runtime` 或 `shadow_runner`。
- `decision/__init__.py` 改为 lazy export，保留候选 DecisionInput 与 candidate audit 的包级导出，但单纯导入包名不会提前加载 candidate/final/frozen 等实现模块。
- `lead/__init__.py` 改为 lazy export，保留 `LeadAgent`、Lead synthesis 和 synthesis artifact 的包级导出，但单纯导入包名不会提前加载内部实现模块。
- `artifacts/__init__.py` 改为 lazy export，保留 evidence、facts gate、contribution 和 audit artifact 构造的包级导出，但单纯导入包名不会提前加载内部实现模块。
- 新增结构测试约束上述业务子包不得通过 `__init__` eager import 内部实现，避免后续把复杂编排重新堆回包入口。

后续原则：

- 根包只保留入口、基础设施、legacy 外壳或兼容 wrapper；Agent 编排继续进入 `agent_swarm/`，决策输入和门禁继续进入 `decision/`，Lead 规划与规整进入 `lead/`，证据和贡献进入 `artifacts/`。
- 业务子包可以提供少量高频对象的包级导出，但必须通过 lazy export 或等价轻量机制实现；不得为了导出方便在 `__init__.py` 中直接 import 大型 workflow、LLM client、runner、market provider 或 storage 依赖。
- 新增实现文件前必须先判断业务域和职责，避免继续产生单个大 `.py` 或根包散落 `.py`。

本次通过的验证：

- `python -m pytest tests/test_controlled_swarm_contracts.py::test_agent_swarm_package_import_does_not_eagerly_import_implementation_modules tests/test_decision_package_structure.py::test_decision_package_import_does_not_eagerly_import_implementation_modules tests/test_lead_package_structure.py::test_lead_package_import_does_not_eagerly_import_implementation_modules tests/test_artifacts_package_structure.py::test_artifacts_package_import_does_not_eagerly_import_implementation_modules -q`
- `python -m pytest tests/test_controlled_swarm_contracts.py tests/test_decision_package_structure.py tests/test_lead_package_structure.py tests/test_artifacts_package_structure.py -q`

### Full Runner 补充记录：Worker 失败、软降级与冲突读回

本次补充只增强完整入口级测试覆盖，不改变生产 final input，也不让 candidate/replay/eval artifact 产生生产决策效果。

已完成：

- 新增 full-runner required worker failure fixture：通过真实 `RunExecutor.submit()` 进入 legacy workflow，在 `RootCauseAgent` 抛错时验证 `shadow_swarm_audit.failed_workers`、`lead_synthesis.dropped_contributions`、`decision_input_candidate.validation`、`production_control_gate`、candidate replay 和 release gate 均能读回 required worker failure。
- 新增 full-runner optional worker soft downgrade fixture：通过测试替换 `LeadAgent` 将 `MarketSentimentAgent.required=False`，再让该 worker 失败。验证失败以 `soft_downgrade` 入审计、进入 dropped/advisory 读回，但不触发 `production_control.required_worker_missing_or_failed` 或 `production_control.shadow_swarm_harness_failed`。
- 新增 full-runner multi-worker conflict fixture：让两个 worker 返回同一个结构化 conflict，验证 `lead_synthesis.conflict_refs`、`lead_synthesis_artifact.conflict_refs`、candidate replay 的 `counter_conflict_coverage` 和 release gate 读回均保留冲突引用；当前 conflict 仍是审计信息，不新增生产阻断规则。

边界：

- required worker failure 可以通过 production control gate 收紧可执行动作空间；optional worker failure 只能作为 soft downgrade/advisory 保留，不得升级为 required-worker hard block。
- multi-worker conflict 当前只参与 replay/readback 和人工评审，不等价于自动交易阻断。若后续要把特定 conflict 提升为生产 gate，必须另开规则、测试和人工开关。
- 上述 replay/release gate 仍保持 `decision_effect=none`，只能阻断 candidate promotion 或给出人工评审依据，不能修改生产 plan、risk verdict、journal 或 notification。

本次通过的验证：

- `python -m pytest tests/test_workflow_run_executor.py::test_run_executor_blocks_executable_action_when_required_shadow_worker_fails tests/test_workflow_run_executor.py::test_run_executor_soft_downgrades_optional_shadow_worker_failure tests/test_workflow_run_executor.py::test_run_executor_records_multi_worker_conflict_refs_without_production_effect -q`
- `python -m pytest tests/test_root_package_structure.py tests/test_market_package_structure.py tests/test_telemetry_package_structure.py tests/test_workflow_package_structure.py tests/test_artifacts_package_structure.py tests/test_lead_package_structure.py tests/test_decision_package_structure.py tests/test_controlled_swarm_contracts.py tests/test_workflow_run_executor.py tests/test_eval_replay_llmjudge.py tests/test_eval_release_gate.py tests/test_eval_case_builder_candidate_audit.py -q`
- `python -m pytest tests/test_agent_runtime.py tests/test_agent_pool_runner.py tests/test_shadow_swarm.py tests/test_shadow_orchestration.py tests/test_shadow_orchestration_boundaries.py tests/test_pre_final_orchestration.py tests/test_decision_input_candidate.py tests/test_production_control_gate.py tests/test_replayable_input_candidate.py -q`

### 目录分层补充记录：Legacy PlanRunner 收敛

本次补充仍只做目录分层和公开审计命名收敛，不改变生产决策语义，不切换 FinalDecisionAgent 输入，也不放宽任何风控规则。

已完成：

- `runner.py` 的真实 `PlanRunner` 实现迁入 `workflow/legacy_plan_runner.py`，该模块作为 legacy 生产链路外壳的 canonical 路径。
- 根目录 `runner.py` 只保留兼容 wrapper，旧路径导出的 `PlanRunner`、`build_market_provider`、`build_decision_engine`、`build_notifier`、`journal_path` 和 `plan_to_json` 与 `workflow.legacy_plan_runner` 保持同一性。
- `workflow.legacy_adapter`、CLI 和 API 已切到 `workflow.legacy_plan_runner` canonical 路径；根目录 `runner.py` 不再承载 workflow、provider、notifier、observability 或 persistence 真实逻辑。
- `tests/test_root_package_structure.py` 已把 `runner.py` 纳入纯 wrapper 护栏，并新增通用结构约束：内部运行时代码不得继续 import 根目录兼容 wrapper，必须使用业务子包 canonical 路径。
- `workflow/__init__.py` 继续使用 lazy export，并补充 `legacy_adapter` 与 `legacy_plan_runner` 子模块 lazy access，避免包级入口重新变成大型 eager import。
- 完整 replay coverage 的最终决策输出公开引用名收敛为 `final_decision_output`，只暴露引用和 hash，不暴露原始决策文本，也避免 API 响应出现敏感字段名。

边界：

- 生产 payload 中的 legacy 原始决策保存语义不在本轮改变；本轮只调整 replay/candidate coverage 的公开引用命名和根包目录结构。
- 根目录兼容 wrapper 仍保留给历史 import 和外部调用；项目内部新代码必须继续使用 `workflow/`、`decision/`、`agent_swarm/`、`artifacts/`、`lead/` 等 canonical 路径。
- `config.py`、`domain.py`、`cli.py` 当前仍作为根包基础设施或入口保留。`journal.py` 已降级为兼容 wrapper，真实实现迁入 `storage/journal.py`；项目内部新代码必须使用 `crypto_manual_alert.storage.journal` canonical 路径。

本次之后的目录边界补充：

- `storage/` 是 SQLite journal、查询 repository 和后续持久化边界的 canonical 包；根目录 `journal.py` 不得重新承载表结构、查询、trace、badcase 或 LLM interaction 写入逻辑。
- `storage/__init__.py` 使用 lazy export，单独 `import crypto_manual_alert.storage` 不得提前加载 `storage.journal` 或 `storage.query_repository`。
- 内部运行时代码不得继续 import `crypto_manual_alert.journal`；旧路径只用于外部兼容和兼容性测试。

本次通过的验证：

- `python -m pytest tests/test_root_package_structure.py tests/test_runner_boundaries.py -q`
- `python -m pytest tests/test_legacy_adapter.py tests/test_workflow_package_structure.py tests/test_root_package_structure.py -q`
- `python -m pytest tests/test_runner_cli.py -q`
- `python -m pytest tests/test_api_runs.py tests/test_api_eval.py -q`
- `python -m pytest tests/test_eval_replay_llmjudge.py tests/test_eval_release_gate.py tests/test_eval_promotion_artifact_store.py tests/test_eval_promotion_review.py -q`
- `python -m pytest tests/test_decision_control_step.py tests/test_plan_payload.py tests/test_replayable_input_candidate.py tests/test_eval_case_builder_candidate_audit.py tests/test_eval_context_artifact_readback.py -q`

### 目录分层补充记录：根包业务 `.py` 清零

本次补充仍只做目录分层和 import 边界收敛，不改变生产决策语义，不切换 FinalDecisionAgent 输入，也不放宽任何风控规则。生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`，最终模型输入仍锁定 legacy prompt。

已完成：

- 根包业务 `.py` 已清零，`src/crypto_manual_alert/*.py` 当前只保留 `__init__.py`。
- 原根包基础设施入口已子包化：`cli.py -> cli/__init__.py`，`config.py -> config/__init__.py`，`domain.py -> domain/__init__.py`。旧导入语义仍保持为 `crypto_manual_alert.cli`、`crypto_manual_alert.config`、`crypto_manual_alert.domain`，但物理文件不再平铺在根包。
- `cli/main.py` 承载命令行参数装配和分发，`cli/__init__.py` 只保留公开导出；`cli/__main__.py` 已补齐，`python -m crypto_manual_alert.cli ...` 继续作为文档和本地调试入口。
- `config/` 已拆为 `models.py` 与 `loader.py`，分别承载配置 dataclass 和加载/环境变量覆盖/安全校验。
- `domain/` 已拆为 `market.py`、`decision.py`、`risk.py`、`notification.py`，分别承载行情快照、决策计划、风控结果和通知结果。
- Agent Swarm、Decision、Workflow、Lead、Artifacts、Skill runtime、Telemetry、Market、Notification、Research pipeline 和 Storage journal 的调用方与测试均改为业务子包 canonical 路径。
- `tests/structure/test_root_package_structure.py` 收紧为根包白名单测试，防止后续新增业务 `.py` 文件回到根包。
- `tests/structure/test_tests_layout.py` 补充项目根层脚本护栏，禁止仓库根目录重新散放 `.py`、`.ps1`、`.bat`、`.cmd` 或 `.sh` 脚本。
- 历史阶段记录中出现的“旧根目录 wrapper 保留”只表示当时迁移过程，不代表当前代码状态；后续评审以本节和 `test_root_package_structure.py` 为准。

边界：

- `cli/` 当前仍是 console script 入口包；后续如果拆 CLI 子命令，只能在 `cli/` 内继续拆分，不得把入口逻辑放回根包 `.py`。
- `config/__init__.py` 与 `domain/__init__.py` 只能作为轻量导出入口，不得重新承载 dataclass、loader、validator 或领域模型实现。
- 不得为了外部兼容重新增加根包业务 `.py` 或 wrapper；如确需兼容，应优先在现有子包入口、lazy export 或明确迁移适配层内解决，并补结构测试。

本次通过的验证：

- `python -m pytest tests/structure/test_root_package_structure.py tests/structure/test_tests_layout.py tests/structure/test_project_naming.py -q`
- `python -m pytest tests/config/test_config.py tests/cli/test_runner_cli.py -q`
- `python -m pytest tests/workflow/test_run_executor.py tests/workflow/test_legacy_adapter.py tests/decision/test_plan_parser_and_risk.py -q`
- `python -m crypto_manual_alert.cli show-config`

### 目录分层补充记录：测试目录与包入口护栏

本次补充仍只做目录结构、测试结构和包入口副作用收敛，不改变生产决策语义，不切换 FinalDecisionAgent 输入，也不放宽任何风控规则。生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`，最终模型输入仍锁定 legacy prompt。

已完成：

- `tests/` 根层不再直接放置 `.py` 文件；测试按业务域归档到 `tests/agent_swarm/`、`tests/api/`、`tests/artifacts/`、`tests/cli/`、`tests/config/`、`tests/context/`、`tests/decision/`、`tests/eval/`、`tests/lead/`、`tests/market/`、`tests/notification/`、`tests/research_pipeline/`、`tests/skills/`、`tests/storage/`、`tests/structure/`、`tests/telemetry/`、`tests/workflow/`。
- 本地自测脚本从 `tests/*.py` 迁到 `tools/local_stack/`：`run_local_checks.py`、`smoke_local_stack.py`、`start_local_stack.py`、`stop_local_stack.py`。`tests/README.md` 已同步新命令路径。
- 新增 `tests/structure/test_tests_layout.py`，约束 `tests/` 根层只能保留 `README.md`、`fixtures/` 和业务测试目录，禁止脚本或测试文件重新堆回根层。
- 业务包结构测试文件改为唯一命名，例如 `tests/workflow/test_workflow_package_structure.py`，避免 pytest 在默认 import 模式下因多个 `test_package_structure.py` 发生模块名冲突。
- `api/__init__.py`、`context/__init__.py`、`eval/judges/__init__.py` 改为 lazy export，避免单纯导入包名时提前构造 FastAPI app、Journal/Eval/Workflow 依赖、Decision frozen input 或 LLM judge 依赖。
- 新增 `tests/api/test_api_package_structure.py`、`tests/context/test_context_package_structure.py`、`tests/eval/test_eval_package_structure.py`，约束上述包入口不得重新变成大型 eager import。
- 旧的结构边界测试已改为 canonical 路径：`tests/structure/test_runner_boundaries.py` 检查 `workflow/legacy_plan_runner.py`、`workflow/legacy_decision_workflow.py` 和 `decision/decision_input.py`；`tests/structure/test_shadow_swarm_boundaries.py` 检查 `agent_swarm/shadow_runner.py`。

边界：

- 本轮没有拆分 `eval/case_builder.py`、`eval/replay.py`、`eval/release_gate.py`、`decision/replayable_input.py` 等大文件；这些是下一批重构候选，必须单独按行为测试和结构测试推进。
- 测试目录迁移只是物理归档和路径修正，不改变测试语义。后续新增测试必须进入对应业务目录；只有跨包结构约束测试进入 `tests/structure/`。
- 包级 lazy export 只允许作为轻量 namespace；不得在 `__init__.py` 里直接 import workflow、runner、LLM client、market provider、storage、journal 或 notification 等重依赖。

本次通过的验证：

- `python -m pytest tests/structure/test_tests_layout.py tests/local_stack/test_scripts.py -q`
- `python -m pytest tests/api/test_api_package_structure.py tests/context/test_context_package_structure.py tests/eval/test_eval_package_structure.py tests/artifacts/test_artifacts_package_structure.py tests/decision/test_decision_package_structure.py tests/lead/test_lead_package_structure.py tests/market/test_market_package_structure.py tests/notification/test_notification_package_structure.py tests/research_pipeline/test_research_pipeline_package_structure.py tests/storage/test_storage_package_structure.py tests/telemetry/test_telemetry_package_structure.py tests/workflow/test_workflow_package_structure.py -q`
- `python -m pytest --collect-only -q`
- `python -m pytest tests/local_stack/test_scripts.py tests/cli/test_runner_cli.py::test_runner_fixture_flow tests/cli/test_runner_cli.py::test_cli_run_once_uses_workflow_executor tests/cli/test_runner_cli.py::test_cli_scheduler_uses_workflow_executor tests/workflow/test_run_executor.py::test_run_executor_creates_context_before_calling_legacy_adapter tests/workflow/test_run_executor.py::test_run_executor_still_supports_existing_manual_run_contract -q`
- `python -m pytest tests/agent_swarm/test_controlled_contracts.py tests/agent_swarm/test_harness_validation.py tests/agent_swarm/test_pool_runner.py tests/agent_swarm/test_shadow_orchestration.py tests/agent_swarm/test_llm_tool_worker.py -q`
- `python -m pytest tests/eval/test_replay_llmjudge.py tests/eval/test_release_gate.py tests/eval/test_context_artifact_readback.py tests/decision/test_decision_input.py tests/decision/test_replayable_input.py -q`

### 目录分层补充记录：编排契约上移

本次补充只调整契约归属和依赖方向，不改变生产决策语义，不切换 FinalDecisionAgent 输入，不改变 shadow worker、harness、payload、release gate 或风控规则。生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`，最终模型输入仍锁定 legacy prompt。

已完成：

- 新增 `orchestration/` 中立包，承载跨 Lead 和 Agent Swarm 共享的契约。
- `LeadPlan`、`SubTask`、`WorkerAgent`、`WorkerResult`、`ShadowSwarmAudit` 已迁入 `orchestration/contracts.py`。
- `AgentRunRequest`、`AgentRunResult` 已迁入 `orchestration/runtime.py`；`agent_swarm/runtime.py` 只保留 `AgentRunner`、`RuntimeWorker` 和执行/失败归一化逻辑。
- `HarnessPolicy`、`HarnessValidationResult`、`load_harness_policy` 和 harness 校验函数已迁入 `orchestration/harness.py`；`agent_swarm/harness.py` 仅作为兼容导出。
- `lead/agent.py` 已改为只依赖 `orchestration.contracts` 与 `orchestration.harness`，不再导入 `agent_swarm.contracts`、`agent_swarm.runtime` 或 `agent_swarm.harness`。
- `agent_swarm/contracts.py`、`agent_swarm/harness.py` 继续作为旧路径兼容导出，但生产源码的新依赖方向以 `orchestration/` 为准。
- 新增 `tests/structure/test_orchestration_contract_boundaries.py`，约束 `lead/` 和 `orchestration/` 不得反向导入 `agent_swarm`。

边界：

- 本轮没有拆 `shadow_orchestration.py` 的职责；它仍同时负责审计输入兜底、LeadAgent、registry、runner 和失败 envelope。这是下一批重构候选。
- 本轮没有把 shadow worker 升级为生产决策 agent；所有 shadow/candidate 产物仍必须保持 `decision_effect=none`。
- 旧测试和外部调用仍可通过 `crypto_manual_alert.agent_swarm.contracts`、`crypto_manual_alert.agent_swarm.harness`、`crypto_manual_alert.agent_swarm.runtime` 读取兼容对象；项目内部新代码应优先使用 `orchestration/` 中立路径。

本次通过的验证：

- `python -m pytest tests/structure/test_orchestration_contract_boundaries.py tests/lead/test_agent.py tests/lead/test_lead_package_structure.py -q`
- `python -m pytest tests/agent_swarm/test_runtime.py tests/agent_swarm/test_harness_validation.py tests/agent_swarm/test_controlled_contracts.py tests/agent_swarm/test_shadow_swarm.py tests/agent_swarm/test_llm_tool_worker.py -q`
- `python -m pytest tests/agent_swarm/test_shadow_orchestration.py tests/agent_swarm/test_pool_runner.py tests/agent_swarm/test_registry.py -q`
- `python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_controlled_adapter.py -q`
- `python -m pytest tests/workflow/test_run_executor.py -q`

### 目录分层补充记录：Shadow Orchestration 职责拆分

本次补充只拆分 shadow audit 编排入口的文件职责，不改变 shadow worker 运行语义、不改变 harness 校验、不改变 payload 字段、不改变失败降级策略，也不让 shadow/candidate 产物产生生产决策效果。

已完成：

- `agent_swarm/shadow_orchestration.py` 收缩为 shadow audit 编排入口：负责捕获异常、调用 LeadAgent 规划、调用 worker registry、运行 ShadowSwarmRunner、挂接 Lead synthesis。
- 新增 `agent_swarm/shadow_inputs.py`：负责 audit payload 兜底构造、worker input view 组装和 raw snippet/claims/value 的 safe/redacted 视图生成。
- 新增 `agent_swarm/shadow_failure.py`：负责把 shadow 编排异常归一化为 `decision_effect=none` 的失败 envelope。
- `shadow_orchestration.py` 不再直接导入 `build_audit_artifacts`，也不再内联 `_safe_worker_payload` 或 `failed_shadow_swarm_audit` 的实现。
- `failed_shadow_swarm_audit` 仍通过 `agent_swarm.shadow_orchestration` 公开导入，兼容既有测试和旧调用点。
- `tests/structure/test_shadow_orchestration_boundaries.py` 新增边界约束，防止 shadow 编排入口重新堆回输入构造和失败 envelope 细节。

边界：

- `ShadowSwarmRunner`、`AgentRunner`、`ControlledAgentPoolRunner` 仍保持原职责，不在本轮拆分。
- `shadow_orchestration.py` 仍位于 `agent_swarm/` 内；后续如果继续推进真正生产级 orchestration，可以再评估是否把入口移到 `workflow/` 或 `orchestration/`，但不能提前改变生产链路。
- 本轮只降低文件职责复杂度；不代表生产链已切换为 agent swarm。

本次通过的验证：

- `python -m pytest tests/structure/test_shadow_orchestration_boundaries.py -q`
- `python -m pytest tests/agent_swarm/test_shadow_orchestration.py -q`
- `python -m pytest tests/cli/test_runner_cli.py::test_runner_records_shadow_swarm_failure_without_changing_verdict tests/workflow/test_pre_final_orchestration.py -q`
- `python -m pytest tests/agent_swarm/test_controlled_contracts.py tests/agent_swarm/test_pool_runner.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_llm_tool_worker.py tests/agent_swarm/test_shadow_swarm.py tests/agent_swarm/test_shadow_orchestration.py -q`
- `python -m pytest tests/structure/test_shadow_orchestration_boundaries.py tests/structure/test_orchestration_contract_boundaries.py -q`

### 目录分层补充记录：Replayable Input 职责拆分

本次补充只拆分 `decision/replayable_input.py` 的文件职责，不改变 `replayable_input_candidate` 的 public payload、hash 语义、coverage 字段、`decision_effect=none` 语义，也不切换 FinalDecisionAgent 输入。

已完成：

- `decision/replayable_input.py` 收敛为候选对象、构建入口、失败 envelope 和少量顶层 refs 组合逻辑。
- `decision/replay_observed_refs.py` 承载生产链观测产物的安全引用提取：final decision output、final input selection、parsed plan、gate refs、side-effect policy、context artifact summary、version lock、telemetry、evidence snapshot、memory snapshot 和 span tree refs。
- `decision/replay_worker_refs.py` 承载 shadow lead/worker 引用、worker result manifest、required 字段读取、tool audit refs 和 worker manifest 完整性检查。
- `decision/replay_sanitization.py` 承载 replay 侧稳定 hash、raw 字段剥离和 rule id 提取，避免脱敏/哈希规则继续散落在大文件中。
- 新增 `tests/structure/test_replayable_input_boundaries.py`，约束 replayable input 入口不得重新内联 observed refs、worker manifest 或 hash/sanitization 实现。

边界：

- `ReplayableInputCandidate`、`build_replayable_input_candidate` 和 `failed_replayable_input_candidate` 仍保留在 `decision/replayable_input.py`，保持既有 import 路径兼容。
- `replayable_input_candidate` 仍是 audit sidecar，不替换生产 `FrozenInput`，也不进入 production final input。
- `observed_run_refs` 只输出安全 refs/hash/count，不复制 raw prompt、raw completion、raw exchange payload、raw snippets 或 raw conversation。
- 本轮没有拆分 `eval/case_builder.py`、`eval/replay.py`、`eval/release_gate.py` 等 eval 大文件；它们仍是后续 checkpoint 候选。

本次通过的验证：

- `python -m pytest tests/structure/test_replayable_input_boundaries.py -q`
- `python -m pytest tests/decision/test_replayable_input.py tests/decision/test_decision_input.py tests/decision/test_switch_readiness.py -q`
- `python -m pytest tests/eval/test_replay_llmjudge.py tests/eval/test_release_gate.py tests/eval/test_context_artifact_readback.py -q`

### 目录分层补充记录：Shadow Audit 编排归属上移

本次补充只调整 shadow audit 的编排归属，不改变 shadow worker 运行语义、LeadPlan 内容、Lead synthesis 内容、harness 校验、失败 envelope、payload 字段、生产 final input 或任何风控规则。生产主链仍是 `RunExecutor -> LegacyPlanRunnerAdapter -> PlanRunner/LegacyDecisionWorkflow`，最终模型输入仍锁定 legacy prompt。

已完成：

- 新增 `orchestration/shadow_audit.py`，作为 shadow audit 的 canonical 编排入口，负责调用 `LeadAgent` 规划任务、构建 worker registry、运行 `ShadowSwarmRunner` 并挂接 Lead synthesis。
- 新增 `orchestration/shadow_failure.py`，承载 shadow audit 异常时的 `decision_effect=none` 失败 envelope 与 Lead synthesis 归一化。
- `agent_swarm/shadow_orchestration.py` 降级为兼容导出，只 re-export `run_shadow_swarm_audit` 和 `failed_shadow_swarm_audit`，不再拥有 worker registry、LeadAgent、runner 或 synthesis 实现。
- `agent_swarm/shadow_failure.py` 降级为兼容导出，不再直接导入或实例化 `LeadAgent`。
- `workflow/pre_final_orchestration.py` 已切到 `orchestration.shadow_audit.run_shadow_swarm_audit`，生产入口不再通过 `agent_swarm.shadow_orchestration` 兼容层。
- `tests/structure/test_shadow_orchestration_boundaries.py` 已约束：`agent_swarm/` 不得拥有 Lead planning/synthesis；旧 shadow orchestration wrapper 不得导入 worker registry 或内部实现；workflow 必须走 orchestration 层 canonical 路径。

边界：

- `agent_swarm/` 当前只作为 worker、runner、registry、tool/LLM worker 及旧路径兼容层；它不再作为 Lead 编排归属层。
- `orchestration/contracts.py`、`orchestration/runtime.py`、`orchestration/harness.py` 仍保持中立契约，不依赖 `agent_swarm/`；只有 `orchestration/shadow_audit.py` 作为上层编排入口依赖 worker registry/runner。
- 旧 import `crypto_manual_alert.agent_swarm.shadow_orchestration.run_shadow_swarm_audit` 仍可用，但项目内部新代码必须使用 `crypto_manual_alert.orchestration.shadow_audit`。
- 本轮仍不表示生产链已经由 Agent Swarm 接管；shadow/candidate 产物仍必须保持 `decision_effect=none`。

本次通过的验证：

- `python -m pytest tests/structure/test_shadow_orchestration_boundaries.py tests/structure/test_orchestration_contract_boundaries.py -q`
- `python -m pytest tests/agent_swarm/test_shadow_orchestration.py -q`
- `python -m pytest tests/workflow/test_pre_final_orchestration.py -q`
- `python -m pytest tests/cli/test_runner_cli.py::test_runner_shadow_swarm_uses_lead_agent_planner tests/workflow/test_run_executor.py::test_run_executor_soft_downgrades_optional_shadow_worker_failure -q`
- `python -m pytest tests/agent_swarm/test_controlled_contracts.py tests/agent_swarm/test_pool_runner.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_llm_tool_worker.py tests/agent_swarm/test_shadow_swarm.py tests/agent_swarm/test_shadow_orchestration.py -q`

### 目录分层补充记录：中立 Hash 与 Skill Runtime 职责拆分

本次补充只处理代码所有权和依赖方向，不改变 hash 算法、不改变 `FrozenInput` 语义、不改变 final decision LLM 请求格式、不改变生产 final input，也不放宽任何风控规则。

已完成：

- 新增 `artifacts/hashing.py`，承载跨 context、decision、eval 共享的稳定 hash 实现。
- `decision/frozen_input.py` 继续导出 `stable_hash`，但实现来自 `artifacts.hashing`，保持旧 replay/eval import 兼容。
- `context/run_context.py` 已改为依赖 `artifacts.hashing`，不再从 `decision.frozen_input` 取 hash。
- 新增 `tests/structure/test_context_boundaries.py`，约束 `context/` 生产代码不得导入 `decision/`。
- `skills/runtime.py` 已收缩为兼容导出，不再定义 `SkillRuntime`、`SkillContext`、`DecisionEngine` 或 OpenAI-compatible final engine。
- 新增 `skills/context_loader.py`，承载 `SkillRuntime`、`SkillInfo`、`SkillContext`、skill reference/script 加载、skill hash 和 legacy prompt packet 构建。
- 新增 `skills/prompt_context.py`，承载 skill 文档与 references 的 compact prompt context 构造。
- 新增 `decision/final_engine.py`，承载 `DecisionEngine`、`FixtureDecisionEngine`、禁用的 `CommandDecisionEngine` 和 `OpenAICompatibleDecisionEngine`。
- `workflow.legacy_plan_runner` 已改为从 `decision.final_engine` 构造 final decision engine；`workflow.market_context_step`、`workflow.legacy_decision_workflow`、`decision.legacy_final_input_step` 已改为从 `skills.context_loader` 读取 skill runtime 类型。
- 新增 `tests/structure/test_skill_runtime_boundaries.py`，约束内部生产代码不得继续依赖 `skills.runtime` 兼容层。

边界：

- `artifacts.hashing.stable_hash` 的 JSON dump 参数必须保持 `ensure_ascii=False`、`sort_keys=True`、`default=str`，否则会破坏历史 replay/eval hash。
- `decision.frozen_input.stable_hash` 是兼容 API，不能直接删除；但新代码应优先使用 `artifacts.hashing`。
- `skills.runtime` 是兼容 API，不能继续增加业务实现；新 skill 能力应进入 `skills/` 下职责明确的模块。
- `decision.final_engine` 仍是 legacy FinalDecisionAgent 的 engine 实现，不表示 `DecisionInput` 已切入生产 final input。

本次通过的验证：

- `python -m pytest tests/artifacts/test_hashing.py tests/structure/test_context_boundaries.py tests/context/test_context_package_structure.py -q`
- `python -m pytest tests/context/test_run_context.py tests/context/test_artifacts.py -q`
- `python -m pytest tests/decision/test_decision_package_structure.py tests/decision/test_replayable_input.py tests/decision/test_decision_input.py -q`
- `python -m pytest tests/structure/test_skill_runtime_boundaries.py tests/skills/test_runtime_contract.py tests/skills/test_openai_compatible.py -q`
- `python -m pytest tests/workflow/test_market_context_step.py tests/decision/test_legacy_final_input_step.py tests/workflow/test_controlled_adapter.py -q`
- `python -m pytest tests/workflow/test_run_executor.py::test_run_executor_soft_downgrades_optional_shadow_worker_failure tests/cli/test_runner_cli.py::test_runner_shadow_swarm_uses_lead_agent_planner -q`

### 目录分层补充记录：Eval Case Builder 候选 Artifact Snapshot 拆分

本次补充只拆分 eval case 构造中的候选 artifact snapshot/ref 汇总逻辑，不改变 eval case schema、不改变 sidecar 读回、不调用生产 runner/LLM/tool，也不影响生产 final input。

已完成：

- 新增 `eval/candidate_artifact_snapshots.py`，承载 `artifact_snapshot_summary`、candidate artifact hash/ref、lead synthesis ref、worker manifest ref、candidate gate ref 和 artifact hash 脱敏逻辑。
- `eval/case_builder.py` 只调用 `artifact_snapshot_summary(source)`，不再内联 `_artifact_snapshot_summary`、`_lead_synthesis_snapshot_ref`、`_worker_manifest_snapshot_ref`、`_candidate_gate_snapshot_ref` 或 `_sanitize_for_artifact_hash`。
- 新增 `tests/structure/test_eval_case_builder_boundaries.py`，约束 candidate artifact snapshot/ref 逻辑不得回流 `eval/case_builder.py`。

边界：

- 该模块只服务 eval case/candidate artifact sidecar 摘要，不产生生产决策效果。
- artifact hash 仍必须基于脱敏后的 payload；任何 `raw*` 或密钥相关字段继续被替换为 `<redacted>`。
- `eval/case_builder.py` 仍较大，后续可继续拆 replay refs、execution fact violations 等独立区域，但每次必须有结构测试护栏。

本次通过的验证：

- `python -m pytest tests/structure/test_eval_case_builder_boundaries.py tests/eval/test_case_builder_candidate_audit.py -q`
- `python -m pytest tests/eval/test_context_artifact_readback.py tests/eval/test_promotion_artifact_store.py -q`
- `python -m pytest tests/eval/test_decision_input_experiment.py tests/eval/test_candidate_audit_rules.py tests/eval/test_eval_package_structure.py -q`

### 目录分层补充记录：Eval Replay 候选 Artifact 一致性拆分

本次补充只拆分 candidate replay 中的 artifact snapshot sidecar 一致性检查，不改变 replay output schema、不改变 release gate 规则、不调用生产 runner/LLM/tool，也不影响生产 final input。

已完成：

- 新增 `eval/candidate_artifact_consistency.py`，承载 candidate artifact 类型列表、artifact snapshot ref/hash 一致性检查和 store metadata 剥离逻辑。
- `eval/replay.py` 改为调用 `artifact_snapshot_consistency(...)`，不再内联 `_artifact_snapshot_consistency` 或 `CANDIDATE_ARTIFACT_TYPES`。
- 新增 `tests/structure/test_eval_replay_boundaries.py`，约束 artifact snapshot consistency 不得回流 `eval/replay.py`。

边界：

- 该模块只校验 eval sidecar readback 的候选 artifact 是否齐全、自洽和 hash 对账一致。
- `candidate_artifact_store_hash_mismatch` 等阻断语义保持不变；release gate 仍只消费 replay output 中的安全 violation 摘要。
- `worker_manifest_consistency` 和 `context_artifact_consistency` 仍在 `eval/replay.py`，后续可继续拆，但不得和本轮合并成大范围改动。

本次通过的验证：

- `python -m pytest tests/structure/test_eval_replay_boundaries.py -q`
- `python -m pytest tests/eval/test_replay_llmjudge.py::test_candidate_replay_reads_artifact_snapshot_back_from_eval_store tests/eval/test_replay_llmjudge.py::test_candidate_replay_detects_candidate_artifact_store_hash_mismatch -q`
- `python -m pytest tests/eval/test_context_artifact_readback.py -q`
- `python -m pytest tests/eval/test_release_gate.py::test_release_gate_blocks_when_artifact_snapshot_readback_fails tests/eval/test_release_gate.py::test_release_gate_blocks_when_artifact_snapshot_consistency_missing_or_malformed -q`

### 目录分层补充记录：Eval Case Builder Context Artifact Summary 拆分

本次补充只拆分 Eval case builder 中的 context artifact refs 投影规则，不改变 case summary schema，不改变 replay/release gate 语义，不调用生产 runner/LLM/tool，也不影响生产 final input。

已完成：

- 新增 `eval/context_artifact_summary.py`，承载 `run_context.artifacts` 到 eval `candidate_audit.context_artifacts` 的安全摘要投影。
- `eval/case_builder.py` 改为调用 `context_artifacts_summary(...)`，不再内联 `_context_artifacts_summary`、`_context_gate_result_refs`、`_context_evidence_refs` 或 `_context_contribution_refs`。
- 新增 `tests/eval/test_context_artifact_summary.py`，覆盖 context artifact summary 只保留安全 refs，不复制 raw payload/snippet。
- `tests/structure/test_eval_case_builder_boundaries.py` 已约束 context artifact summary 逻辑不得回流 `eval/case_builder.py`。

边界：

- `context_artifact_summary` 只做 eval summary projection，不写 eval store、不读取 journal、不做 release gate 判定。
- `context_*_mismatch`、`context_*_missing` 等 replay/release gate 阻断语义保持不变。

本次通过的验证：

- `python -m pytest tests/eval/test_context_artifact_summary.py tests/structure/test_eval_case_builder_boundaries.py tests/eval/test_case_builder_candidate_audit.py -q`
- `python -m pytest tests/eval/test_context_artifact_readback.py tests/eval/test_promotion_artifact_store.py tests/eval/test_replay_llmjudge.py -q`

### 目录分层补充记录：Eval Replay Worker Manifest 一致性拆分

本次补充只拆分 candidate replay 中的 worker manifest 一致性检查，不改变 replay output schema、不改变 release gate 规则、不调用生产 runner/LLM/tool，也不影响生产 final input。

已完成：

- 新增 `eval/worker_manifest_consistency.py`，承载 worker manifest 数量/hash/required/failure policy 对账、Lead synthesis 必填 worker drop 校验、可选 worker drop advisory，以及 counter/conflict coverage 需要的 Lead synthesis artifact helper。
- `eval/replay.py` 改为调用 `worker_manifest_consistency(...)`，不再内联 `_worker_manifest_consistency`、`_lead_synthesis_worker_drop_violations`、`_lead_synthesis_optional_worker_drop_advisories`、`_manifest_item_required` 等实现。
- `tests/structure/test_eval_replay_boundaries.py` 已约束 worker manifest consistency 不得回流 `eval/replay.py`。

边界：

- 该模块只服务 eval replay/release gate 的候选 artifact 对账，不产生生产决策效果。
- required worker 缺失、failure policy mismatch、optional worker drop advisory 等语义保持不变。
- `context_artifact_consistency` 仍在 `eval/replay.py`，后续可作为独立 checkpoint 继续拆分。

本次通过的验证：

- `python -m pytest tests/structure/test_eval_replay_boundaries.py -q`
- `python -m pytest tests/eval/test_context_artifact_readback.py::test_candidate_replay_detects_failed_required_worker_not_propagated_to_lead_synthesis tests/eval/test_context_artifact_readback.py::test_candidate_replay_advises_when_optional_worker_drop_is_not_recorded tests/eval/test_context_artifact_readback.py::test_candidate_replay_accepts_recorded_optional_soft_downgrade_drop -q`
- `python -m pytest tests/eval/test_release_gate.py::test_release_gate_blocks_when_worker_manifest_consistency_fails tests/eval/test_release_gate.py::test_release_gate_blocks_when_worker_manifest_is_incomplete_even_with_enough_workers -q`
- `python -m pytest tests/eval/test_replay_llmjudge.py::test_replay_runner_writes_sidecar_output_without_prod_side_effects tests/eval/test_replay_llmjudge.py::test_replay_runner_enforces_supported_modes_without_prod_side_effects tests/eval/test_replay_llmjudge.py::test_candidate_decision_replay_can_run_injected_decision_input_shadow_final -q`

### 目录分层补充记录：Eval Replay Context Artifact 一致性拆分

本次补充只拆分 candidate replay 中的 context artifact refs/hash 一致性检查，不改变 replay output schema、不改变 release gate 规则、不调用生产 runner/LLM/tool，也不影响生产 final input。

已完成：

- 新增 `eval/context_artifact_consistency.py`，承载 context artifacts、DecisionInput refs、ReplayableInput refs、evidence/contribution 计数和 candidate artifact sidecar hash/ref 对账。
- `eval/replay.py` 改为调用 `context_artifact_consistency(...)`，不再内联 `_context_artifact_consistency` 或 `_append_context_candidate_artifact_violations`。
- `tests/structure/test_eval_replay_boundaries.py` 已约束 context artifact consistency 不得回流 `eval/replay.py`。

边界：

- 该模块只服务 eval replay/release gate 的候选 artifact 对账，不产生生产决策效果。
- `context_*_mismatch`、`context_*_missing` 等 rule_id 保持不变，release gate 的阻断语义保持不变。
- `eval/replay.py` 当前仍保留 replay 编排和 candidate replay payload 组装；后续拆分必须继续保持 readback 和 side-effect-free 约束。

本次通过的验证：

- `python -m pytest tests/structure/test_eval_replay_boundaries.py -q`
- `python -m pytest tests/eval/test_context_artifact_readback.py::test_candidate_replay_detects_context_lead_synthesis_artifact_hash_mismatch tests/eval/test_context_artifact_readback.py::test_candidate_replay_detects_missing_context_gate_candidate_artifact_ref tests/eval/test_context_artifact_readback.py::test_candidate_replay_detects_context_candidate_gate_hash_mismatches -q`
- `python -m pytest tests/eval/test_release_gate.py::test_release_gate_blocks_when_context_artifact_consistency_fails -q`

### 目录分层补充记录：Eval Replay 完整引用与反方冲突覆盖拆分

本次补充只拆分 candidate replay 中的 complete replay refs 和 counter/conflict coverage 计算，不改变 replay output schema、不改变 release gate 规则、不调用生产 runner/LLM/tool，也不影响生产 final input。

已完成：

- 新增 `eval/complete_replay_refs.py`，承载 complete replay refs key map、布尔覆盖率投影和缺失引用名计算。
- 新增 `eval/counter_conflict_coverage.py`，承载 lead synthesis counter thesis、strongest counter、conflict refs 与 lead synthesis artifact 顶层 refs 的覆盖检查。
- `eval/replay.py` 改为调用 `complete_replay_refs(...)`、`complete_replay_missing_refs(...)` 和 `counter_conflict_coverage(...)`，不再内联 `_complete_replay_refs`、`_complete_replay_missing_refs`、`_counter_conflict_coverage` 或相关 key map。
- 新增 `tests/eval/test_complete_replay_refs.py` 和 `tests/eval/test_counter_conflict_coverage.py`，覆盖两个拆出模块的直接语义。
- `tests/structure/test_eval_replay_boundaries.py` 已约束这两类规则不得回流 `eval/replay.py`。

边界：

- `complete_replay_refs` 仍只输出安全布尔覆盖率和缺失引用名，不复制 raw final output、raw prompt、raw worker payload。
- `counter_conflict_coverage` 仍只服务 eval replay/release gate 的候选 artifact 对账，不产生生产决策效果。
- `release_gate` 的 `complete_replay_input_incomplete` 与 `counter_conflict_coverage_failed` 阻断语义保持不变。

本次通过的验证：

- `python -m pytest tests/eval/test_complete_replay_refs.py tests/eval/test_counter_conflict_coverage.py tests/structure/test_eval_replay_boundaries.py -q`
- `python -m pytest tests/eval/test_context_artifact_readback.py tests/eval/test_replay_llmjudge.py tests/eval/test_release_gate.py -q`

### 目录分层补充记录：DecisionInput Shadow Final 与 Legacy Observed 对照

本次补充只增强 eval/replay 的人工评审材料，不改变生产决策语义，不让 `DecisionInput` 进入生产 `FinalDecisionAgent`，也不让 release gate 自动切换配置。

已完成：

- 新增 `eval/shadow_final_comparison.py`，负责从 legacy observed parsed plan 和 `decision_input_shadow_final` 中提取安全摘要，并输出 `main_action_match`、`probability_delta` 和差异类型。
- `ReplayRunner(candidate_decision)` 在显式注入 `decision_input_final_adapter` 时生成 `shadow_legacy_comparison`；没有 adapter 时不运行 shadow final，不访问生产 runner/LLM/tool。
- `build_shadow_candidate_comparison` 会把 `shadow_legacy_comparison` 投影为安全人工评审摘要，不复制 raw prompt、raw final output、raw worker payload。
- `release_promotion_review.clean_shadow_candidate_case` 要求每个可用 case 同时具备 completed/no-effect shadow final 和 available/no-effect shadow-vs-legacy comparison；缺少 comparison 时 `shadow_candidate_comparison` 视为缺失材料。

边界：

- `shadow_legacy_comparison` 只比较安全字段，不判定交易对错，不覆盖 release gate 的其他硬门禁。
- `main_action_match=false` 不会自动修改生产计划；它只进入人工切换评审材料。
- `promotion_approved` 和 `allowed_to_change_production_final_input` 继续保持 `false`。

本次通过的验证：

- `python -m pytest tests/eval/test_shadow_final_comparison.py tests/eval/test_replay_llmjudge.py::test_candidate_decision_replay_can_run_injected_decision_input_shadow_final tests/eval/test_promotion_artifacts.py::test_shadow_candidate_comparison_uses_safe_refs_without_raw_payloads tests/eval/test_release_gate.py::test_release_gate_requires_shadow_legacy_comparison_for_shadow_candidate_comparison_material -q`
- `python -m pytest tests/eval/test_promotion_artifacts.py tests/eval/test_promotion_review.py tests/eval/test_promotion_artifact_store.py tests/eval/test_release_gate.py -q`
- `python -m pytest tests/eval/test_shadow_final_comparison.py tests/eval/test_decision_input_experiment.py tests/eval/test_replay_llmjudge.py tests/eval/test_context_artifact_readback.py -q`
- `python -m pytest tests/workflow/test_run_executor.py tests/structure/test_eval_replay_boundaries.py tests/structure/test_formal_docs_current_state.py -q`

### 目录分层补充记录：Agent Swarm Compatibility Import 收口

本次补充只收口内部 import ownership，不改变生产决策语义，不切换 FinalDecisionAgent 输入，不删除外部兼容路径。

已完成：

- 内部测试的常规 contract/harness 使用路径已迁到 `crypto_manual_alert.orchestration.contracts` 与 `crypto_manual_alert.orchestration.harness`。
- `agent_swarm.contracts`、`agent_swarm.harness` 和 `agent_swarm.shadow_failure` 继续作为 compatibility re-export 保留。
- `tests/agent_swarm/test_controlled_contracts.py` 保留兼容性断言，证明旧路径 re-export 与 canonical object 相同。
- `tests/structure/test_orchestration_contract_boundaries.py` 新增源码 ownership 护栏：除 compatibility wrapper 自身外，内部源码不得导入 `agent_swarm.contracts`、`agent_swarm.harness` 或 `agent_swarm.shadow_failure`。

边界：

- `agent_swarm/` 仍承载 worker、runner、registry、tool/LLM worker 和旧路径兼容层。
- `orchestration/` 是 Lead/worker contract、harness、shadow failure 的 canonical owner。
- 本轮只改变导入归属和测试 ownership 信号，不改变 worker 行为、release gate 或 production control。

本次通过的验证：

- `python -m pytest tests/structure/test_orchestration_contract_boundaries.py tests/agent_swarm/test_controlled_contracts.py -q`
- `python -m pytest tests/agent_swarm/test_workers.py tests/agent_swarm/test_shadow_swarm.py tests/agent_swarm/test_runtime.py tests/agent_swarm/test_llm_tool_worker.py tests/agent_swarm/test_pool_runner.py tests/agent_swarm/test_harness_validation.py tests/agent_swarm/test_controlled_contracts.py -q`
- `python -m pytest tests/lead/test_agent.py tests/workflow/test_run_executor.py tests/structure/test_orchestration_contract_boundaries.py -q`

### 目录分层补充记录：Release Gate Promotion Review 状态机拆分

本次补充只拆分 release gate 中的 promotion review 状态机，不改变硬门禁规则、不改变 promotion artifact schema、不允许自动切换生产 final input，也不产生任何生产副作用。

已完成：

- 新增 `eval/release_promotion_review.py`，承载 promotion review 状态机、required promotion artifact 校验、manual release decision 校验和 config change review request 校验。
- `eval/release_gate.py` 只保留 release gate 汇总主流程、candidate replay hard gate、badcase coverage 和安全 violation 摘要；promotion review 通过 `promotion_review(...)` 委托。
- 新增 `tests/structure/test_release_gate_boundaries.py`，约束 promotion review 状态机不得回流 `eval/release_gate.py`。

边界：

- `promotion_review.allowed_to_change_production_final_input` 必须保持 `False`；manual release decision 和 config change review request 都只是人工评审 artifact，不是自动切换开关。
- `release_promotion_review.py` 只读取 eval replay/promotion artifacts，不调用生产 runner、LLM、tool、journal 写入或 notification。
- release gate 硬阻断原因和 `hard_gate_results` 结构保持不变。

本次通过的验证：

- `python -m pytest tests/structure/test_release_gate_boundaries.py -q`
- `python -m pytest tests/eval/test_release_gate.py::test_release_gate_result_is_a_no_side_effect_promotion_review tests/eval/test_release_gate.py::test_release_gate_manual_release_decision_only_reaches_config_review tests/eval/test_release_gate.py::test_release_gate_records_config_change_review_request_without_allowing_switch -q`
- `python -m pytest tests/eval/test_promotion_review.py tests/eval/test_promotion_artifacts.py -q`

### 目录分层补充记录：EvalStore Promotion Artifact 校验拆分

本次补充只拆分 `EvalStore` 中的 promotion artifact 业务校验逻辑，不改变 SQLite schema、不改变 artifact JSON 结构、不改变 release gate 规则，不调用生产 runner/LLM/tool，也不影响生产 final input。

已完成：

- 新增 `eval/promotion_artifact_validation.py`，承载 `validate_promotion_artifact(...)`、artifact ref 归属检查和 config change review request 的 no-effect 校验。
- `eval/store.py` 在写入 `eval_promotion_artifacts` 前只调用 `validate_promotion_artifact(...)`，不再内联 `_validate_promotion_artifact`、`_promotion_artifact_ref_matches` 或 `_validate_config_change_review_request_artifact`。
- 新增 `tests/eval/test_promotion_artifact_validation.py`，直接覆盖 cross-run、side effect、artifact ref mismatch 和 config review request 不得声称可切换生产 final input。
- 新增 `tests/structure/test_eval_store_boundaries.py`，约束 promotion artifact 校验逻辑不得回流 `eval/store.py`。

边界：

- `eval/store.py` 仍保留 eval SQLite 表初始化、CRUD、candidate artifact 写入和 JSON readback，不在本轮拆分 candidate artifact 校验。
- promotion artifact 仍必须 `decision_effect=none`；`config_change_review_request.allowed_to_change_production_final_input` 必须保持 `False`。
- 本轮不允许开启 `decision.final_input_mode=decision_input`，也不允许 release gate 自动修改生产配置。

本次通过的验证：

- `python -m pytest tests/eval/test_promotion_artifact_validation.py tests/structure/test_eval_store_boundaries.py -q`
- `python -m pytest tests/eval/test_promotion_artifact_store.py tests/eval/test_promotion_review.py tests/eval/test_release_gate.py -q`

### 目录分层补充记录：EvalStore Candidate Artifact 校验拆分

本次补充只拆分 `EvalStore` 中的 candidate artifact snapshot/ref 校验逻辑，不改变 eval case schema、不改变 candidate artifact sidecar schema、不改变 replay/release gate 规则，不调用生产 runner/LLM/tool，也不影响生产 final input。

已完成：

- 新增 `eval/candidate_artifact_validation.py`，承载 `CANDIDATE_ARTIFACT_TYPES`、`validate_candidate_artifact_snapshot(...)`、`validate_candidate_artifact(...)` 和 `candidate_artifact_ref(...)`。
- `eval/store.py` 的 `_insert_candidate_artifacts(...)` 继续负责 snapshot 提取、事务内 SQL insert 和 `stable_hash(artifact)` 存储 hash 重算；candidate artifact 校验已委托给新模块。
- `eval/candidate_artifact_consistency.py` 复用 `candidate_artifact_validation.CANDIDATE_ARTIFACT_TYPES`，避免 replay consistency 与 store 写入类型列表漂移。
- 新增 `tests/eval/test_candidate_artifact_validation.py`，直接覆盖 snapshot no-effect 校验、artifact hash、decision_effect、input/ref mismatch、ref fallback、unknown type 当前兼容行为。
- `tests/structure/test_eval_store_boundaries.py` 已约束 candidate artifact 校验逻辑不得回流 `eval/store.py`，且 consistency 模块必须复用同一 artifact type 列表。

边界：

- `input_summary`、`candidate_audit` 或 `artifact_snapshot` 不是 mapping 时仍静默跳过；缺失 artifact type 或 artifact 值不是 mapping 时仍跳过；额外 snapshot key 仍忽略。
- `decision_input_candidate` 与 `replayable_input_candidate` 仍只检查 `input_ref.endswith(...)`，不在本轮引入 case/trace 强绑定。
- 缺失 `input_ref` 当前仍先命中对应 `artifact_ref mismatch`，本轮不改变错误顺序。
- `artifact_hash` 存储列继续使用 `stable_hash(artifact)` 重算，不信任 artifact 自报 `artifact_hash`。
- 本轮不允许开启 `decision.final_input_mode=decision_input`，也不允许 candidate/replay/release 路径产生生产副作用。

本次通过的验证：

- `python -m pytest tests/eval/test_candidate_artifact_validation.py tests/eval/test_promotion_artifact_store.py tests/structure/test_eval_store_boundaries.py -q`
- `python -m pytest tests/eval/test_candidate_artifact_validation.py tests/eval/test_promotion_artifact_validation.py tests/eval/test_promotion_artifact_store.py tests/structure/test_eval_store_boundaries.py tests/structure/test_eval_replay_boundaries.py -q`
- `python -m pytest tests/eval/test_context_artifact_readback.py tests/eval/test_replay_llmjudge.py tests/eval/test_release_gate.py -q`

### 目录分层补充记录：EvalStore Row/JSON 转换拆分

本次补充只拆分 `EvalStore` 中的纯 row/JSON 转换逻辑，不改变 SQLite schema、不改变 SQL 查询、不改变 replay fallback 语义，不调用生产 runner/LLM/tool，也不影响生产 final input。

已完成：

- 新增 `eval/store_rows.py`，承载 `dump_json(...)`、`load_json(...)`、`run_row(...)`、`case_to_row(...)`、`case_row(...)`、`frozen_input_row(...)`、`replay_row(...)`、`not_run_replay_result(...)` 和 `score_row(...)`。
- `eval/store.py` 继续负责 SQLite connection、DDL、SQL CRUD、artifact insert 和事务边界；JSON dump/load 与 row-to-object 转换改为委托 `store_rows.py`。
- 新增 `tests/eval/test_store_rows.py`，直接覆盖 JSON dump 参数、空 JSON 默认、row 布尔转换、`created_at` 剥离、`not_run` replay fallback 和 score evidence refs。
- `tests/structure/test_eval_store_boundaries.py` 已约束 row/JSON helper 不得回流 `eval/store.py`，且 `store_rows.py` 不得依赖 sqlite/store/workflow/journal/notification。

边界：

- `dump_json(...)` 必须保持 `ensure_ascii=False`、`sort_keys=True`、`default=str`。
- `load_json(None)` 与 `load_json("")` 仍返回 `None`，默认 `{}` 或 `[]` 由调用方决定。
- `replay_row(...)` 仍保持 `allowed=None` 不变、`0/1` 转 bool、移除 `created_at`，并把空 `output_json/metadata_json` 投影为 `{}`。
- `not_run_replay_result(...)` 仍只返回 side-effect-free fallback，不包含 `output_payload`、production final input、journal 或 notification 字段。
- candidate artifact 的存储 hash 仍由 `stable_hash(artifact)` 重算；`stored_artifact_hash` 只在 readback metadata 中临时注入，不污染原始 artifact JSON。

本次通过的验证：

- `python -m pytest tests/eval/test_store_rows.py tests/structure/test_eval_store_boundaries.py tests/eval/test_promotion_artifact_store.py -q`
- `python -m pytest tests/eval/test_context_artifact_readback.py tests/eval/test_replay_llmjudge.py tests/eval/test_release_gate.py -q`
- `python -m pytest tests/eval/test_eval_package_structure.py tests/workflow/test_run_executor.py tests/structure/test_formal_docs_current_state.py -q`

### 目录分层补充记录：Eval Case Builder Replayable Input Summary 拆分

本次补充只拆分 `eval/case_builder.py` 中 replayable input candidate 的 coverage 与 artifact refs 安全摘要投影，不改变 eval case schema、不改变 frozen summary 主流程、不读取 journal、不调用生产 runner/LLM/tool，也不影响生产 final input。

已完成：

- 新增 `eval/replayable_input_summary.py`，承载 `replayable_coverage_summary(...)` 与 `replayable_artifact_refs_summary(...)`，内部保留各类 replayable artifact refs 的字段白名单。
- `eval/case_builder.py` 的 `_candidate_audit_summary(...)` 改为调用上述两个公开函数，不再内联 `_replayable_coverage_summary`、`_replayable_artifact_refs_summary` 及其子投影 helper。
- 新增 `tests/eval/test_replayable_input_summary.py`，直接覆盖 coverage allowlist 排序、observed run refs、telemetry/evidence/memory/span tree refs 与 raw 字段剥离。
- `tests/structure/test_eval_case_builder_boundaries.py` 已约束 replayable summary helper 不得回流 `eval/case_builder.py`，且新模块不得依赖 Journal/EvalStore/workflow/notification/final input 相关实现。

边界：

- coverage 仍只保留当前 allowlist，并按 `sorted(allowed_keys)` 输出。
- artifact refs 仍使用逐类型白名单，raw prompt、raw payload、raw decision、request/response JSON、密钥类字段不得进入 summary。
- `_candidate_audit_summary(...)`、`_candidate_audit_source(...)`、`_frozen_summary(...)` 仍留在 `case_builder.py`，保持 case/candidate audit 主流程归属。
- `audit_only.decision_effect == "none"` 优先行为不变。
- 本轮不允许开启 `decision.final_input_mode=decision_input`，也不允许 eval case 构建路径产生生产副作用。

本次通过的验证：

- `python -m pytest tests/eval/test_replayable_input_summary.py tests/structure/test_eval_case_builder_boundaries.py tests/eval/test_case_builder_candidate_audit.py -q`
- `python -m pytest tests/eval/test_context_artifact_summary.py tests/eval/test_case_builder_candidate_audit.py tests/eval/test_replay_llmjudge.py -q`
- `python -m pytest tests/eval/test_eval_package_structure.py tests/structure/test_formal_docs_current_state.py -q`

### 目录分层补充记录：Agent Swarm Local Workers 拆分

本次补充只调整本地 shadow worker 的模块归属，不改变 worker 输出、不改变 LeadPlan、不改变 shadow runner、harness、release gate 或生产 final input。

已完成：

- `agent_swarm/local_workers/` 包已降级为兼容 re-export；真实业务 worker canonical owner 是 `market_agents/`，当前 required worker 覆盖 `live_fact.py`、`derivatives.py`、`macro_event.py`、`root_cause.py`、`sentiment_crowding.py`、`data_quality.py`、`execution_risk.py`。
- `agent_swarm/workers.py` 与 `agent_swarm/local_workers/` 都是兼容导出，只 re-export market agent 类和 `build_local_shadow_workers()`。
- `agent_swarm/registry.py` 不得新增市场业务规则；新增业务 worker 必须先进入 `market_agents/`。
- `tests/structure/test_local_worker_boundaries.py` 约束本地 worker 包结构、旧 wrapper 只做导出、registry 使用 canonical market agent 路径。

边界：

- 本地 worker 仍是 audit-only shadow worker，不调用 LLM、不检索实时信息、不写 journal、不发 notification、不修改主链路。
- `agent_swarm/workers.py` 与 `agent_swarm/local_workers/` 暂时保留兼容路径，旧测试和外部导入仍可使用；项目内部新依赖应使用 `market_agents`。
- 本轮不改变 `RootCauseAgent`、`MarketSentimentAgent`、`DataQualityAgent`、`ExecutionRiskAgent` 的 contribution 结构、`decision_effect=none` 约束或 output hash 计算。

本次通过的验证：

- `python -m pytest tests/structure/test_local_worker_boundaries.py tests/agent_swarm/test_workers.py tests/agent_swarm/test_controlled_contracts.py -q`
- `python -m pytest tests/agent_swarm/test_registry.py tests/agent_swarm/test_shadow_swarm.py tests/workflow/test_run_executor.py -q`

### 目录分层补充记录：Default LeadPlan Builder 拆分

本次补充只调整默认 shadow LeadPlan 构造函数的模块归属，不改变 LeadPlan 字段、不改变 task 顺序、不改变 worker runner、harness、registry、release gate 或生产 final input。

已完成：

- 新增 `agent_swarm/default_lead_plan.py`，承载 `build_default_lead_plan(...)` 和 `_role_for_agent(...)`。
- `agent_swarm/shadow_runner.py` 继续负责运行 worker、preflight/postflight、失败 envelope 和 audit 产物，不再内联默认任务规划。
- `agent_swarm.shadow_runner.build_default_lead_plan` 仍作为兼容导入保留；包级 `crypto_manual_alert.agent_swarm.build_default_lead_plan` 指向 canonical `default_lead_plan.py`。
- 新增 `tests/structure/test_default_lead_plan_boundaries.py`，约束 default plan builder 不回流 shadow runner，且 default plan 模块不依赖 runner/pool runner。

当前补充说明：`lead/default_plan.py` 已进一步收敛为 `LeadAgent.plan_tasks(...)` 的 canonical 门面，`agent_swarm/default_lead_plan.py` 只保留兼容导出，不再承载 `_role_for_agent(...)`、`SubTask(...)` 或 `LeadPlan(...)` 构造细节。真实 Lead planning 归属以 `lead/agent.py` 为准。

边界：

- 默认计划生成 7 个 required shadow worker task：`LiveFactAgent`、`DerivativesAgent`、`MacroEventAgent`、`RootCauseAgent`、`MarketSentimentAgent`、`DataQualityAgent`、`ExecutionRiskAgent`。
- `decision_effect` 仍固定为 `none`，worker requested tools 仍为空，failure_policy 仍为 `soft_downgrade`。
- 本轮不改变 LeadAgent 动态规划、不切换生产 final input，也不把 shadow audit 升级为生产决策链。

本次通过的验证：

- `python -m pytest tests/structure/test_default_lead_plan_boundaries.py tests/agent_swarm/test_shadow_swarm.py tests/agent_swarm/test_controlled_contracts.py -q`
- `python -m pytest tests/agent_swarm/test_shadow_orchestration.py tests/workflow/test_run_executor.py tests/cli/test_runner_cli.py::test_runner_shadow_swarm_uses_lead_agent_planner -q`

### 目录分层补充记录：Shadow Worker Failure Envelope 拆分

本次补充只调整 shadow worker 失败/超时/未配置/preflight reject 结果封装的模块归属，不改变 worker 执行顺序、不改变 LeadPlan、不改变 harness 校验、不改变 failure policy、不改变 `decision_effect=none`，也不切换生产 final input。

已完成：

- 新增 `agent_swarm/shadow_worker_failures.py`，承载 `failed_worker_result(...)`、`preflight_rejected_worker_result(...)`、`timeout_worker_result(...)` 和 `not_configured_worker_result(...)`。
- `agent_swarm/shadow_runner.py` 继续负责 worker pool 调用、preflight/postflight 聚合和 `ShadowSwarmAudit` 产物组装，不再内联失败 contribution、timeout contribution、未配置 contribution 或 hash helper。
- 新增 `tests/structure/test_shadow_swarm_boundaries.py` 护栏，约束失败 envelope 和 hash 细节不得回流 `shadow_runner.py`。

边界：

- 失败 worker 仍必须显式进入 `WorkerResult` 和 `AgentContribution`，不能伪装成功。
- timeout 仍只产生 audit result，不取消或修改生产决策链路。
- preflight reject 仍不得调用 worker；相关 violation 继续进入 `harness_validation`。
- 本轮不改变 `orchestration/shadow_audit.py` 的编排归属，也不把 shadow audit 升级为生产决策链。

本次通过的验证：

- `python -m pytest tests/structure/test_shadow_swarm_boundaries.py -q`
- `python -m pytest tests/agent_swarm/test_shadow_swarm.py tests/agent_swarm/test_shadow_orchestration.py tests/agent_swarm/test_controlled_contracts.py -q`

### 目录分层补充记录：Default LeadPlan 规划归属收敛

本次补充只收敛默认 LeadPlan 兼容入口的规划归属，不改变默认 worker 列表、task 顺序、LeadPlan 字段、requested tools、harness resource caps、worker runner、release gate 或生产 final input。

已完成：

- 新增 `lead/default_plan.py`，作为 `build_default_lead_plan(...)` 的 canonical owner，并调用 `LeadAgent.plan_tasks(...)`。
- `agent_swarm/default_lead_plan.py` 降级为兼容导出，不再内联 `SHADOW_WORKER_AGENTS`、`SubTask(...)`、`LeadPlan(...)` 或 `_role_for_agent(...)`。
- `build_default_lead_plan(...)` 继续作为旧路径兼容入口，输出必须与 `LeadAgent(policy).plan_tasks(...)` 保持等价。
- `tests/structure/test_default_lead_plan_boundaries.py` 已改为约束 default builder 委托 LeadAgent，并禁止规划实现细节回流到 `agent_swarm/default_lead_plan.py`。
- `tests/lead/test_agent.py` 新增等价测试，直接比较 `build_default_lead_plan(...).to_public_dict()` 与 `LeadAgent.plan_tasks(...).to_public_dict()`。

边界：

- `lead/agent.py` 是 Lead planning 与 synthesis 的 canonical owner。
- `agent_swarm/` 继续只拥有 worker、runner、registry、pool runner、tool/LLM worker 和兼容导出，不拥有 Lead planning 规则。
- 本轮不改变 `orchestration/shadow_audit.py` 的 shadow 编排入口，也不打开 `decision.final_input_mode=decision_input`。

本次通过的验证：

- `python -m pytest tests/structure/test_default_lead_plan_boundaries.py tests/lead/test_agent.py -q`
- `python -m pytest tests/agent_swarm/test_shadow_swarm.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_controlled_contracts.py tests/agent_swarm/test_shadow_orchestration.py tests/workflow/test_pre_final_orchestration.py -q`

### 目录分层补充记录：Research Pipeline Search Adapter 拆分

本次补充只拆分 research fallback 中的搜索适配器与共享 LLM helper，不改变 research plan schema、不改变 search evidence schema、不改变 leader synthesis、不调用生产 runner/notification，也不改变生产 final input。

已完成：

- 新增 `research_pipeline/search_adapters.py`，承载 `DisabledSearchAdapter`、`FixtureSearchAdapter`、`DuckDuckGoHtmlSearchAdapter`、`ResponsesWebSearchAdapter` 和 DuckDuckGo HTML parser。
- 新增 `research_pipeline/llm_support.py`，承载 OpenAI-compatible 配置读取和耗时计算 helper，避免 search adapter 反向依赖 `core.py`。
- 新增 `research_pipeline/prompts.py`，承载 `USER_FACING_LANGUAGE_RULE` 与 `LEADER_REVIEW_KEYS`，供 planner、leader synthesizer 和 web search adapter 共用。
- `research_pipeline/factory.py` 改为从 `search_adapters.py` 构造搜索 adapter；包级 `research_pipeline.__init__` 的 lazy export 指向 canonical 模块。
- `research_pipeline/core.py` 保留 planner、fallback planner、leader synthesizer 与 LLM chat completion 解析，不再内联搜索 adapter class 或 DuckDuckGo parser。

边界：

- `ResponsesWebSearchAdapter` 仍只通过显式配置和显式 client/环境变量执行，不改变默认 offline/disabled 行为。
- research evidence 仍只是降级证据，不能升级为 mark/index/order_book 等交易所执行事实。
- 本轮不拆 planner 和 leader synthesizer；后续如继续拆分，应保持 `ResearchPlan`、`ResearchAudit` 与 telemetry 字段兼容。

本次通过的验证：

- `python -m pytest tests/research_pipeline/test_research_pipeline_package_structure.py -q`
- `python -m pytest tests/research_pipeline/test_fallback.py -q`
- `python -m pytest tests/research_pipeline tests/workflow/test_run_executor.py tests/workflow/test_pre_final_orchestration.py -q`

### 目录分层补充记录：Research Pipeline Leader Synthesizer 拆分

本次补充只拆分 research fallback 中的 leader synthesis 与 chat completion helper，不改变 ResearchPlan/ResearchAudit schema、不改变 leader summary key、不改变 telemetry 字段、不改变 production final input。

已完成：

- 新增 `research_pipeline/leader_synthesizers.py`，承载 `StaticLeaderResearchSynthesizer`、`OpenAICompatibleLeaderResearchSynthesizer` 和 `FallbackLeaderResearchSynthesizer`。
- `research_pipeline/llm_support.py` 增加 `post_chat_completion(...)`，统一 OpenAI-compatible chat completion 调用和 LLM telemetry 记录。
- `research_pipeline/factory.py` 改为从 `leader_synthesizers.py` 构造 leader synthesizer；包级 lazy export 指向 canonical 模块。
- `research_pipeline/core.py` 当前只保留 research planner 与 planner JSON 解析，不再内联 leader synthesis 类。

边界：

- leader synthesis 仍只做 research evidence 汇总和对抗审查，不生成最终交易计划、不写 journal、不发 notification。
- `LEADER_REVIEW_KEYS` 仍由 `research_pipeline/prompts.py` 统一承载，输出 key 不变。
- research evidence 仍是降级证据，不得冒充交易所原生执行事实。

本次通过的验证：

- `python -m pytest tests/research_pipeline/test_research_pipeline_package_structure.py -q`
- `python -m pytest tests/research_pipeline/test_fallback.py -q`
- `python -m pytest tests/research_pipeline tests/workflow/test_run_executor.py tests/workflow/test_pre_final_orchestration.py -q`

### 目录分层补充记录：Storage Journal Schema 拆分

本次补充只拆分 SQLite journal 的 schema/migration/index 初始化，不改变表结构、不改变写入 API、不改变 query repository、不改变 eval/replay side-effect 边界，也不影响生产 final input。

已完成：

- 新增 `storage/journal_schema.py`，承载 `init_journal_schema(conn)` 和 schema 兼容迁移 helper。
- `storage/journal.py` 的 `_init_db()` 只负责打开连接并调用 `init_journal_schema(conn)`，不再内联 `CREATE TABLE`、`ALTER TABLE` 或 `CREATE INDEX`。
- `tests/storage/test_storage_package_structure.py` 新增结构护栏，防止 DDL/migration/index 逻辑回流 `journal.py`。

边界：

- `Journal` 仍负责 SQLite connection、业务写入、trace/LLM/badcase 查询和 row 投影。
- `journal_schema.py` 只负责 schema 初始化和兼容迁移，不读写业务 payload、不调用 notification、不执行 workflow。
- 现有 llm_interactions migration 语义保持不变。

本次通过的验证：

- `python -m pytest tests/storage/test_storage_package_structure.py tests/workflow/test_scheduler.py::test_journal_migrates_existing_llm_interaction_table tests/storage/test_query_repository.py -q`
- `python -m pytest tests/storage tests/telemetry tests/workflow/test_scheduler.py tests/workflow/test_run_persistence_step.py tests/workflow/test_run_executor.py -q`

### 目录分层补充记录：Storage Journal Row Projection 拆分

本次补充只拆分 Journal 查询结果的 JSON/row 投影，不改变 SQLite schema、不改变 Journal 写入 API、不改变 query repository 行为、不改变 eval/replay side-effect 边界。

已完成：

- 新增 `storage/journal_rows.py`，承载 `load_json(...)`、trace/plan/span/LLM/badcase row 投影，以及按 trace 查找 plan run 的只读 helper。
- `storage/journal.py` 改为导入 row helper，保留连接管理、业务写入、查询 SQL 和 trace/plan 归属校验。
- `tests/storage/test_storage_package_structure.py` 新增结构护栏，防止 row 投影 helper 回流 `journal.py`。

边界：

- `journal_rows.py` 不打开连接、不写数据库、不调用 workflow/notification，只处理已查询出的 SQLite row。
- `Journal` 仍是持久化 API owner，外部调用路径不变。

本次通过的验证：

- `python -m pytest tests/storage/test_storage_package_structure.py tests/storage/test_query_repository.py -q`
- `python -m pytest tests/storage tests/telemetry tests/workflow/test_scheduler.py tests/workflow/test_run_persistence_step.py tests/workflow/test_run_executor.py -q`

### 目录分层补充记录：DecisionInput Policy 拆分

本次补充只拆分 DecisionInput candidate/pre-final input 的规则策略，不改变 candidate schema、不改变 validation rule_id、不改变 production control gate、不改变 final input mode。

已完成：

- 新增 `decision/decision_input_policy.py`，承载 missing facts、conflicts、blocked actions、confidence policy、validation summary、required dropped contribution 和 worker hard block helper。
- `decision/decision_input.py` 继续负责 candidate/pre-final 对象、builder、refs 投影和 hash，不再内联策略规则。
- `required_dropped_contributions(...)` 与 `worker_hard_block_contributions(...)` 继续通过 `decision_input.py` re-export 兼容旧调用方。
- `tests/structure/test_runner_boundaries.py` 新增结构护栏，防止 policy helper 回流 builder。

边界：

- policy helper 只处理已给定的 facts gate、worker contribution refs 和 Lead synthesis，不读取 journal、不调用 LLM/tool、不写 production payload。
- `llm_tool_shadow_worker` hard block 仍只是 audit 信号，生产阻断语义继续由 `production_control_gate` 控制。

本次通过的验证：

- `python -m pytest tests/structure/test_runner_boundaries.py::test_decision_input_builder_delegates_policy_rules tests/decision/test_decision_input.py -q`
- `python -m pytest tests/decision/test_decision_input.py tests/decision/test_pre_final_switch_readiness.py tests/decision/test_production_control_gate.py tests/eval/test_context_artifact_readback.py tests/eval/test_replay_llmjudge.py tests/workflow/test_run_executor.py -q`
