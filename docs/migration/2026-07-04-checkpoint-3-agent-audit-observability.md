# Checkpoint 3 Agent Audit Observability

## Scope

This checkpoint adds first-class API projection fields and frontend panels for the Agent Swarm audit chain. It does not switch production final input away from `legacy_prompt`, and it does not enable live order, notification, or journal side effects.

## Backend Changes

- Added focused projection helpers under `src/crypto_manual_alert/storage/agent_audit_projection/`.
- `build_agent_audit_view()` now exposes first-class fields:
  - `tool_calls[]`
  - `evidence_sources[]`
  - `source_freshness[]`
  - `root_cause_graph`
  - `conflict_edges[]`
  - `strongest_counter_thesis_ref`
  - `input_lineage`
  - `release_eval_gate`
- Projection remains ref/hash/source/freshness oriented and does not expose raw prompt, raw candidate final output, raw skill payload, snippets, or raw error messages.
- `input_lineage` explicitly shows production final input remains `legacy_prompt`.
- `release_eval_gate.financial_quality_gate.status` is `not_configured` until the financial quality evaluation checkpoint lands.

## Frontend Changes

- Added typed schemas for the new Agent Audit projection fields in `frontend/src/lib/schemas/runs.ts`.
- Replaced the corrupted large run detail page with a smaller page shell plus focused Agent Audit components:
  - `agent-audit-panel.tsx`
  - `worker-matrix.tsx`
  - `tool-call-graph.tsx`
  - `source-freshness-panel.tsx`
  - `conflict-matrix.tsx`
  - `candidate-comparison.tsx`
- `/runs/{trace_id}` now renders LeadPlan, Worker Matrix, Skill Tool Calls, Source Freshness, Root Cause Graph, Conflict Matrix, Candidate Comparison, Input Lineage, and Release/Gate status.

## Verification

Commands run:

```powershell
python -m pytest tests/storage/test_agent_audit_view.py::test_agent_audit_view_projects_full_chain_observability_fields_without_raw_payloads tests/api/test_runs_routes.py::test_run_detail_exposes_sanitized_agent_audit_view -q
python -m pytest tests/storage/test_agent_audit_view.py tests/api/test_runs_routes.py tests/decision/test_decision_input.py tests/decision/test_replayable_input.py tests/decision/test_pre_final_input_gate.py tests/context/test_run_context.py tests/structure/test_skill_executor_boundaries.py -q
npm run typecheck
npm run build
python tools/local_stack/smoke_local_stack.py
python tools/local_stack/start_local_stack.py
```

Runtime self-test result on the running local stack:

- API: `http://127.0.0.1:8010`
- Frontend: `http://127.0.0.1:3001`
- Trace checked: `c22e1c7fda204d92aad5af4c65031a70`
- API returned `available=true`, `workers=7`, `tool_calls`, `evidence_sources`, `source_freshness`, `input_lineage`, and `release_eval_gate`.
- Frontend HTML contained `Skill Tool Calls`, `Source Freshness`, `Root Cause Graph`, and `Candidate Comparison`.

## Known Limits

- Default `shadow.worker_mode=local_audit` does not fabricate SkillExecutor calls, so runtime `tool_calls[]` can be empty until `llm_tool_shadow` and real Skill execution are enabled for a run.
- `RootCauseSearchSkill` still does not perform real recursive web searched retrieval.
- Financial prediction quality evaluation is still not implemented; the UI correctly reports the financial quality gate as `not_configured`.

## Side Effect Statement

Production final input remains `legacy_prompt`. Candidate/Swarm artifacts remain audit/candidate data with `decision_effect=none`. This checkpoint does not send notifications, place orders, or enable production candidate switching.
