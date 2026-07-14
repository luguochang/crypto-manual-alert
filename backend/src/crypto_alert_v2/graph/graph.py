from datetime import UTC, datetime
import json
from typing import Any
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from langchain_core.runnables import RunnableConfig
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from crypto_alert_v2 import __version__
from crypto_alert_v2.domain.evidence_policy import check_evidence_sufficiency
from crypto_alert_v2.domain.models import (
    Artifact,
    MarketAnalysis,
    MarketSnapshot,
    ResearchBundle,
)
from crypto_alert_v2.domain.risk_policy import apply_risk_policy
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.graph.request import (
    AnalysisRequest,
    ArtifactEdit,
    ReviewResponse,
)
from crypto_alert_v2.graph.runtime import AnalysisRuntime, get_default_runtime
from crypto_alert_v2.graph.state import AnalysisState
from crypto_alert_v2.observability.callbacks import build_observability_config
from crypto_alert_v2.providers.errors import ProviderUnavailable
from crypto_alert_v2.providers.capability_probe import SearchReadinessError
from crypto_alert_v2.providers.models import MarketSnapshot as ProviderMarketSnapshot
from crypto_alert_v2.providers.search import SearchEvidenceUnavailable


def _runtime(runtime: Runtime[AnalysisRuntime]) -> AnalysisRuntime:
    context = runtime.context
    if (
        context is None
        or context.market_provider is None
        or context.research_collector is None
        or context.analysis_agent is None
    ):
        return get_default_runtime()
    return context


def _root_observability_config() -> RunnableConfig:
    settings = get_settings()
    return build_observability_config(
        {
            "metadata": {
                "environment": settings.app_environment,
                "version": __version__,
            }
        },
        langfuse_enabled=settings.langfuse_enabled,
        langfuse_public_key=settings.langfuse_public_key,
    )


def validate_request(
    state: AnalysisState,
    config: RunnableConfig,
) -> AnalysisState:
    request = AnalysisRequest.model_validate(state.get("request"))
    requested_review_policy = state.get("review_policy", "bypass")
    server_review_policy = config.get("configurable", {}).get(
        "review_policy",
        "bypass",
    )
    if requested_review_policy not in {"bypass", "required"} or (
        server_review_policy not in {"bypass", "required"}
    ):
        raise ValueError("invalid server review policy")
    review_policy = (
        "required"
        if "required" in {requested_review_policy, server_review_policy}
        else "bypass"
    )
    return {
        "request": request.model_dump(mode="json"),
        "review_policy": review_policy,
        "review_action": None,
        "review_edits": None,
        "review_comment": None,
        "review_iteration": 0,
        "lifecycle": "request_validated",
        "terminal_status": "running",
        "errors": [],
    }


def _to_domain_snapshot(snapshot: Any) -> MarketSnapshot:
    if isinstance(snapshot, MarketSnapshot):
        return snapshot
    if not isinstance(snapshot, ProviderMarketSnapshot):
        return MarketSnapshot.model_validate(snapshot)
    return MarketSnapshot.model_validate(
        {
            "symbol": snapshot.symbol,
            "fetched_at": datetime.fromtimestamp(
                snapshot.client_timestamp_ms / 1000, tz=UTC
            ),
            "source_level": snapshot.source_level,
            "ticker": {"last": snapshot.ticker.last},
            "mark_price": snapshot.mark_price,
            "index_price": snapshot.index_price,
            "funding_rate": snapshot.funding_rate,
            "open_interest": snapshot.open_interest,
            "order_book": {
                "bids": [
                    {"price": level.price, "size": level.size}
                    for level in snapshot.order_book.bids
                ],
                "asks": [
                    {"price": level.price, "size": level.size}
                    for level in snapshot.order_book.asks
                ],
            },
            "candles": [
                {
                    "timestamp": datetime.fromtimestamp(
                        candle.exchange_timestamp_ms / 1000, tz=UTC
                    ),
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
                for candle in snapshot.candles
            ],
        }
    )


def collect_market_snapshot(
    state: AnalysisState, runtime: Runtime[AnalysisRuntime]
) -> AnalysisState:
    request = AnalysisRequest.model_validate(state["request"])
    correlation_id = uuid4().hex
    try:
        snapshot = _runtime(runtime).market_provider.fetch_snapshot(
            request.symbol,
            correlation_id=correlation_id,
        )
        validated = _to_domain_snapshot(snapshot)
    except ProviderUnavailable as exc:
        return {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": "provider_unavailable",
                    "provider": exc.provider,
                    "endpoint": exc.endpoint,
                    "retryable": exc.retryable,
                    "correlation_id": exc.correlation_id,
                }
            ],
        }
    return {
        "market_snapshot": validated.model_dump(mode="json"),
        "lifecycle": "market_collected",
    }


