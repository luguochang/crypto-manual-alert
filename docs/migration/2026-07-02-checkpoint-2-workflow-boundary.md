# Checkpoint 2 Workflow Boundary

Date: 2026-07-02

Source plan: `docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md`

## Scope

This checkpoint makes controlled shadow routing explicit without promoting Agent Swarm output to production final input.

## Changes

- Added `workflow.execution_mode` config with allowed values:
  - `legacy_baseline`
  - `controlled_shadow`
- Default config remains `workflow.execution_mode: legacy_baseline`.
- `RunExecutor` now selects the decision step from config:
  - `legacy_baseline` -> `LegacyPlanRunnerAdapter`
  - `controlled_shadow` -> `ControlledSwarmAuditAdapter`
- `controlled_shadow` remains audit-only and returns a blocked `no trade` result with `controlled_swarm_audit_only`.
- Added structure guard preventing `LegacyDecisionWorkflow` from directly importing Agent Swarm business modules, Lead modules, contribution/evidence internals, or `DecisionInput` builder internals.
- Extracted explicit `workflow.side_effect_gate.evaluate_side_effect_gate(...)`.
- `run_persistence_step.py` now evaluates side-effect permission through the explicit gate before production journal or notification writes.

## Non-Changes

- `decision.final_input_mode` remains `legacy_prompt`.
- Config loader still rejects `decision_input` final mode.
- Production default still runs the legacy baseline path.
- Controlled shadow route does not write production `plan_runs`, notifications, or current-plan side effects.

## Verification

Commands run:

```powershell
python -m pytest tests/config/test_config.py::test_default_config_disables_auto_ordering tests/config/test_config.py::test_config_accepts_controlled_shadow_workflow_mode tests/config/test_config.py::test_config_rejects_unknown_workflow_execution_mode -q
python -m pytest tests/workflow/test_controlled_adapter.py::test_run_executor_can_route_to_controlled_shadow_mode_from_config -q
python -m pytest tests/workflow/test_side_effect_gate.py -q
python -m pytest tests/workflow/test_run_persistence_step.py -q
python -m pytest tests/workflow tests/config tests/structure -q
```

Observed result:

- Focused config route tests passed.
- Controlled shadow route test passed.
- SideEffectGate tests passed.
- Persistence side-effect tests passed.
- Checkpoint 2 suite passed with exit code 0.

## Remaining Boundary

This checkpoint only establishes a controlled workflow route and side-effect gate boundary. It does not implement production-grade real-time facts, business workers, candidate final quality gates, or production `DecisionInput` switching.
