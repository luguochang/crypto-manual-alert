# 前端 Cockpit 重设计与去黑盒实施计划

- 日期：2026-07-07
- 状态：首版 Cockpit 已落地，2026-07-07 本轮继续补齐 Eval 去黑盒、控制/审计文案、真实 judge 提示与自测验收；F2、F1.0、F1.2、F1.3、F1.4、F1.5 已落地，F1.1 保留现有详情 tab 文件结构但已补业务驾驶舱/矩阵/raw 去黑盒能力
- 适用仓库：`crypto-manual-alert`（Python 后端 + Next.js 前端）
- 关联文档：`docs/formal/36-成熟观测与评测平台接入方案.md`、`docs/formal/37-真实多Agent对抗审查与交付方向裁决.md`

## 0. 背景与起点

现有前端四个页面（`/`、`/runs`、`/runs/[traceId]`、`/eval`、`/config`、`/manual-run`）不一定满足当前代码业务现状与后续设计方向。本计划的目标是：

- 既要有**评估业务**，也要有**业务界面**，以及**配置界面**；
- 不是一个黑盒子，能够**可观测到 agent 的执行情况**；
- 后续知道怎么优化。

结论：在现有 4-tab 基线上**重组而非推倒重来**。后端数据模型与 `agent_audit_view` 投影已经足够丰富，**不重构后端**，只做少量"暴露已有数据"的小补丁。前端做信息架构重组 + 去黑盒（把通用 JSON 渲染改为消费 schema 具名字段的结构化渲染）。

## 1. 基线确认（已核实）

- frontend `tsc --noEmit` 绿。当前 `runs/[traceId]` 已是 4-tab 结构（decision / agent / eval / raw + `format-helpers`，均为未跟踪新文件），可编译。
- 后端数据模型与 `agent_audit_view` 投影足够丰富，**不重构**。`/api/runs/{id}?include_payloads=true` 已返回 LLM request/response、span input/output/error、badcases 结构化字段、`plan_run.agent_audit_view`（含 `facts_gate` / `gates` / `workers` / `conflict_edges` / `candidate_final_comparison` 等）。
- 踩 doc 37 §8 冻结红线：不为 `production_candidate_swarm` 旁路造新展示位、不扩张 eval 死代码 UI、不接 Langfuse/DeepEval、配置 L3/L4 只读、不写新 formal 文档。

## 1.1 2026-07-07 实施记录

- F2.1-F2.3 已完成：run detail 暴露顶层 `facts_gate` / `production_control_gate`；eval 暴露 promotion artifacts 与 frozen input summary，frozen input API 不返回 raw `input_payload`。
- F1.0 已完成：sidebar 分为业务 / 评估 / 配置；`/runs?view=alerts|observe` 假双入口已合并到单一 `/runs`，观测入口使用 `columns=observability` 列组预设。
- F1.1 已完成主要能力但未强行改文件命名：`/runs/[traceId]` 仍使用 cockpit / matrix / raw tab 结构，已展示生产 final input 模式、阻断原因、缺失执行事实、tool health、financial quality、worker/tool/source/candidate/gate 矩阵、LLM/span raw 摘要。
- F1.2 已完成：`/eval` tab 化，eval run 下钻页 `/eval/runs/[id]` 接 promotion artifacts、frozen input summaries、replay 与 judge scores；run-eval-form 改 typed API 并严格校验 badcase ids。
- F1.3 已完成：配置页增加 L0-L4 分级标注与只读生效值说明。
- F1.4 已完成轻量口径修正：dashboard 的 LLM 交互 trend 改为“最近 20 条累计”；未新增可选 `/api/dashboard/stats`。
- 2026-07-07 追加补齐：`/eval` 与 `/eval/runs/[id]` 的 replay / side-effect delta 摘要改为结构化证据卡；`judge_openai` 增加真实外部 judge 调用确认；Dashboard/Runs/Config 文案收敛为“人工复核/只读控制面”；Run Detail 驾驶舱增加审计总判定，强调 allowed 不是下单许可。

## 2. F2：后端小补（先行，3 处，仅暴露已有数据）

