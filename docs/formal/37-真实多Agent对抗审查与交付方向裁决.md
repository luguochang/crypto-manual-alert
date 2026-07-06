# 真实多 Agent 对抗审查与交付方向裁决

日期：2026-07-06

## 1. 文档定位

本文是项目第一次**真实**多 Agent 对抗审查的结论与方向裁决记录。

`35-剩余主缺口对抗审查与执行清单.md` §2 自己承认："当前会话没有可调用的独立 subagent 调度工具，因此本轮采用多角色对抗审查方式记录结论。后续如果有真实 subagent 工具，应按本文角色分别派发只读审查。" 即此前文档里的"多角色对抗审查"是单模型角色扮演，不是真实独立 Agent。本文履行该未尽意图。

本文不是新的 swarm 重构设计文档，不重写 `29/30/31/32/34/35` 已定义的受控 Agent Swarm 目标；它是审查记录与交付方向裁决。后续执行以本文的裁决、关键路径和冻结项为准，直到 §7 的交付闭环跑通。

## 2. 审查方法

- 5 路独立审查员，每路实际打开并阅读代码（不盲信文档），输出 top 5 结构化发现，每条带 `file:line` 证据、`doc_claim vs code_fact`、方向影响。
- 5 个维度：后端 Agent 代码架构、前端产品与业务理解、Eval 与金融预测质量、交付关键路径与 MVP、方向与范围（meta）。
- 每条发现派独立反驳者对抗验证：默认怀疑其夸大或错误，必须打开相关文件核对，能反驳则 `is_real=false`。
- 最后由综合 Agent 汇总验证后结果。

规模：31 个 Agent，约 145 万 token，709 次工具调用，约 104 分钟。25 条发现中 23 条完成对抗验证：**18 条确认为真，5 条被反驳推翻**。

## 3. 总体裁决

**partly-off-track（方向部分偏离）。**

项目比文档自查更接近可用：legacy 主链代码端到端存在、安全护栏真实生效（`auto_order_enabled=false`、`manual_execution_required=true`、harness 经 `legacy_decision_workflow.py:169/210` 集成、forbidden_env 在 `config/loader.py:207-210` 强制为空）、`config/prod.yaml` 已配真实 provider 并由 `Dockerfile:19` 加载、secret 清洁达标。

但三层 gap 阻碍交付：

1. "生产候选 Agent Swarm"是永远 blocked 的审计旁路，状态机无"提升"出口。
2. 默认/本地配置不交付核心价值，且 `local_audit` 下开仓动作被 `production_control_gate` 阻断——这一隐藏陷阱只埋在 `formal/30:414`，未进 README。
3. eval 6925 行几乎全在做结构安全/schema 一致性自检，金融质量闭环"有配置无数据"，到交付日拿不出"预测有效"证据。

附带：6 个 pytest 失败破验收门；文档 ~22234 行 ≈ 代码量 77%，`doc29→36` 形成重构循环；前端 manual-run 成功页丢弃 entry/stop/target/probability。

## 4. 文档 vs 现实落差

最大落差在 `doc 35` 阶段一~三的 `[x]` 完成标记：

- `doc 35` 阶段一目标"让 production_candidate_swarm 从 audit-only 变成可审计的生产候选状态机"标 `[x]`，命名暗示生产候选能力。代码事实：`controlled_adapter.py:105-114` 的 `controlled_shadow` 恒为 `{production_candidate:False, blocked:True, status:'blocked'}`，`:163-184` `_audit_only_plan` 恒返回 `main_action='no trade'`，`:187-200` `_audit_only_verdict` 恒返回 `allowed=False`。三个状态字段是硬编码字面量，全库无任何迁移逻辑把它们转出 blocked。
- `doc 35:9` 称"llm_tool_shadow 可产出真实 ToolCallArtifact"、`:11` 称"LiveFactAgent 已进入受控 realtime_search skill 链路"。代码事实：默认 `shadow.worker_mode=local_audit`（`config/default.yaml:72`）下 7 个 worker 全是确定性规则函数（`agent_swarm/registry.py:106-108` → `market_agents/root_cause.py:12-65` 纯 if/else），`realtime_search` 在 `provider=None` 时 fallback 读已有 input_view（`skills/realtime_search/skill.py:26-28`），`research.search_provider=disabled`（`config/default.yaml:65`）。这些"已完成基础"在默认态全部不成立。

