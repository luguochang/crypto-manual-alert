from typing import Any, Literal, TypedDict


class AnalysisState(TypedDict, total=False):
    lifecycle: str
    task_type: Literal["market_analysis", "deep_research", "monitor_ingress"]
    request: dict[str, Any]
    market_snapshot: dict[str, Any]
    research_bundle: dict[str, Any]
    web_evidence: list[dict[str, Any]]
    model_audits: list[dict[str, Any]]
    analysis: dict[str, Any]
    evidence_verdict: dict[str, Any]
    risk_verdict: dict[str, Any]
    artifact: dict[str, Any]
    deep_research_artifact: dict[str, Any]
    monitor_trigger: dict[str, Any]
    admitted_task_id: str | None
    research_harness_mode: Literal["deepagents", "langchain"]
    review_policy: Literal["bypass", "required"]
    review_action: Literal["approve", "reject", "edit"] | None
    review_edits: dict[str, Any] | None
    review_comment: str | None
    review_iteration: int
    terminal_status: str
    errors: list[dict[str, Any]]