def research_events(
    state: AnalysisState,
    runtime: Runtime[AnalysisRuntime],
    config: RunnableConfig,
) -> AnalysisState:
    request = AnalysisRequest.model_validate(state["request"])
    asset = request.symbol.partition("-")[0]
    query = f"{asset} cryptocurrency macro market news {request.horizon}"
    try:
        result = _runtime(runtime).research_collector.collect(query, config=config)
    except (
        SearchEvidenceUnavailable,
        SearchReadinessError,
        ProviderUnavailable,
        APIError,
        ValueError,
        TypeError,
    ) as exc:
        retryable = bool(getattr(exc, "retryable", False)) or isinstance(
            exc,
            (
                APIConnectionError,
                APITimeoutError,
                InternalServerError,
                RateLimitError,
            ),
        )
        error = {
            "code": "research_unavailable",
            "error_type": getattr(exc, "error_type", None) or type(exc).__name__,
            "retryable": retryable,
        }
        provider = getattr(exc, "provider", None)
        attempt = getattr(exc, "attempt", None)
        if isinstance(provider, str) and provider:
            error["provider"] = provider
        if isinstance(attempt, int) and attempt > 0:
            error["attempt"] = attempt
        return {
            "terminal_status": "failed",
            "errors": [error],
        }
    return {
        "research_bundle": result.bundle.model_dump(mode="json"),
        "web_evidence": [item.model_dump(mode="json") for item in result.evidence],
        "lifecycle": "research_collected",
    }


def analyze_market(
    state: AnalysisState,
    runtime: Runtime[AnalysisRuntime],
    config: RunnableConfig,
) -> AnalysisState:
    payload = {
        "request": state["request"],
        "market_snapshot": state["market_snapshot"],
        "research_bundle": state["research_bundle"],
        "web_evidence": state["web_evidence"],
    }
    try:
        result = _runtime(runtime).analysis_agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=True),
                    }
                ]
            },
            config=config,
        )
        analysis = result["structured_response"]
        if not isinstance(analysis, MarketAnalysis):
            raise TypeError("analysis agent did not return MarketAnalysis")
    except Exception as exc:
        return {
            "terminal_status": "failed",
            "errors": [{"code": "model_unavailable", "error_type": type(exc).__name__}],
        }
    request = AnalysisRequest.model_validate(state["request"])
    for field, expected, actual in (
        ("instrument", request.symbol, analysis.instrument),
        ("horizon", request.horizon, analysis.horizon),
    ):
        if actual != expected:
            return {
                "terminal_status": "failed",
                "errors": [
                    {
                        "code": "model_output_mismatch",
                        "field": field,
                        "expected": expected,
                        "actual": actual,
                        "retryable": False,
                    }
                ],
            }
    return {
        "analysis": analysis.model_dump(mode="json"),
        "lifecycle": "analysis_completed",
    }


def validate_evidence(state: AnalysisState) -> AnalysisState:
    verdict = check_evidence_sufficiency(
        MarketSnapshot.model_validate(state["market_snapshot"]),
        ResearchBundle.model_validate(state["research_bundle"]),
        MarketAnalysis.model_validate(state["analysis"]).main_action,
    )
    return {
        "evidence_verdict": verdict.model_dump(mode="json"),
        "lifecycle": "evidence_validated",
    }


def apply_risk(state: AnalysisState) -> AnalysisState:
    verdict = apply_risk_policy(state["analysis"], state["evidence_verdict"])
    return {
        "risk_verdict": verdict.model_dump(mode="json"),
        "terminal_status": "running" if verdict.allowed else "blocked",
        "lifecycle": "risk_validated",
    }


def build_artifact(state: AnalysisState) -> AnalysisState:
    artifact = Artifact(
        content_version=1,
        status="draft",
        analysis=MarketAnalysis.model_validate(state["analysis"]),
        evidence_verdict=state["evidence_verdict"],
        risk_verdict=state["risk_verdict"],
        source_references=[item["final_url"] for item in state["web_evidence"]],
    )
    return {
        "artifact": artifact.model_dump(mode="json"),
        "lifecycle": "artifact_built",
    }


def review_policy(state: AnalysisState) -> AnalysisState:
    return {"lifecycle": f"review_{state.get('review_policy', 'bypass')}"}


