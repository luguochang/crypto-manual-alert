from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from crypto_alert_v2.agents.security import secret_redaction_middleware
from crypto_alert_v2.agents.retry import (
    AGENT_RETRYABLE_ERRORS,
    MODEL_TRANSPORT_RETRY_ERRORS,
)
from crypto_alert_v2.domain.models import MarketAnalysis, Symbol
from crypto_alert_v2.providers.model import as_chat_completions_model


SYSTEM_PROMPT = """You are the deterministic analysis component of a crypto market
intelligence product. Use only the market snapshot and cited research supplied in the
request. Never claim unavailable data is present, never invent a source, and never
convert a provider failure into success. Return a cautious analysis for manual
execution only. The structured response schema is authoritative; do not emit JSON as
plain text and do not place orders or imply automatic execution. Write every
human-readable structured text field in concise Simplified Chinese, especially
root_cause_chain, why_not_opposite, and invalidation. Leave unavailable_data empty;
the product derives that field deterministically from typed provider data. Preserve
instrument symbols, numeric values, URLs, provider names, and cited source titles as
supplied when translating would reduce auditability.
When market_snapshot.source_level is web_search_verified, return main_action=no_trade,
probability no greater than 0.5, and position_size_class=none. Web Search market
context must never become an executable holding, closing, flipping, triggering, or
opening recommendation.
"""

MARKET_ANALYSIS_PROMPT_VERSION = "market-analysis-v2"
MARKET_ANALYSIS_STRUCTURED_OUTPUT_REPAIR = (
    "The response did not satisfy the MarketAnalysis schema. Correct the tool "
    "arguments using only the supplied evidence, preserve all required fields, and "
    "call the structured response tool again."
)
WEB_MARKET_PROMPT_VERSION = "web-market-extraction-v2"
WEB_MARKET_SYSTEM_PROMPT = """Extract current crypto market measurements only from
the supplied provider-cited evidence. Never use model knowledge. For every value, copy
an exact supporting quote and its exact source URL from the evidence. Return null when
the evidence does not establish a field. When at least one excerpt explicitly states a
current or as-of USD price for the requested asset, populate ticker_last from the most
explicitly current cited excerpt even if other cited prices differ. Never average or
reconcile conflicting values. ticker_last, mark_price, and index_price use the quoted
currency value. funding_rate is a decimal fraction, so 0.01% is 0.0001.
open_interest must be the quoted numeric amount after applying an explicit K/M/B unit.
Do not infer order-book levels or candles because those fields are intentionally absent.
"""


class CitedMarketValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: Decimal = Field(allow_inf_nan=False)
    source_url: HttpUrl
    quote: str = Field(min_length=1, max_length=500)


class WebMarketExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: Symbol
    ticker_last: CitedMarketValue | None = None
    mark_price: CitedMarketValue | None = None
    index_price: CitedMarketValue | None = None
    funding_rate: CitedMarketValue | None = None
    open_interest: CitedMarketValue | None = None


def create_market_analysis_agent(
    *,
    model: BaseChatModel | Any,
    additional_middleware: Sequence[AgentMiddleware] = (),
) -> Any:
    return create_agent(
        model=as_chat_completions_model(model),
        tools=[],
        middleware=[
            ModelCallLimitMiddleware(run_limit=3, exit_behavior="error"),
            *secret_redaction_middleware(),
            *additional_middleware,
        ],
        system_prompt=SYSTEM_PROMPT,
        response_format=ToolStrategy(
            MarketAnalysis,
            handle_errors=MARKET_ANALYSIS_STRUCTURED_OUTPUT_REPAIR,
        ),
    ).with_retry(
        retry_if_exception_type=MODEL_TRANSPORT_RETRY_ERRORS,
        stop_after_attempt=2,
    )


def create_web_market_extraction_agent(*, model: BaseChatModel | Any) -> Any:
    return create_agent(
        model=as_chat_completions_model(model),
        tools=[],
        middleware=list(secret_redaction_middleware()),
        system_prompt=WEB_MARKET_SYSTEM_PROMPT,
        response_format=ToolStrategy(WebMarketExtraction, handle_errors=False),
    ).with_retry(
        retry_if_exception_type=AGENT_RETRYABLE_ERRORS,
        stop_after_attempt=2,
    )