| # | 文件 | 改动 | 依据 |
|---|---|---|---|
| F2.1 | `storage/journal_rows.py` `plan_run_row` | public dict 增加 `facts_gate` 和 `production_control_gate` 两键（从 payload 直取） | 这两字段每个 payload 都计算存储（`persistence_payload.py`），但只经 `agent_audit_view` 暴露，而该视图对无 shadow 的 run 短路 `available:false`。加这 2 行让 Cockpit 第一屏对所有 run 都能显示"缺失执行事实/阻断理由"。 |
| F2.2 | `api/routes_eval.py` | 新增 `GET /api/eval/runs/{eval_run_id}/promotion-artifacts` → `eval_store.get_promotion_artifacts` | store 有方法有数据，无路由，`get_run_detail` 也不捆绑 |
| F2.3 | `api/routes_eval.py` | 新增 `GET /api/eval/cases/{case_id}/frozen-input` → `eval_store.get_frozen_input` | store 有方法无路由 |
| F2.4（可选） | `api/routes_runs.py` 或 `routes_system.py` | 新增 `GET /api/dashboard/stats` 聚合 total/allowed/blocked/failed | 替代死代码 `dashboardStatsSchema`；不做则前端聚合 |

**配套测试**：`tests/` 下 routes_eval 测试加 2 端点用例；journal_rows 测试加 facts_gate 暴露断言。运行 `pytest` 全绿。

> 注：原计划的 `GET /api/eval/replay/{caseId}` 撤销——`get_run_detail` 已把 `replay_result` 挂到每个 case。candidates status/severity 与 badcase_ids 后端已支持，是前端不传，归 F1。

## 3. F1：前端重设计（在 4-tab 基线上重组 + 去黑盒）

### F1.0 信息架构（`shared/sidebar.tsx` + 路由）
- sidebar 三组 → 三块：**业务**（提醒列表 / 新建提醒）、**评估**（评估工作台）、**配置**（配置）。`/runs?view=alerts|observe` 假双入口合并为单一 `/runs`（列开关替代），详情页高亮"提醒业务"。
- 新增路由 `/eval/runs/[id]`（eval run 详情，从 eval 总览下钻）。

### F1.1 Cockpit 三屏（`runs/[traceId]/`，最大改动）
4 tab → 三屏，首屏服务管理者（doc 37 §11：5 秒看懂能不能信 / 为什么不能执行 / 缺什么）：
- **第一屏·业务驾驶舱**（升级 `decision-tab.tsx`）：保留 `DecisionSummaryCard`；新增"能否用于生产 final input"yes/no（`input_lineage.production_final_input_mode`）+ 阻断原因 top3（优先 `facts_gate.reasons` / `production_control_gate.reasons`，回退 `verdict.reasons`）+ 缺失执行事实（`facts_gate.missing_execution_facts`，需 F2.1）+ Tool health（`tool_calls` 数）+ Financial quality 状态 + trace link 占位。`data_gaps` / `risk_rule_hits` 从 `JsonDetails` 改结构化列表。
- **第二屏·业务矩阵**（重组 `agent-tab` + `eval-tab` 面板）：WorkerMatrix / ToolCallGraph / SourceFreshnessPanel / CandidateComparison / ConflictMatrix / Facts Gate / Release Gate。**去黑盒**：`agent-audit-panel.tsx` 的 `fieldText(Record,key)` 通用取值改为消费 schema 具名字段（`facts_gate.reasons` / `missing_execution_facts` / `blocked_action_classes`、`decision_input.effective_allowed_actions`、`worker.hard_block` / `hard_block_reasons` / `missing_facts` 等，schema 已定义于 `lib/schemas/runs.ts`）。`eval-tab.tsx` badcases 从 `JsonDetails` 改结构化表（category / severity / expected / actual / evidence_refs）。
- **第三屏·raw 辅助**（降级 `raw-tab.tsx`）：删 "Full parsed_plan JSON" 重复；LLM 表加可展开 `request_json` / `response_json`（已有数据，`agent-tab.tsx` 现仅显示 token/cost）；span 火焰图加可展开 `input_summary` / `output_summary` / `error_type` / `error_message`（已有数据，现仅显示 name/duration/status）。