`doc 35` 正文 `L14/L32/L163` 确实多处自承"仍是 blocked audit-only"，并非完全隐瞒；但"补完整状态机"标题 + `[x]` 完成标记与"仅有三个硬编码字段、无迁移条件"的实现之间存在落差。

## 5. 确认的核心问题（对抗验证后为真）

### 5.1 Critical

**C1. production_candidate_swarm 永远 blocked，状态机无"提升"出口。**
`controlled_adapter.py:105-114,163-200` 硬编码 `main_action="no trade"` + `allowed=False`；`candidate_final_decision.py:22-26,59` sidecar docstring 明确"never produces a production final input"、`decision_effect='none'`。全库无路径把 `production_candidate` 置 True。任何"候选"相关投入都在度量一条永远 no-trade 的旁路。

**C2. 金融质量闭环"有配置无数据"。**
`eval/outcome_store.py:56` 的 `upsert_outcomes` 与 `eval/market_outcome_collector.py:8` 在 src 下零调用（仅 tests 调用），`market_outcome_collector.py:24-28` 自述"intentionally does not fetch live data"。`outcomes.py:43-44` 要求 `source_type=='exchange_native'` 才打分，而默认 `market_data.provider=fixture`。`financial_quality_gate.py:16-25` 在 `scored_count<30` 时永远返回 `not_enough_samples`。到交付日拿不出"系统预测有效"的量化证据。

### 5.2 High

**H1.【交付生死线陷阱】local_audit 下开仓动作被 production_control_gate 阻断。**
`tests/api/test_runs_routes.py:55,57` 断言默认运行 `verdict.allowed is False` 且命中 `production_control.candidate.action_not_allowed`。阻断链路：`evidence.py` 缺执行事实 → `decision_input.py:158-160` `effective_allowed_actions` 移除开仓动作 → `gate_candidate.py:36-44` 触发 `action_not_allowed` → `production_control_gate.py` 因开仓动作升级为 blocking。即使 `prod.yaml` 接了真实 LLM，`trigger long` 等开仓动作仍被卡死。逃生口（`test_runs_routes.py:181`）：切 `shadow.worker_mode=llm_tool_shadow` + 配 `skill_providers.liquidity_order_book=exchange_native` + 真实 execution-fact worker，或放行 `effective_allowed_actions`。此陷阱只埋在 `formal/30:414`，必须写入 README/部署文档。

**H2. 默认 swarm 全是确定性规则 worker，无 LLM 自主规划。**
`market_agents/root_cause.py`、`live_fact.py` 等纯规则函数，`decision_effect='none'`。`LlmToolShadowWorker`（`agent_swarm/llm_tool_worker.py:49`）仅在非默认的 `llm_tool_shadow` 模式注入。命名"受控 Agent Swarm"与默认实现不匹配，会误导就绪度判断。

**H3. 默认 skills 不主动触发外部搜索。**
`skills/realtime_search/skill.py:26-28` 在 `provider=None` 时读已有 input_view；`skills/registry.py:57-64` 默认 `realtime_mode='disabled'`。`ResponsesWebSearchProvider`（`providers.py:76-147`）与 `OkxPublicOrderBookProvider` 均需显式配置 + key。注意：`liquidity_order_book` 默认是 `fixture`（非 disabled）；disabled-by-default 是 `doc 35` 的显式安全约束（暂停条件 L425），不是疏漏。落地建议是"在专用可验收路径上默认开真实 provider"，而非翻转生产默认。

**H4. release_gate 的 hard_gates 无金融预测质量门。**
`eval/release_gate.py:327-377` 的 hard_gate_results 共 16 项，全是结构/schema/安全/语义检查，无方向命中/Brier/相对 legacy 与 no-trade 的 PnL。`financial_quality_summary.py:45,72` 把 `structural_release_gate_blocking` 硬编码 False，`release_gate.py:384` `promotion_approved` 硬编码 False。这是 `doc 35:333` 有意设计的 advisory（不阻断安全 gate），但意味着 release gate 全绿也只能证明"结构一致、无生产副作用"，无法证明"预测更好"。

