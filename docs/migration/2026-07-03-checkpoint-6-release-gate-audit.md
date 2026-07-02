# Checkpoint 6 Release Gate 与发布审计实施记录

Date: 2026-07-03

Source plan: `docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md`

## Status

Checkpoint 6 is complete.

Completed slices:

- 6A. release gate 硬门禁。
- 6B. 发布样本与 badcase 覆盖。
- 6C. 无生产副作用证明。
- 6D. 记忆与事实隔离回归。

Next slice:

- Checkpoint 7A. 人工 config-change review artifact。

## 6A Release Gate 硬门禁进行记录

Modified:

- `src/crypto_manual_alert/eval/release_gate.py`
- `tests/eval/test_release_gate.py`

What changed:

- Extended candidate replay side-effect guard to reject effectful `candidate_final_legacy_comparison` artifacts.
- Added defensive rejection if a `candidate_final_decision` sidecar appears in replay output with `decision_effect != none` or `production_final_input=true`.
- Kept production switching blocked; this gate remains audit-only and cannot approve production final input changes by itself.

Red test evidence:

```powershell
python -m pytest tests/eval/test_release_gate.py::test_release_gate_rejects_candidate_final_comparison_decision_effect_violation -q
```

Observed:

- Failed because release gate accepted a replay output whose `candidate_final_legacy_comparison.decision_effect` was `production_final_input`.

Green verification:

```powershell
python -m pytest tests/eval/test_release_gate.py::test_release_gate_rejects_candidate_final_comparison_decision_effect_violation tests/eval/test_release_gate.py::test_release_gate_rejects_candidate_replay_with_nested_decision_effect_violation tests/eval/test_release_gate.py::test_release_gate_rejects_candidate_replay_without_no_side_effect_metadata -q
python -m pytest tests/eval/test_release_gate.py -q
python -m pytest tests/eval/test_promotion_review.py tests/eval/test_promotion_artifacts.py tests/eval/test_promotion_artifact_validation.py -q
python -m pytest tests/eval/test_candidate_audit_rules.py tests/eval/test_counter_conflict_coverage.py tests/eval/test_complete_replay_refs.py -q
```

Result: passed.

Open gaps found by adversarial review:

- Fixed: worker artifact threshold is now `7` in release gate and promotion review.
- Fixed: missing or malformed `worker_manifest_consistency`, `context_artifact_consistency`, `counter_conflict_coverage`, span parent evidence, and complete replay refs now block release gate.
- Fixed: promotion recompute paths now pass stored cases and configured badcase severity requirements into release gate.

Additional red test evidence:

```powershell
python -m pytest tests/eval/test_release_gate.py::test_release_gate_requires_current_seven_required_worker_artifacts -q
python -m pytest tests/eval/test_release_gate.py::test_release_gate_blocks_when_required_candidate_replay_evidence_is_missing tests/eval/test_release_gate.py::test_release_gate_blocks_when_complete_replay_refs_are_false_even_if_missing_list_is_empty tests/eval/test_release_gate.py::test_release_gate_blocks_when_span_tree_parent_evidence_is_missing -q
python -m pytest tests/eval/test_promotion_review.py::test_upsert_promotion_review_artifacts_preserves_required_badcase_severity_gate -q
```

Observed:

- 4-worker candidate replay was initially accepted.
- Missing worker/context/counter/span/complete replay evidence was initially accepted.
- Promotion recompute initially rejected the new `required_badcase_severities` argument.

Final 6A verification:

```powershell
python -m pytest tests/eval/test_release_gate.py -q
python -m pytest tests/eval/test_promotion_review.py tests/eval/test_promotion_artifacts.py tests/eval/test_promotion_artifact_validation.py -q
python -m pytest tests/eval/test_replay_llmjudge.py::test_eval_runner_uses_configured_release_gate_thresholds_without_prod_side_effects tests/eval/test_replay_llmjudge.py::test_candidate_decision_replay_can_run_injected_decision_input_shadow_final tests/eval/test_replay_llmjudge.py::test_candidate_decision_replay_compares_persisted_candidate_final_sidecar -q
python -m pytest tests/eval/test_context_artifact_readback.py tests/eval/test_candidate_artifact_validation.py tests/eval/test_promotion_artifact_store.py -q
python -m pytest tests/structure -q
```

Result: passed.

## 6B 发布样本与 badcase 覆盖记录

Modified:

- `config/default.yaml`
- `src/crypto_manual_alert/config/models.py`
- `tests/config/test_config.py`

What changed:

- Raised default release-grade eval sample requirement to `minimum_case_count=20`.
- Raised default schema-valid threshold to `schema_valid_rate_threshold=0.95`.
- Required stored badcase coverage for `high` and `critical` severities before release promotion can pass.
- Kept production default on `legacy_baseline + legacy_prompt`; this slice only changes audit/eval thresholds.

Red evidence:

- Default release gate configuration was too weak for release-grade promotion and did not require `high` plus `critical` badcase coverage by default.

Green verification:

```powershell
python -m pytest tests/config/test_config.py::test_default_config_disables_auto_ordering tests/config/test_config.py::test_config_accepts_release_gate_thresholds tests/config/test_config.py::test_config_rejects_invalid_release_gate_thresholds tests/config/test_config.py::test_config_rejects_unknown_release_gate_badcase_severity -q
python -m pytest tests/config -q
python -m pytest tests/eval/test_replay_llmjudge.py::test_eval_runner_uses_configured_release_gate_thresholds_without_prod_side_effects tests/eval/test_promotion_review.py tests/eval/test_release_gate.py -q
```

Result: passed.

Depth boundary:

- `tests/workflow/test_run_executor.py` was not run for 6B because the slice did not change workflow executor, journal write, side-effect gate, CLI entrypoint, replay entrypoint, or production switching behavior.
- Runner depth verification remains reserved for checkpoint closeout or entry-boundary changes.

## 6C 无生产副作用证明记录

Modified:

- `src/crypto_manual_alert/eval/side_effect_proof.py`
- `src/crypto_manual_alert/eval/runner.py`
- `src/crypto_manual_alert/eval/release_gate.py`
- `src/crypto_manual_alert/eval/release_promotion_review.py`
- `tests/eval/test_side_effect_proof.py`
- `tests/eval/test_release_gate.py`
- `tests/eval/test_promotion_review.py`
- `tests/eval/test_replay_llmjudge.py`

What changed:

- Added `no_production_side_effect_proof` as a structured eval artifact with `decision_effect=none`, `production_final_input=false`, `notification_input=false`, and `live_order_input=false`.
- EvalRunner now records before/after production table counts and stable row fingerprints for `plan_runs`, `notifications`, `manual_outcomes`, `traces`, `trace_spans`, and `llm_interactions`.
- Release gate now hard-blocks missing, failed, or malformed proof when evaluating a concrete `eval_run_id`.
- Promotion review also requires the proof as release material, so manual release decisions must reference it.
- Candidate replay side-effect guard now rejects nested `production_final_input`, `notification_input`, and `live_order_input` flags.

Adversarial review findings handled:

- Fixed: malformed proof with missing deltas no longer passes validation.
- Fixed: proof is now a release hard gate, not only promotion paperwork.
- Fixed: count-stable mutation risk is covered by row fingerprints.
- Fixed: nested replay side-effect flags are rejected across candidate replay payloads.

Red evidence:

```powershell
python -m pytest tests/eval/test_side_effect_proof.py -q
python -m pytest tests/eval/test_release_gate.py::test_release_gate_requires_no_production_side_effect_proof_for_promotion_material -q
python -m pytest tests/eval/test_release_gate.py::test_release_gate_rejects_candidate_replay_with_nested_side_effect_flags -q
```

Observed:

- Missing proof builder initially failed import.
- Release gate initially allowed hard gates to pass without proof.
- Nested side-effect flags were not fully rejected.

Green verification:

```powershell
python -m pytest tests/eval/test_side_effect_proof.py tests/eval/test_release_gate.py tests/eval/test_promotion_review.py tests/eval/test_promotion_artifacts.py tests/eval/test_promotion_artifact_validation.py tests/eval/test_replay_llmjudge.py::test_eval_runner_uses_configured_release_gate_thresholds_without_prod_side_effects -q
python -m pytest tests/eval -q
python -m pytest tests/structure -q
```

Result: passed.

Depth boundary:

- `tests/workflow/test_run_executor.py` was not run for 6C because the slice did not change workflow executor, production journal write entrypoint, notification sender entrypoint, CLI entrypoint, or production switching behavior.
- Runner depth verification remains reserved for Checkpoint 6 closeout or entry-boundary changes.

## 6D 记忆与事实隔离回归记录

Modified:

- `src/crypto_manual_alert/context/memory_firewall.py`
- `src/crypto_manual_alert/context/run_context.py`
- `src/crypto_manual_alert/decision/replay_observed_refs.py`
- `src/crypto_manual_alert/eval/replayable_input_summary.py`
- `tests/context/test_run_context.py`
- `tests/decision/test_replayable_input.py`
- `tests/eval/test_replayable_input_summary.py`

What changed:

- Added a shared memory firewall for structured session memory.
- `DecisionRunContext.set_memory_snapshot()` now filters `allowed_fields` through a whitelist of user/session context fields.
- Old market facts and stale decision facts are quarantined instead of being exposed as current memory context: `mark`, `funding`, `open_interest`, `order_book`, `news_status`, `macro_event_status`, `last_model_conclusion`, and `previous_final_action`.
- Replayable input observed refs reuse the same firewall so direct observed artifact input cannot bypass context sanitization.
- Replayable input summary keeps `quarantined_fields` and `memory_warnings` for audit without copying quarantined values.

Red evidence:

```powershell
python -m pytest tests/context/test_run_context.py::test_decision_run_context_quarantines_market_fact_like_memory_fields tests/decision/test_replayable_input.py::test_replayable_input_candidate_quarantines_memory_market_facts -q
```

Observed:

- `DecisionRunContext.memory_snapshot.allowed_fields` initially preserved stale market facts.
- Replayable input construction from observed artifacts initially preserved the same stale fact fields.

Green verification:

```powershell
python -m pytest tests/context/test_run_context.py -q
python -m pytest tests/context -q
python -m pytest tests/decision/test_replayable_input.py -q
python -m pytest tests/eval/test_replayable_input_summary.py -q
python -m pytest tests/decision/test_switch_readiness.py tests/decision/test_pre_final_switch_readiness.py -q
python -m pytest tests/structure -q
python -m pytest tests/eval -q --durations=10
```

Result: passed.

Depth boundary:

- `tests/workflow/test_run_executor.py` was not run for 6D because the slice did not change workflow executor, production journal write entrypoint, notification sender entrypoint, CLI entrypoint, replay entrypoint, or production switching behavior.
- First `python -m pytest tests/eval -q` run used a 120 second limit and timed out; rerun with a 300 second limit passed. Slow tests were concentrated in replay/LLM-judge eval fixtures, not in an infinite retry loop.

## Boundaries Preserved

- Production still defaults to `legacy_baseline + legacy_prompt`.
- `decision.final_input_mode=decision_input` remains blocked by config validation.
- Release gate remains a no-side-effect audit artifact; manual promotion artifacts still cannot directly switch production final input.
