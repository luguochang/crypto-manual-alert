import os

import pytest
from langchain_openai import ChatOpenAI

from crypto_alert_v2.agents.deep_research import DeepResearchExecutor
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.graph.request import DeepResearchRequest
from crypto_alert_v2.providers.search import (
    BuiltinWebSearchProvider,
    TavilySearchProvider,
)


pytestmark = pytest.mark.skipif(
    os.getenv("REAL_DEEP_RESEARCH_TESTS") != "1",
    reason=(
        "set REAL_DEEP_RESEARCH_TESTS=1 only after the configured model endpoint "
        "and approved Search Provider pass their readiness probes"
    ),
)


@pytest.mark.asyncio
async def test_real_deep_agent_produces_a_cited_draft_report() -> None:
    settings = get_settings()
    assert settings.openai_api_key is not None
    assert settings.deep_research_harness_mode == "deepagents"

    model = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=90,
        max_retries=0,
        output_version="responses/v1",
    )
    if settings.search_provider == "builtin_web_search":
        search = BuiltinWebSearchProvider(model)
        expected_source = "openai_builtin_web_search"
    elif settings.search_provider == "tavily":
        assert settings.tavily_api_key is not None
        search = TavilySearchProvider(
            api_key=settings.tavily_api_key.get_secret_value()
        )
        expected_source = "tavily"
    else:
        pytest.fail(
            "real production Deep Research proof requires builtin_web_search or tavily"
        )

    executor = DeepResearchExecutor(
        model=model,
        search=search,
        harness_mode="deepagents",
    )

    result = await executor.execute(
        DeepResearchRequest(
            symbol="BTC-USDT-SWAP",
            horizon="7d",
            query_text=(
                "Using current public sources, assess the main macro, regulatory, "
                "and market-structure factors that could materially affect Bitcoin "
                "over the next seven days. Separate verified findings from evidence "
                "gaps and do not provide personalized trading advice."
            ),
        ),
        config={"metadata": {"correlation_id": "real-deep-research-direct"}},
    )

    assert result.artifact.status == "draft"
    assert result.artifact.harness_mode == "deepagents"
    assert result.artifact.sources
    assert len(result.artifact.sources) <= 8
    assert result.artifact.report.referenced_source_indexes()
    assert result.artifact.report.referenced_source_indexes() <= {
        source.index for source in result.artifact.sources
    }
    assert (
        tuple(source.evidence for source in result.artifact.sources) == result.evidence
    )
    assert all(
        source.evidence.source == expected_source for source in result.artifact.sources
    )
    assert all(
        str(source.evidence.final_url).startswith("https://")
        for source in result.artifact.sources
    )
    assert result.model_audits
    assert all(
        audit.prompt_version == "deep-research-v1" for audit in result.model_audits
    )