**H5. 默认配置不交付核心价值。**
`decision/final_engine.py:21-26` `FixtureDecisionEngine.run()` 直接 `read_text(tests/fixtures/decision_plan_valid.json)` 忽略请求 symbol；`notification.enabled=false` → `NoopNotificationSink`；`run_persistence_step.py:140-141` 在 `enabled=false` 时 return None。注意：`config/prod.yaml` 已用 `openai_compatible`+`okx_public`+`notification.enabled=true` 覆盖默认并由 Dockerfile 加载，故此条对生产部署降级为"本地裸跑不可用"；但 `prod.yaml` 的 `app.mode` 仍为 SHADOW，且 H1 的开仓阻断在 prod 下仍生效。

**H6. manual-run 成功页丢弃 entry/stop/target/probability。**
后端 `api/routes_runs.py:19` 完整返回 `reference_price/entry_trigger/stop_price/target_1/target_2/probability`，`notification/sinks.py:59-61` 推 Bark 时也用它们，但 `frontend/src/app/manual-run/run-form.tsx:142-155` 成功页只显示 Trace ID/动作/风控三行。提醒工作台入口不直显提醒要素。`run-form.tsx:14` 仅 3 个硬编码 symbol 且 `<select>` 不可自定义；`alert_channel` 锁死 bark（但 `notification.enabled=false` 下影响有限）。

**H7. pytest 有 6 个失败。**
实跑确认：2 个 `tests/agent_swarm/test_shadow_orchestration.py`（LLM tool worker 已演进、测试未同步）、1 个 `tests/context/test_artifacts.py`、1 个 `tests/decision/test_replayable_input.py`、2 个 `tests/local_stack/test_scripts.py`（过时硬编码 HTML 夹具缺 'Worker Matrix' token，**非前端渲染缺陷**）。方向是更新测试夹具，不改生产行为。README:31-32 把 `pytest` 当通过性验证，红状态下不交付、不推公开仓。

**H8. doc 35 vs doc 36 方向冲突。**
`doc 35` 阶段四~六未完成要收敛；`doc 36` 又新开 Langfuse+DeepEval 平台面（Phase A~G，新增 `telemetry/sinks.py`、`telemetry/langfuse_sink.py`、`eval/deepeval_runner.py`、`eval/deepeval_cases.py`，目前均不存在），且 `doc 36` 完全未覆盖 `doc 35` 阶段五/六。同时推进不现实。

**H9. 文档自我增殖。**
`docs/formal` ~19420 行（38 篇）+ `docs/migration` ~2814 行（35 篇）≈ 22234 行，约为代码量（src 25864 + frontend 3044 ≈ 28908）的 77%。`doc29→36` 反复重写同一套 swarm 目标，每篇都自称"新执行入口"把前作降格——正是 `doc 35 §1` 自己要防止的症状。

### 5.3 Medium（已验证为真，可延后）

- M1. 后端 `analysis.decision_ladder`（含阻断理由 reasons，`persistence_payload.py:208-211`）已产出但前端不突出展示，埋在底部折叠 JSON；`schemas/runs.ts:287-338` 多个字段后端产出前端未消费。
- M2. 前端首屏术语全是 trace/span/gate/worker/skill，淹没加密操作提醒业务语义，缺一句话建议锚点。
- M3. replay（`frozen_observed/judge_only` 模式）不重新决策，baseline 对比（`shadow_final_comparison.py:35-53,78-96`）只查 action 字符串相等 + probability_delta，**缺 no-trade 反事实对照组**（但 `prediction_metrics.py` 对 legacy_final/swarm_candidate_final 两个 baseline 已有 brier/方向命中/PnL 度量）。
- M4. 所有 judge 评推理/schema 质量不评预测命中（`judges/rules.py:36-46`、`judges/fixture_llm.py:16-17`、`judges/llm.py:17-23,178-204`）；`FixtureLLMJudge` 是确定性规则替身。但 outcome metrics 路径才是预测证据主源，这是有意设计边界（`doc 36:542`）。
- M5. eval 6925 行中 `regime_slices.py`、`market_outcome_collector.py`、`outcome_store` 写入路径是生产中零调用死代码；`doc 36:594` 把"补金融 outcome"排到最后是优先级倒置。
- M6. README/.env.example 与默认行为有落差（`.env.example:7 SCHEDULER_ENABLED=true` vs `config/default.yaml:54 false`；src 全仓无 load_dotenv，该 env 不自动加载；CLI scheduler 子命令不检查 `scheduler.enabled`）。
- M7. `doc 36` Phase D/E（Langfuse exporter + DeepEval runner 外部接入）在交付期属镀金，引入网络/鉴权/schema 漂移新失败面。**但 Phase B（Run Detail 收缩为 Cockpit）必须保留**，它直接修前端业务语义缺失且零外部依赖。

