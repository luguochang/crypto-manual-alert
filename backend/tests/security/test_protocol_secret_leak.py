from __future__ import annotations

import importlib
import json
from types import SimpleNamespace
from typing import Any

from pydantic import SecretStr

from crypto_alert_v2.api.schemas import (
    AnalysisSubmission,
    NotificationSettingsUpdate,
    NotificationSettingsView,
    TerminalGraphOutput,
)
from crypto_alert_v2.domain.models import MarketAnalysis, MarketSnapshot, ResearchBundle
from crypto_alert_v2.graph.graph import create_graph
from crypto_alert_v2.graph.request import AnalysisRequest
from crypto_alert_v2.graph.runtime import AnalysisRuntime, ResearchResult
from crypto_alert_v2.providers.search import WebEvidence
from tests.fixtures.golden_cases import (
    NOW,
    complete_market_snapshot,
    complete_research_bundle,
    valid_market_analysis,
)


graph = create_graph()


RUNTIME_CANARY = "protocol-runtime-secret-canary-20260718"
INPUT_CANARY = "protocol-input-secret-canary-20260718"
EMAIL_CANARY = "protocol-owner@example.test"


class _SecretBearingMarketProvider:
    def __init__(self) -> None:
        self.api_key = SecretStr(RUNTIME_CANARY)

    def fetch_snapshot(
        self,
        symbol: str,
        *,
        horizon: str | None = None,
        correlation_id: str,
    ) -> MarketSnapshot:
        del symbol, horizon, correlation_id
        return MarketSnapshot.model_validate(complete_market_snapshot())


class _SecretBearingResearchCollector:
    def __init__(self) -> None:
        self.authorization = f"Bearer {RUNTIME_CANARY}"
        self.queries: list[str] = []

    def collect(self, query: str, config: object = None) -> ResearchResult:
        del config
        self.queries.append(query)
        return ResearchResult(
            bundle=ResearchBundle.model_validate(complete_research_bundle()),
            evidence=(
                WebEvidence(
                    query=query,
                    final_url=(
                        "https://www.federalreserve.gov/monetarypolicy/"
                        "fomccalendars.htm"
                    ),
                    fetched_at=NOW,
                    content_hash="a" * 64,
                    title="Fed calendar checked",
                    source="test_search",
                    excerpt="No FOMC decision falls inside the analysis horizon.",
                    evidence_relation="supports",
                ),
            ),
        )


class _SecretBearingAgent:
    def __init__(self, *, fail: bool = False) -> None:
        self.cookie = f"session={RUNTIME_CANARY}"
        self.fail = fail
        self.payloads: list[dict[str, Any]] = []

    def invoke(
        self,
        payload: dict[str, Any],
        config: object = None,
    ) -> dict[str, Any]:
        del config
        self.payloads.append(payload)
        if self.fail:
            raise RuntimeError(
                f"Authorization: Bearer {RUNTIME_CANARY} must never reach protocol state"
            )
        return {
            "structured_response": MarketAnalysis.model_validate(
                valid_market_analysis()
            )
        }


def _runtime(
    *, fail_agent: bool = False
) -> tuple[AnalysisRuntime, _SecretBearingResearchCollector, _SecretBearingAgent]:
    research = _SecretBearingResearchCollector()
    agent = _SecretBearingAgent(fail=fail_agent)
    return (
        AnalysisRuntime(
            market_provider=_SecretBearingMarketProvider(),
            research_collector=research,
            analysis_agent=agent,
        ),
        research,
        agent,
    )


def _raw_request() -> dict[str, object]:
    return {
        "symbol": "BTC-USDT-SWAP",
        "horizon": "4h",
        "query_text": (
            f"Assess current BTC risk. api_key={INPUT_CANARY} owner={EMAIL_CANARY}"
        ),
        "notify": False,
    }


def _serialized(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def test_product_and_graph_inputs_redact_sensitive_query_before_serialization() -> None:
    product_input = AnalysisSubmission.model_validate(_raw_request())
    graph_input = AnalysisRequest.model_validate(_raw_request())

    for payload in (
        product_input.model_dump(mode="json"),
        graph_input.model_dump(mode="json"),
    ):
        serialized = _serialized(payload)
        assert INPUT_CANARY not in serialized
        assert EMAIL_CANARY not in serialized
        assert "[REDACTED]" in serialized


def test_runtime_secrets_do_not_enter_graph_state_stream_or_artifact_provenance(
    monkeypatch: Any,
) -> None:
    graph_module = importlib.import_module("crypto_alert_v2.graph.graph")
    monkeypatch.setattr(
        graph_module,
        "get_settings",
        lambda: SimpleNamespace(
            openai_base_url=(
                f"https://user:{RUNTIME_CANARY}@model.example.test/v1"
                f"?api_key={RUNTIME_CANARY}"
            ),
            search_provider="builtin",
            model_name="controlled-protocol-test",
        ),
    )
    runtime, research, agent = _runtime()
    sanitized = AnalysisSubmission.model_validate(_raw_request()).model_dump(
        mode="json"
    )

    events = list(
        graph.stream(
            {"request": sanitized},
            context=runtime,
            stream_mode=["updates", "values"],
        )
    )
    final_state = next(
        payload
        for mode, payload in reversed(events)
        if mode == "values" and payload.get("terminal_status") == "succeeded"
    )
    terminal = TerminalGraphOutput.model_validate(final_state)

    assert final_state["artifact"]["provenance"]["model_endpoint_host"] == (
        "model.example.test"
    )
    for value in (
        events,
        final_state,
        terminal.model_dump(mode="json"),
        research.queries,
        agent.payloads,
    ):
        serialized = _serialized(value)
        assert RUNTIME_CANARY not in serialized
        assert INPUT_CANARY not in serialized
        assert EMAIL_CANARY not in serialized


def test_runtime_exception_message_does_not_enter_terminal_protocol_errors() -> None:
    runtime, _, _ = _runtime(fail_agent=True)
    sanitized = AnalysisSubmission.model_validate(_raw_request()).model_dump(
        mode="json"
    )

    result = graph.invoke({"request": sanitized}, context=runtime)
    terminal = TerminalGraphOutput.model_validate(result)

    assert terminal.terminal_status == "failed"
    assert terminal.errors[0].code == "model_unavailable"
    serialized = _serialized(result)
    assert RUNTIME_CANARY not in serialized
    assert INPUT_CANARY not in serialized
    assert EMAIL_CANARY not in serialized


def test_notification_settings_contract_never_serializes_input_credential() -> None:
    submission = NotificationSettingsUpdate(
        enabled=True,
        device_key=SecretStr(RUNTIME_CANARY),
    )
    response = NotificationSettingsView(
        enabled=True,
        configured=True,
    )

    assert RUNTIME_CANARY not in submission.model_dump_json()
    assert RUNTIME_CANARY not in response.model_dump_json()
    assert set(response.model_dump(mode="json")) == {
        "channel",
        "enabled",
        "configured",
        "updated_at",
    }
