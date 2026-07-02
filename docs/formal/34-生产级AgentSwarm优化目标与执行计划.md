# 生产级 Agent Swarm 优化目标与执行计划

## 1. 文档定位

本文是后续重构的当前执行入口，用来收敛以下问题：

- 当前生产主链路仍是 `legacy_baseline + legacy_prompt`，Agent Swarm 主要是 pre-final shadow audit，不是最终决策主链路。
- Skill 已有 facade 和契约测试，但还没有形成默认生产链路中的真实 `Worker -> SkillExecutor -> 实时来源 -> 证据回流` 闭环。
- 前端已有 Agent Swarm Audit 基础视图，但还不足以支撑生产级可视化审查。
- Eval 已能覆盖 replay、artifact consistency、release gate 和副作用证明，但还不能评估金融预测质量。
- 代码结构已从根目录散落文件中收敛了一部分，但仍有大文件、兼容层和过渡命名影响可读性。

本文继承 `29-Agent与Skill拆分详细设计.md` 的目标架构思想，继承 `31-受控AgentSwarm主链收敛与质量切换计划.md` 和 `32-架构功能收敛总计划与追踪清单.md` 中已经验证过的约束。后续执行以本文检查点为追踪入口；旧文档保留为历史记录和背景材料，不再作为新的任务队列继续追加。

## 2. 当前真实状态

### 2.1 后端主链路

当前真实主链路是：

```text
POST /api/runs/manual
  -> DecisionRequest
  -> DecisionRunContext
  -> RunExecutor
  -> LegacyPlanRunnerAdapter
  -> LegacyDecisionWorkflow
  -> market/research/legacy prompt build
  -> pre_final_orchestration
  -> shadow audit: LeadPlan + 7 Worker Agents
  -> pre_final DecisionInput / pre_final bundle
  -> legacy FinalDecisionAgent
  -> parser
  -> decision_control_step
       -> candidate audit / replay artifacts
       -> production_control_gate / risk gate
  -> journal persistence
  -> API projection: agent_audit_view
  -> frontend: /runs/{trace_id}
```

关键事实：

- `workflow.execution_mode` 默认仍是 `legacy_baseline`。
- `decision.final_input_mode` 默认仍是 `legacy_prompt`。
- `shadow.worker_mode` 默认仍是 `local_audit`。
- `LeadAgent` 当前只规划和综合 shadow audit worker。
- 7 个 Worker Agent 已经存在，但 `decision_effect=none`。
- `DecisionInput` 当前是候选、审计、回放和后续切换输入，不是默认生产最终输入。
- `candidate final` 已有 sidecar 函数，但尚未接入 `decision_control_step`，也没有进入脱敏 API projection。
- `production_control_gate` 会消费 candidate audit 并阻断风险动作，因此 shadow/candidate 不是“完全无影响”，而是“不会生成最终生产输入，但能参与生产阻断”。

### 2.2 Skill 接入状态

当前已有 Skill facade：

- `RealtimeSearchSkill`
- `RootCauseSearchSkill`
- `MarketSentimentSkill`
- `MacroEventSkill`
- `LiquidityOrderBookSkill`

当前不足：

- facade 主要是结构契约，不是真实默认工具执行层。
- 还没有统一的 `SkillExecutor`、`ToolBudget`、`SourceFreshness`、`ToolCallArtifact` 和 replay refs。
- `SkillExecutor` 注入路径还不清晰；`run_shadow_swarm_audit()` 可以接收工具执行器，但 `run_pre_final_orchestration()` 和主链路还没有稳定 executor/factory 入口。
- 工具命名还没有收敛到业务 Skill 名称；当前仍有 `web_search` 这类底层工具名混在 worker/harness 里。
- 当前业务 worker 可以直接产出 `AgentContribution`，缺少“必须经过 SkillExecutor 获取事实证据”的正向结构护栏。
- `RootCauseSearchSkill` 还没有真正执行递归检索，只声明了递归搜索约束。
- `RealtimeSearchSkill` 只读取输入视图中已有 search results，不主动触发实时 web searched。
- exchange-native execution facts 和 search-derived evidence 的事实防火墙还需要贯穿 SkillExecutor 和 Worker。

### 2.3 前端可视化状态

当前 `/runs/{trace_id}` 已能展示：

- trace summary
- span timeline
- LLM interactions
- Agent Swarm Audit
- LeadPlan
- Worker Agent Matrix
- DecisionInput
- Gates
- Runtime Flow

当前不足：

- 缺少 Agent/Tool 调用图。
- 缺少 source freshness 和 source tier 面板。
- 缺少 root-cause causal graph。
- 缺少 worker 冲突矩阵和 strongest counter thesis 展示。
- 缺少 legacy final 与 swarm candidate final 对比。
- 缺少 “哪些数据进入最终输入、哪些只是 audit note” 的明确可视化。
- 缺少 release/eval gate 面板与生产切换状态说明。
- 后端 projection 目前只给摘要字段，缺少一等字段：`tool_calls[]`、`evidence_sources[]`、`source_freshness[]`、`root_cause_graph`、`conflict_edges[]`、`candidate_final_comparison`、`input_lineage`、`release_eval_gate`。

### 2.4 Eval 状态

当前 Eval 已覆盖：

- badcase case builder
- frozen/replay readback
- candidate artifact consistency
- worker artifact coverage
- release gate
- no production side-effect proof
- candidate replay

当前不足：

- 没有 `OutcomeCollector`。
- 没有决策后价格结果回收。
- 没有 PnL、MFE、MAE、R multiple、命中率、最大回撤。
- 没有概率校准，如 Brier score。
- 没有按市场状态切片的质量指标。
- 没有实时性和消息新鲜度对决策质量的指标。
- 没有明确评测对象、窗口、价格源、K 线粒度、手续费/滑点、`no trade` 和 blocked action 的计分规则。
- 没有对照基线，至少需要比较 legacy final、swarm candidate final、no-trade/hold 等基线。
- 当前 badcase case builder 有样本偏置，不能单独代表整体预测质量。
- 金融 outcome 是滞后结果，不应直接混进即时 release gate 的 hard gate。

### 2.5 代码结构状态

当前根目录业务 `.py` 基本已经清理，但仍有大文件：

- `eval/store.py`
- `skills/facade.py`
- `eval/release_gate.py`
- `eval/case_builder.py`
- `storage/agent_audit_view.py`
- `artifacts/evidence.py`
- `storage/journal.py`
- `workflow/legacy_decision_workflow.py`

后续结构优化必须服务主链路，不做无目标拆分。

## 3. 不变约束

- 不自动打开生产 `decision.final_input_mode=decision_input`。
- 不自动下单、撤单、提币或读取交易密钥。
- 所有实盘相关输出必须保持 `manual_execution_required=true`。
- Worker Agent 不得输出最终动作、仓位、杠杆、止损、目标价或 risk verdict。
- Skill 不得返回 `AgentContribution`，不得写 journal，不得发通知。
- search-derived evidence 不得满足 mark、index、order book 等 execution facts。
- FinalDecisionAgent 不得调用工具。
- Eval/replay 不得触发 live fetch、web search、journal production write、Bark notification 或 live order。
- candidate final 可以作为 audit/candidate artifact 持久化到同一个 trace，但不得生成生产 final input、不得写单独生产决策结果、不得发通知。
- 未接入真实 `ToolCallArtifact` 前，candidate final 只能标记为 `audit_only` 或等价状态，不得宣称已经是生产候选 Agent Swarm 主链路。
- 新增业务代码不得放到项目根目录或 `src/crypto_manual_alert/*.py` 根包文件。
- 新增测试不得放到 `tests/` 根目录，必须按领域进入 `tests/<domain>/`。
- 同一问题连续失败 3 次必须暂停，记录失败现象、尝试方案、当前证据和需要用户决策的问题。

## 4. 目标主链路

目标不是自由聊天式 swarm，而是受控生产候选链路：

```text
DecisionRequest
  -> DecisionRunContext
  -> Fact Pack
  -> LeadAgent builds LeadPlan
  -> Worker Agents run in parallel
  -> Worker-controlled SkillExecutor calls
  -> EvidencePacket / ToolCallArtifact / AgentContribution
  -> Harness validation
  -> LeadAgent synthesis
  -> DecisionInput
  -> pre_final_input_gate
  -> candidate FinalDecisionAgent sidecar
  -> candidate parse / sanitize / semantic checks
  -> candidate audit + replay artifacts
  -> legacy final comparison
  -> production control gate remains explicit and conservative
  -> structural release gate + separate financial quality gate
  -> manual switch review
  -> production final input switch only after approval
```

阶段目标：

- Agent Swarm 要成为“候选最终决策主链路”，而不是只做旁路审计。
- legacy 保留为 fallback 和对照基线。
- Skill 必须真实参与 Worker 证据构建。
- 前端必须能看到真实 Agent/Skill/Gate 交互。
- Eval 必须能判断结构安全和金融预测质量。

