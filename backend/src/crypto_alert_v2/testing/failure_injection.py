from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Protocol, Sequence
from uuid import uuid4

import httpx
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from crypto_alert_v2.domain.models import (
    MarketSnapshot,
    ModelExecutionAudit,
    ResearchBundle,
)
from crypto_alert_v2.providers.errors import ProviderUnavailable, ResearchUnavailable
from crypto_alert_v2.providers.models import MarketSnapshot as ProviderMarketSnapshot
from crypto_alert_v2.providers.search import ResearchResult, WebEvidence
from crypto_alert_v2.providers.web_market import WebMarketResult


class FailureInjectionScenario(StrEnum):
    NONE = "none"
    OKX_UNAVAILABLE = "okx_unavailable"
    OKX_HTTP_500 = "okx_http_500"
    OKX_TIMEOUT = "okx_timeout"
    OKX_WEB_FALLBACK_SUCCESS = "okx_web_fallback_success"
    OKX_WEB_FALLBACK_RESEARCH_UNAVAILABLE = "okx_web_fallback_research_unavailable"
    OKX_WEB_FALLBACK_UNAVAILABLE = "okx_web_fallback_unavailable"
    SEARCH_UNAVAILABLE = "search_unavailable"
    MODEL_INVALID_OUTPUT = "model_invalid_output"
    NOTIFICATION_FAILURE = "notification_failure"
    DATABASE_ROLLBACK = "database_rollback"


class FailureInjectionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    scenario: FailureInjectionScenario = FailureInjectionScenario.NONE
    generation: str
    updated_at: datetime


class FailureScenarioUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: FailureInjectionScenario
    expected_generation: str