## 6. 被对抗验证推翻的误判

以下 5 条原审查担心经独立反驳者核对代码后**不成立**，后续无需再查：

| 原担心 | 反驳结论 |
|---|---|
| 默认主链下 Run Detail 首屏 Agent Swarm Audit 整块空壳 | 错。legacy 工作流无条件跑 `run_pre_final_orchestration` + `run_decision_control_step`，`agent_audit_view.available=True`，7 workers 完整渲染。`tests/api/test_runs_routes.py:85-120` 用默认 config 复现并断言。 |
| 默认主链不调 LLM、不发通知、读静态 fixture（作为 critical） | 错（作为 critical）。`config/prod.yaml` + `Dockerfile:19` 已启用 openai_compatible + okx_public + Bark + scheduler + LLM research。仅本地裸跑走 fixture。降为 low。 |
| harness 只治理 audit 旁路、legacy 主链不受治理、production_decision 是死代码 | 错。legacy 经 `run_shadow_swarm_audit` → `production_control_gate` 治理，失败时阻断可执行动作；`production_decision` policy 经 `orchestration_inputs.py:35` 可达。仅"policy 未外显到 YAML"为真（`harness.py:63-65` 明示有意保守）。 |
| decision/ 29 文件两套 final input 路径并存、有死代码 | 夸大。`legacy_final_input_step` 是 `select_final_input` 的顺序上游 packet 构造器，非并行路径；`decision_input` 是 feature-flagged 迁移目标且有 `tests/decision/test_final_input.py` 等 3+ 测试覆盖。合并会违反 coding-style 800 行/小文件原则。降为 low。 |
| eval 页 Financial Quality Panel 默认空壳、无管理者视图 | 错。默认部署总装配 OutcomeStore（`api/app.py:34,57`），Panel 显示 2 行 not_enough_samples；管理者视角的允许/阻断摘要在首页 Dashboard（`frontend/src/app/page.tsx:28-33`）。 |

## 7. 交付关键路径（按优先级）

剩余时间内的最小可交付切片：

1. **[P0] 端到端打通真实提醒。** 用 `prod.yaml` 路径实测一次手动 query：openai_compatible + okx_public + enabled Bark，验证产出 `allowed=True`、symbol 一致、真正触发 Bark 的计划。**关键解开 H1 的阻断陷阱**：切 `shadow.worker_mode=llm_tool_shadow` + 配 `skill_providers.liquidity_order_book=exchange_native` + 真实 execution-fact worker，或在 prod 配置放行 `effective_allowed_actions`。把该陷阱从 `formal/30:414` 提到 README/部署文档。
2. **[P0] 修绿或隔离 6 个失败测试。** 更新过时夹具（local_stack 的硬编码 HTML、shadow_orchestration 的演进同步），不改生产行为；或在 README/`doc 24` 显式划为非 legacy-MVP 阻塞项。红状态下不交付。
3. **[P1] 接通 outcome 收集。** 实现手动/定时 collector：决策 horizon 成熟后拉 exchange-native K 线调 `OutcomeStore.upsert_outcomes`（当前 src 零调用）；新增 no-trade/hold baseline outcome，让 legacy_final/candidate_final/no-trade 三方真实对照。这是拿"预测有效"证据的唯一路径。
4. **前端低成本高价值。** manual-run 成功页内联渲染 entry/stop/target/probability（后端已返回）；Run Detail 突出渲染 `analysis.decision_ladder` 的 `risk_gate.reasons` 作为可读阻断理由；首屏补一张跨主链/旁路通用的决策摘要卡（方向+概率+价位+阻断理由+数据缺口数），把 Spans/LLM Calls 降级。
5. **对齐配置与文档。** `.env.example`（`SCHEDULER_ENABLED=false`）与 README（区分"默认关闭 vs 配置开启"，补注"API 服务不内置 scheduler，调度仅 CLI"）。

## 8. 应立即停止（防止方向继续走偏）