关键命名约束：

- “candidate sidecar” 表示无副作用审计候选，只能用于同 trace 对比和后续评测。
- “production candidate Agent Swarm” 只能在 Worker 证据具备真实 `ToolCallArtifact`、通过 harness 和 gate 后使用。
- 不使用版本号式难追踪命名；用职责命名，如 `candidate_final_comparison`、`tool_call_artifacts`、`financial_quality_gate`。

## 5. 检查点总览

### 检查点一：固定 candidate final sidecar 与安全投影边界

目标：

先把已有 `run_candidate_final_decision_sidecar()` 接入真实主链路，让 Agent Swarm 产出的 `DecisionInput` 能进入候选 final sidecar，并在同一个 trace 中形成脱敏 comparison。这个检查点不宣称已经完成生产候选 Swarm；在真实 `ToolCallArtifact` 接入前，候选结果必须标记为 `audit_only` 或等价无副作用状态。

建议文件：

- 修改 `src/crypto_manual_alert/workflow/decision_control_step.py`
- 修改 `src/crypto_manual_alert/workflow/persistence_payload.py`
- 修改 `src/crypto_manual_alert/decision/candidate_final_decision.py`
- 修改 `src/crypto_manual_alert/decision/pre_final_input_gate.py`
- 修改 `src/crypto_manual_alert/storage/agent_audit_view.py`
- 修改 `src/crypto_manual_alert/api/routes_runs.py`
- 修改 `src/crypto_manual_alert/config/loader.py`（仅当需要显式配置开关时）
- 新增或修改 `tests/workflow/test_decision_control_step.py`
- 新增或修改 `tests/decision/test_candidate_final_decision.py`
- 新增或修改 `tests/storage/test_agent_audit_view.py`
- 新增或修改 `tests/api/test_runs_routes.py`
- 新增或修改 `tests/structure/test_swarm_candidate_boundaries.py`

运行顺序：

```text
pre_final_input_gate
  -> candidate final sidecar
  -> candidate parse/sanitize
  -> candidate audit payload(candidate_final_decision=...)
  -> legacy final comparison
  -> API projection: candidate_final_comparison
```

验收：

- 默认生产仍走 legacy。
- candidate final 能在无副作用模式下运行并写入 audit/candidate artifact。
- candidate final 只能消费 `DecisionInput`。
- candidate final 输入必须剥离或拒绝 `legacy_prompt`、`prompt_packet`、`raw_decision`、`frozen_input` 等原始 prompt/legacy 字段。
- candidate final 输出只能进入同 trace 的 candidate artifact，不生成生产 final input，不写单独生产决策结果，不发通知。
- legacy final 与 candidate final 能在同一 trace 下对比。
- API projection 能暴露脱敏 `candidate_final_comparison`：legacy/candidate 的 input ref/hash、action、probability、allowed、error、diff、decision_effect、production_final_input。
- 未接入真实 `ToolCallArtifact` 时，comparison 必须明确 `audit_only`，不得用于 production switch。

禁止：

- 不把 `controlled_shadow` 当作生产实现。
- 不直接把 `decision.final_input_mode` 默认改成 `decision_input`。
- 不为了跑通测试降低 worker required 数量。
- 不把 `raw_candidate_decision` 投到前端或 API。

### 检查点二：接入真实 SkillExecutor

目标：

让 Worker 能通过受控 `SkillExecutor` 调用实时搜索、宏观事件、根因递归、情绪拥挤度和交易所执行事实工具。这个检查点完成后，candidate final 才能从 `audit_only` 进入“生产候选 Agent Swarm”评估状态。

建议文件：

- 拆分 `src/crypto_manual_alert/skills/facade.py`
- 新建 `src/crypto_manual_alert/skills/contracts.py`
- 新建 `src/crypto_manual_alert/skills/executor.py`
- 新建 `src/crypto_manual_alert/skills/registry.py`
- 新建 `src/crypto_manual_alert/skills/tool_budget.py`
- 新建 `src/crypto_manual_alert/skills/source_freshness.py`
- 新建 `src/crypto_manual_alert/skills/tool_call_artifact.py`
- 修改 `src/crypto_manual_alert/agent_swarm/llm_tool_worker.py`
- 修改 `src/crypto_manual_alert/lead/agent.py`
- 修改 `src/crypto_manual_alert/orchestration/harness.py`
- 修改 `src/crypto_manual_alert/orchestration/shadow_audit.py`
- 修改 `src/crypto_manual_alert/workflow/pre_final_orchestration.py`
- 修改 `src/crypto_manual_alert/decision/decision_input.py`
- 修改 `src/crypto_manual_alert/decision/replay_worker_refs.py`
- 新增或修改 `tests/skills/`
- 新增或修改 `tests/agent_swarm/test_llm_tool_worker.py`
- 新增或修改 `tests/structure/test_skill_executor_boundaries.py`

最小 artifact 契约：

- `tool_call_id`
- `skill_name`
- `status`
- `source_type`
- `source_tier`
- `retrieved_at`
- `freshness_status`
- `result_ref`
- `output_hash`
- `can_satisfy_execution_fact`
- `error`

注入路径：

- `run_pre_final_orchestration()` 必须能接收 `SkillExecutor` 或 factory。
- `run_shadow_swarm_audit()` 继续保留注入点，但不能成为唯一入口。
- `LeadAgent` 和 harness 使用 Skill 名称 allowlist，不再暴露自由 `web_search` 请求。
- `LlmToolShadowWorker` 不直接接受自由 `tool_requests` dict；必须通过 `SkillExecutor.execute(skill_name, context)` 获取 artifact refs。

必须支持的 Skill：

- `realtime_search`
- `root_cause_search`
- `market_sentiment`
- `macro_event`
- `liquidity_order_book`

根因 Skill 约束：

- 支持受控递归深度。
- 每一层必须有 query、source、retrieved_at、evidence_ref、confidence。
- 每个影响因素可以继续扩展影响因素，但必须受 `max_depth`、`max_branch_count`、`deadline` 和 `tool_budget` 限制。
- 输出必须区分 known fact、inference、scenario。
- 不能直接给交易动作。

市场情绪 Skill 约束：

- 必须区分客观事实和群体行为偏差。
- 必须识别 crowded long、crowded short、priced-in、reflexivity risk。
- 必须给出对客观事实短期失真的可能路径。
- 不能把社媒叙事直接提升为事实。

验收：

- Worker 能看到 tool result refs，而不是 raw snippets。
- `ToolCallArtifact` 能进入 replay refs。
- source freshness 能在 API projection 中展示。
- execution fact 只能由 exchange-native source 满足。
- 超预算、超时、未授权 tool 都必须显式失败并进入 audit。
- 缺少真实 `ToolCallArtifact` 的 Worker contribution 不能进入 production candidate comparison，只能进入 audit note。

### 检查点三：前端全链路可视化升级

目标：

让评审在页面上不用读代码，也能看清一次 query/manual run 的真实 Agent/Skill/Gate 数据流。

建议后端文件：

- 修改 `src/crypto_manual_alert/storage/agent_audit_view.py`
- 可拆分到 `src/crypto_manual_alert/api/projections/agent_audit_view.py`
- 可继续拆为 `worker_projection.py`、`tool_projection.py`、`gate_projection.py`
- 修改 `src/crypto_manual_alert/storage/journal_rows.py`
- 修改 `src/crypto_manual_alert/api/routes_runs.py`
- 修改 `tests/storage/test_agent_audit_view.py`
- 修改 `tests/api/test_runs_routes.py`

建议前端文件：

- 拆分 `frontend/src/app/runs/[traceId]/page.tsx`
- 新建 `frontend/src/app/runs/[traceId]/agent-audit-panel.tsx`
- 新建 `frontend/src/app/runs/[traceId]/worker-matrix.tsx`
- 新建 `frontend/src/app/runs/[traceId]/tool-call-graph.tsx`
- 新建 `frontend/src/app/runs/[traceId]/source-freshness-panel.tsx`
- 新建 `frontend/src/app/runs/[traceId]/conflict-matrix.tsx`
- 新建 `frontend/src/app/runs/[traceId]/candidate-comparison.tsx`
- 修改 `frontend/src/lib/schemas/runs.ts`

后端 projection 必须先提供的一等字段：

- `tool_calls[]`：worker、skill_name、status、source_type、source_tier、retrieved_at、freshness_status、result_ref、output_hash、error。
- `evidence_sources[]`：evidence_ref、claim_ref、source_url、source_type、source_tier、observed_at、retrieved_at、freshness_status、can_satisfy_execution_fact。
- `source_freshness[]`：按 freshness/source tier 聚合，能显示缺失或 stale 的 execution fact。
- `root_cause_graph`：node、edge、layer、query、evidence_ref、confidence、fact_type。
- `conflict_edges[]`：worker_a、worker_b、claim/ref、conflict_type、severity。
- `strongest_counter_thesis_ref`：最强反向链路或缺失原因。
- `candidate_final_comparison`：只暴露脱敏 comparison，不暴露 raw candidate decision。
- `input_lineage`：哪些字段进入 final input，哪些只是 audit note。
- `release_eval_gate`：结构安全 gate 与金融质量 gate 的状态引用。

