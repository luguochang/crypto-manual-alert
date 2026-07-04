# Checkpoint 4 Financial Quality Eval Slice

## Scope

This slice adds the first offline financial prediction quality primitives. It does not fetch live market data, does not write production journal outcome rows, and does not change the structural release gate.

## Added Modules

- `src/crypto_manual_alert/eval/outcomes.py`
  - `OutcomeWindow`
  - `DecisionOutcome`
  - exchange-native source requirement for scored execution outcomes
  - explicit `pending_outcome`, `price_source_not_exchange_native`, `no_trade_action`, and `missing_trade_levels` reasons
- `src/crypto_manual_alert/eval/prediction_metrics.py`
  - `PredictionQualityMetrics`
  - `calculate_prediction_metrics()`
  - direction hit rate, target hit rate, invalidation hit rate, PnL percentage, R multiple, Brier score
  - separate evaluation targets such as `legacy_final` and `swarm_candidate_final`
- `src/crypto_manual_alert/eval/financial_quality_gate.py`
  - `build_financial_quality_gate()`
  - independent status for `not_enough_samples`, `failed`, and `passed`
  - `decision_effect=none`
- `src/crypto_manual_alert/eval/outcome_store.py`
  - independent SQLite store for frozen decision outcomes
  - does not reuse production journal outcome rows
- `src/crypto_manual_alert/eval/market_outcome_collector.py`
  - builds `OutcomeWindow` from already-collected candle rows
  - intentionally does not perform live fetch
- `src/crypto_manual_alert/eval/regime_slices.py`
  - computes `PredictionQualityMetrics` per market regime
- `src/crypto_manual_alert/eval/financial_quality_summary.py`
  - reads already frozen `DecisionOutcome` rows from the independent outcome store
  - writes advisory `EvalRun.metadata.financial_quality_gate`
  - keeps `structural_release_gate_blocking=false`

## Tests

Added:

- `tests/eval/test_outcomes.py`
- `tests/eval/test_prediction_metrics.py`
- `tests/eval/test_financial_quality_gate.py`
- `tests/eval/test_outcome_store.py`
- `tests/eval/test_market_outcome_collector.py`
- `tests/eval/test_regime_slices.py`
- `tests/eval/test_runner_financial_quality_metadata.py`
- structure guard in `tests/eval/test_eval_package_structure.py`
- API assertion in `tests/api/test_eval_routes.py`
- config threshold assertions in `tests/config/test_config.py`

Commands run:

```powershell
python -m pytest tests/eval/test_outcomes.py tests/eval/test_prediction_metrics.py tests/eval/test_financial_quality_gate.py -q
python -m pytest tests/eval/test_outcomes.py tests/eval/test_prediction_metrics.py tests/eval/test_financial_quality_gate.py tests/eval/test_release_gate.py tests/eval/test_replayable_input_summary.py tests/eval/test_candidate_artifact_validation.py tests/eval/test_side_effect_proof.py -q
python -m pytest tests/eval/test_eval_package_structure.py tests/eval/test_outcomes.py tests/eval/test_prediction_metrics.py tests/eval/test_financial_quality_gate.py -q
python -m pytest tests/eval/test_outcome_store.py tests/eval/test_market_outcome_collector.py tests/eval/test_regime_slices.py -q
python -m pytest tests/eval -q
python -m pytest tests/config/test_config.py tests/eval/test_outcome_store.py tests/eval/test_financial_quality_gate.py tests/eval/test_prediction_metrics.py tests/eval/test_runner_financial_quality_metadata.py tests/api/test_eval_routes.py -q
npm run typecheck
```

## Current Limits

- No scheduled or API-triggered `OutcomeCollector` yet.
- No exchange API adapter in the collector yet; current collector consumes already supplied candle rows.
- Eval now has a first financial quality panel, but it still depends on outcome rows being written by a separate offline/manual collector.
- `EvalRunner` now writes `metadata.financial_quality_gate`; it remains advisory and is not part of `release_gate.hard_gate_results`.
- `agent_audit_view.release_eval_gate` still reports `not_configured` unless a stored run payload explicitly provides a financial quality gate.
- No freshness quality metric yet.

## Frontend / API

- `frontend/src/lib/schemas/eval.ts` now has typed financial quality schemas.
- `frontend/src/app/eval/financial-quality-panel.tsx` shows target metrics, sample counts, direction hit rate, Brier score, PnL, R multiple, and `structural_release_gate_blocking`.
- `/api/eval/runs` and `/api/eval/runs/{eval_run_id}` expose `metadata.financial_quality_gate` through the existing eval run metadata.

## Side Effect Statement

The financial quality modules are pure offline calculation helpers. They do not perform live fetch, production journal writes, notification sends, order placement, or production final input switching. The independent outcome store keeps `(decision_ref, evaluation_target, window_name)` rows so `1h`, `4h`, and `24h` windows do not overwrite each other.
