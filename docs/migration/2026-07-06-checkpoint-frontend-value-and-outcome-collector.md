# Checkpoint: 前端价值 + 预测 outcome 闭环（Phase 1 / Phase 2.1 / 2.3）

日期：2026-07-06
对应：`docs/formal/37` §5.2 H6（manual-run 丢弃价位）、M1/M2（前端业务语义）、C2（金融质量闭环无数据）
计划：`.tmp/optimization-plan.md` Phase 1 / Phase 2.1 / Phase 2.3

## Phase 1.1 manual-run 成功页直显价位 + 概率

**问题**：`run-form.tsx` 成功页只显示 Trace ID/动作/风控，丢弃后端已返回的 entry/stop/target/probability；symbol 硬编码 3 个 `<select>` 不可自定义；`alert_channel` 锁死 `bark`。

**改动**：
- `frontend/src/lib/schemas/manual-run.ts`：`alert_channel` 从 `z.literal("bark")` 放开为 `z.string().default("bark")`。
- `frontend/src/app/shared/direction.ts`（新）：抽 `classifyDirection`/`DIRECTION_LABEL`/`DIRECTION_TONE`/`formatPrice`/`formatPercent` 共享工具，供 manual-run 与 run-detail 复用。
- `frontend/src/app/manual-run/run-form.tsx`：symbol 改 `<input list>` + `<datalist>`（建议 + 可自定义）；成功页重写为"方向色块 badge + 概率 + 参考价/触发价/止损/目标1/目标2/过期时间 + 阻断理由列表 + manual_execution_required 提示"。
- `frontend/src/app/styles.css`：新增 `.alert-summary`/`.direction-badge`/`.tone-*`/`.price-grid`/`.verdict-reasons`/`.hint` 及移动端适配。

**效果**：生成提醒后，入口页直接显示提醒要素（方向+价位+概率+阻断理由），管理者不必点进 trace 即可看到建议本体。

## Phase 1.2 Run Detail 首屏决策摘要卡

**问题**：Run Detail 首屏是 4 个工程 stat card + Agent Swarm Audit 面板，业务语义被淹没；阻断理由 `analysis.decision_ladder.risk_gate.reasons` 后端已产出但前端只放在折叠 JSON。

**改动**：
- `frontend/src/app/runs/[traceId]/decision-summary-card.tsx`（新）：首屏决策摘要卡——方向色块 + 概率 + 参考价/触发价/止损/目标1/目标2/数据缺口数 + 阻断理由（从 `analysis.decision_ladder` 提取 `risk_gate.reasons`，回退 `verdict.reasons`）+ 模式 + 生产最终输入状态。
- `frontend/src/app/runs/[traceId]/page.tsx`：在 stat card 之前插入 `DecisionSummaryCard`；加 `asString`/`asNumber` helper 把 `parsed_plan`（`z.record(unknown)`）安全 coerce 为类型化字段。
- `frontend/src/app/styles.css`：新增 `.decision-card`/`.decision-allowed`/`.decision-blocked`/`.decision-status`/`.tone-warning` 等及移动端适配。

**效果**：管理者打开 Run Detail 首屏 5 秒看到"能不能信（allowed/blocked）+ 为什么不能执行（阻断理由）+ 缺什么（数据缺口数）+ 是不是生产输入"，业务语义优先，工程细节下钻。

## Phase 2.1 outcome collector（金融质量闭环的真实数据源）

**问题**：`OutcomeStore.upsert_outcomes` 在 src 下零调用，`financial_quality_gate` 永远 `not_enough_samples`，到交付日拿不出"预测有效"证据。

**改动**：
- `src/crypto_manual_alert/eval/outcome_collector.py`（新）：`OutcomeCollector` —— 对每个决策，horizon 成熟后拉 OKX `/api/v5/market/history-candles` 覆盖窗口，经 `build_outcome_window_from_candles` 建 `OutcomeWindow`（source=exchange_native），建 `DecisionOutcome` 并 `upsert_outcomes`。支持 `http_get` 注入（CI 可测，不依赖网络）+ `clock` 注入（可测未成熟窗口）。未成熟窗口不拉数据、不打分。`horizon_seconds` 解析 "6h"/"1d" 等。
- `src/crypto_manual_alert/cli/main.py`：新增 `collect-outcomes` 子命令（`--limit`/`--symbol`），读最近 plan_runs，对每个成熟决策调 collector，报告 collected/skipped。
- `tests/eval/test_outcome_collector.py`（新）：3 测试——horizon 解析、成熟窗口 upsert（验证 OHLC + 持久化）、未成熟窗口不拉数据不写。

**效果**：`crypto-alert collect-outcomes` 即可把历史决策的真实市场 outcome 灌入 OutcomeStore，`financial_quality_gate` 不再永远空库。这是"预测有效"证据的唯一路径。

## Phase 2.3 eval API 暴露 outcomes

**改动**：`src/crypto_manual_alert/api/routes_eval.py` 新增 `GET /api/eval/outcomes?evaluation_target=`，返回 OutcomeStore 中的 outcome 列表（脱敏 public dict），供前端金融质量面板展示真实样本。

## 验收

```powershell
# 后端
python -m pytest tests/eval/test_outcome_collector.py tests/api tests/workflow tests/eval -q
# 前端
cd frontend && npm run typecheck
python -m pytest tests/structure/test_frontend_route_boundaries.py -q
```

- outcome collector 3 测试通过；前端 typecheck 通过；结构测试通过。
- 全量套件（除 local_stack）回归通过（见本轮 `pytest --ignore=tests/local_stack` 绿）。

## 不变约束维持

- outcome collector 只读市场历史 + 写 eval sidecar（`crypto-outcomes.db`），不写生产 journal、不发 Bark、不触发 live fetch（未成熟不拉）。
- 未默认启用真实 provider/LLM；collector 用真实 OKX 仅在显式运行 `collect-outcomes` 时。
- 默认 `macro_event.provider=disabled`、`market_data.provider=fixture` 不变。
- 前端只消费已有后端字段，未新增 raw payload 暴露。

## 剩余

- Phase 2.2：no-trade baseline（`evaluation_targets` 加 `no_trade` + 三方对照）——可选，prediction_metrics 已支持两 baseline。
- 前端 eval 页金融质量面板接入 `/api/eval/outcomes` 真实数据展示。
- Phase 3（交付后）：harness policy YAML 外显、结构收敛、Langfuse/DeepEval、真实宏观事件日历 provider。