前端 schema 约束：

- `frontend/src/lib/schemas/runs.ts` 必须为上述核心字段建立 typed schema。
- 新增面板不得继续依赖 `z.record(z.unknown())` 承接核心数据。
- 可以保留 passthrough 用于兼容旧 trace，但关键验收字段缺失时测试必须失败。

页面必须展示：

- LeadPlan 任务拆分。
- Worker 并发执行状态。
- 每个 Worker 的贡献、缺失事实、冲突、hard block、confidence cap。
- Skill/tool 调用结果、来源、时间、新鲜度、hash/ref。
- 根因因果图。
- 情绪/拥挤度/反身性风险。
- legacy final 与 candidate final 对比。
- final input selection。
- gates 放行/阻断原因。
- release/eval gate 状态。

验收：

- 启动 API 和 frontend。
- 生成真实 trace。
- 打开 `/runs/{trace_id}`。
- 页面必须能看到 LeadPlan、7 个 Worker、Skill/tool refs、DecisionInput、candidate comparison、production_control_gate。
- local stack smoke 必须断言关键 UI 文本和 API 字段。
- 新增 `tool-call-graph`、`source-freshness-panel`、`conflict-matrix`、`candidate-comparison` 前，必须先有对应后端 projection 字段；禁止先做空壳 UI。

### 检查点四：建立金融预测质量评测

目标：

在现有结构安全 Eval 之外，新增金融预测结果评测，判断系统是否真的提高趋势预测质量。

建议文件：

- 新建 `src/crypto_manual_alert/eval/outcomes.py`
- 新建 `src/crypto_manual_alert/eval/outcome_store.py`
- 新建 `src/crypto_manual_alert/eval/prediction_metrics.py`
- 新建 `src/crypto_manual_alert/eval/market_outcome_collector.py`
- 新建 `src/crypto_manual_alert/eval/regime_slices.py`
- 新建 `src/crypto_manual_alert/eval/financial_quality_gate.py`
- 仅在需要引用状态时小改 `src/crypto_manual_alert/eval/runner.py`
- 不把金融指标直接塞进 `src/crypto_manual_alert/eval/release_gate.py` 的 hard gate；最多挂载独立 quality gate 的状态引用。
- 修改 `frontend/src/app/eval/page.tsx`
- 新增 `tests/eval/test_outcomes.py`
- 新增 `tests/eval/test_prediction_metrics.py`
- 新增 `tests/eval/test_financial_quality_gate.py`

核心数据结构：

- `DecisionOutcome`
- `OutcomeWindow`
- `PredictionQualityMetrics`
- `RegimeSlice`
- `FreshnessQualityMetric`

首批指标：

- action direction hit rate
- PnL estimate
- MFE
- MAE
- R multiple
- invalidation hit
- target hit
- Brier score
- calibration bucket
- latency/freshness penalty
- regime-sliced hit rate

评分定义必须先落地：

- 评测对象：legacy final、swarm candidate final、no-trade/hold baseline 必须分开记录。
- 时间窗口：至少定义 `1h`、`4h`、`24h` 或当前项目采用的固定窗口，窗口未成熟时标记 `pending_outcome`。
- 价格源：优先 exchange-native mark/index/candle；web/search-derived 价格不得作为 execution outcome。
- K 线粒度：记录 source、symbol、interval、collected_at、window_start、window_end。
- 成本假设：手续费、滑点、资金费率是否计入必须显式记录；缺失时写 `unscored_reason`。
- `no trade`、blocked action、缺 entry/stop/target 的决策必须有独立计分或 `unscored_reason`，不能混入交易命中率。
- Brier score 的标签事件必须明确，如“窗口内方向命中”或“目标先于失效触发”，不能直接使用泛化 `probability`。
- outcome collection 必须冻结、缓存、可重放；不得复用生产 `Journal.record_outcome()` 作为自动价格 outcome。
- market outcome collection 不在 replay/eval runner 中同步 live fetch；使用离线 collector 或明确的人工触发任务。

验收：

- 能从历史 plan_run 构建 outcome case。
- 能在无 live side effect 的情况下计算结果。
- release gate 能显示结构安全和金融质量是两类不同门禁；金融质量 gate 样本不足或窗口未成熟时不阻断结构安全门禁。
- 前端 Eval 页面能展示预测质量，而不是只展示 replay 是否通过。

### 检查点五：代码结构收敛

目标：

把仍然过大的文件按稳定边界拆分，删除或登记兼容层生命周期，避免后续多人评审时难以理解。

优先拆分：

- `skills/facade.py`
- `eval/release_gate.py`
- `eval/store.py`
- `eval/case_builder.py`
- `storage/agent_audit_view.py`
- `storage/journal.py`
- `workflow/legacy_decision_workflow.py`

验收：

- 每个新增文件职责一句话能说清。
- 每个拆分都有结构测试防止回流。
- legacy 相关代码集中到清晰位置。
- root package 不新增业务 `.py`。
- `tests/` 根目录不新增测试 `.py`。
- README、formal index、deployment 说明当前真实架构。

## 6. 每个检查点完成定义

每个检查点完成前必须满足：

- 有失败测试或结构护栏先行记录。
- 有最小实现，不扩大到后续检查点。
- 有明确修改文件列表。
- 有验证命令和结果。
- 有文档/migration 记录。
- 有前端变更时必须启动前后端做运行态自测。
- 有 production side effect 说明。
- 没有把 candidate/sidecar 伪装成 production。

## 7. 推荐执行顺序

当前建议从检查点一开始：

```text
检查点一：candidate final sidecar 与安全投影边界
  -> 检查点二：真实 SkillExecutor 与 ToolCallArtifact
  -> 检查点三：前端全链路可视化 projection 与 UI
  -> 检查点四：金融预测质量评测
  -> 检查点五：代码结构收敛
```

如果执行中发现某个大文件阻碍当前检查点，可以在当前检查点内做最小拆分；不单独为了“看起来整洁”提前重构。结构收敛不全部推迟到检查点五：谁被当前检查点扩展，谁先做最小边界拆分，避免继续扩大大文件。

## 8. 汇报模板

每完成一个检查点或小闭环，按以下模板汇报：

```text
当前检查点:
当前小闭环:
完成项:
修改文件:
测试或结构护栏是否先写:
验证命令:
结果:
生产默认链路是否仍可回到 legacy:
是否有副作用风险:
未完成项:
是否触发暂停条件:
下一步:
```

## 9. 暂停规则

立即暂停的情况：

- 同一测试连续失败 3 次。
- 同一导入边界连续失败 3 次。
- 同一设计冲突连续失败 3 次。
- 为了通过测试需要删除关键测试或绕过结构护栏。
- 发现 candidate/eval/replay 产生生产 journal、notification 或 live order 副作用。
- 发现需要打开 `decision.final_input_mode=decision_input` 才能继续。

暂停时必须记录：

- 失败现象。
- 已尝试方案。
- 当前证据。
- 可选方案。
- 需要用户决策的问题。

## 10. 当前执行状态

检查点一已经完成第一批小闭环：

- `decision_control_step` 会把 `run_candidate_final_decision_sidecar()` 结果传入 candidate audit payload。
- candidate final 只消费净化后的 `DecisionInput`，会剥离 legacy prompt/raw/frozen 字段。
- 默认生产链路仍是 legacy final input，不切换 `decision.final_input_mode`。
- API projection 可以展示脱敏 `candidate_final_comparison`，且不暴露 raw candidate decision。
- 没有真实 `ToolCallArtifact` 时，comparison 状态是 `audit_only`。
- migration 记录见 `docs/migration/2026-07-04-checkpoint-1-candidate-final-sidecar.md`。

检查点二已经完成后端受控 Skill/Artifact 小闭环：

