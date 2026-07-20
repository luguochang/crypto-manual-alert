from decimal import Decimal
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parents[1]))

from crypto_alert_v2.domain.models import (
    Artifact,
    EvidenceVerdict,
    MarketAnalysis,
    MarketSnapshot,
    ResearchBundle,
    RiskBudget,
    RiskVerdict,
)
from tests.fixtures.golden_cases import (
    SUPPORTED_SYMBOLS,
    complete_market_snapshot,
    complete_research_bundle,
    valid_market_analysis,
)


@pytest.mark.parametrize("symbol", SUPPORTED_SYMBOLS)
def test_market_snapshot_supports_each_v2_perpetual(symbol: str) -> None:
    snapshot = MarketSnapshot.model_validate(complete_market_snapshot(symbol))

    assert snapshot.symbol == symbol
    assert snapshot.ticker is not None
    assert snapshot.ticker.last == Decimal("65000.25")
    assert snapshot.mark_price == Decimal("65001.00")
    assert snapshot.order_book is not None
    assert snapshot.order_book.bids[0].price == Decimal("65000.00")
    assert snapshot.candles[0].close == Decimal("65000.25")


def test_market_snapshot_accepts_provider_abbreviations() -> None:
    payload = complete_market_snapshot()
    payload["ticker"]["vol_24h"] = payload["ticker"].pop("volume_24h")
    payload["candles"][0] = {
        "ts": payload["candles"][0]["timestamp"],
        "o": "64900",
        "h": "65100",
        "l": "64850",
        "c": "65000.25",
        "vol": "100.5",
    }

    snapshot = MarketSnapshot.model_validate(payload)

    assert snapshot.ticker is not None
    assert snapshot.ticker.volume_24h == Decimal("1250.5")
    assert snapshot.candles[0].open == Decimal("64900")


def test_market_snapshot_accepts_partial_verified_web_search_fallback() -> None:
    snapshot = MarketSnapshot.model_validate(
        {
            "symbol": "BTC-USDT-SWAP",
            "fetched_at": "2026-07-17T08:00:00Z",
            "source_level": "web_search_verified",
            "ticker": {"last": "65000.25"},
            "mark_price": None,
            "index_price": None,
            "funding_rate": None,
            "open_interest": None,
            "order_book": None,
            "candles": [],
        }
    )

    assert snapshot.source_level == "web_search_verified"
    assert snapshot.ticker is not None
    assert snapshot.order_book is None
    assert snapshot.candles == []


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("symbol",), "DOGE-USDT-SWAP"),
        (("mark_price",), 0),
        (("ticker", "last"), -1),
        (("candles", 0, "high"), "64800"),
    ],
)
def test_market_snapshot_rejects_invalid_provider_values(
    path: tuple, value: object
) -> None:
    payload = complete_market_snapshot()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        MarketSnapshot.model_validate(payload)


def test_research_bundle_preserves_completed_empty_event_scan() -> None:
    bundle = ResearchBundle.model_validate(complete_research_bundle())

    assert bundle.vix == Decimal("15.25")
    assert bundle.real_yield_10y == Decimal("1.82")
    assert bundle.dxy == Decimal("98.40")
    assert bundle.macro_event_scan == []
    assert bundle.findings[0].source_url.startswith("https://")


def test_research_bundle_rejects_non_numeric_macro_metric() -> None:
    payload = complete_research_bundle()
    payload["vix"] = "unknown"

    with pytest.raises(ValidationError):
        ResearchBundle.model_validate(payload)


def test_market_analysis_is_validated_structured_output() -> None:
    analysis = MarketAnalysis.model_validate(valid_market_analysis())

    assert analysis.instrument == "BTC-USDT-SWAP"
    assert analysis.reference_price == Decimal("65000.25")
    assert analysis.factor_scores["market_structure"] == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("main_action", "buy_now"),
        ("probability", 1.01),
        ("max_leverage", 0),
        ("risk_pct", -0.01),
        ("expires_in_seconds", 0),
        ("factor_scores", {"macro": 3}),
    ],
)
def test_market_analysis_rejects_illegal_input(field: str, value: object) -> None:
    payload = valid_market_analysis(**{field: value})

    with pytest.raises(ValidationError):
        MarketAnalysis.model_validate(payload)


def test_evidence_verdict_rejects_inconsistent_state() -> None:
    with pytest.raises(ValidationError):
        EvidenceVerdict(
            sufficient=False,
            confidence_cap=0,
            missing_required=[],
        )


def test_risk_verdict_rejects_block_without_reason() -> None:
    with pytest.raises(ValidationError):
        RiskVerdict(allowed=False, blocked_reasons=[], confidence_cap=0)


def test_risk_budget_rejects_impossible_limits() -> None:
    with pytest.raises(ValidationError):
        RiskBudget(max_leverage=0, max_risk_pct=0.10)

    with pytest.raises(ValidationError):
        RiskBudget(max_leverage=2, max_risk_pct=1.1)


def test_artifact_round_trips_typed_domain_results() -> None:
    analysis = MarketAnalysis.model_validate(valid_market_analysis())
    evidence = EvidenceVerdict(sufficient=True, confidence_cap=1)
    risk = RiskVerdict(allowed=True, confidence_cap=1)

    artifact = Artifact(
        status="committed",
        content_version=1,
        analysis=analysis,
        evidence_verdict=evidence,
        risk_verdict=risk,
        source_references=["market:btc:2026-07-13T04:00:00Z"],
    )
    restored = Artifact.model_validate_json(artifact.model_dump_json())

    assert restored.artifact_type == "analysis_report"
    assert restored.analysis.instrument == "BTC-USDT-SWAP"
    assert restored.risk_verdict.allowed is True


def test_models_forbid_unknown_fields() -> None:
    payload = complete_market_snapshot()
    payload["provider_error"] = "timeout"

    with pytest.raises(ValidationError):
        MarketSnapshot.model_validate(payload)