### F1.2 评估块（`eval/page.tsx` + 子组件 + 新 `/eval/runs/[id]`）
- `eval/page.tsx`：6 section 堆叠 → tab（Runs / Cases / Outcomes / Quality）。"最新摘要" `metadata.replay` / `side_effect_deltas` 从 `JSON.stringify` 改结构化卡片。
- `run-eval-form.tsx`：加 `badcase_ids` 输入 + 撤裸 `fetch`，改走 `apiRequest` 类型化客户端（契约一致）。
- `eval-candidates-table.tsx`：加 status/severity 过滤 UI（透传，后端已支持）。
- `eval-replay-table.tsx`：渲染 `input_summary`（frozen input 摘要，现不显示）。
- `eval-judge-scores-table.tsx`：渲染 `reason_summary` / `evidence_refs` / `needs_human_review`（现仅取 duration/tokens 2 字段）。
- 新 `/eval/runs/[id]/page.tsx`：pass/fail + judge 评分明细 + badcase 结构化 + 成本 + promotion-artifacts（用 F2.2 新路由）+ frozen input（用 F2.3）。

### F1.3 配置块分级标注（`config/page.tsx`）
- 保持只读。每段加 L0-L4 分级标注（`SECTION_LABEL` 旁加级别徽标）+ "可前端改 / 需 YAML / 需 eval+审批 / 禁止"说明。`skill_providers` 段若 `safe_dict` 未返回则标注"planned, not yet wired"。加"当前生效值 vs 默认"提示行。

### F1.4 dashboard 统计口径（`page.tsx`）
- "LLM 交互" trend 从"累计调用数"改为"最近 20 条累计"（诚实口径）；或接 F2.4 `/api/dashboard/stats` 做全局聚合。`dashboardStatsSchema` 死代码：接端点或删除。

### F1.5 runs 列表真分页（`runs/page.tsx`）
- `listRuns()` 传 `limit` + 加分页/过滤（symbol / 状态 / 允许 / 阻断）。alerts/observe 改列开关（同一表，可切业务列 / 可观测列），不再假双入口。

## 4. 实施顺序与验证

1. **F2** 后端 3 处 + 测试 → `pytest` 绿
2. **F1.1** Cockpit 三屏（最大，先做；依赖 F2.1 的 facts_gate 暴露）
3. **F1.2** 评估块 tab 化 + 去黑盒 + `/eval/runs/[id]`
4. **F1.0 + F1.3 + F1.4 + F1.5** 收尾（IA / 配置 / dashboard / 列表）
5. 每步后：`npx tsc --noEmit` 绿 + `pytest` 绿

## 5. 不在本次范围（后置 F3）

- L1 配置编辑（需写入端点 + 审计）
- Case/Evidence 页、HumanReview/Release 页
- Langfuse/DeepEval link 激活（Phase D/E 冻结）
- outcome collector 持续调度 / 运维 runbook / prod actionable 真实提醒部署路径（本轮仅完成手动 `collect-outcomes` 与 legacy/candidate/hold baseline hardening，见 `docs/migration/2026-07-07-checkpoint-outcome-baseline-collection-hardening.md`）

## 6. 风险

- F1.1 是单点最大改动，需保留现有 7 子面板逻辑不破坏。策略：tab 文件改为 screen 文件，子面板组件复用不改，只重排 + 补结构化渲染。
- 工作树有未跟踪新文件（4 tab + format-helpers），实施前先确认基线绿（已确认 `tsc --noEmit` 绿）。

## 7. 接手须知（给下一位开发者）

- 本地启动：`uvicorn crypto_manual_alert.api.app:app --reload` + 前端 `cd frontend && npm run dev`（先 `npm install`）。
- 前端类型检查：`cd frontend && npx tsc --noEmit`。
- 后端测试：`python -m pytest`。
- 后端数据字段以 `src/crypto_manual_alert/storage/persistence_payload.py` 和 `agent_audit_view` 投影为准；前端 schema 在 `frontend/src/lib/schemas/`。
- 冻结红线见 doc 37 §8，不要扩张被冻结的展示位。