- 新增 `ToolCallArtifact`、`ToolBudget`、`SourceFreshness`、`SkillExecutor` 和默认 `skills.registry`。
- 默认 Skill registry 收敛到业务 Skill 名称：`realtime_search`、`root_cause_search`、`market_sentiment`、`macro_event`、`liquidity_order_book`。
- Harness/LeadPlan 的 llm tool shadow allowlist 已从底层 `web_search` 切换到业务 Skill 名称；旧 `FixtureShadowToolExecutor(web_search)` 只保留为隔离兼容对象，不再接入 `LlmToolShadowWorker` 主通道。
- `LlmToolShadowWorker` 只接受 `skill_requests` 经 `SkillExecutor` 生成 `ToolCallArtifact`，并把 refs 写入 `AgentContribution.tool_call_artifact_refs`；旧 `tool_requests` 会硬拒绝，模型伪造的 tool artifact 字段会被剥离。
- `ToolCallArtifact` 已进入 `DecisionInput.contribution_refs[*].tool_call_artifact_refs`、`replayable_input_candidate.artifact_refs.worker_result_manifest[*].tool_call_artifact_refs`、`RunContext.artifact_summary.contribution_refs[*].tool_call_artifact_refs` 和 `agent_audit_view.workers[*].tool_call_artifact_refs`；旧 `tool_audit_result_refs` 不再进入 replay/API 主 projection。
- `pre_final_input_gate` 已验证 execution fact 防火墙：只有 `source_type=exchange_native` 且 `freshness_status=fresh` 的 artifact 才能满足 execution fact。
- `run_pre_final_orchestration()` 已具备显式 `tool_executor` 注入入口；llm tool worker registry 在未显式传 executor 时默认注入 `SkillExecutor(build_default_skill_registry())`。
- production 默认仍保持 `legacy_prompt`，candidate/swarm 仍是 `decision_effect=none`，不会写生产最终输入、通知或订单。
- 新增结构护栏 `tests/structure/test_skill_executor_boundaries.py`，防止 `tool_requests`、`tool_name`、`tool_audit_results` 回流到 LLM worker、replay manifest 和 agent audit projection 主通道。
- migration 记录见 `docs/migration/2026-07-04-checkpoint-2-skill-executor-tool-artifacts.md`。

检查点二未完成或只完成结构边界的部分：

- `RootCauseSearchSkill` 仍是受控契约和 artifact 边界，尚未实现真实递归 web searched 检索。
- `RealtimeSearchSkill` 仍消费输入视图中已有搜索结果，尚未直接调大模型 web search 或外部实时搜索源。
- `MacroEventSkill`、`MarketSentimentSkill`、`LiquidityOrderBookSkill` 仍主要表达来源类型、约束和 artifact 边界，真实数据源接入需要在后续 Skill 实现里补齐。
- 当前后端 projection 只把 `tool_call_artifact_refs` 挂在 worker/DecisionInput/replay/context 中，还没有提供检查点三要求的一等 `tool_calls[]`、`source_freshness[]`、`root_cause_graph`、`conflict_edges[]`、`input_lineage` 和 `release_eval_gate`。
- 前端还没有消费本次新增的 canonical `tool_call_artifact_refs` 字段，也没有完成 tool call graph/source freshness/root cause graph 的页面自测。
- 金融预测质量评测仍未开始，不能用当前结构测试代表收益或预测准确率提升。

检查点三已经完成第一批可观测小闭环：

- `agent_audit_view` 已新增一等 projection 字段：`tool_calls[]`、`evidence_sources[]`、`source_freshness[]`、`root_cause_graph`、`conflict_edges[]`、`strongest_counter_thesis_ref`、`input_lineage`、`release_eval_gate`。
- 后端 projection 已拆出到 `src/crypto_manual_alert/storage/agent_audit_projection/`，避免继续扩大 `storage/agent_audit_view.py`。
- 前端 `runs.ts` 已为核心字段建立 typed schema，不再靠 `z.record(z.unknown())` 承接这些验收字段。
- `/runs/{trace_id}` 已拆出 Agent Audit 组件并展示 LeadPlan、Worker Matrix、Skill Tool Calls、Source Freshness、Root Cause Graph、Conflict Matrix、Candidate Comparison、Input Lineage、Release/Gate 状态。
- 本地栈 smoke 已通过，运行态 trace 可打开页面验证。migration 记录见 `docs/migration/2026-07-04-checkpoint-3-agent-audit-observability.md`。

检查点三剩余限制：

- 默认 `shadow.worker_mode=local_audit` 不会伪造 SkillExecutor 调用，因此真实运行 trace 的 `tool_calls[]` 可以为空；只有启用 `llm_tool_shadow` 并真实走 SkillExecutor 时才会出现非空 tool refs。
- `RootCauseSearchSkill` 的真实递归 web searched 检索仍未实现。
- 金融预测质量评测仍未开始，`release_eval_gate.financial_quality_gate.status` 当前应保持 `not_configured`。

下一步执行检查点四：建立金融预测质量评测。开始写代码前必须先定义 outcome、窗口、价格源、计分规则和独立 financial quality gate 测试，避免把金融质量混进结构安全 release gate。

检查点四已经完成第一批离线评测小闭环：

- 新增 `eval/outcomes.py`，定义 `OutcomeWindow` 与 `DecisionOutcome`，明确 exchange-native 价格源、窗口成熟度、`no_trade`、缺交易价位等不可计分原因。
- 新增 `eval/prediction_metrics.py`，支持按 `legacy_final`、`swarm_candidate_final` 等目标分别计算 direction hit rate、target hit rate、invalidation hit rate、PnL pct、R multiple、Brier score。
- 新增 `eval/financial_quality_gate.py`，作为独立金融质量 gate，不塞进结构安全 `release_gate.py`。
- 新增 `eval/outcome_store.py`，用独立 SQLite 表存储冻结后的 decision outcome，不复用生产 journal outcome。
- 新增 `eval/market_outcome_collector.py`，从已经收集好的 candle rows 构建 `OutcomeWindow`，不在 eval runner 内同步 live fetch。
- 新增 `eval/regime_slices.py`，按市场状态切片复用同一套金融质量指标。
- 新增测试 `tests/eval/test_outcomes.py`、`tests/eval/test_prediction_metrics.py`、`tests/eval/test_financial_quality_gate.py`，并在 `tests/eval/test_eval_package_structure.py` 增加结构护栏。
- 新增测试 `tests/eval/test_outcome_store.py`、`tests/eval/test_market_outcome_collector.py`、`tests/eval/test_regime_slices.py`。
- migration 记录见 `docs/migration/2026-07-04-checkpoint-4-financial-quality-eval-slice.md`。

检查点四剩余限制：

- 还没有定时或 API 触发的 `OutcomeCollector`。
- 还没有真正的 exchange API adapter；当前 collector 只消费调用方传入的 candle rows。
- 还没有 freshness quality metric。
- 还没有把 financial quality gate 接入 `EvalRunner` metadata 和前端 Eval 页面。
- 当前 `/runs/{trace_id}` 的 `release_eval_gate.financial_quality_gate` 仍应在没有持久化金融质量结果时显示 `not_configured`。

## 11. 当前目标执行 checklist

本轮目标不是继续写抽象文档，而是把前面暴露出的主流程问题落到可验证代码和页面上。执行顺序固定为：

1. 检查点三：先补后端一等 projection，再让前端消费真实字段。
2. 检查点四：建立金融预测质量评测，证明不是只有结构安全测试。
3. 检查点五：围绕已触碰的大文件做边界拆分和结构护栏，不做无目标搬家。

### 11.1 检查点三执行清单

- [x] 在 `tests/storage/test_agent_audit_view.py` 先补失败测试，要求 `agent_audit_view` 输出一等字段：`tool_calls[]`、`evidence_sources[]`、`source_freshness[]`、`root_cause_graph`、`conflict_edges[]`、`strongest_counter_thesis_ref`、`input_lineage`、`release_eval_gate`。
- [x] 在 `tests/api/test_runs_routes.py` 补 API 级断言，确保真实 manual run 的 `/api/runs/{trace_id}` 返回上述字段，而不是只返回 worker 内嵌 refs。
- [x] 在 `src/crypto_manual_alert/storage/agent_audit_view.py` 做最小 projection 实现；如文件继续膨胀，先拆到 `src/crypto_manual_alert/storage/agent_audit_projection/` 下的专责文件。
- [x] projection 只能输出脱敏 ref/hash/source/freshness/status，不输出 raw prompt、raw candidate、raw skill payload、snippet、error_message。
- [x] `release_eval_gate` 必须显式区分结构安全 gate 与金融质量 gate；金融质量尚未建立时标记为 `not_configured` 或 `not_enough_samples`，不能伪装成已通过。
- [x] `input_lineage` 必须明确生产 final input 仍是 `legacy_prompt`，Agent Swarm/DecisionInput/candidate final 当前是 audit/candidate 路径。
- [x] 更新 `frontend/src/lib/schemas/runs.ts`，为核心字段建立 typed schema；不得继续靠 `z.record(z.unknown())` 承接验收字段。
- [x] 拆分或整理 `frontend/src/app/runs/[traceId]/page.tsx`，让页面看到 tool call、source freshness、root cause、conflict、candidate comparison、gate/input lineage。
- [x] 启动 API 和前端，生成真实 trace，自测 `/runs/{trace_id}`。页面必须能看到 LeadPlan、7 个 Worker、Skill/tool refs、DecisionInput、candidate comparison、production_control_gate。
- [x] 写 migration 记录，说明 production 默认链路仍是 legacy，Swarm/Skill/candidate 仍无生产副作用。

### 11.2 检查点四执行清单

