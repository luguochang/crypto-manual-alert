import os

import pytest
from langchain_openai import ChatOpenAI

from crypto_alert_v2.agents.market_analysis import create_market_analysis_agent
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.domain.models import MarketAnalysis


@pytest.mark.skipif(
    os.getenv("REAL_MODEL_TESTS") != "1",
    reason="set REAL_MODEL_TESTS=1 to exercise the configured model endpoint",
)
def test_real_agent_returns_structured_response() -> None:
    settings = get_settings()
    assert settings.openai_api_key is not None
    model = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=90,
        max_retries=0,
    )
    agent = create_market_analysis_agent(model=model)

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Analyze a hypothetical BTC-USDT-SWAP snapshot: last 60000, "
                        "mark 59990, index 59980, funding 0.0001, open interest "
                        "100000, balanced book, neutral macro evidence. This is a "
                        "schema capability proof, not live trading advice."
                    ),
                }
            ]
        }
    )

    assert isinstance(result["structured_response"], MarketAnalysis)
