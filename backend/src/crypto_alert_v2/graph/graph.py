from datetime import UTC, datetime
import json
from typing import Any
from urllib.parse import urlsplit

from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain.agents.structured_output import StructuredOutputError
from langgraph.graph import END, START, StateGraph
from langgraph.stream import CheckpointsTransformer
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
from crypto_alert_v2.agents.execution_audit import (
    build_model_execution_audit,
    start_model_timer,
)
from crypto_alert_v2.agents.market_analysis import MARKET_ANALYSIS_PROMPT_VERSION
from crypto_alert_v2.api.request_identity import correlation_id_for_task
from crypto_alert_v2.domain.evidence_policy import (
    check_evidence_sufficiency,
    derive_unavailable_data,
)
from crypto_alert_v2.domain.models import (
    Artifact,
    MarketAnalysis,
    MarketSnapshot,
    ResearchBundle,
)
from crypto_alert_v2.domain.deep_research import (
    DeepResearchArtifact,
    commit_deep_research_artifact,
)
from crypto_alert_v2.domain.risk_policy import apply_risk_policy
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.graph.request import (
    AnalysisRequest,
    ArtifactEdit,
    ArtifactReviewPayload,
    DeepResearchRequest,
    DeepResearchReportEdit,
    DeepResearchReviewPayload,
    ReviewResponse,
    validate_review_response_for_payload,
)
from crypto_alert_v2.graph.events import (
    emit_artifact,
    emit_evidence,
    emit_notification,
    emit_quality,
    emit_task_progress,
    emit_usage,
)
from crypto_alert_v2.graph.monitor_ingress import run_monitor_ingress
from crypto_alert_v2.graph.runtime import AnalysisRuntime, get_default_runtime
from crypto_alert_v2.graph.state import AnalysisState
from crypto_alert_v2.observability.callbacks import (
    create_observability_config_factory,
)
from crypto_alert_v2.observability.config import runtime_config_from_settings
from crypto_alert_v2.providers.errors import ProviderUnavailable, TRANSIENT_MODEL_ERRORS
from crypto_alert_v2.providers.capability_probe import SearchReadinessError
from crypto_alert_v2.providers.models import MarketSnapshot as ProviderMarketSnapshot
from crypto_alert_v2.providers.search import SearchEvidenceUnavailable, WebEvidence
from crypto_alert_v2.monitors.models import MonitorIngressRequest


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


def _root_observability_config(config: RunnableConfig) -> RunnableConfig:
    settings = get_settings()
    factory = create_observability_config_factory(
        runtime_config_from_settings(settings, release=__version__)
    )
    return factory(config)


def validate_request(
    state: AnalysisState,
    config: RunnableConfig,
) -> AnalysisState:
    raw_request = state.get("request")
    requested_task_type = (
        raw_request.get("task_type") if isinstance(raw_request, dict) else None
    )
    if requested_task_type == "deep_research":
        task_type = "deep_research"
        request = DeepResearchRequest.model_validate(raw_request)
    elif requested_task_type == "monitor_ingress":
        task_type = "monitor_ingress"
        request = MonitorIngressRequest.model_validate(raw_request)
    elif requested_task_type in {None, "market_analysis"}:
        task_type = "market_analysis"
        request = AnalysisRequest.model_validate(raw_request)
    else:
        raise ValueError("unsupported task_type")
    if task_type == "monitor_ingress":
        return {
            "request": request.model_dump(mode="json"),
            "task_type": task_type,
            "lifecycle": "monitor_ingress_validated",
            "terminal_status": "running",
            "errors": [],
        }
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
    emit_task_progress(
        config,
        sequence=10,
        phase="request_validated",
        status="active",
    )
    emit_notification(
        config,
        sequence=11,
        requested=(request.notify if isinstance(request, AnalysisRequest) else False),
    )
    return {
        "request": request.model_dump(mode="json"),
        "task_type": task_type,
        "review_policy": review_policy,
        "review_action": None,
        "review_edits": None,
        "review_comment": None,
        "review_iteration": 0,
        "lifecycle": "request_validated",
        "terminal_status": "running",
        "errors": [],
    }