- [x] 先在 `tests/eval/` 定义 outcome、窗口、价格源、no trade/blocked action、Brier label 和成本假设的失败测试。
- [x] 新增 `eval/outcomes.py`、`eval/prediction_metrics.py`、`eval/financial_quality_gate.py` 等小模块，不把金融质量逻辑塞进现有结构安全 release gate。
- [x] 金融质量 gate 只作为独立状态引用进入 release/eval 展示；样本不足或窗口未成熟时不阻断结构安全 gate。
- [x] 对 legacy final、swarm candidate final、no-trade/hold baseline 分开计分。
- [x] 不在 replay/eval runner 中同步 live fetch；价格 outcome 通过离线 collector 或人工触发任务进入可重放存储。
- [x] 把离线 `OutcomeStore` 中已经冻结的 `DecisionOutcome` 汇总为 `EvalRun.metadata.financial_quality_gate`，并明确 `structural_release_gate_blocking=false`，证明金融质量不混入结构安全 hard gate。
- [x] 给 `EvalRunner` 增加只读 outcome store 注入点；没有 outcome store 时显示 `not_configured`，没有足够样本时显示 `not_enough_samples`，不得在 eval run 内触发 live fetch。
- [x] 更新 `frontend/src/lib/schemas/eval.ts` 和 `frontend/src/app/eval/page.tsx`，让 Eval 工作台展示金融质量目标、样本量、命中率、Brier、PnL/R multiple 和 gate 状态。
- [x] local stack smoke 至少断言 Eval 页面存在金融质量面板；API detail 需要暴露脱敏后的 `financial_quality_gate` metadata。
- [x] 写 migration 记录，说明金融质量 gate 是滞后评测与候选提升参考，不是即时生产下单或结构安全 hard gate。

### 11.3 检查点五执行清单

- [ ] 只拆当前 checkpoint 实际扩展到的大文件；优先 `storage/agent_audit_view.py`、`frontend/src/app/runs/[traceId]/page.tsx`、`skills/facade.py`、`eval/release_gate.py`。
- [x] 每次拆分必须有结构测试防止业务 `.py` 回流到项目根目录或 `src/crypto_manual_alert/*.py` 根包。
- [x] legacy、compatibility、fixture 命名必须有生命周期说明，避免 reviewer 误以为旧路径仍是生产主链路。
- [x] README、deployment、formal index 最后同步当前真实架构，不提前宣称生产切换完成。

检查点五第一批结构收敛小闭环已经完成：

- `frontend/src/app/eval/page.tsx` 拆出候选 case、Replay、Judge 和 Financial Quality 组件，主页面从 372 行降到 186 行。
- 新增 `tests/structure/test_frontend_route_boundaries.py`，防止 Eval 页面和 Run Detail 页面重新膨胀为黑盒。
- `src/crypto_manual_alert/eval/store.py` 拆出 `eval/store_schema.py`，主文件从 591 行降到 434 行，结构测试禁止 SQL DDL 回流。
- `src/crypto_manual_alert/skills/facade.py` 拆出 `skills/contracts.py`、`skills/contract_policy.py` 和 `skills/contract_validation.py`，主文件从 596 行降到 157 行，具体 Skill facade 与契约/校验职责分离。
- 新增根包 `__init__.py` 结构护栏，禁止根包导入业务模块。
- README、deployment、formal index 和 compatibility wrapper lifecycle 已同步当前真实状态：34 是当前执行入口，生产默认仍是 `legacy_prompt`。
- migration 记录见 `docs/migration/2026-07-04-checkpoint-5-structure-convergence-slice.md`。

检查点五剩余限制：

- `eval/release_gate.py`、`eval/case_builder.py`、`storage/agent_audit_view.py`、`storage/journal.py` 和 `workflow/legacy_decision_workflow.py` 仍然偏大。
- 后续只在有明确边界和测试时继续拆分，不做无目标搬家。

### 11.4 本轮执行纪律

- [ ] 每个小闭环先写失败测试或结构护栏，再写实现。
- [ ] 每完成一个 checkpoint 或可验证小闭环汇报一次。
- [ ] 同一问题连续失败 3 次立即暂停，记录失败现象、已尝试方案、当前证据和需要决策的问题。
- [ ] 不切换 `decision.final_input_mode=decision_input`。
- [ ] 不引入订单、通知、journal production side effect。

## 12. 当前复盘与目标重置

本节记录 2026-07-04 对当前代码、文档、业务流程和页面可观测性的复盘结论。后续执行必须先满足本节的主流程验收，避免继续把工作推进成“文档和结构测试很多，但生产级 Agent Swarm 主链路没有实质提升”。

### 12.1 已跑通的真实业务链路

本轮使用默认 fixture 配置执行过一次主流程：

```powershell
python -m crypto_manual_alert.cli run-once --symbol BTC-USDT-SWAP
python -m crypto_manual_alert.cli trace-list --limit 1
```

观察到的事实：

- trace_id: `0b7866319b4145c1bd825d84e2138fc8`。
- trace symbol 是 `BTC-USDT-SWAP`，但 fixture final plan instrument 是 `ETH-USDT-SWAP`。
- 生产链路生成 17 个 span：`market.fetch`、`skill.load`、`prompt.build`、`input.freeze`、`decision_input.pre_final`、7 个 `shadow_swarm.worker`、`decision.final`、`parser.strict_json`、`production_control.check`、`risk.check`、`journal.write`。
- `agent_audit_view.available=true`。
- 7 个 Worker Agent 均有 contribution：`LiveFactAgent`、`DerivativesAgent`、`MacroEventAgent`、`RootCauseAgent`、`MarketSentimentAgent`、`DataQualityAgent`、`ExecutionRiskAgent`。
- `tool_calls.length=0`，说明默认 `local_audit` 路径没有真实 SkillExecutor 调用。
- `input_lineage.production_final_input_mode=legacy_prompt`，`DecisionInput` 没有成为生产 final input。
- `candidate_final_comparison.status=audit_only`，candidate final 因 input gate failed 没有产出可比较 action。
- `release_eval_gate.financial_quality_gate.status=not_configured`。
- final verdict 被 production control 阻断，原因包括 legacy action 不在 candidate allowed actions、概率超过 candidate cap、worker hard block。

这次 smoke 证明：后端结构链路和 audit projection 能跑通，但不能证明已经完成生产级 Agent Swarm、真实 Skill 接入、实时 web searched、金融预测质量评测或前端可观测闭环。

### 12.2 对抗审查结论

#### 后端主流程审查

当前真实链路仍是：

```text
POST /api/runs/manual
  -> DecisionRequest
  -> DecisionRunContext
  -> RunExecutor
  -> LegacyPlanRunnerAdapter
  -> PlanRunner
  -> LegacyDecisionWorkflow
  -> market.fetch / research / legacy prompt
  -> shadow pre-final audit
  -> legacy FinalDecisionAgent
  -> parser
  -> production_control_gate + risk gate
  -> journal
  -> API projection
```

问题：

- 默认 `workflow.execution_mode=legacy_baseline`，`decision.final_input_mode=legacy_prompt`，不是生产候选 Agent Swarm 主链。
- `controlled_shadow` adapter 只是 blocked audit-only 记录，不是可替代生产链路。
- `decision_control_step` 当前用 `plan.instrument` 构建 candidate audit symbol，容易掩盖 request symbol 与 plan instrument 不一致。
- `RiskGate` 只校验 instrument 是否在 allowed list，没有显式校验 `DecisionRequest.symbol == DecisionPlan.instrument`。
- 页面 runtime_flow 由 `agent_audit_view._runtime_flow()` 静态生成，不是从真实 span tree 动态构造。

必须补齐：

- 请求品种与最终计划品种一致性硬门禁。
- candidate audit、production control、页面 projection 都必须同时显示 request symbol、snapshot symbol、plan instrument。
- 主流程 smoke 必须断言以上三者一致；不一致时必须 blocked，并在页面红色展示。

#### Agent/Skill 审查

当前 `skills/` 更像 skill runtime 和 contract layer，不像生产级业务 Skill package。当前已有：

- `RealtimeSearchSkill`
- `RootCauseSearchSkill`
- `MarketSentimentSkill`
- `MacroEventSkill`
- `LiquidityOrderBookSkill`

问题：

- 这些 Skill 仍集中在 `skills/facade.py`，没有按业务 Skill 建目录。
- `RootCauseSearchSkill` 只声明递归约束，没有真实递归检索。
- `RealtimeSearchSkill` 只消费 input_view 里的已有 search results，不主动触发实时 web searched。
- `MarketSentimentSkill`、`MacroEventSkill`、`LiquidityOrderBookSkill` 仍以 contract/facade 为主，没有稳定真实数据源适配。
- 默认 `shadow.worker_mode=local_audit`，不会产生 `ToolCallArtifact`，所以页面 `tool_calls[]` 可以为空。
- `market_agents/` 和 `agent_swarm/local_workers/` 并存，评审者难以判断真实业务 worker owner。

目标结构：

