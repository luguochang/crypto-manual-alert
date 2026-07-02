# Checkpoint 5 DecisionInput 候选 final 实施记录

Date: 2026-07-03

Source plan: `docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md`

## Status

Checkpoint 5 is complete.

Completed slices:

- 5A. 定义 `DecisionInput` 最小可生产候选 schema 与前置输入 gate。
- 5B. 隔离 candidate FinalDecisionAgent，候选 final 只消费通过前置输入 gate 的 `DecisionInput`，只写 sidecar，不改生产 final。
- 5C. 建立 legacy 与 candidate final 对照回放。

## 5A DecisionInput 前置输入 gate

Added:

- `src/crypto_manual_alert/decision/pre_final_input_gate.py`
- `tests/decision/test_pre_final_input_gate.py`

Modified:

- `src/crypto_manual_alert/decision/pre_final_switch_readiness.py`
- `src/crypto_manual_alert/decision/__init__.py`
- `tests/decision/test_pre_final_switch_readiness.py`
- `tests/workflow/test_run_executor.py`

What changed:

- Added `evaluate_pre_final_input_gate()` as the pre-final `DecisionInput` gate.
- The gate validates minimum candidate-input schema, `decision_effect=none`, seven required worker refs, upstream validation status, exchange-native execution fact sources, worker hard blocks and side-effect fields.
- `build_pre_final_switch_readiness()` now includes the input gate result and `pre_final_input_gate_passed`.
- Switch readiness remains audit-only and always returns `ready=false` in this slice.
- Production final input remains `legacy_prompt`; no candidate FinalDecisionAgent was enabled.

Red test evidence:

```powershell
python -m pytest tests/decision/test_pre_final_input_gate.py -q
```

Observed:

- Failed because `crypto_manual_alert.decision.pre_final_input_gate` did not exist.

Additional red evidence:

```powershell
python -m pytest tests/decision/test_pre_final_switch_readiness.py -q
```

Observed:

- Existing readiness tests failed because the old readiness envelope did not include `input_gate` or `pre_final_input_gate_passed`.

Green verification:

```powershell
python -m pytest tests/decision -q
python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q
python -m pytest tests/structure -q
```

Result: passed.

## 5B Candidate FinalDecisionAgent sidecar

Added:

- `src/crypto_manual_alert/decision/candidate_final_decision.py`
- `tests/decision/test_candidate_final_decision.py`

Modified:

- `src/crypto_manual_alert/decision/candidate_audit.py`
- `src/crypto_manual_alert/decision/__init__.py`
- `src/crypto_manual_alert/context/artifacts.py`
- `src/crypto_manual_alert/workflow/persistence_payload.py`
- `tests/decision/test_candidate_audit.py`
- `tests/context/test_artifacts.py`
- `tests/workflow/test_persistence_payload.py`

What changed:

- Added `run_candidate_final_decision_sidecar()` as an audit-only candidate final runner.
- The sidecar consumes only a gate-passed pre-final `DecisionInput`; candidate engine input is forced to `mode=candidate_final_input` and `decision_effect=none`.
- Sidecar output is fixed to `artifact_type=candidate_final_decision`, `mode=candidate_final_sidecar`, `decision_effect=none`, and `production_final_input=false`.
- Input gate failures and candidate engine exceptions are captured as sidecar errors and do not affect the production final decision.
- Candidate audit, context artifact summary, and persistence `audit_only` namespace can now carry candidate final sidecar refs.
- No workflow entrypoint automatically calls the candidate engine in this slice.

Red test evidence:

```powershell
python -m pytest tests/decision/test_candidate_final_decision.py -q
```

Observed:

- Failed because `crypto_manual_alert.decision.candidate_final_decision` did not exist.

Additional red evidence:

```powershell
python -m pytest tests/workflow/test_persistence_payload.py::test_build_plan_payload_mirrors_candidate_final_sidecar_in_audit_only_namespace -q
```

Observed:

- Failed because `audit_only.mirrored_legacy_fields` and `audit_only.candidate_final_decision` did not include the candidate final sidecar.

Green verification:

```powershell
python -m pytest tests/decision/test_candidate_final_decision.py tests/decision/test_candidate_audit.py tests/context/test_artifacts.py tests/workflow/test_persistence_payload.py -q
python -m pytest tests/decision -q
python -m pytest tests/structure -q
```

Result: passed.

Depth control:

- `tests/workflow/test_run_executor.py` was not run for 5B because this slice did not modify Runner, Journal, Replay, Release gate, or production entrypoint behavior.
- Deep workflow/eval verification remains reserved for Checkpoint 5 closeout or 5C if the replay comparison entry boundary changes.

## 5C Legacy vs candidate final replay comparison

Modified:

- `src/crypto_manual_alert/eval/shadow_final_comparison.py`
- `src/crypto_manual_alert/eval/case_builder.py`
- `src/crypto_manual_alert/eval/replay.py`
- `tests/eval/test_shadow_final_comparison.py`
- `tests/eval/test_case_builder_candidate_audit.py`
- `tests/eval/test_replay_llmjudge.py`

What changed:

- Added `build_candidate_final_legacy_comparison()` for comparing the legacy observed final decision with a `candidate_final_decision` sidecar.
- The comparison accepts either a raw 5B sidecar or a sanitized case summary sidecar and emits only safe summaries: action, probability and instrument.
- Candidate audit case summaries now preserve safe `candidate_final_decision` metadata and `candidate_final_output_hash`; they do not preserve `raw_candidate_decision`.
- `ReplayRunner` in `candidate_decision` mode emits `candidate_final_legacy_comparison` when the sidecar is present.
- This slice does not switch production final input and does not introduce production journal, notification or live order side effects.

Red test evidence:

```powershell
python -m pytest tests/eval/test_shadow_final_comparison.py::test_candidate_final_legacy_comparison_reports_safe_action_diff_without_raw_payload -q
```

Observed:

- Failed because `build_candidate_final_legacy_comparison()` did not exist.

Additional red evidence:

```powershell
python -m pytest tests/eval/test_case_builder_candidate_audit.py::test_candidate_audit_summary_preserves_safe_candidate_final_sidecar_summary -q
python -m pytest tests/eval/test_replay_llmjudge.py::test_candidate_decision_replay_compares_persisted_candidate_final_sidecar -q
```

Observed:

- Case summary failed because `candidate_final_decision` was missing.
- Replay failed because `candidate_final_legacy_comparison` was missing.

Green verification:

```powershell
python -m pytest tests/eval/test_shadow_final_comparison.py tests/eval/test_case_builder_candidate_audit.py tests/eval/test_replay_llmjudge.py::test_candidate_decision_replay_compares_persisted_candidate_final_sidecar -q
python -m pytest tests/eval/test_candidate_artifact_validation.py tests/eval/test_promotion_artifact_store.py -q
```

Result: passed.

Checkpoint 5 closeout verification:

```powershell
python -m pytest tests/decision -q
python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q
python -m pytest tests/eval/test_shadow_final_comparison.py tests/eval/test_replayable_input_summary.py -q
python -m pytest tests/structure -q
```

Result: passed.

## Boundaries Preserved

- Production still defaults to `legacy_baseline + legacy_prompt`.
- `decision.final_input_mode=decision_input` remains blocked by config validation.
- Candidate/pre-final artifacts remain audit sidecars with `decision_effect=none`.
- This checkpoint still does not write production journal, notification or live order side effects from candidate/pre-final artifacts.