async def run_deep_research(
    state: AnalysisState,
    runtime: Runtime[AnalysisRuntime],
    config: RunnableConfig,
) -> AnalysisState:
    request = DeepResearchRequest.model_validate(state["request"])
    runtime_context = _runtime(runtime)
    executor = runtime_context.deep_research_executor
    harness_mode = runtime_context.deep_research_harness_mode
    if executor is None or harness_mode is None:
        emit_task_progress(
            config,
            sequence=20,
            phase="deep_research",
            status="failed",
        )
        return {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": "deep_research_unavailable",
                    "error_type": "MissingDeepResearchRuntime",
                    "retryable": False,
                }
            ],
        }
    emit_task_progress(
        config,
        sequence=20,
        phase="deep_research",
        status="active",
    )
    try:
        result = await executor.execute(request, config=config)
    except (
        SearchEvidenceUnavailable,
        SearchReadinessError,
        ProviderUnavailable,
        StructuredOutputError,
        ModelCallLimitExceededError,
        ToolCallLimitExceededError,
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
        emit_task_progress(
            config,
            sequence=20,
            phase="deep_research",
            status="failed",
        )
        return {
            "terminal_status": "failed",
            "errors": [_deep_research_failure_error(exc, config, retryable=retryable)],
        }

    artifact = DeepResearchArtifact.model_validate(
        {
            **result.artifact.model_dump(mode="json"),
            "status": "draft",
        }
    )
    evidence = list(result.evidence)
    audits = [audit.model_dump(mode="json") for audit in result.model_audits]
    emit_task_progress(
        config,
        sequence=30,
        phase="deep_research_draft_ready",
        status="complete",
    )
    emit_evidence(
        config,
        sequence=31,
        stage="collected",
        verified_source_count=len(evidence),
    )
    emit_usage(config, sequence=32, audits=audits)
    emit_artifact(
        config,
        sequence=33,
        status="draft",
        content_version=1,
    )
    return {
        "deep_research_artifact": artifact.model_dump(mode="json"),
        "web_evidence": [item.model_dump(mode="json") for item in evidence],
        "model_audits": audits,
        "research_harness_mode": harness_mode,
        "lifecycle": "deep_research_draft_ready",
    }


def _deep_research_failure_error(
    exc: Exception,
    config: RunnableConfig,
    *,
    retryable: bool,
) -> dict[str, Any]:
    """Keep provider root-cause coordinates without persisting exception text."""

    metadata = config.get("metadata", {})
    correlation_id = metadata.get("correlation_id")
    is_search_failure = isinstance(exc, SearchEvidenceUnavailable)
    is_readiness_failure = isinstance(exc, SearchReadinessError)
    is_budget_failure = isinstance(exc, ToolCallLimitExceededError)
    if is_search_failure:
        provider = getattr(exc, "provider", None) or "search"
    elif is_readiness_failure:
        provider = "search_readiness"
    elif is_budget_failure:
        provider = "deepagents"
    else:
        provider = "model"

    error: dict[str, Any] = {
        "code": "deep_research_unavailable",
        "error_type": getattr(exc, "error_type", None) or type(exc).__name__,
        "retryable": retryable,
        "provider": provider,
        "endpoint": (
            "verified_web_search"
            if is_search_failure
            else "startup_probe"
            if is_readiness_failure
            else "delegation_budget"
            if is_budget_failure
            else "deep_research_model"
        ),
    }
    attempt = getattr(exc, "attempt", None)
    if (
        isinstance(attempt, int)
        and not isinstance(attempt, bool)
        and 1 <= attempt <= 100
    ):
        error["attempt"] = attempt
    if isinstance(correlation_id, str) and correlation_id:
        error["correlation_id"] = correlation_id
    return error


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
    state: AnalysisState,
    runtime: Runtime[AnalysisRuntime],
    config: RunnableConfig,
) -> AnalysisState:
    request = AnalysisRequest.model_validate(state["request"])
    metadata = config.get("metadata", {})
    configured_correlation = metadata.get("correlation_id")
    correlation_id = (
        configured_correlation
        if isinstance(configured_correlation, str) and configured_correlation
        else correlation_id_for_task(metadata.get("task_id", "direct-graph"))
    )
    runtime_context = _runtime(runtime)
    try:
        snapshot = runtime_context.market_provider.fetch_snapshot(
            request.symbol,
            horizon=request.horizon,
            correlation_id=correlation_id,
        )
        validated = _to_domain_snapshot(snapshot)
    except ProviderUnavailable as exc:
        fallback = runtime_context.market_fallback_collector
        if (
            fallback is None
            or exc.provider != "okx"
            or not exc.retryable
            or not exc.retry_exhausted
        ):
            emit_task_progress(
                config,
                sequence=20,
                phase="market_collection",
                status="failed",
            )
            return _market_provider_failure(exc)
        try:
            result = fallback.collect(
                request.symbol,
                horizon=request.horizon,
                config=config,
            )
        except (
            SearchEvidenceUnavailable,
            SearchReadinessError,
            StructuredOutputError,
            APIError,
            ValueError,
            TypeError,
        ) as fallback_exc:
            retryable = bool(getattr(fallback_exc, "retryable", False)) or isinstance(
                fallback_exc,
                (
                    APIConnectionError,
                    APITimeoutError,
                    InternalServerError,
                    RateLimitError,
                ),
            )
            emit_task_progress(
                config,
                sequence=20,
                phase="market_collection",
                status="failed",
            )
            return {
                "terminal_status": "failed",
                "errors": [
                    {
                        "code": "provider_unavailable",
                        "provider": getattr(
                            fallback_exc,
                            "provider",
                            "builtin_web_search",
                        ),
                        "endpoint": "web_search_market",
                        "error_type": getattr(fallback_exc, "error_type", None)
                        or type(fallback_exc).__name__,
                        "retryable": retryable,
                        "fallback_from": exc.provider,
                        "primary_attempt": exc.attempt,
                        "correlation_id": exc.correlation_id,
                    }
                ],
            }
        validated = result.snapshot
        emit_task_progress(
            config,
            sequence=20,
            phase="market_collected",
            status="complete",
        )
        return {
            "market_snapshot": validated.model_dump(mode="json"),
            "web_evidence": [item.model_dump(mode="json") for item in result.evidence],
            "model_audits": [result.model_audit.model_dump(mode="json")],
            "lifecycle": "market_collected_with_web_search_fallback",
        }
    emit_task_progress(
        config,
        sequence=20,
        phase="market_collected",
        status="complete",
    )
    return {
        "market_snapshot": validated.model_dump(mode="json"),
        "lifecycle": "market_collected",
    }


