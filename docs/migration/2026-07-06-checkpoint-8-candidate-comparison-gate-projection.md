# Checkpoint 8 - Candidate Comparison Gate Projection

## Context

This slice closes the remaining phase-one projection gap from
`docs/formal/35-剩余主缺口对抗审查与执行清单.md`.

Before this change, `candidate_final_comparison` exposed the legacy final and
candidate final summaries, while `production_control_gate` was available in a
separate gate projection. Reviewers had to cross-read multiple panels to answer
whether the legacy final, candidate final, and production control gate were
consistent for the same trace.

## Changes

- `build_agent_audit_view()` now includes a sanitized
  `candidate_final_comparison.production_control_gate` summary.
- The summary exposes only `allowed`, `reasons`, and `blocking_rule_ids`.
- `CandidateComparison` shows candidate error plus Production Gate, Gate
  Reasons, and Blocking Rules.
- Frontend run schemas include `production_control_gate` as a typed candidate
  comparison field.
- `production_candidate_swarm` remains blocked audit-only and still does not
  write notification output or production final input.

## Verification

```powershell
python -m pytest tests/storage/test_agent_audit_view.py::test_agent_audit_view_projects_sanitized_candidate_final_comparison -q
python -m pytest tests/storage/test_agent_audit_view.py -q
python -m pytest tests/workflow/test_controlled_adapter.py::test_run_executor_can_route_to_production_candidate_swarm_but_keeps_it_blocked -q
python -m pytest tests/workflow/test_controlled_adapter.py tests/api/test_runs_routes.py tests/storage/test_agent_audit_view.py -q
npm run typecheck
```

API smoke:

- trace id: `production-candidate-swarm-run_65e1ab37ed2c4c84a6e260f8154d89d2`
- mode: `production_candidate_swarm`
- workers: 7
- tool calls: 4
- candidate status: `audit_only`
- production final input: `false`
- comparison gate reasons: `production_candidate_swarm_audit_only`

## Remaining Gaps

- `production_candidate_swarm` is still a blocked audit-only adapter.
- It still does not run a real legacy production final inside that adapter path.
- Real external providers remain fail-closed unless explicitly implemented and
  configured.
- A runtime page smoke should still be run after the focused tests to confirm
  real trace visibility.
