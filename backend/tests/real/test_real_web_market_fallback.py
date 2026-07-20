import os

import pytest
from langchain_openai import ChatOpenAI

from crypto_alert_v2.config import get_settings
from crypto_alert_v2.providers.web_market import WebSearchMarketCollector


pytestmark = pytest.mark.skipif(
    os.getenv("REAL_MODEL_TESTS") != "1",
    reason="set REAL_MODEL_TESTS=1 to exercise real built-in Web Search and extraction",
)


def test_real_web_search_market_fallback_returns_cited_partial_snapshot() -> None:
    settings = get_settings()
    assert settings.openai_api_key is not None
    model = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=90,
        max_retries=0,
        output_version="responses/v1",
    )

    result = WebSearchMarketCollector(model).collect(
        "BTC-USDT-SWAP",
        horizon="4h",
        config={"metadata": {"correlation_id": "real-web-market-fallback"}},
    )

    assert result.snapshot.source_level == "web_search_verified"
    assert result.snapshot.ticker is not None
    assert result.snapshot.ticker.last > 0
    assert result.snapshot.order_book is None
    assert result.snapshot.candles == []
    assert result.evidence
    assert all(item.source == "openai_builtin_web_search" for item in result.evidence)
    assert all(item.evidence_relation == "market_snapshot" for item in result.evidence)
    assert all(str(item.final_url).startswith("https://") for item in result.evidence)