class FailureInjectionController:
    """Atomic, file-backed scenarios shared by local Product/Agent processes."""

    def __init__(self, path: str | Path) -> None:
        candidate = Path(path)
        if not candidate.is_absolute():
            raise ValueError("failure injection scenario file must be absolute")
        self._path = candidate

    @property
    def path(self) -> Path:
        return self._path

    def snapshot(self) -> FailureInjectionSnapshot:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return FailureInjectionSnapshot(
                generation="initial",
                updated_at=datetime.now(UTC),
            )
        try:
            return FailureInjectionSnapshot.model_validate(json.loads(raw))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("failure injection scenario state is invalid") from exc

    def set(
        self,
        scenario: FailureInjectionScenario | str,
        *,
        expected_generation: str | None = None,
    ) -> FailureInjectionSnapshot:
        current = self.snapshot()
        if (
            expected_generation is not None
            and expected_generation != current.generation
        ):
            raise FailureInjectionConflict("failure injection generation is stale")
        selected = FailureInjectionScenario(scenario)
        snapshot = FailureInjectionSnapshot(
            scenario=selected,
            generation=uuid4().hex,
            updated_at=datetime.now(UTC),
        )
        self._write(snapshot)
        return snapshot

    def reset(
        self, *, expected_generation: str | None = None
    ) -> FailureInjectionSnapshot:
        return self.set(
            FailureInjectionScenario.NONE,
            expected_generation=expected_generation,
        )

    def _write(self, snapshot: FailureInjectionSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps(snapshot.model_dump(mode="json"), sort_keys=True, indent=2)
            + "\n"
        ).encode("utf-8")
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._path.parent,
            prefix=f".{self._path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
            directory_descriptor = os.open(self._path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def failure_injection_from_settings(settings: Any) -> FailureInjectionController | None:
    if not bool(getattr(settings, "failure_injection_enabled", False)):
        return None
    environment = str(getattr(settings, "app_environment", "")).strip().lower()
    if environment not in {"development", "local", "test"}:
        raise ValueError(
            "failure injection is allowed only in non-production local profiles"
        )
    path = getattr(settings, "failure_injection_scenario_file", None)
    if not isinstance(path, str) or not path.strip():
        raise ValueError("failure injection scenario file is required")
    return FailureInjectionController(path)


_NOTIFICATION_OUTBOX_INSERT = re.compile(
    r'^\s*INSERT\s+INTO\s+(?:"app"|app)\s*\.\s*'
    r'(?:"notification_outbox"|notification_outbox)(?=\s|\(|$)',
    re.IGNORECASE,
)


def install_database_failure_injection(
    engine: AsyncEngine,
    controller: FailureInjectionController | None,
) -> Callable[[], None]:
    """Install the test-only Product worker SQL failure boundary."""

    if controller is None:
        return lambda: None

    sync_engine = engine.sync_engine

    def before_cursor_execute(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        del connection, cursor, context, executemany
        if (
            controller.snapshot().scenario is FailureInjectionScenario.DATABASE_ROLLBACK
            and _NOTIFICATION_OUTBOX_INSERT.match(statement) is not None
        ):
            raise OperationalError(
                statement,
                parameters,
                RuntimeError("injected_database_rollback"),
            )

    event.listen(sync_engine, "before_cursor_execute", before_cursor_execute)
    removed = False

    def remove() -> None:
        nonlocal removed
        if removed:
            return
        event.remove(sync_engine, "before_cursor_execute", before_cursor_execute)
        removed = True

    return remove


class MarketDelegate(Protocol):
    def fetch_snapshot(
        self, symbol: str, **kwargs: Any
    ) -> MarketSnapshot | ProviderMarketSnapshot: ...


class ResearchDelegate(Protocol):
    def collect(self, query: str, config: Any = None) -> ResearchResult: ...


class WebMarketDelegate(Protocol):
    def collect(
        self,
        symbol: str,
        *,
        horizon: str | None = None,
        config: Any = None,
    ) -> WebMarketResult: ...


class FailureInjectionConflict(RuntimeError):
    """The caller attempted to overwrite a newer scenario generation."""


class InjectingOkxTransport(httpx.BaseTransport):
    """Inject failures at the real OKX HTTP seam so provider retries still run."""

    def __init__(
        self,
        delegate: httpx.BaseTransport,
        controller: FailureInjectionController,
    ) -> None:
        self._delegate = delegate
        self._controller = controller

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        scenario = self._controller.snapshot().scenario
        if scenario is FailureInjectionScenario.OKX_TIMEOUT:
            raise httpx.ReadTimeout("injected_okx_timeout", request=request)
        if scenario in {
            FailureInjectionScenario.OKX_HTTP_500,
            FailureInjectionScenario.OKX_WEB_FALLBACK_SUCCESS,
            FailureInjectionScenario.OKX_WEB_FALLBACK_RESEARCH_UNAVAILABLE,
            FailureInjectionScenario.OKX_WEB_FALLBACK_UNAVAILABLE,
        }:
            return httpx.Response(
                500,
                request=request,
                json={"code": "500", "msg": "injected_okx_http_500", "data": []},
            )
        return self._delegate.handle_request(request)

    def close(self) -> None:
        self._delegate.close()


class InjectingMarketProvider:
    def __init__(
        self, delegate: MarketDelegate, controller: FailureInjectionController
    ):
        self._delegate = delegate
        self._controller = controller

    def fetch_snapshot(
        self, symbol: str, **kwargs: Any
    ) -> MarketSnapshot | ProviderMarketSnapshot:
        scenario = self._controller.snapshot().scenario
        if scenario is FailureInjectionScenario.OKX_UNAVAILABLE:
            correlation_id = str(kwargs.get("correlation_id") or "injected")
            raise ProviderUnavailable(
                f"injected_{scenario.value}",
                provider="okx",
                endpoint="snapshot",
                retryable=scenario is FailureInjectionScenario.OKX_TIMEOUT,
                correlation_id=correlation_id,
            )
        if scenario in {
            FailureInjectionScenario.SEARCH_UNAVAILABLE,
            FailureInjectionScenario.MODEL_INVALID_OUTPUT,
            FailureInjectionScenario.NOTIFICATION_FAILURE,
            FailureInjectionScenario.DATABASE_ROLLBACK,
        }:
            return _controlled_market_snapshot(symbol)
        return self._delegate.fetch_snapshot(symbol, **kwargs)


class InjectingResearchCollector:
    def __init__(
        self, delegate: ResearchDelegate, controller: FailureInjectionController
    ):
        self._delegate = delegate
        self._controller = controller

    def collect(self, query: str, config: Any = None) -> Any:
        scenario = self._controller.snapshot().scenario
        if scenario is FailureInjectionScenario.SEARCH_UNAVAILABLE:
            raise ResearchUnavailable(
                "injected_search_unavailable",
                provider="failure_injection",
                retryable=False,
                error_type="InjectedSearchUnavailable",
                attempt=1,
            )
        if scenario is FailureInjectionScenario.OKX_WEB_FALLBACK_RESEARCH_UNAVAILABLE:
            raise ResearchUnavailable(
                "injected_research_unavailable_after_web_market_fallback",
                provider="failure_injection",
                retryable=False,
                error_type="InjectedSearchUnavailable",
                attempt=1,
            )
        if scenario in {
            FailureInjectionScenario.MODEL_INVALID_OUTPUT,
            FailureInjectionScenario.NOTIFICATION_FAILURE,
            FailureInjectionScenario.DATABASE_ROLLBACK,
            FailureInjectionScenario.OKX_WEB_FALLBACK_SUCCESS,
        }:
            return _controlled_research_result(query, scenario=scenario)
        return self._delegate.collect(query, config=config)


class InjectingWebMarketCollector:
    """Control only the Web Search market fallback after real OKX retries."""

    def __init__(
        self,
        delegate: WebMarketDelegate,
        controller: FailureInjectionController,
    ) -> None:
        self._delegate = delegate
        self._controller = controller

    def collect(
        self,
        symbol: str,
        *,
        horizon: str | None = None,
        config: Any = None,
    ) -> WebMarketResult:
        scenario = self._controller.snapshot().scenario
        if scenario in {
            FailureInjectionScenario.OKX_WEB_FALLBACK_SUCCESS,
            FailureInjectionScenario.OKX_WEB_FALLBACK_RESEARCH_UNAVAILABLE,
        }:
            return _controlled_web_market_result(symbol)
        if scenario is FailureInjectionScenario.OKX_WEB_FALLBACK_UNAVAILABLE:
            raise ResearchUnavailable(
                "injected_web_market_fallback_unavailable",
                provider="builtin_web_search",
                retryable=False,
                error_type="InjectedWebMarketFallbackUnavailable",
                attempt=1,
            )
        return self._delegate.collect(symbol, horizon=horizon, config=config)


class _MalformedMarketAnalysisModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "failure-injection-malformed-market-analysis"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Any:
        del tool_choice, kwargs
        if "MarketAnalysis" not in {_tool_name(tool) for tool in tools}:
            raise RuntimeError("MarketAnalysis structured output tool is unavailable")
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "MarketAnalysis",
                                "args": {},
                                "id": "controlled-invalid-market-analysis",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )


class _SuccessfulMarketAnalysisModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "failure-injection-successful-market-analysis"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Any:
        del tool_choice, kwargs
        if "MarketAnalysis" not in {_tool_name(tool) for tool in tools}:
            raise RuntimeError("MarketAnalysis structured output tool is unavailable")
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        request_payload = _analysis_request_from_messages(messages)
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "MarketAnalysis",
                                "args": {
                                    "regime": "risk_off",
                                    "factor_scores": {"controlled_dependency": 0},
                                    "total_score": 0,
                                    "main_action": "no_trade",
                                    "instrument": request_payload["symbol"],
                                    "horizon": request_payload["horizon"],
                                    "reference_price": "1",
                                    "probability": 0,
                                    "position_size_class": "none",
                                    "max_leverage": 1,
                                    "risk_pct": "0",
                                    "root_cause_chain": [
                                        "Controlled dependency notification test."
                                    ],
                                    "why_not_opposite": (
                                        "No directional trade is justified in this test."
                                    ),
                                    "invalidation": "Controlled test only.",
                                    "unavailable_data": [],
                                    "manual_execution_required": True,
                                    "expires_in_seconds": 300,
                                },
                                "id": "controlled-successful-market-analysis",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )


