# Checkpoint 9 Observability Slice

Date: 2026-07-04

## Scope

This slice closes the most visible Checkpoint 9 gap: a manual run can now be audited from stored backend payload through API projection and frontend UI. It does not complete the remaining Checkpoint 9 items for query-driven planning, explicit trace binding, controlled shadow trace semantics, or stale 29/30 document cleanup.

## Changes

- Added `storage.agent_audit_view.build_agent_audit_view()` as the sanitized projection layer for `plan_runs.payload_json`.
- `GET /api/runs/{trace_id}` now exposes `plan_run.agent_audit_view` by default.
- The projection includes LeadPlan tasks, 7 worker results, lead synthesis, harness/facts gates, pre-final DecisionInput, candidate DecisionInput, gate/readiness results, final input selection, safe replay refs, and runtime flow.
- The projection filters raw/frozen prompt and completion material. Full replay material remains in storage only.
- The run detail frontend now renders a first-class `Agent Swarm Audit` view with LeadPlan, worker matrix, DecisionInput, gates, runtime flow, and `ExecutionRiskAgent`.
- Local stack smoke now asserts API and page visibility for `LeadPlan`, `ExecutionRiskAgent`, `DecisionInput`, and `production_control_gate`.

## Verification

```powershell
python -m pytest tests/storage/test_agent_audit_view.py tests/storage/test_query_repository.py tests/api/test_runs_routes.py tests/local_stack/test_scripts.py -q
cd frontend
npm run typecheck
npm run build
cd ..
python tools/local_stack/smoke_local_stack.py
```

Observed results:

- Focused pytest: 17 passed.
- Frontend typecheck: passed.
- Frontend build: passed.
- Local stack smoke: passed after stopping an existing local uvicorn process on port 8010.

## Remaining

- `query_text` still needs a clear decision: audit note only, or controlled intent input into planning/tool budgets/facts requirements.
- `RunExecutor` still needs explicit trace id binding instead of recent-trace lookup.
- `controlled_shadow` trace/persistence semantics still need cleanup or clear UI/API labeling.
- Documents 29 and 30 still need stale worker/canonical-owner facts corrected.
- A structural guard is still needed for future artifacts: producer -> persistence -> API projection -> frontend view -> runtime smoke assertion.