```text
skills/
  registry.py
  executor.py
  contracts.py
  realtime_search/
    skill.py
    adapters.py
    schemas.py
  root_cause/
    skill.py
    graph.py
    recursion_policy.py
    schemas.py
  sentiment_crowding/
    skill.py
    signals.py
    schemas.py
  macro_event/
    skill.py
    source_policy.py
    schemas.py
  liquidity_order_book/
    skill.py
    exchange_adapters.py
    schemas.py
```

约束：

- Skill 只能返回 `SkillToolResult` 或 `ToolCallArtifact`，不能返回最终交易动作，不能写 journal，不能发通知。
- Worker 必须通过 `SkillExecutor` 获取事实和工具结果，不能绕过 tool artifact 直接把 raw snippet 写进 contribution。
- `search_derived` 永远不能满足 mark/index/order_book 等 execution facts。

#### 前端可观测审查

当前 `/runs/{trace_id}` 已展示 Trace summary、Span Timeline、LLM Requests、Agent Swarm Audit、LeadPlan、Worker Matrix、ToolCallGraph、SourceFreshness、RootCauseGraph、ConflictMatrix、CandidateComparison、InputLineage、Gate 状态。

问题：

- 页面更像日志浏览器和审计说明页，不是主流程驾驶舱。
- `Runtime Flow` 是静态说明，不是每次 run 的真实 step graph。
- 默认 run 的 `tool_calls[]` 为空，页面不能证明真实 Skill 发生过。
- 大量 JSON/code box 对管理者和用户不友好；需要把关键阻断原因、缺失事实、是否进入最终输入、是否可生产切换做成一眼可读状态。
- 页面必须明确显示“当前生产 final input 仍是 legacy_prompt”，避免把 shadow audit 误读为已接管生产。

必须补齐：

- 基于真实 spans 和 artifact refs 构建 Run Flow graph。
- 每个 step 展示 owner、input refs、output refs、status、duration、gate effect。
- 将 `tool_calls=0` 作为醒目状态，而不是静默空表。
- 将 request/plan symbol mismatch、worker hard block、candidate gate failed、financial quality not configured 作为页面首屏风险信号。

#### Eval/测试审查

当前 collect-only 共有 842 个测试项，结构/边界测试占比高。

问题：

- 结构护栏有价值，但不能替代端到端主流程验收。
- checkpoint 执行中容易把时间花在过深的结构拆分和局部测试上，主流程和页面没有成为硬门。
- 金融质量模块已有 outcome、metrics、store、gate 雏形，但真实 run detail 仍显示 `financial_quality_gate=not_configured`。
- outcome collector 没有定时任务、API 触发或真实 exchange adapter，金融质量评测还不是闭环。

新的测试策略：

- 每个 checkpoint 必须先跑一个主流程 smoke：`run-once -> trace detail -> agent_audit_view 核心字段断言`。
- 有前端改动时必须启动 API 和前端，做页面可见性 smoke。
- 单点修改只跑相关单测和结构测试；全量测试作为阶段性 release gate，不作为每个小闭环默认动作。
- 任何测试不能通过“降低 required worker、关闭 gate、隐藏字段缺失”来换取通过。

#### 代码结构审查

根包业务 `.py` 已基本清理，但仍存在可维护性问题：

- `eval/release_gate.py`、`storage/agent_audit_view.py`、`eval/case_builder.py`、`storage/journal.py`、`eval/store.py`、`artifacts/evidence.py` 等仍偏大。
- `skills/` 没有按业务能力建子包。
- compatibility wrapper 生命周期已经有文档，但代码中仍有 `agent_swarm/local_workers` 与 `market_agents` 并存的理解成本。
- 后续拆分不能继续无目标搬家，必须服务主流程和评审可读性。

### 12.3 新的最终目标

最终目标不是“把所有模块拆得更细”，而是交付一个可被评审、可被页面观察、可被 gate 控制的生产候选 Agent Swarm：

```text
Manual Query
  -> DecisionRequest / DecisionRunContext
  -> exchange-native Fact Pack
  -> LeadAgent 生成受控 LeadPlan
  -> Worker Agents 并行执行
  -> Worker 通过 SkillExecutor 调用真实 Skill
  -> ToolCallArtifact / EvidencePacket / AgentContribution
  -> Harness / FactsGate / DataQualityGate
  -> LeadAgent synthesis
  -> DecisionInput
  -> candidate FinalDecisionAgent sidecar
  -> candidate parse / semantic / risk / production control gates
  -> legacy final comparison
  -> release/eval quality view
  -> 前端全链路可观测
```

完成定义：

- 一个真实 manual run 页面能看到请求、事实、每个 worker、每个 skill/tool call、每个 gate、最终输入选择和阻断原因。
- 默认仍不自动切换生产 final input；切换只能通过明确人工 release review。
- legacy final 是 fallback 和对照基线，不再是唯一有实际输出的主链。
- Skill 至少有一个真实实时检索闭环和一个 exchange-native execution fact 闭环。
- 金融质量评测能从历史 run 生成 outcome，并与结构安全 gate 分开展示。

### 12.4 下一阶段检查点

#### 检查点六：主流程一致性和可观测硬门禁

目标：先修正主流程可控性问题，不继续堆新抽象。

必须完成：

- 增加 request symbol、snapshot symbol、plan instrument 一致性检查。
- 一致性失败必须进入 `RiskVerdict.rule_hits` 或 `production_control_gate`，并阻断可执行动作。
- `candidate_audit` 和 `agent_audit_view` 同时暴露 request symbol、snapshot symbol、plan instrument。
- `Runtime Flow` 改为优先基于真实 spans 和 artifact refs 生成；静态 fallback 必须标记为 fallback。
- 新增 smoke 断言：run-once 后 `agent_audit_view` 有 7 workers、input lineage、gate 状态、symbol consistency 字段。

验收命令：

```powershell
python -m pytest tests/workflow/test_run_executor.py tests/workflow/test_decision_control_step.py tests/storage/test_agent_audit_view.py tests/api/test_runs_routes.py -q
python -m crypto_manual_alert.cli run-once --symbol BTC-USDT-SWAP
python -m crypto_manual_alert.cli trace-list --limit 1
```

#### 检查点七：Skill 业务包化和真实工具闭环

目标：把 `skills/facade.py` 拆成业务 Skill package，并至少完成真实工具调用闭环。

必须完成：

- 按 12.2 的目录结构拆分 skill。
- `realtime_search` 接入可注入的 web search provider；默认测试使用 fixture provider，生产配置显式启用。
- `root_cause` 实现受控递归策略：`max_depth`、`max_branch_count`、`deadline`、`tool_budget`。
- `liquidity_order_book` 接入 exchange-native provider 或明确 fixture adapter，能产出 `source_type=exchange_native` 的 `ToolCallArtifact`。
- 默认 local_audit 不伪造 tool calls；启用 llm/tool shadow 的集成测试必须能产生非空 `tool_calls[]`。

验收：

- Worker 只能通过 `SkillExecutor` 获取 tool artifact。
- 未授权 skill、超预算、超时必须进入 failed audit。
- `search_derived` 不能满足 execution facts 的测试继续存在。

#### 检查点八：生产候选 Agent Swarm 主链

目标：让 Agent Swarm 从 shadow audit 进入生产候选链路，但不自动替换生产 final input。

必须完成：

- 新增清晰执行模式，例如 `production_candidate_swarm`，区别于 `legacy_baseline` 和 `controlled_shadow`。
- candidate FinalDecisionAgent 只能消费 `DecisionInput`。
- legacy final、candidate final、production control gate 在同一 trace 中可比较。
- candidate final 有真实 Skill/ToolCallArtifact 支撑时，状态从 `audit_only` 升级为 `production_candidate`；否则继续 audit_only。

禁止：

- 不默认设置 `decision.final_input_mode=decision_input`。
- 不把 candidate 写成生产 final result。
- 不发送通知或订单。

#### 检查点九：前端主流程驾驶舱

目标：页面能让用户和管理者看清每一步真实交互，而不是读 JSON。

必须完成：

- 首屏风险摘要：symbol mismatch、tool_calls 为空、candidate gate failed、worker hard block、financial quality not configured。
- Run Flow graph 基于真实 spans。
- Worker/Skill/Gate/Input Lineage 形成可点击或可展开的链路。
- JSON 只作为辅助，不作为主要信息表达。

验收：

- 启动 API 和 frontend。
- 生成真实 trace。
- 页面能看到 7 workers、tool call 状态、input lineage、production final input mode、candidate comparison、gate block reasons。

#### 检查点十：金融质量闭环

目标：让金融质量评测从离线模块变成可运行闭环。

必须完成：

- outcome collector 有显式命令或 API 触发入口。
- exchange-native candle/mark/index 来源进入 outcome store。
- Eval 页面展示 legacy final、candidate final、baseline 的样本量、命中率、Brier、PnL/R multiple、未成熟窗口。
- `financial_quality_gate` 不阻断结构安全 gate，但必须作为 release review 必看项。