def _market_provider_failure(exc: ProviderUnavailable) -> AnalysisState:
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


def _merge_web_evidence(
    existing: list[dict[str, Any]],
    incoming: list[WebEvidence],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in [*existing, *incoming]:
        evidence = (
            raw if isinstance(raw, WebEvidence) else WebEvidence.model_validate(raw)
        )
        key = (str(evidence.final_url), evidence.content_hash)
        if key in seen:
            continue
        seen.add(key)
        merged.append(evidence.model_dump(mode="json"))
    return merged


def _effective_web_evidence(
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return evidence allowed to influence analysis while retaining the audit set.

    The research collector keeps excluded provider results in the state so the
    Product projection can explain the relevance decision.  They must not be
    counted as verified evidence, sent to the market-analysis agent, or cited by
    the committed artifact.
    """

    return [
        item
        for item in evidence
        if str(item.get("evidence_relation", "")).strip().casefold() != "excluded"
    ]


def research_events(
    state: AnalysisState,
    runtime: Runtime[AnalysisRuntime],
    config: RunnableConfig,
) -> AnalysisState:
    request = AnalysisRequest.model_validate(state["request"])
    asset = request.symbol.partition("-")[0]
    query = (
        f"{request.query_text.strip()}\n"
        f"Asset: {asset}\n"
        f"Market: cryptocurrency\n"
        f"Analysis horizon: {request.horizon}"
    )
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
            "endpoint": "research_events",
            "error_type": getattr(exc, "error_type", None) or type(exc).__name__,
            "retryable": retryable,
        }
        provider = getattr(exc, "provider", None)
        attempt = getattr(exc, "attempt", None)
        if isinstance(provider, str) and provider:
            error["provider"] = provider
        if isinstance(attempt, int) and attempt > 0:
            error["attempt"] = attempt
        emit_task_progress(
            config,
            sequence=30,
            phase="research_collection",
            status="failed",
        )
        return {
            "terminal_status": "failed",
            "errors": [error],
        }
    merged_evidence = _merge_web_evidence(
        state.get("web_evidence", []),
        list(result.evidence),
    )
    emit_task_progress(
        config,
        sequence=30,
        phase="research_collected",
        status="complete",
    )
    emit_evidence(
        config,
        sequence=31,
        stage="collected",
        verified_source_count=len(_effective_web_evidence(merged_evidence)),
    )
    return {
        "research_bundle": result.bundle.model_dump(mode="json"),
        "web_evidence": merged_evidence,
        "model_audits": [
            *state.get("model_audits", []),
            *(
                [result.model_audit.model_dump(mode="json")]
                if result.model_audit is not None
                else []
            ),
        ],
        "lifecycle": "research_collected",
    }


def analyze_market(
    state: AnalysisState,
    runtime: Runtime[AnalysisRuntime],
    config: RunnableConfig,
) -> AnalysisState:
    effective_evidence = _effective_web_evidence(state.get("web_evidence", []))
    payload = {
        "request": state["request"],
        "market_snapshot": state["market_snapshot"],
        "research_bundle": state["research_bundle"],
        "web_evidence": effective_evidence,
    }
    try:
        started_at = start_model_timer()
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
        model_audit = build_model_execution_audit(
            result,
            prompt_version=MARKET_ANALYSIS_PROMPT_VERSION,
            started_at=started_at,
        )
        analysis = result["structured_response"]
        if not isinstance(analysis, MarketAnalysis):
            raise TypeError("analysis agent did not return MarketAnalysis")
    except (StructuredOutputError, ModelCallLimitExceededError) as exc:
        emit_task_progress(
            config,
            sequence=40,
            phase="analysis",
            status="failed",
        )
        return {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": "model_invalid_output",
                    "error_type": type(exc).__name__,
                    "retryable": False,
                }
            ],
        }
    except TRANSIENT_MODEL_ERRORS as exc:
        emit_task_progress(
            config,
            sequence=40,
            phase="analysis",
            status="failed",
        )
        return {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": "model_unavailable",
                    "error_type": type(exc).__name__,
                    "retryable": True,
                }
            ],
        }
    except Exception as exc:
        emit_task_progress(
            config,
            sequence=40,
            phase="analysis",
            status="failed",
        )
        return {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": "model_unavailable",
                    "error_type": type(exc).__name__,
                    "retryable": False,
                }
            ],
        }
    request = AnalysisRequest.model_validate(state["request"])
    for field, expected, actual in (
        ("instrument", request.symbol, analysis.instrument),
        ("horizon", request.horizon, analysis.horizon),
    ):
        if actual != expected:
            emit_task_progress(
                config,
                sequence=40,
                phase="analysis",
                status="failed",
            )
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
    analysis = analysis.model_copy(
        update={
            "unavailable_data": derive_unavailable_data(
                state["market_snapshot"],
                state["research_bundle"],
                verified_web_evidence_count=len(effective_evidence),
            )
        }
    )
    model_audits = [
        *state.get("model_audits", []),
        model_audit.model_dump(mode="json"),
    ]
    emit_task_progress(
        config,
        sequence=40,
        phase="analysis_completed",
        status="complete",
    )
    emit_usage(
        config,
        sequence=41,
        audits=model_audits,
    )
    return {
        "model_audits": model_audits,
        "analysis": analysis.model_dump(mode="json"),
        "lifecycle": "analysis_completed",
    }


def validate_evidence(
    state: AnalysisState,
    config: RunnableConfig,
) -> AnalysisState:
    verdict = check_evidence_sufficiency(
        MarketSnapshot.model_validate(state["market_snapshot"]),
        ResearchBundle.model_validate(state["research_bundle"]),
        MarketAnalysis.model_validate(state["analysis"]).main_action,
    )
    sequence_offset = state.get("review_iteration", 0) * 100
    emit_task_progress(
        config,
        sequence=50 + sequence_offset,
        phase="evidence_validated",
        status="complete" if verdict.sufficient else "blocked",
    )
    emit_evidence(
        config,
        sequence=51 + sequence_offset,
        stage="validated",
        verified_source_count=len(
            _effective_web_evidence(state.get("web_evidence", []))
        ),
        sufficient=verdict.sufficient,
    )
    return {
        "evidence_verdict": verdict.model_dump(mode="json"),
        "lifecycle": "evidence_validated",
    }


def apply_risk(
    state: AnalysisState,
    config: RunnableConfig,
) -> AnalysisState:
    verdict = apply_risk_policy(state["analysis"], state["evidence_verdict"])
    sequence_offset = state.get("review_iteration", 0) * 100
    evidence = state["evidence_verdict"]
    emit_task_progress(
        config,
        sequence=60 + sequence_offset,
        phase="risk_validated",
        status="complete" if verdict.allowed else "blocked",
    )
    emit_quality(
        config,
        sequence=61 + sequence_offset,
        evidence_sufficient=bool(evidence.get("sufficient")),
        risk_allowed=verdict.allowed,
        warning_count=len(verdict.warnings),
        blocked_reason_count=len(verdict.blocked_reasons),
    )
    return {
        "risk_verdict": verdict.model_dump(mode="json"),
        "terminal_status": "running" if verdict.allowed else "blocked",
        "lifecycle": "risk_validated",
    }


def build_artifact(
    state: AnalysisState,
    config: RunnableConfig,
) -> AnalysisState:
    settings = get_settings()
    market_source_level = state["market_snapshot"].get("source_level")
    controlled_dependency = market_source_level == "controlled_dependency"
    effective_evidence = _effective_web_evidence(state["web_evidence"])
    evidence_sources = {
        str(item.get("source"))
        for item in effective_evidence
        if isinstance(item.get("source"), str) and item["source"]
    }
    parser_versions = {
        str(item.get("parser_version"))
        for item in effective_evidence
        if isinstance(item.get("parser_version"), str) and item["parser_version"]
    }
    endpoint_host = (
        urlsplit(settings.openai_base_url).hostname
        if settings.openai_base_url
        else None
    )
    artifact = Artifact(
        content_version=1,
        status="draft",
        analysis=MarketAnalysis.model_validate(state["analysis"]),
        evidence_verdict=state["evidence_verdict"],
        risk_verdict=state["risk_verdict"],
        source_references=[item["final_url"] for item in effective_evidence],
        provenance={
            "market_provider": (
                "controlled_dependency"
                if controlled_dependency
                else (
                    "web_search_market"
                    if market_source_level == "web_search_verified"
                    else "okx"
                )
            ),
            "search_provider": ", ".join(sorted(evidence_sources))
            or settings.search_provider,
            "search_parser_version": ", ".join(sorted(parser_versions))
            or "unavailable",
            "model_provider": (
                "controlled_dependency"
                if controlled_dependency
                else ("openai-compatible" if settings.openai_base_url else "openai")
            ),
            "model_name": (
                "controlled-dependency-test"
                if controlled_dependency
                else settings.model_name
            ),
            "model_endpoint_host": (None if controlled_dependency else endpoint_host),
            "model_audits": state.get("model_audits", []),
        },
    )
    sequence_offset = state.get("review_iteration", 0) * 100
    emit_task_progress(
        config,
        sequence=70 + sequence_offset,
        phase="artifact_built",
        status="complete",
    )
    emit_artifact(
        config,
        sequence=71 + sequence_offset,
        status="draft",
        content_version=artifact.content_version,
    )
    return {
        "artifact": artifact.model_dump(mode="json"),
        "lifecycle": "artifact_built",
    }


def review_policy(
    state: AnalysisState,
    config: RunnableConfig,
) -> AnalysisState:
    sequence_offset = state.get("review_iteration", 0) * 100
    emit_task_progress(
        config,
        sequence=80 + sequence_offset,
        phase=f"review_{state.get('review_policy', 'bypass')}",
        status="active" if state.get("review_policy") == "required" else "complete",
    )
    return {"lifecycle": f"review_{state.get('review_policy', 'bypass')}"}


def interrupt_review(
    state: AnalysisState,
    config: RunnableConfig,
) -> AnalysisState:
    review_iteration = state.get("review_iteration", 0) + 1
    if state.get("task_type") == "deep_research":
        request = DeepResearchRequest.model_validate(state["request"])
        payload = DeepResearchReviewPayload(
            symbol=request.symbol,
            horizon=request.horizon,
            review_iteration=review_iteration,
            artifact=state["deep_research_artifact"],
        )
    else:
        payload = ArtifactReviewPayload(
            review_iteration=review_iteration,
            artifact=state["artifact"],
        )
    response = interrupt(payload.model_dump(mode="json"))
    decision = validate_review_response_for_payload(
        payload,
        ReviewResponse.model_validate(response),
    )
    edits = (
        decision.edits.model_dump(mode="json", exclude_unset=True)
        if decision.edits is not None
        else None
    )
    emit_task_progress(
        config,
        sequence=81 + state.get("review_iteration", 0) * 100,
        phase=f"review_{decision.action}",
        status="blocked" if decision.action == "reject" else "complete",
    )
    return {
        "review_action": decision.action,
        "review_edits": edits,
        "review_comment": decision.comment,
        "review_iteration": review_iteration,
        "lifecycle": f"review_{decision.action}",
    }


def apply_edits(
    state: AnalysisState,
    config: RunnableConfig,
) -> AnalysisState:
    if state.get("task_type") == "deep_research":
        edits = DeepResearchReportEdit.model_validate(state.get("review_edits"))
        artifact = DeepResearchArtifact.model_validate(
            {
                **state["deep_research_artifact"],
                "status": "draft",
                "report": edits.report.model_dump(mode="json"),
            }
        )
        review_iteration = state.get("review_iteration", 1)
        emit_task_progress(
            config,
            sequence=82 + max(review_iteration - 1, 0) * 100,
            phase="review_edits_applied",
            status="complete",
        )
        return {
            "deep_research_artifact": artifact.model_dump(mode="json"),
            "lifecycle": "review_edits_applied",
        }
    edits = ArtifactEdit.model_validate(state.get("review_edits"))
    edited_analysis = {
        **state["analysis"],
        **edits.model_dump(mode="json", exclude_unset=True),
    }
    validated = MarketAnalysis.model_validate(edited_analysis)
    review_iteration = state.get("review_iteration", 1)
    emit_task_progress(
        config,
        sequence=82 + max(review_iteration - 1, 0) * 100,
        phase="review_edits_applied",
        status="complete",
    )
    return {
        "analysis": validated.model_dump(mode="json"),
        "lifecycle": "review_edits_applied",
    }


def commit_artifact(
    state: AnalysisState,
    config: RunnableConfig,
) -> AnalysisState:
    if state.get("task_type") == "deep_research":
        artifact = commit_deep_research_artifact(
            DeepResearchArtifact.model_validate(state["deep_research_artifact"])
        )
        sequence_offset = state.get("review_iteration", 0) * 100
        emit_task_progress(
            config,
            sequence=90 + sequence_offset,
            phase="artifact_committed",
            status="complete",
        )
        emit_artifact(
            config,
            sequence=91 + sequence_offset,
            status="committed",
            content_version=1,
        )
        return {
            "deep_research_artifact": artifact.model_dump(mode="json"),
            "lifecycle": "artifact_committed",
        }
    artifact = Artifact.model_validate(
        {
            **state["artifact"],
            "status": "committed",
        }
    )
    sequence_offset = state.get("review_iteration", 0) * 100
    emit_task_progress(
        config,
        sequence=90 + sequence_offset,
        phase="artifact_committed",
        status="complete",
    )
    emit_artifact(
        config,
        sequence=91 + sequence_offset,
        status="committed",
        content_version=artifact.content_version,
    )
    return {
        "artifact": artifact.model_dump(mode="json"),
        "lifecycle": "artifact_committed",
    }


def complete(
    state: AnalysisState,
    config: RunnableConfig,
) -> AnalysisState:
    emit_task_progress(
        config,
        sequence=100 + state.get("review_iteration", 0) * 100,
        phase="completed",
        status="complete",
    )
    return {"terminal_status": "succeeded", "lifecycle": "completed"}


def complete_blocked(
    state: AnalysisState,
    config: RunnableConfig,
) -> AnalysisState:
    lifecycle = (
        "completed_rejected"
        if state.get("review_action") == "reject"
        else "completed_blocked"
    )
    emit_task_progress(
        config,
        sequence=100 + state.get("review_iteration", 0) * 100,
        phase=lifecycle,
        status="blocked",
    )
    result: AnalysisState = {
        "terminal_status": "blocked",
        "lifecycle": lifecycle,
    }
    if (
        state.get("task_type") == "deep_research"
        and state.get("deep_research_artifact") is not None
    ):
        artifact = DeepResearchArtifact.model_validate(
            {
                **state["deep_research_artifact"],
                "status": "draft",
            }
        )
        result["deep_research_artifact"] = artifact.model_dump(mode="json")
        return result
    if state.get("review_action") == "reject" and state.get("artifact") is not None:
        artifact_payload = state["artifact"]
        risk_payload = artifact_payload["risk_verdict"]
        rejection_reason = "Rejected during required human review."
        blocked_reasons = list(risk_payload.get("blocked_reasons", []))
        if rejection_reason not in blocked_reasons:
            blocked_reasons.append(rejection_reason)
        artifact = Artifact.model_validate(
            {
                **artifact_payload,
                "status": "draft",
                "risk_verdict": {
                    **risk_payload,
                    "allowed": False,
                    "blocked_reasons": blocked_reasons,
                    "confidence_cap": 0,
                },
            }
        )
        result["artifact"] = artifact.model_dump(mode="json")
    return result


def complete_failed(
    state: AnalysisState,
    config: RunnableConfig,
) -> AnalysisState:
    emit_task_progress(
        config,
        sequence=100 + state.get("review_iteration", 0) * 100,
        phase="completed_failed",
        status="failed",
    )
    return {"terminal_status": "failed", "lifecycle": "completed_failed"}


def _after_external_call(state: AnalysisState) -> str:
    return "failed" if state.get("terminal_status") == "failed" else "continue"


def _after_request_validation(state: AnalysisState) -> str:
    if state.get("terminal_status") == "failed":
        return "failed"
    if state.get("task_type") == "deep_research":
        return "deep_research"
    if state.get("task_type") == "monitor_ingress":
        return "monitor_ingress"
    return "market_analysis"


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


def _after_edits(state: AnalysisState) -> str:
    return (
        "deep_research"
        if state.get("task_type") == "deep_research"
        else "market_analysis"
    )


builder = StateGraph(AnalysisState, context_schema=AnalysisRuntime)
builder.add_node("validate_request", validate_request)
builder.add_node("run_deep_research", run_deep_research)
builder.add_node("monitor_ingress", run_monitor_ingress)
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
builder.add_conditional_edges(
    "validate_request",
    _after_request_validation,
    {
        "market_analysis": "collect_market_snapshot",
        "deep_research": "run_deep_research",
        "monitor_ingress": "monitor_ingress",
        "failed": "complete_failed",
    },
)
builder.add_edge("monitor_ingress", END)
builder.add_conditional_edges(
    "run_deep_research",
    _after_external_call,
    {"failed": "complete_failed", "continue": "review_policy"},
)
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
builder.add_conditional_edges(
    "apply_edits",
    _after_edits,
    {
        "market_analysis": "validate_evidence",
        "deep_research": "review_policy",
    },
)
builder.add_edge("commit_artifact", "complete")
builder.add_edge("complete", END)
builder.add_edge("complete_blocked", END)
builder.add_edge("complete_failed", END)


def create_graph(
    *,
    checkpointer: Any = None,
    config: RunnableConfig | None = None,
) -> Any:
    compiled = builder.compile(
        checkpointer=checkpointer,
        transformers=[CheckpointsTransformer],
    )
    if config is None:
        return compiled

    # Agent Server places its private ServerRuntime in both this request config and
    # the ambient RunnableConfig. The observability factory may inspect that config
    # for trace identity and normalize its request-owned metadata/tags in place, but
    # no config merge is safe here: RunnableConfig merging also inherits the ambient
    # ServerRuntime. Bind only fields newly created by the observability factory.
    observability_addition = _root_observability_config(config)
    root_observability: RunnableConfig = {
        key: observability_addition[key]
        for key in ("callbacks", "metadata", "tags")
        if key in observability_addition
    }
    return compiled.copy(update={"config": root_observability})


def graph_factory(config: RunnableConfig) -> Any:
    """Build a native Pregel graph for each official Agent Server Run."""
    return create_graph(config=config)