class FailureInjectionModelMiddleware(AgentMiddleware):
    """Route one test-only scenario through LangChain's real output validator."""

    def __init__(self, controller: FailureInjectionController) -> None:
        self._controller = controller
        self._malformed_model = _MalformedMarketAnalysisModel()
        self._successful_model = _SuccessfulMarketAnalysisModel()

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Any,
    ) -> ModelResponse:
        if (
            self._controller.snapshot().scenario
            is FailureInjectionScenario.MODEL_INVALID_OUTPUT
        ):
            return handler(request.override(model=self._malformed_model))
        if self._controller.snapshot().scenario in {
            FailureInjectionScenario.NOTIFICATION_FAILURE,
            FailureInjectionScenario.DATABASE_ROLLBACK,
            FailureInjectionScenario.OKX_WEB_FALLBACK_SUCCESS,
        }:
            return handler(request.override(model=self._successful_model))
        return handler(request)


def _tool_name(tool: dict[str, Any] | type | Any | BaseTool) -> str | None:
    name = getattr(tool, "name", None)
    if isinstance(name, str):
        return name
    if not isinstance(tool, dict):
        return getattr(tool, "__name__", None)
    function = tool.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    direct_name = tool.get("name")
    return direct_name if isinstance(direct_name, str) else None


def _controlled_market_snapshot(symbol: str) -> MarketSnapshot:
    return MarketSnapshot.model_validate(
        {
            "symbol": symbol,
            "fetched_at": datetime.now(UTC),
            "source_level": "controlled_dependency",
            "ticker": {"last": "1"},
            "mark_price": "1",
            "index_price": "1",
            "funding_rate": "0",
            "open_interest": "0",
            "candles": [],
        }
    )


