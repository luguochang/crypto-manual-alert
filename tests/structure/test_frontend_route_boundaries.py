from __future__ import annotations

from pathlib import Path


EVAL_ROUTE = Path("frontend/src/app/eval/page.tsx")
EVAL_COMPONENTS = {
    "financial-quality-panel.tsx",
    "eval-candidates-table.tsx",
    "eval-replay-table.tsx",
    "eval-judge-scores-table.tsx",
}
RUN_DETAIL_ROUTE = Path("frontend/src/app/runs/[traceId]/page.tsx")
RUN_DETAIL_COMPONENTS = {
    "agent-audit-panel.tsx",
    "worker-matrix.tsx",
    "tool-call-graph.tsx",
    "source-freshness-panel.tsx",
    "conflict-matrix.tsx",
    "candidate-comparison.tsx",
}


def test_eval_route_keeps_tables_and_financial_quality_in_components():
    eval_dir = EVAL_ROUTE.parent
    component_files = {path.name for path in eval_dir.glob("*.tsx")}

    assert EVAL_COMPONENTS <= component_files
    assert _line_count(EVAL_ROUTE) <= 280


def test_run_detail_route_keeps_agent_audit_in_components():
    run_detail_dir = RUN_DETAIL_ROUTE.parent
    component_files = {path.name for path in run_detail_dir.glob("*.tsx")}

    assert RUN_DETAIL_COMPONENTS <= component_files
    assert _line_count(RUN_DETAIL_ROUTE) <= 380


def test_run_detail_agent_audit_panel_exposes_first_screen_risk_summary():
    source = (RUN_DETAIL_ROUTE.parent / "agent-audit-panel.tsx").read_text(encoding="utf-8")

    assert "buildRiskSummaryItems" in source
    assert "<dt>Mode</dt>" in source
    assert "<dt>Candidate Status</dt>" in source
    assert "<dt>Blocked Reason</dt>" in source
    assert "Tool Calls Missing" in source
    assert "Candidate Gate Failed" in source
    assert "Financial Quality Missing" in source
    assert "Production Final Input" in source


def test_run_detail_tool_call_graph_exposes_tool_error_summary():
    source = (RUN_DETAIL_ROUTE.parent / "tool-call-graph.tsx").read_text(encoding="utf-8")

    assert "<th>Error</th>" in source
    assert "error_type" in source
    assert "error_hash" in source


def test_run_detail_json_payloads_are_collapsed_auxiliary_details():
    source = RUN_DETAIL_ROUTE.read_text(encoding="utf-8")

    assert "JsonDetails" in source
    assert 'open={index < 3}' not in source
    assert 'open={index === 0 || item.status !== "ok"}' not in source
    assert '<pre className="code-box light-code">{formatJson(analysis.data_gaps ?? [])}</pre>' not in source
    assert '<pre className="code-box light-code">{formatJson(analysis.risk_rule_hits ?? verdict)}</pre>' not in source
    assert '<pre className="code-box">{formatJson(badcases)}</pre>' not in source
    assert '<pre className="code-box large-code">{formatJson(parsedPlan)}</pre>' not in source


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())