- 停止在 blocked audit 旁路上叠加更多 audit 结构与前端展示（C1）。
- 停止启动 `doc 36` Phase D/E（Langfuse exporter + DeepEval runner 外部接入）——在 outcome 管道为零时接入观测平台只是在度量空库，且与交付日期竞争。Phase B（UI 收缩）除外，必须保留。
- 停止新增 formal 设计文档（不写 doc 38）。后续只改代码 + migration 记录，直到 §7 交付闭环跑通。
- 停止把"状态机/边界标 `[x]` 完成"等同于"agent 能力就绪"。
- 停止扩张 eval 脚手架（`regime_slices`/`market_outcome_collector` 等是生产零调用死代码）。
- 生产配置不要开 candidate sidecar——`final_input_mode=legacy_prompt` 下对生产决策零作用却翻倍 LLM 成本（生产 openai_compatible 下 sidecar 多跑一次 FinalDecisionAgent）。

## 9. 对 doc 35/36 的处置

- **doc 35**：阶段一~三 `[x]` 保留但重新标注为"仅完成字段定义/开关边界/audit 面板，非 agent 能力就绪"；停止追加 audit 结构与前端展示。阶段四（金融质量闭环）升为交付前最高优先级（§7 P1）。阶段五（harness policy 外显）缩窄范围：legacy 主链已集成 harness（§6 反驳成立），只需把硬编码 policy 搬到更严格 YAML loader，不扩治理范围。阶段六（结构收敛）标准改为"补 decision/ 模块索引文档降导航成本 + 删除真正未使用代码"，**绝不能删除 candidate 路径或合并 replay 文件**（违反 coding-style 小文件原则，且 candidate 路径是 feature-flagged 迁移目标）。
- **doc 36**：Phase A（方案冻结不改代码）可保留。Phase B（Run Detail 收缩为 Cockpit）必须留在交付清单内。Phase C（sink 抽象）可选，仅在不挤占交付时做。Phase D/E 推迟到 v1 交付后。Phase F（金融 outcome）与 doc 35 阶段四合并优先做。Phase G（release review）后置。
- **新增约束**：冻结新 formal 设计文档，只允许改代码与 migration 记录，直到真实提醒闭环跑通。

## 10. 不变约束（沿用 doc 35 §3，继续生效）

- 不默认设置 `decision.final_input_mode=decision_input`。
- 不默认设置 `workflow.execution_mode=production_candidate_swarm`。
- 不默认设置 `shadow.worker_mode=llm_tool_shadow`、不默认启用真实外部 provider/LLM/web/exchange。
- 不写订单、不撤单、不发交易通知；`manual_execution_required=true` 必须保持。
- FinalDecisionAgent 不得调用 tool；Worker 不得输出最终交易动作字段。
- search-derived evidence 不得满足 mark/index/order_book execution facts。
- 同一问题连续失败 3 次必须暂停。

## 11. 完成定义（交付候选）

只有同时满足以下条件，才能称为"人工确认的真实加密提醒工作台"基本可交付：

- 用 `prod.yaml` 路径实测一次手动 query，能产出 `allowed=True`、symbol 一致、真正触发 Bark 的开仓计划（解 H1）。
- 默认生产 final input 仍安全保守（`legacy_prompt`），真实 provider 显式配置。
- execution facts 只来自 exchange-native refs。
- pytest 全绿或失败项显式划为非 MVP 阻塞项。
- manual-run 成功页与 Run Detail 首屏能让管理者 5 秒看懂"能不能信/为什么不能执行/缺什么"。
- 至少有一条真实 outcome 进入 `OutcomeStore`（证明金融质量闭环不再是空壳）。

swarm/candidate/eval-金融质量全量闭环不在该 MVP 切片内，应显式 descoping 为交付后事项。

## 12. 最大单一风险

交付日临近下继续在 blocked audit 旁路与 Langfuse/DeepEval 观测平台上投入，导致到交付日仍拿不出"一条真实可用的加密操作提醒"——默认被阻断、`prod.yaml` 仍 SHADOW、开仓动作被 `production_control_gate` 卡死、6 测试红、无预测有效性证据，核心价值零交付。破局点只有一个：先打通 §7 P0 的真实提醒闭环，其余全部冻结或后置。

---

审查原始数据：5 路审查 + 23 条对抗验证 + 综合的完整 JSON 见 `.tmp/review_extract.json` 与 `.tmp/synth.json`（被 `.gitignore` 忽略，仅本地参考）；审查工作流脚本见 `.tmp/adversarial-review-workflow.js`。
