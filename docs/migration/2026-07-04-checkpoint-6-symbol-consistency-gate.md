# Checkpoint 6: Symbol Consistency Gate

## Scope

This slice implements the first checkpoint 6 hard gate from `docs/formal/34-生产级AgentSwarm优化目标与执行计划.md`.

It fixes a main-flow risk found during smoke testing: a manual request can use one symbol while the final fixture plan carries another instrument. The system now records and blocks this mismatch instead of leaving it implicit.

## Changes

- Added request/snapshot/final-plan symbol consistency evaluation in `workflow/decision_control_step.py`.
- Added blocking rule hit `production_control.symbol_consistency.mismatch`.
- Added `symbol_consistency` to candidate audit payloads.
- Projected `symbol_consistency` through `agent_audit_view`.
- Added typed frontend schema for `symbol_consistency`.
- Displayed symbol consistency status in the run detail Agent Audit panel.

## Safety Boundary

- Production final input remains `legacy_prompt`.
- No order, notification, or production final-input switch behavior was added.
- Candidate and shadow artifacts remain audit/candidate sidecars.

## Verification

```powershell
python -m pytest tests/workflow/test_decision_control_step.py tests/storage/test_agent_audit_view.py tests/api/test_runs_routes.py -q
npm run typecheck
python -m crypto_manual_alert.cli run-once --symbol BTC-USDT-SWAP
```

Latest smoke evidence:

- Latest trace: `2f1e485b0c3f4d28a9bbd548ac32c155`.
- `agent_audit_view.symbol_consistency`:

```json
{
  "request_symbol": "BTC-USDT-SWAP",
  "snapshot_symbol": "BTC-USDT-SWAP",
  "plan_instrument": "ETH-USDT-SWAP",
  "consistent": false
}
```

- Blocking rule ids include `production_control.symbol_consistency.mismatch`.

Runtime UI smoke:

```powershell
uvicorn crypto_manual_alert.api.app:app --host 127.0.0.1 --port 8000
npm run dev -- -p 3000
POST http://127.0.0.1:8000/api/runs/manual
GET  http://127.0.0.1:3000/runs/{trace_id}
```

- UI smoke trace: `445061af25144256abe3ad7c0bb05be7`.
- Run detail page returned HTTP 200.
- Rendered page contains `Symbol Check`, `mismatch`, and `ETH-USDT-SWAP`.

Runtime flow smoke after dynamic projection:

- Runtime-flow smoke trace: `18cc5c8f84fd43df82c5ed609e940fc4`.
- First runtime flow item:

```json
{
  "name": "market.fetch",
  "owner": "market.fetch",
  "effect": "runtime span executed",
  "status": "ok",
  "duration_ms": 2,
  "source": "span_tree_refs"
}
```

- Rendered page contains `market.fetch`, `span_tree_refs`, and `mismatch`.

Runtime flow artifact ref smoke:

- Span-ref smoke trace: `9e0854effea44818a3d3d8db67c921e2`.
- `runtime_flow[0]` includes `span_input_hash`, `span_output_hash`, `input_refs.symbol`, and `output_refs.symbol`.
- `agent_audit_view` does not contain the string `frozen_input`.
- Rendered page contains `span_tree_refs` and `sha256`.

## Remaining Checkpoint 6 Work

- Continue enriching runtime flow with domain-specific refs for gates, worker contributions, and tool call artifacts.
