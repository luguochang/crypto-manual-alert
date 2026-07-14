from typing import Any, Literal, TypedDict


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
    review_policy: Literal["bypass", "required"]
    review_action: Literal["approve", "reject", "edit"] | None
    review_edits: dict[str, Any] | None
    review_comment: str | None
    review_iteration: int
    terminal_status: str
    errors: list[dict[str, Any]]
