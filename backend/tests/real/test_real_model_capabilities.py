import os

import pytest
from langchain_openai import ChatOpenAI

from crypto_alert_v2.config import get_settings
from crypto_alert_v2.providers.capability_probe import probe_openai_capabilities


@pytest.mark.skipif(
    os.getenv("REAL_MODEL_TESTS") != "1",
    reason="set REAL_MODEL_TESTS=1 to exercise the configured model endpoint",
)
def test_configured_model_capability_probe_is_honest() -> None:
    settings = get_settings()
    assert settings.openai_api_key is not None

    model = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=60,
        max_retries=0,
        output_version="responses/v1",
    )

    capabilities = probe_openai_capabilities(model)

    assert capabilities.tool_calling is True
    assert capabilities.structured_output is True
    assert capabilities.streaming is True
    assert capabilities.usage_reporting is True
    assert capabilities.builtin_web_search_invoked is True
    assert capabilities.builtin_web_search_citation_count > 0
