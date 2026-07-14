from typing import Any

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel

from crypto_alert_v2.domain.models import MarketAnalysis
from crypto_alert_v2.providers.errors import TRANSIENT_MODEL_ERRORS
from crypto_alert_v2.providers.model import as_chat_completions_model


SYSTEM_PROMPT = """You are the deterministic analysis component of a crypto market
intelligence product. Use only the market snapshot and cited research supplied in the
request. Never claim unavailable data is present, never invent a source, and never
convert a provider failure into success. Return a cautious analysis for manual
execution only. The structured response schema is authoritative; do not emit JSON as
plain text and do not place orders or imply automatic execution.
"""


def create_market_analysis_agent(*, model: BaseChatModel | Any) -> Any:
    return create_agent(
        model=as_chat_completions_model(model),
        tools=[],
        system_prompt=SYSTEM_PROMPT,
        response_format=ToolStrategy(MarketAnalysis),
    ).with_retry(
        retry_if_exception_type=TRANSIENT_MODEL_ERRORS,
        stop_after_attempt=2,
    )
