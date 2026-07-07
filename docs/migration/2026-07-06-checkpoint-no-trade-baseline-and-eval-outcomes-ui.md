# Checkpoint: no-trade baseline + eval 页真实 outcome 展示（Phase 2.2 / 2.3 前端）

日期：2026-07-06
对应：`docs/formal/37` §5.3 M3（缺 no-trade 反事实对照组）、Phase 2.3 前端
计划：`.tmp/optimization-plan.md` Phase 2.2 / 2.3

## Phase 2.2 no-trade baseline（反事实对照组）

**问题**：`prediction_metrics` 已对 legacy_final/swarm_candidate_final 两个 baseline 算 brier/PnL/方向命中，但缺第三类 baseline——hold/no-trade 反事实对照（doc 35 line 331）。无法回答"提醒是否比什么都不做强"。

**改动**：
- `src/crypto_manual_alert/eval/prediction_metrics.py`：新增 `calculate_no_trade_metrics(outcomes)`——对每个真实交易 outcome 的窗口，no-trade 反事实 PnL=0、无方向下注（direction_hit_rate=None）、0.5 概率参考 Brier=0.25。scored_count = 真实可评分交易窗口数。
- `src/crypto_manual_alert/eval/financial_quality_summary.py`：在 target_gates 末尾追加 `no_trade` baseline gate，status=`baseline_reference`、`blocking=False`、`brier_event_label=no_trade_counterfactual`，纯参考不阻断。从全部 outcomes 派生。
- `tests/eval/test_prediction_metrics.py`：新增 `test_no_trade_baseline_metrics_are_zero_pnl_counterfactual`。

**效果**：金融质量面板可对比 legacy_final 的 average_pnl_pct 与 no_trade 的 0.0，回答"提醒是否跑赢空仓"。

## Phase 2.3 前端 eval 页接入真实 outcome

**问题**：`FinancialQualityPanel` 只显示 financial_quality_gate（来自 eval run metadata），不显示已收集的真实 outcome 样本——管理者看不到预测命中的具体记录（黑盒）。

**改动**：
- `frontend/src/lib/schemas/eval.ts`：新增 `evalOutcomeWindowSchema`/`evalOutcomeSchema`/`evalOutcomeListSchema` + `EvalOutcome` 类型。
- `frontend/src/lib/api/eval.ts`：新增 `listEvalOutcomes({evaluationTarget})` 调 `GET /api/eval/outcomes`。
- `frontend/src/app/eval/financial-quality-panel.tsx`：接受 `outcomes`/`outcomesError` props；新增"已收集 Outcome"统计（可评分/待成熟计数）+ outcome 样本表（decision_ref/target/symbol/action/entry-stop/窗口 close/可评分/未评分原因）。
- `frontend/src/app/eval/page.tsx`：`Promise.all` 并行拉 outcomes，传给 `FinancialQualityPanel`。
- `tests/api/test_eval_routes.py`：新增 `test_eval_outcomes_endpoint_exposes_collected_samples`——seed 一个 DecisionOutcome，GET 端点验证返回脱敏 public dict（close_price/source_type/can_score）。

**效果**：eval 页金融质量面板同屏显示 gate 状态 + 真实 outcome 样本表，预测结果可见、可核对、非黑盒。数据来自 `crypto-alert collect-outcomes` 写入的 OutcomeStore。

## 验收

```powershell
python -m pytest tests/eval/test_prediction_metrics.py tests/eval/test_financial_quality_gate.py tests/eval/test_runner_financial_quality_metadata.py tests/eval/test_outcome_collector.py tests/api/test_eval_routes.py -q
cd frontend && npm run typecheck && npm run build
```

- eval 全套测试通过（含 no-trade baseline + outcomes 端点）。
- 前端 typecheck + production build 通过（所有路由构建无误）。
- 后端 CLI 烟测：`crypto-alert show-config` 显示 macro_event 段；`crypto-alert run-once` 产出 blocked plan（fixture 默认）；`crypto-alert collect-outcomes` 空 journal 报 `{collected:0,skipped:0}`，有成熟决策时尝试拉 OKX（沙箱无外网故超时，单测已用 mock http_get 覆盖逻辑）。

## 不变约束维持

- no-trade baseline 永不阻断（`blocking=False`、`status=baseline_reference`），不影响 release gate。
- outcome 端点只读 OutcomeStore（eval sidecar），不碰生产 journal。
- 未默认启用真实 provider/LLM。

## 剩余（Phase 3，交付后）

- harness policy YAML 外显（doc 35 阶段五，缩窄范围）。
- 结构收敛（删真正未用代码、补 decision/ 索引文档）。
- Langfuse/DeepEval 外部平台接入（doc 36 Phase D/E）。
- 真实宏观事件日历 provider（替换 no_active_event 操作员断言）。
- 运行时验证：prod+staging 配置下真实 OKX + Bark 端到端跑通一条开仓提醒（CI 已用 mock 覆盖逻辑，真实网络需部署环境验证）。
