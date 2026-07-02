# Checkpoint 8 Legacy 收敛实施记录

Date: 2026-07-03

Source plan: `docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md`

## Status

Checkpoint 8 is complete.

Completed slices:

- 8A. legacy prompt 用途降级。
- 8B. compatibility wrapper 生命周期表。
- 8C. 文档与全量验收。

## 8A legacy prompt 用途降级记录

Modified:

- `src/crypto_manual_alert/workflow/persistence_payload.py`
- `tests/workflow/test_persistence_payload.py`
- `tests/workflow/test_run_executor.py`

What changed:

- Added `legacy_prompt_lifecycle` to persisted plan payloads.
- The lifecycle marks legacy prompt as one of:
  - `legacy_primary_until_switch_review`
  - `decision_input_fallback`
  - `replay_and_comparison_only`
- When DecisionInput is selected, legacy prompt is explicitly limited to replay baseline and legacy comparison.
- When DecisionInput is approved by config but runtime readiness falls back, legacy prompt is marked as `decision_input_fallback` and includes fallback reason and blocking reasons.

Red evidence:

```powershell
python -m pytest tests/workflow/test_persistence_payload.py -q
```

Observed:

- Plan payloads initially had no legacy prompt lifecycle marker.

Green verification:

```powershell
python -m pytest tests/workflow/test_persistence_payload.py -q
python -m pytest tests/workflow/test_run_executor.py::test_run_executor_full_legacy_chain_feeds_candidate_replay_and_release_gate tests/workflow/test_run_executor.py::test_run_executor_falls_back_to_legacy_when_decision_input_mode_is_approved_but_runtime_not_ready -q
python -m pytest tests/structure -q
```

Result: passed.

## 8B compatibility wrapper 生命周期表记录

Modified:

- `docs/formal/33-compatibility-wrapper-lifecycle.md`
- `docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md`
- `tests/structure/test_compatibility_wrapper_lifecycle.py`

What changed:

- Added the formal compatibility wrapper lifecycle table.
- The table records each wrapper's canonical owner, allowed usage, no-new-logic rule, removal condition, and current structure guard.
- The table covers `agent_swarm/contracts.py`, `agent_swarm/harness.py`, `agent_swarm/default_lead_plan.py`, `agent_swarm/shadow_orchestration.py`, `agent_swarm/shadow_failure.py`, `agent_swarm/workers.py`, `agent_swarm/local_workers/`, and `skills/runtime.py`.
- The table also separates retained non-wrapper runtime modules from removable compatibility wrappers.
- Read-only subagent review was adopted for two edge cases: `shadow_orchestration.py` now records `orchestration/shadow_failure.py` as a secondary owner, and package facades `agent_swarm/__init__.py` plus `skills/__init__.py` are explicitly classified as stable package API facades rather than removable wrappers.

Red evidence:

```powershell
python -m pytest tests/structure/test_compatibility_wrapper_lifecycle.py -q
```

Observed:

- The lifecycle table document did not exist.
- The main plan and this migration note did not reference the lifecycle table.

Green verification:

```powershell
python -m pytest tests/structure/test_compatibility_wrapper_lifecycle.py -q
```

Result: passed.

Depth boundary:

- 8B did not run `tests/workflow/test_run_executor.py` because it only changed formal docs and a structure guard. Runner, journal, notification, CLI, release gate, and production switch entrypoints were not changed.

## 8C 文档与全量验收记录

Modified:

- `docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md`
- `docs/migration/2026-07-03-checkpoint-8-legacy-convergence.md`
- `tests/api/test_api_package_structure.py`
- `tests/structure/test_formal_docs_current_state.py`

What changed:

- Marked Checkpoint 8 as complete in the main execution plan.
- Corrected the main plan's current switch-state section to match the controlled switch review behavior implemented in Checkpoint 7.
- Fixed the API package structure test helper so temporary module removal restores parent package attributes as well as `sys.modules`.
- Rebuilt the formal-doc current-state structure test around stable ASCII key fields to avoid preserving old mojibake assertions.

Failure and root cause:

- First full verification failed 6 tests in CLI/workflow monkeypatch scenarios.
- Root cause: `_without_modules()` restored `sys.modules` but left parent package attributes, such as `crypto_manual_alert.workflow`, pointing at modules imported inside the isolation block. Later monkeypatch calls patched the temporary module while already-collected tests still held objects from the original module.
- This was test isolation pollution, not a production workflow behavior change.

Green verification:

```powershell
python -m pytest tests/api/test_api_package_structure.py tests/cli/test_runner_cli.py::test_runner_records_shadow_swarm_failure_without_changing_verdict -q
python -m pytest tests/agent_swarm tests/api tests/artifacts tests/config tests/context tests/decision tests/cli/test_runner_cli.py::test_runner_records_shadow_swarm_failure_without_changing_verdict -q
python -m pytest tests/cli/test_runner_cli.py::test_runner_records_shadow_swarm_failure_without_changing_verdict tests/cli/test_runner_cli.py::test_runner_sends_notification_even_when_shadow_swarm_fails tests/workflow/test_legacy_adapter.py::test_legacy_plan_runner_adapter_passes_full_context_to_plan_runner tests/workflow/test_pre_final_orchestration.py::test_pre_final_orchestration_passes_config_to_shadow_worker_registry tests/workflow/test_pre_final_orchestration.py::test_pre_final_orchestration_builds_single_audit_payload_source tests/workflow/test_run_executor.py::test_run_executor_passes_pre_final_decision_input_to_final_step_boundary -q
python -m pytest
python -m pytest tests/structure -q
```

Result:

- `python -m pytest` passed on the final current worktree: `775 passed in 352.27s`.
- Post-document update structure verification passed.

## Boundaries Preserved

- Production still defaults to `legacy_baseline + legacy_prompt` unless an explicit switch review artifact approves DecisionInput config.
- DecisionInput runtime fallback does not hide candidate blocking reasons.
- Legacy prompt lifecycle is audit metadata only; it does not create notification, journal, or live-order side effects.
