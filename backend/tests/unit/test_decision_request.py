from decimal import Decimal

import pytest
from pydantic import ValidationError

from crypto_alert_v2.api.schemas import (
    AnalysisSubmission,
    DecisionRequestSubmission,
    DeepResearchSubmission,
)
from crypto_alert_v2.commands.dispatcher import _product_submission_from_payload
from crypto_alert_v2.domain.decision_request import (
    DecisionComplexity,
    DecisionEntryKind,
    DecisionIntent,
    DecisionRequest,
    LiveSideEffectPolicy,
    PositionContext,
    RiskContext,
    route_decision_request,
)
from crypto_alert_v2.graph.request import (
    AnalysisRequest,
    DeepResearchRequest,
    graph_request_for_decision,
)


def request(**overrides: object) -> DecisionRequest:
    payload: dict[str, object] = {
        "entry_kind": "manual",
        "actor_id": "user-1",
        "workspace_id": "workspace-1",
        "session_id": "session-1",
        "intent": "market_analysis",
        "intent_confidence": 1,
        "complexity": "standard",
        "symbol": "BTC-USDT-SWAP",
        "horizon": "4h",
        "query_text": "Assess the current BTC risk.",
        "side_effects": {
            "live_market_data": True,
            "live_web_research": True,
            "product_writes": True,
        },
    }
    payload.update(overrides)
    return DecisionRequest.model_validate(payload)


def test_decision_request_covers_every_entry_and_route_enum() -> None:
    assert {item.value for item in DecisionEntryKind} == {
        "manual",
        "scheduled",
        "postmortem",
        "eval",
        "replay",
        "system",
    }
    assert {item.value for item in DecisionIntent} == {
        "market_analysis",
        "deep_research",
        "monitor_review",
        "postmortem",
        "evaluation",
        "replay",
        "system_query",
        "unknown",
    }
    assert {item.value for item in DecisionComplexity} == {
        "simple_fast",
        "standard",
        "deep_research",
        "eval_replay",
        "blocked_clarify",
    }


def test_unknown_intent_fails_closed_with_a_typed_clarification_route() -> None:
    decision = request(
        intent="unknown",
        intent_confidence=0,
        symbol=None,
        horizon=None,
        complexity="blocked_clarify",
    )

    route = route_decision_request(decision)

    assert route.status == "blocked_clarify"
    assert route.task_type is None
    assert route.complexity is DecisionComplexity.BLOCKED_CLARIFY
    assert route.missing_slots == ("intent",)
    with pytest.raises(ValueError, match="not executable"):
        graph_request_for_decision(decision)


@pytest.mark.parametrize("entry_kind", ["postmortem", "eval", "replay", "system"])
def test_non_live_entry_kinds_reject_live_provider_side_effects(
    entry_kind: str,
) -> None:
    intent = {
        "postmortem": "postmortem",
        "eval": "evaluation",
        "replay": "replay",
        "system": "system_query",
    }[entry_kind]
    with pytest.raises(ValidationError, match="cannot use live providers"):
        request(
            entry_kind=entry_kind,
            intent=intent,
        )


def test_side_effect_contract_permanently_forbids_notifications_and_trading() -> None:
    with pytest.raises(ValidationError):
        LiveSideEffectPolicy.model_validate({"external_notifications": True})
    with pytest.raises(ValidationError):
        LiveSideEffectPolicy.model_validate({"trade_execution": True})


@pytest.mark.parametrize(
    ("position", "expected_missing"),
    [
        (
            None,
            (
                "position",
                "position.entry_price",
                "position.size",
                "position.leverage",
            ),
        ),
        (
            {"side": "long", "entry_price": "65000"},
            ("position.size", "position.leverage"),
        ),
    ],
)
def test_open_or_flip_intent_requires_position_and_risk_slots(
    position: dict[str, str] | None,
    expected_missing: tuple[str, ...],
) -> None:
    decision = request(
        requested_action="flip_long_to_short",
        position=position,
        risk={"mode": "balanced", "max_loss_quote": "250"},
    )

    route = route_decision_request(decision)

    assert route.status == "blocked_clarify"
    assert route.task_type is None
    assert route.missing_slots == expected_missing


def test_typed_position_and_risk_context_preserve_decimal_values() -> None:
    decision = request(
        requested_action="open_long",
        position=PositionContext(
            side="flat",
            entry_price=Decimal("65000.25"),
            size=Decimal("0.02"),
            leverage=Decimal("2"),
        ),
        risk=RiskContext(
            mode="conservative",
            max_loss_quote=Decimal("100"),
            max_position_notional=Decimal("1500"),
        ),
    )

    route = route_decision_request(decision)

    assert route.status == "admitted"
    assert decision.position is not None
    assert decision.position.entry_price == Decimal("65000.25")
    assert decision.risk.max_loss_quote == Decimal("100")


def test_admitted_requests_reuse_existing_graph_request_contracts() -> None:
    analysis = graph_request_for_decision(request())
    research = graph_request_for_decision(
        request(
            intent="deep_research",
            complexity="deep_research",
            horizon="7d",
            query_text="Research BTC institutional demand.",
        )
    )

    assert isinstance(analysis, AnalysisRequest)
    assert analysis.task_type == "market_analysis"
    assert analysis.notify is False
    assert isinstance(research, DeepResearchRequest)
    assert research.task_type == "deep_research"


def test_query_is_redacted_before_routing_or_serialization() -> None:
    decision = request(query_text="Assess BTC with api_key=sk-example-secret-1234")

    assert "sk-example-secret-1234" not in decision.query_text
    assert "[REDACTED]" in decision.query_text


def test_api_submission_injects_authoritative_identity() -> None:
    payload = request().model_dump(mode="json")
    payload.pop("schema_version")
    payload.pop("actor_id")
    payload.pop("workspace_id")
    submission = DecisionRequestSubmission.model_validate(payload)

    decision = submission.to_domain_request(
        actor_id="server-user",
        workspace_id="server-workspace",
    )

    assert decision.actor_id == "server-user"
    assert decision.workspace_id == "server-workspace"
    with pytest.raises(ValidationError):
        DecisionRequestSubmission.model_validate(payload | {"actor_id": "attacker"})


@pytest.mark.parametrize(
    ("task_type", "intent", "complexity", "expected_type"),
    [
        ("market_analysis", "market_analysis", "standard", AnalysisSubmission),
        ("deep_research", "deep_research", "deep_research", DeepResearchSubmission),
    ],
)
def test_dispatcher_adapts_persisted_envelope_to_legacy_graph_submission(
    task_type: str,
    intent: str,
    complexity: str,
    expected_type: type[AnalysisSubmission] | type[DeepResearchSubmission],
) -> None:
    decision = request(intent=intent, complexity=complexity)

    submission = _product_submission_from_payload(  # type: ignore[arg-type]
        task_type,
        decision.model_dump(mode="json"),
    )

    assert isinstance(submission, expected_type)
    assert submission.symbol == decision.symbol
    assert submission.horizon == decision.horizon
    assert submission.query_text == decision.query_text