def interrupt_review(state: AnalysisState) -> AnalysisState:
    review_iteration = state.get("review_iteration", 0) + 1
    response = interrupt(
        {
            "kind": "artifact_review",
            "schema_version": "1.0",
            "allowed_actions": ["approve", "reject", "edit"],
            "review_iteration": review_iteration,
            "artifact": state["artifact"],
        }
    )
    decision = ReviewResponse.model_validate(response)
    edits = (
        decision.edits.model_dump(mode="json", exclude_unset=True)
        if decision.edits is not None
        else None
    )
    return {
        "review_action": decision.action,
        "review_edits": edits,
        "review_comment": decision.comment,
        "review_iteration": review_iteration,
        "lifecycle": f"review_{decision.action}",
    }


def apply_edits(state: AnalysisState) -> AnalysisState:
    edits = ArtifactEdit.model_validate(state.get("review_edits"))
    edited_analysis = {
        **state["analysis"],
        **edits.model_dump(mode="json", exclude_unset=True),
    }
    validated = MarketAnalysis.model_validate(edited_analysis)
    return {
        "analysis": validated.model_dump(mode="json"),
        "lifecycle": "review_edits_applied",
    }


def commit_artifact(state: AnalysisState) -> AnalysisState:
    artifact = Artifact.model_validate(
        {
            **state["artifact"],
            "status": "committed",
        }
    )
    return {
        "artifact": artifact.model_dump(mode="json"),
        "lifecycle": "artifact_committed",
    }


def complete(state: AnalysisState) -> AnalysisState:
    return {"terminal_status": "succeeded", "lifecycle": "completed"}


def complete_blocked(state: AnalysisState) -> AnalysisState:
    lifecycle = (
        "completed_rejected"
        if state.get("review_action") == "reject"
        else "completed_blocked"
    )
    return {"terminal_status": "blocked", "lifecycle": lifecycle}


def complete_failed(state: AnalysisState) -> AnalysisState:
    return {"terminal_status": "failed", "lifecycle": "completed_failed"}


def _after_external_call(state: AnalysisState) -> str:
    return "failed" if state.get("terminal_status") == "failed" else "continue"


def _after_review_policy(state: AnalysisState) -> str:
    if state.get("review_policy") == "required":
        return "required"
    if state.get("terminal_status") == "blocked":
        return "blocked"
    return "bypass"


def _after_review(state: AnalysisState) -> str:
    action = state.get("review_action")
    if action == "edit":
        return "edit"
    if action == "reject":
        return "reject"
    if action == "approve" and state.get("terminal_status") != "blocked":
        return "approve"
    return "blocked"


builder = StateGraph(AnalysisState, context_schema=AnalysisRuntime)
builder.add_node("validate_request", validate_request)
builder.add_node("collect_market_snapshot", collect_market_snapshot)
builder.add_node("research_events", research_events)
builder.add_node("analyze_market", analyze_market)
builder.add_node("validate_evidence", validate_evidence)
builder.add_node("apply_risk_policy", apply_risk)
builder.add_node("build_artifact", build_artifact)
builder.add_node("review_policy", review_policy)
builder.add_node("interrupt_review", interrupt_review)
builder.add_node("apply_edits", apply_edits)
builder.add_node("commit_artifact", commit_artifact)
builder.add_node("complete", complete)
builder.add_node("complete_blocked", complete_blocked)
builder.add_node("complete_failed", complete_failed)
builder.add_edge(START, "validate_request")
builder.add_edge("validate_request", "collect_market_snapshot")
builder.add_conditional_edges(
    "collect_market_snapshot",
    _after_external_call,
    {"failed": "complete_failed", "continue": "research_events"},
)
builder.add_conditional_edges(
    "research_events",
    _after_external_call,
    {"failed": "complete_failed", "continue": "analyze_market"},
)
builder.add_conditional_edges(
    "analyze_market",
    _after_external_call,
    {"failed": "complete_failed", "continue": "validate_evidence"},
)
builder.add_edge("validate_evidence", "apply_risk_policy")
builder.add_edge("apply_risk_policy", "build_artifact")
builder.add_edge("build_artifact", "review_policy")
builder.add_conditional_edges(
    "review_policy",
    _after_review_policy,
    {
        "bypass": "commit_artifact",
        "required": "interrupt_review",
        "blocked": "complete_blocked",
    },
)
builder.add_conditional_edges(
    "interrupt_review",
    _after_review,
    {
        "approve": "commit_artifact",
        "reject": "complete_blocked",
        "edit": "apply_edits",
        "blocked": "complete_blocked",
    },
)
builder.add_edge("apply_edits", "validate_evidence")
builder.add_edge("commit_artifact", "complete")
builder.add_edge("complete", END)
builder.add_edge("complete_blocked", END)
builder.add_edge("complete_failed", END)

def create_graph(*, checkpointer: Any = None) -> Any:
    return builder.compile(checkpointer=checkpointer).with_config(
        _root_observability_config()
    )


graph = create_graph()