def _controlled_research_result(
    query: str,
    *,
    scenario: FailureInjectionScenario,
) -> ResearchResult:
    fetched_at = datetime.now(UTC)
    scenario_name = scenario.value.replace("_", "-")
    return ResearchResult(
        bundle=ResearchBundle(
            evidence_gaps=[f"controlled_dependency:{scenario.value}"]
        ),
        evidence=(
            WebEvidence(
                query=query,
                final_url=f"https://controlled-dependency.invalid/{scenario_name}",
                fetched_at=fetched_at,
                content_hash="0" * 64,
                parser_version="controlled-dependency-v1",
                title="Controlled dependency evidence",
                source="controlled_dependency_test",
                excerpt=(
                    "Synthetic evidence used only to reach the selected canonical "
                    "failure boundary."
                ),
                evidence_relation="controlled_dependency",
            ),
        ),
    )


def _controlled_web_market_result(symbol: str) -> WebMarketResult:
    fetched_at = datetime.now(UTC)
    return WebMarketResult(
        snapshot=MarketSnapshot.model_validate(
            {
                "symbol": symbol,
                "fetched_at": fetched_at,
                "source_level": "web_search_verified",
                "ticker": {"last": "65000"},
                "mark_price": None,
                "index_price": None,
                "funding_rate": None,
                "open_interest": None,
                "order_book": None,
                "candles": [],
            }
        ),
        evidence=(
            WebEvidence(
                query=f"What is the current {symbol.partition('-')[0]} price in USD?",
                final_url=(
                    f"https://controlled-dependency.invalid/web-market/{symbol.lower()}"
                ),
                fetched_at=fetched_at,
                content_hash="1" * 64,
                parser_version="controlled-web-market-v1",
                title="Controlled Web Search market fallback",
                source="controlled_dependency_test",
                excerpt=(
                    f"Controlled evidence states {symbol} is $65,000 USD for "
                    "the canonical fallback test."
                ),
                evidence_relation="market_snapshot",
            ),
        ),
        model_audit=ModelExecutionAudit(
            prompt_version="controlled-web-market-v1",
            call_count=0,
            latency_ms=0,
        ),
    )


def _analysis_request_from_messages(messages: list[BaseMessage]) -> dict[str, str]:
    for message in reversed(messages):
        if not isinstance(message.content, str):
            continue
        try:
            payload = json.loads(message.content)
        except json.JSONDecodeError:
            continue
        request = payload.get("request") if isinstance(payload, dict) else None
        if not isinstance(request, dict):
            continue
        symbol = request.get("symbol")
        horizon = request.get("horizon")
        if isinstance(symbol, str) and isinstance(horizon, str):
            return {"symbol": symbol, "horizon": horizon}
    raise ValueError("controlled analysis request is unavailable")


__all__ = [
    "FailureInjectionController",
    "FailureInjectionScenario",
    "FailureInjectionSnapshot",
    "FailureInjectionConflict",
    "FailureScenarioUpdate",
    "FailureInjectionModelMiddleware",
    "InjectingMarketProvider",
    "InjectingOkxTransport",
    "InjectingResearchCollector",
    "InjectingWebMarketCollector",
    "failure_injection_from_settings",
    "install_database_failure_injection",
]