### 12.5 执行纪律

- 每个 checkpoint 必须先跑主流程 smoke，再做局部实现。
- 每完成一个 checkpoint 或小闭环必须按第 8 节模板汇报。
- 同一问题连续失败 3 次暂停，不再无限重试。
- 不再把“文档完成”“结构测试完成”“文件搬家完成”单独作为生产级完成标准。
- 如发现主流程和页面验收不成立，优先修主流程，不继续扩展旁路模块。

### 12.6 检查点六执行记录

第一段小闭环已经完成：symbol consistency hard gate。

完成项：

- `decision_control_step` 增加 request symbol、snapshot symbol、final plan instrument 一致性检查。
- 不一致时生成 `production_control.symbol_consistency.mismatch` critical blocking rule hit。
- `candidate_audit` 和 `agent_audit_view` 暴露 `symbol_consistency`。
- 前端 `runs.ts` 增加 typed schema，Run Detail 的 Agent Audit 首屏显示 `Symbol Check`。
- 用 fixture 主流程复现 BTC 请求 / ETH plan 的 mismatch，已能在 verdict 和 API projection 中看到明确阻断。

验证：

```powershell
python -m pytest tests/workflow/test_decision_control_step.py tests/storage/test_agent_audit_view.py tests/api/test_runs_routes.py -q
npm run typecheck
python -m crypto_manual_alert.cli run-once --symbol BTC-USDT-SWAP
```

当前证据：

- latest smoke trace: `2f1e485b0c3f4d28a9bbd548ac32c155`
- `symbol_consistency.consistent=false`
- blocking rule ids 包含 `production_control.symbol_consistency.mismatch`
- runtime UI smoke trace: `445061af25144256abe3ad7c0bb05be7`
- `/runs/{trace_id}` 返回 HTTP 200，页面包含 `Symbol Check`、`mismatch` 和 `ETH-USDT-SWAP`
- runtime-flow smoke trace: `18cc5c8f84fd43df82c5ed609e940fc4`
- `runtime_flow[0].source=span_tree_refs`，页面包含 `market.fetch` 和 `span_tree_refs`
- span-ref smoke trace: `9e0854effea44818a3d3d8db67c921e2`
- `runtime_flow[0]` 包含 `span_input_hash`、`span_output_hash`、`input_refs.symbol` 和 `output_refs.symbol`
- `agent_audit_view` 不包含 `frozen_input` 字样
- migration 记录：`docs/migration/2026-07-04-checkpoint-6-symbol-consistency-gate.md`

检查点六剩余：

- `runtime_flow` 已优先基于真实 spans，并有安全 input/output hash/ref；下一步继续补 gate、worker contribution、tool call artifact 的领域级跳转引用。

### 12.7 检查点七执行记录

第一段小闭环已经完成：`llm_tool_shadow` 可在 fixture 决策引擎下通过主 API 链路产出真实 `ToolCallArtifact`。

完成项：

- `build_shadow_worker_registry()` 保持默认 `local_audit` 不变。
- `shadow.worker_mode=llm_tool_shadow` 仍然优先要求显式 `llm_client_factory`。
- 仅当 `decision.engine=fixture` 且没有显式 factory 时，自动注入 deterministic fixture shadow client。
- fixture shadow client 会让 `RootCauseAgent`、`MarketSentimentAgent`、`ExecutionRiskAgent` 分别请求 `root_cause_search`、`market_sentiment`、`liquidity_order_book`。
- Worker 仍通过 `LlmToolShadowWorker -> SkillExecutor` 执行 skill，并由 `agent_audit_view.tool_calls[]` 投影，未改变 final decision 输入模式。

验证：

```powershell
python -m pytest tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls -q
python -m pytest tests/api/test_runs_routes.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_llm_tool_worker.py -q
```

当前证据：

- 聚焦 API 红绿测试已覆盖 `/api/runs/manual -> /api/runs/{trace_id} -> agent_audit_view.tool_calls[]`。
- 小范围回归结果：30 passed。
- 临时主链路 smoke trace: `9c65bdc62c40485c81d21f9a60569700`
- smoke 结果包含 7 个 workers。
- smoke `tool_calls` 包含 `root_cause_search`、`market_sentiment`、`liquidity_order_book`。
- `liquidity_order_book` 标记为可满足 execution fact 的 tool call。
- migration 记录：`docs/migration/2026-07-05-checkpoint-7-llm-tool-shadow-skill-artifacts.md`

检查点七剩余：

- `skills/facade.py` 仍未按业务 skill package 拆分。
- `root_cause_search` 仍是受控 facade/contract，不是真实递归检索闭环。
- `realtime_search` 仍未接入可配置实时 web search provider。
- 当前完成的是 fixture 安全链路，不是生产外部 LLM 或实时市场数据链路。

### 12.8 检查点七第二段执行记录

第二段小闭环已经完成：业务 Skill 从单个 `skills/facade.py` 拆成按能力命名的 package，保持外部兼容导出不变。

完成项：

- 新增 `skills/realtime_search/skill.py`。
- 新增 `skills/root_cause/skill.py`。
- 新增 `skills/sentiment_crowding/skill.py`。
- 新增 `skills/macro_event/skill.py`。
- 新增 `skills/liquidity_order_book/skill.py`。
- 新增 `skills/_shared.py` 放置共同的结果构造、约束构造、search result 清理和 missing input 逻辑。
- `skills/facade.py` 改为稳定兼容导出层，不再定义具体业务 Skill class。
- `skills/registry.py` 改为从业务 skill package 导入实现。
- 增加结构测试，约束后续新增业务 skill 必须按能力 package 放置。

验证：

```powershell
python -m pytest tests/structure/test_skill_runtime_boundaries.py::test_business_skills_are_packaged_by_capability -q
python -m pytest tests/skills tests/structure/test_skill_runtime_boundaries.py tests/agent_swarm/test_registry.py tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls -q
```

当前证据：

- 业务 skill package 结构测试通过。
- skills 契约、结构边界、registry 和 API 聚焦链路测试通过。
- 临时主链路 smoke trace: `441a805597b54459aeef8aaa34bbe974`
- smoke 结果包含 7 个 workers。
- smoke `tool_calls` 包含 `root_cause_search`、`market_sentiment`、`liquidity_order_book`。
- `liquidity_order_book` 仍能作为 execution fact tool call 投影。
- migration 记录：`docs/migration/2026-07-05-checkpoint-7-skill-package-split.md`

检查点七剩余：

- `root_cause_search` 仍是受控 contract/facade，不是真实递归检索闭环。
- `realtime_search` 仍未接入可配置实时 web search provider。
- `liquidity_order_book` 仍需要真实 exchange-native provider 或清晰 fixture adapter 边界。
- 当前拆分只解决可读性和职责边界，不宣称实时数据能力已经完成。

### 12.9 检查点七第三段执行记录

第三段小闭环已经完成：`llm_tool_shadow` 模式下 `LiveFactAgent` 进入受控 tool worker 链路，并通过 `SkillExecutor` 调用 `realtime_search`。

完成项：

- `RealtimeSearchSkill` 增加可注入 `SearchProvider` 边界。
- 默认 `RealtimeSearchSkill` 仍回退到 `input_view.search_results`，兼容已有 fixture 和测试。
- 新增 `SearchProviderRequest`，把 `symbol`、`query`、`trace_id`、`task_id` 和 `max_results` 显式传给 provider。
- `build_llm_tool_shadow_worker_registry()` 在 `llm_tool_shadow` 模式下将 `LiveFactAgent` 注册为 `LlmToolShadowWorker`。
- fixture shadow client 为 `LiveFactAgent` 请求 `realtime_search`。
- API 主链路测试要求 `tool_calls[]` 同时包含 `realtime_search`、`root_cause_search`、`market_sentiment` 和 `liquidity_order_book`。

验证：

```powershell
python -m pytest tests/skills/test_realtime_search_provider.py -q
python -m pytest tests/agent_swarm/test_registry.py tests/agent_swarm/test_llm_tool_worker.py tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls tests/skills -q
```

当前证据：

- provider 契约测试通过。
- agent_swarm/API/skills 小范围回归通过。
- 临时主链路 smoke trace: `24a64472c5d343269b060a06f06563df`
- smoke 结果包含 7 个 workers。
- smoke `tool_calls` 包含 `realtime_search`、`root_cause_search`、`market_sentiment`、`liquidity_order_book`。
- `LiveFactAgent.tool_call_artifact_count=1`。
- `liquidity_order_book` 仍是唯一可满足 execution fact 的 tool call。
- migration 记录：`docs/migration/2026-07-05-checkpoint-7-livefact-realtime-search.md`

检查点七剩余：

- 还没有真实外部 web search provider 配置和生产启用开关。
- `root_cause_search` 还没有递归因果检索闭环。
- `liquidity_order_book` 还没有真实 exchange-native adapter。

