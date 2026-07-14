from typing import Any, TypedDict


class AnalysisState(TypedDict, total=False):
    lifecycle: str
    request: dict[str, Any]
    market_snapshot: dict[str, Any]
    research_bundle: dict[str, Any]
    web_evidence: list[dict[str, Any]]
    analysis: dict[str, Any]
    evidence_verdict: dict[str, Any]
    risk_verdict: dict[str, Any]
    artifact: dict[str, Any]
    terminal_status: str
    errors: list[dict[str, Any]]
