# Checkpoint 7 受控切换与回退实施记录

Date: 2026-07-03

Source plan: `docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md`

## Status

Checkpoint 7 is complete.

Completed slices:

- 7A. 人工 config-change review artifact。
- 7B. candidate 故障到 legacy fallback，但不得覆盖事实缺失或风险阻断。
- 7C. 回滚计划。

Next slice:

- Checkpoint 8A. legacy prompt 用途降级。

## 7A 人工 config-change review artifact 记录

Modified:

- `src/crypto_manual_alert/eval/promotion_artifacts.py`
- `src/crypto_manual_alert/eval/promotion_artifact_validation.py`
- `src/crypto_manual_alert/eval/release_promotion_review.py`
- `tests/eval/test_promotion_artifacts.py`
- `tests/eval/test_promotion_artifact_validation.py`
- `tests/eval/test_promotion_review.py`

What changed:

- Added `config_change_review_approval` as the human approval artifact after a valid manual release decision and config-change review request.
- The artifact records reviewer, config-change request ref, manual release decision ref, candidate input ref/hash, config hash, rollback plan ref and notes.
- The artifact remains audit-only: `decision_effect=none`, `allowed_to_change_production_final_input=false`, and `runtime_switch_gate_required=true`.
- Promotion review can now advance from `config_change_review_requested` to `config_change_review_approved`.
- `promotion_approved` remains false; `config/loader.py` still rejects `decision.final_input_mode=decision_input`.

Red evidence:

```powershell
python -m pytest tests/eval/test_promotion_artifacts.py::test_config_change_review_approval_records_no_side_effect_human_review tests/eval/test_promotion_review.py::test_upsert_promotion_review_artifacts_recomputes_release_gate_without_approving -q
```

Observed:

- Missing `build_config_change_review_approval()` caused import failure.
- Promotion review had no terminal config-change approval state after request.

Green verification:

```powershell
python -m pytest tests/eval/test_promotion_artifacts.py tests/eval/test_promotion_artifact_validation.py tests/eval/test_promotion_review.py -q
python -m pytest tests/config -q
python -m pytest tests/eval/test_release_gate.py -q
python -m pytest tests/structure -q
```

Result: passed.

Depth boundary:

- `tests/workflow/test_run_executor.py` was not run for 7A because this slice did not change workflow executor, production journal write entrypoint, notification sender entrypoint, CLI entrypoint, replay entrypoint, or production switching behavior.

## 7B candidate 故障到 legacy fallback 记录

Modified:

- `src/crypto_manual_alert/decision/final_input.py`
- `tests/decision/test_final_input.py`
- `tests/decision/test_production_control_gate.py`

What changed:

- `select_final_input()` now falls back to the legacy prompt when `final_input_mode=decision_input` but the candidate input is not ready, missing, invalid, or missing its input ref/hash.
- The fallback selection keeps audit metadata: `fallback_reason`, `fallback_from_mode`, `fallback_blocking_reasons`, `candidate_input_ref`, and `candidate_input_hash`.
- Fallback metadata does not suppress candidate business gates, FactsGate-derived blockers, or worker hard blocks. Production control still blocks executable actions when candidate audit contains hard blocks.
- Production config remains blocked: `config/loader.py` still rejects `decision.final_input_mode=decision_input`.

Red evidence:

```powershell
python -m pytest tests/decision/test_final_input.py -q
```

Observed:

- `decision_input` not ready raised `ValueError` instead of returning a controlled legacy fallback selection.
- invalid candidate validation raised `ValueError` instead of preserving candidate refs and fallback metadata.

Green verification:

```powershell
python -m pytest tests/decision/test_final_input.py -q
python -m pytest tests/decision/test_final_decision_step.py tests/decision/test_production_control_gate.py -q
python -m pytest tests/workflow/test_decision_control_step.py tests/workflow/test_persistence_payload.py -q
python -m pytest tests/decision -q
python -m pytest tests/structure -q
```

Result: passed.

Depth boundary:

- `tests/workflow/test_run_executor.py` was not run for 7B because this slice did not change workflow executor, production journal write entrypoint, notification sender entrypoint, CLI entrypoint, replay entrypoint, or production switching behavior.

## 7C 回滚计划与 switch review gate 记录

Modified:

- `src/crypto_manual_alert/config/models.py`
- `src/crypto_manual_alert/config/loader.py`
- `src/crypto_manual_alert/config/final_input_switch_review.py`
- `tests/config/test_config.py`
- `tests/workflow/test_run_executor.py`
- `tests/structure/test_root_package_structure.py`

What changed:

- Added `decision.final_input_mode_switch_review_path`.
- Added a config-time switch review gate for `decision.final_input_mode=decision_input`.
- The switch review artifact must bind release gate, promotion/config approval, manual release decision, config-change request, candidate input, config hash, and rollback plan refs/hashes.
- The switch review artifact must keep rollback target as `config:decision.final_input_mode=legacy_prompt` and must include rollback steps.
- The switch review artifact must preserve `fallback_behavior=legacy_prompt_on_candidate_failure`, `manual_execution_required=true`, and `auto_order_enabled=false`.
- Added a workflow smoke proving that an approved `decision_input` config still falls back to legacy prompt when runtime switch readiness is not ready, while preserving candidate ref/hash fallback metadata.

Red evidence:

```powershell
python -m pytest tests/config/test_config.py::test_config_accepts_decision_input_only_with_runtime_switch_review_artifact tests/config/test_config.py::test_config_rejects_decision_input_when_runtime_switch_review_lacks_rollback tests/config/test_config.py::test_config_rejects_decision_input_when_runtime_switch_review_lacks_fallback -q
python -m pytest tests/config/test_config.py::test_config_rejects_decision_input_when_runtime_switch_review_lacks_ref_hash_bindings -q
```

Observed:

- `DecisionConfig` initially rejected the new switch review path field.
- After initial gate implementation, missing ref/hash bindings were not rejected.

Green verification:

```powershell
python -m pytest tests/config -q
python -m pytest tests/workflow/test_run_executor.py::test_run_executor_falls_back_to_legacy_when_decision_input_mode_is_approved_but_runtime_not_ready -q
python -m pytest tests/config tests/decision tests/workflow tests/cli -q
python -m pytest tests/eval/test_release_gate.py tests/eval/test_promotion_review.py -q
python -m pytest tests/structure -q
```

Result: passed.

## Boundaries Preserved

- Production still defaults to `legacy_baseline + legacy_prompt`.
- `decision.final_input_mode=decision_input` is accepted only with a valid switch review artifact. Without that artifact, config validation still blocks it.
- Runtime switch readiness still falls back to `legacy_prompt` when candidate input is not ready.
- Shadow/candidate/eval/replay artifacts remain audit/sidecar only and still cannot create production journal, notification or live-order side effects.