### 12.10 检查点七第四段执行记录

第四段小闭环已经完成：`root_cause_search` 增加受控递归 provider 边界，能够按 depth/branch 限制展开因素候选。

完成项：

- 新增 `skills/root_cause/providers.py`。
- 新增 `RootCauseSearchRequest`，显式传递 `symbol`、`query`、`trace_id`、`task_id`、`depth` 和 `max_branch_count`。
- `RootCauseSearchSkill` 支持注入 `RootCauseProvider`。
- 没有 provider 时保持原有空 evidence 行为，兼容主链路 fixture。
- provider 返回的因素只允许 `ALLOWED_FACTOR_TYPES` 中的类型。
- 递归展开受 `context.max_depth` 和 `max_branch_count` 控制，并对 query 去重。
- 输出仍压成受控 `EvidenceCandidate`，不开放任意 graph payload。

验证：

```powershell
python -m pytest tests/skills/test_root_cause_recursion.py -q
python -m pytest tests/skills tests/structure/test_skill_runtime_boundaries.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_llm_tool_worker.py tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls -q
```

当前证据：

- root-cause provider 递归测试通过。
- skills、结构边界、agent_swarm 和 API 聚焦链路测试通过。
- 临时主链路 smoke trace: `bd00ff24406e4ec9b4da151aaa9a6510`
- smoke `tool_calls` 仍包含 `realtime_search`、`root_cause_search`、`market_sentiment`、`liquidity_order_book`。
- migration 记录：`docs/migration/2026-07-05-checkpoint-7-root-cause-recursion-provider.md`

检查点七剩余：

- root-cause provider 仍未绑定真实 web search 或事件源。
- root-cause 图形 projection 仍需要从 evidence/artifact refs 派生，而不是开放 skill payload。
- `liquidity_order_book` 还没有真实 exchange-native adapter。

### 12.11 检查点七第五段执行记录

第五段小闭环已经完成：`liquidity_order_book` 增加 provider 边界和 execution fact refs，fixture 主链路可以在 API projection 中看到 mark/index/order_book 引用。

完成项：

- `SkillToolResult` 增加受控 `fact_refs` 字段。
- `fact_refs` 只允许 `mark`、`index`、`order_book` 三类 key。
- `fact_refs` 只允许在 `liquidity_order_book` skill 上出现。
- `ToolCallArtifact` 和 `tool_call_artifact_ref_fields()` 透出 `fact_refs`。
- 新增 `skills/liquidity_order_book/providers.py`。
- `LiquidityOrderBookSkill` 支持注入 `OrderBookProvider`。
- 新增 `FixtureOrderBookProvider`，只生成 exchange fact refs，不暴露原始订单簿 payload。
- 新增 `build_fixture_skill_registry()`；仅 fixture config-only `llm_tool_shadow` 分支默认使用 fixture liquidity provider。
- API 主链路测试断言 `liquidity_order_book` 的 tool call 包含 `mark`、`index`、`order_book` refs。

验证：

```powershell
python -m pytest tests/skills/test_liquidity_order_book_provider.py -q
python -m pytest tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls -q
python -m pytest tests/skills tests/storage/test_agent_audit_view.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_llm_tool_worker.py tests/api/test_runs_routes.py::test_manual_run_with_llm_tool_shadow_projects_real_tool_calls -q
```

当前证据：

- liquidity provider 单测通过。
- API 主链路测试已覆盖 `fact_refs` 投影。
- skills、storage projection、agent_swarm 和 API 聚焦链路小范围回归通过。
- migration 记录：`docs/migration/2026-07-05-checkpoint-7-liquidity-fact-refs.md`

检查点七剩余：

- fixture provider 不是生产 exchange adapter。
- 真实 exchange-native provider 需要单独配置、超时、错误 envelope 和敏感数据脱敏策略。
- 前端可以通过 passthrough 接收 `fact_refs`，但还没有专门 UI 组件突出显示三类 execution refs。

### 12.12 检查点九执行记录

第一段小闭环已经完成：Run Detail 页面在 Skill Tool Calls 表格中显式展示 execution fact refs。

完成项：

- `frontend/src/lib/schemas/runs.ts` 为 tool call schema 增加 `fact_refs`。
- `frontend/src/app/runs/[traceId]/tool-call-graph.tsx` 增加 `Fact Refs` 列。
- 页面按 `mark`、`index`、`order_book` 三类固定顺序展示短 ref。
- 没有引入新的 JSON 主展示，也没有改变页面整体风格。

验证：

```powershell
npm run typecheck
```

当前证据：

- 前端 TypeScript typecheck 通过。
- runtime page smoke trace: `production-candidate-swarm-run_e96be3a707f34f15b71d9cdc1f89949b`
- API smoke `agent_audit_view.mode=production_candidate_swarm`。
- API smoke `tool_calls` 包含 `realtime_search`、`root_cause_search`、`market_sentiment`、`liquidity_order_book`。
- API smoke `liquidity_order_book.fact_refs` 包含 `mark`、`index`、`order_book`。
- API smoke `candidate_final_comparison.status=audit_only`，candidate 侧明确显示 `input_gate_failed`。
- `/runs/{trace_id}` 返回 HTTP 200，页面 HTML 包含 `Fact Refs`、`order_book`、`Candidate Comparison` 和 `audit_only`。
- migration 记录：`docs/migration/2026-07-05-checkpoint-9-fact-refs-visibility.md`

检查点九剩余：

- 还需要把 `tool_calls=0`、candidate gate failed、financial quality not configured 等首屏风险进一步收敛成管理者可读的状态摘要。

### 12.13 检查点八执行记录

第一段小闭环已经完成：新增 `production_candidate_swarm` 执行模式入口，但该模式当前仍强制 blocked + audit-only。

完成项：

- config allowlist 增加 `workflow.execution_mode=production_candidate_swarm`。
- `RunExecutor` 可将 `production_candidate_swarm` 路由到受控 swarm adapter。
- trace id 前缀使用 `production-candidate-swarm-`，与 `controlled-audit-` 区分。
- trace metadata 和 `agent_audit_view.mode` 显示 `production_candidate_swarm`。
- 该模式仍返回 `no trade` audit-only plan。
- verdict reason 使用 `production_candidate_swarm_audit_only`。
- 不写 notification，不产生 production final input，不切换 `decision.final_input_mode`。

验证：

```powershell
python -m pytest tests/config/test_config.py::test_config_accepts_production_candidate_swarm_workflow_mode tests/workflow/test_controlled_adapter.py::test_run_executor_can_route_to_production_candidate_swarm_but_keeps_it_blocked -q
python -m pytest tests/config/test_config.py tests/workflow/test_controlled_adapter.py -q
```

当前证据：

- 新模式配置测试通过。
- 新模式路由测试通过。
- config + controlled adapter 回归通过。
- migration 记录：`docs/migration/2026-07-05-checkpoint-8-production-candidate-mode-guard.md`

检查点八剩余：

- 该模式还没有运行 candidate FinalDecisionAgent sidecar。
- 该模式还没有形成可比较的 legacy final / candidate final / production control gate 三方视图。
- 该模式还不能标记为真正 production candidate，只能标记为 audit-only guarded route。

### 12.14 检查点八第二段执行记录

第二段小闭环已经完成：`production_candidate_swarm` 模式会运行 audit-only candidate FinalDecisionAgent sidecar，并把结果写入同一 trace 的 candidate artifact。

完成项：

- `ControlledSwarmAuditAdapter` 在 `production_candidate_swarm` 模式下调用 `run_candidate_final_decision_sidecar()`。
- sidecar 输入继续由 `evaluate_pre_final_input_gate()` 控制。
- sidecar 使用当前 config 对应的 `DecisionEngine`，但输出 `decision_effect=none`。
- sidecar payload 进入 `build_candidate_audit_payload()`，并随 plan payload 展平持久化为 `candidate_final_decision`。
- `controlled_shadow` 模式仍保持原有 audit-only 行为，不强制运行 sidecar。
- 新测试断言 `candidate_final_decision.production_final_input=false`，并且不写 notification。

验证：

```powershell
python -m pytest tests/workflow/test_controlled_adapter.py::test_run_executor_can_route_to_production_candidate_swarm_but_keeps_it_blocked -q
python -m pytest tests/config/test_config.py tests/workflow/test_controlled_adapter.py -q
```

当前证据：

- production candidate swarm sidecar 聚焦测试通过。
- config + controlled adapter 回归通过。
- migration 记录：`docs/migration/2026-07-05-checkpoint-8-candidate-sidecar-route.md`

检查点八剩余：

- 还没有真实 legacy final / candidate final 对比，因为该 adapter 当前不运行 legacy production final。
- 还没有生产候选 release gate；该模式仍必须被视为 blocked audit-only。
- 还需要页面 smoke 确认该模式下 `candidate_final_comparison` 可见。
