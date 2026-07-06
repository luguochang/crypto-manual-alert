# Checkpoint 9 - Risk Summary And Tool Errors

## Context

Run Detail already displayed Agent/Skill/Gate details, but the top of the
Agent Audit panel still required reviewers to scan several tables to understand
whether a trace could be trusted and why it remained blocked.

## Changes

- Added first-screen summary fields for `mode`, `final input`, candidate status,
  and blocked reason.
- Added a compact `Risk Summary` strip with:
  - `Tool Calls Missing`
  - `Candidate Gate Failed`
  - `Financial Quality Missing`
  - `Production Final Input`
- The risk summary uses concise Chinese details for operator readability.
- Added an `Error` column to `Skill Tool Calls`, showing `error_type` and a
  shortened `error_hash`.
- Added responsive CSS so the risk summary renders as four columns on desktop,
  two columns below 900px, and one column below 560px.

## Verification

```powershell
python -m pytest tests/structure/test_frontend_route_boundaries.py::test_run_detail_agent_audit_panel_exposes_first_screen_risk_summary -q
python -m pytest tests/structure/test_frontend_route_boundaries.py::test_run_detail_tool_call_graph_exposes_tool_error_summary -q
python -m pytest tests/structure/test_frontend_route_boundaries.py -q
npm run typecheck
```

## Remaining Gaps

- Browser/page smoke with a real trace is still needed to prove rendered layout
  across desktop and mobile viewports.
- JSON sections still need a separate pass to make sure they are auxiliary
  rather than the main expression.
