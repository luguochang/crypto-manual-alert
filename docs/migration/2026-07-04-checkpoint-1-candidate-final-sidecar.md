# Checkpoint 1 - Candidate Final Sidecar Boundary

Date: 2026-07-04

## Scope

This checkpoint wires the existing candidate final sidecar into the real legacy control step without changing production final input selection.

## Data Flow

```text
pre_final DecisionInput
  -> pre_final_input_gate
  -> run_candidate_final_decision_sidecar
  -> candidate_audit.candidate_final_decision
  -> plan payload audit-only namespace
  -> agent_audit_view.candidate_final_comparison
```

## Safety Boundary

- Production final input remains `legacy_prompt`.
- Candidate final output is stored only as audit/candidate artifact data.
- Candidate final output does not create a production final input.
- Candidate final output does not write a separate production decision.
- Candidate final output does not send notifications or place orders.
- Candidate final input strips legacy/raw/frozen fields before calling the decision engine.

## Verification

- `tests/decision/test_candidate_final_decision.py`
- `tests/workflow/test_decision_control_step.py`
- `tests/storage/test_agent_audit_view.py`
- `tests/api/test_runs_routes.py`
- `tests/workflow/test_persistence_payload.py`
- `tests/workflow/test_run_executor.py`
- `tests/decision/test_candidate_audit.py`

## Remaining Work

The sidecar is still `audit_only`. It must not be treated as production candidate Agent Swarm until real `ToolCallArtifact` and `SkillExecutor` evidence boundaries are implemented.
