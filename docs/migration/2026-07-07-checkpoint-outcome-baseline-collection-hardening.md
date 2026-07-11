# Checkpoint: outcome baseline collection hardening

日期：2026-07-07
对应：`docs/formal/37` §7 P1、`docs/formal/35` 阶段四金融质量闭环

## 背景

`collect-outcomes` 已能把历史决策的成熟 market outcome 写入 OutcomeStore，但此前仍有两个交付风险：

- CLI 写入的 `crypto-outcomes.db` 路径与 API/EvalRunner 读取路径不一致，导致回收后的样本可能不出现在 eval 页面和 `financial_quality_gate`。
- collector 只采 legacy final，缺少同一窗口下的 candidate final 和 hold/no-trade baseline 样本，无法形成 `legacy_final` / `swarm_candidate_final` / `hold_no_trade` 的可核对对照。

## 改动

- `src/crypto_manual_alert/cli/main.py`
  - `collect-outcomes` 统一使用 `eval.runner.outcome_store_path(config.app.data_dir)`，写入 `data/eval/crypto-outcomes.db`，与 API 和 EvalRunner 保持一致。
  - 每个 eligible trace 生成多目标 `PlanOutcomeInput`：
    - `legacy_final`
    - `swarm_candidate_final`（仅当 candidate sidecar 严格满足 audit-only 条件）
    - `hold_no_trade`（仅当同一 trace 至少有一个真实 legacy/candidate 决策输入）
  - candidate sidecar 必须满足 `artifact_type=candidate_final_decision`、`mode=candidate_final_sidecar`、`decision_effect=none`、`production_final_input is False`、`input_gate_passed is True` 且无 error，才进入 outcome baseline。
  - 只处理已结束、trace status 为 `allowed` 或 `blocked`、存在 final plan 且 plan_run status 为 `allowed` 或 `blocked` 的 trace；失败或未完成 trace 不回收金融 outcome。

- `tests/cli/test_runner_cli.py`
  - 覆盖 legacy/candidate/hold 三基线 input 构造。
  - 覆盖空决策不凭空生成 hold/no-trade baseline。
  - 覆盖非严格 audit-only candidate sidecar 不进入 `swarm_candidate_final`。
  - 覆盖 failed / unfinished trace 不进入 collector。
  - 覆盖真实 `OutcomeCollector` + `OutcomeStore` 写入 eval sidecar，并断言不改变生产 journal 表。

## 验收

```powershell
python3 -m pytest tests/cli/test_runner_cli.py::test_cli_collect_outcomes_collects_legacy_candidate_and_no_trade_baselines tests/cli/test_runner_cli.py::test_cli_collect_outcomes_does_not_create_baseline_without_a_decision tests/cli/test_runner_cli.py::test_cli_collect_outcomes_rejects_candidate_sidecar_without_strict_audit_only_flags tests/cli/test_runner_cli.py::test_cli_collect_outcomes_skips_failed_or_unfinished_traces tests/cli/test_runner_cli.py::test_cli_collect_outcomes_writes_real_outcomes_to_eval_sidecar_store -q
python3 -m pytest tests/local_stack/test_scripts.py::test_mock_okx_server_returns_exchange_native_public_payloads tests/eval/test_outcome_collector.py::test_collect_fetches_exchange_native_window_from_local_mock_okx_http tests/cli/test_runner_cli.py::test_cli_collect_outcomes_reads_history_candles_from_local_mock_okx_http -q
python3 -m pytest tests/cli/test_runner_cli.py tests/eval/test_outcome_collector.py tests/eval/test_outcome_store.py tests/eval/test_prediction_metrics.py tests/eval/test_runner_financial_quality_metadata.py tests/api/test_eval_routes.py::test_eval_outcomes_endpoint_exposes_collected_samples -q
python3 -m pytest
cd frontend && npm run typecheck && npm run build
```

后续本地闭环验证（2026-07-08 补充）：

```bash
python3 tools/local_stack/smoke_local_stack.py --collect-outcomes-fixture
```

该 smoke 会启动本地 API/frontend 与 mock OKX，seed 一条成熟历史提醒，调用真实 `collect-outcomes`，并验证 `legacy_final`、`swarm_candidate_final`、`hold_no_trade` 从 eval sidecar 进入 `/api/eval/outcomes` 和 `/eval?tab=quality`。它的输出必须包含 `outcome_collection_profile=local_mock_okx_collector_wiring_only` 与 `real_financial_quality_proven=false`；这是本地 wiring proof，不是真实生产金融质量。

## 不变约束

- 仍不默认启用真实 provider、真实 LLM、Bark 或自动交易。
- `collect-outcomes` 只读历史 market candles，写 eval sidecar，不写新的 production plan_run、notification 或 manual outcome。
- `hold_no_trade` 是 outcome 样本基线；金融质量 summary 中的 no-trade counterfactual 仍保持 advisory / non-blocking。
- 本次不宣称 `production_candidate_swarm` 已生产化，也不解决 `prod/actionable` 真实提醒路径的配置组合问题。

## 剩余

- 将 `collect-outcomes` 接入独立调度或运维 runbook，形成持续样本积累。
- 补真实 `prod/actionable` 成功证据，明确真实开仓提醒需要真实 OKX public execution facts、真实 OpenAI-compatible endpoint、Bark `sent` 与人工确认的 macro event 状态。当前本地 mock OKX collector smoke 只证明 wiring。
- 后续可优化 collector 对同一 trace 的 candle window fetch 复用，以及更细的 collected/skipped 统计字段。

## 边界

- 本 checkpoint 只记录 outcome baseline collection hardening；前端 Cockpit / Eval / Runs 列表实施状态以 `docs/implementation/2026-07-07-frontend-cockpit-redesign-plan.md` 为准。
