import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlsplit

from langchain.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_alert_v2.providers.errors import TRANSIENT_MODEL_ERRORS
from crypto_alert_v2.providers.model import as_chat_completions_model
from crypto_alert_v2.providers.search import (
    BuiltinWebSearchProvider,
    DdgsMetasearchProvider,
    TavilySearchProvider,
)


class SearchProvider(StrEnum):
    BUILTIN = "builtin_web_search"
    TAVILY = "tavily"
    DDGS_METASEARCH = "ddgs_metasearch"


class CapabilityFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: str
    error_type: str


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_calling: bool
    structured_output: bool
    streaming: bool
    usage_reporting: bool
    builtin_web_search_invoked: bool
    builtin_web_search_citation_count: int = Field(ge=0)
    failures: tuple[CapabilityFailure, ...] = ()


class SearchReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ready"]
    selected_provider: SearchProvider
    probed_at: datetime
    model: str
    endpoint: str | None
    capabilities: ModelCapabilities
    tavily_configured: bool
    tavily_connected: bool
    ddgs_metasearch_connected: bool = False

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_sanitized(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("readiness endpoint metadata must be a sanitized origin")
        return value.rstrip("/")

    @model_validator(mode="after")
    def ready_selection_must_be_coherent(self) -> "SearchReadiness":
        missing = [
            name
            for name in (
                "tool_calling",
                "structured_output",
                "streaming",
                "usage_reporting",
            )
            if not getattr(self.capabilities, name)
        ]
        if missing:
            raise ValueError("ready search selection requires all model capabilities")
        if self.selected_provider is SearchProvider.BUILTIN and not (
            self.capabilities.builtin_web_search_invoked
            and self.capabilities.builtin_web_search_citation_count > 0
        ):
            raise ValueError(
                "built-in selection requires a completed search with a citation"
            )
        if self.selected_provider is SearchProvider.TAVILY and not (
            self.tavily_configured and self.tavily_connected
        ):
            raise ValueError(
                "Tavily selection requires configured and connected readiness"
            )
        if (
            self.selected_provider is SearchProvider.DDGS_METASEARCH
            and not self.ddgs_metasearch_connected
        ):
            raise ValueError("DDGS metasearch selection requires connected readiness")
        return self


class SearchReadinessError(RuntimeError):
    """Raised when the configured model/search pair is not production ready."""


class _StructuredOutputProbe(BaseModel):
    capability: str
    supported: bool


@tool
def _multiply_probe(a: int, b: int) -> int:
    """Multiply two integers for a startup capability probe."""

    return a * b


def _failure_name(exc: Exception) -> str:
    return type(exc).__name__


def _with_probe_retry(runnable: Any) -> Any:
    return runnable.with_retry(
        retry_if_exception_type=TRANSIENT_MODEL_ERRORS,
        stop_after_attempt=2,
    )


def probe_openai_capabilities(model: ChatOpenAI) -> ModelCapabilities:
    """Probe required model capabilities using official LangChain interfaces."""

    chat_model = as_chat_completions_model(model)
    failures: dict[str, str] = {}
    tool_calling = False
    usage_reporting = False
    structured_output = False
    streaming = False
    builtin_web_search_invoked = False
    citation_count = 0

    try:
        response = _with_probe_retry(
            chat_model.bind_tools([_multiply_probe], tool_choice="required")
        ).invoke("Use the multiply tool to calculate 6 times 7.")
        tool_calling = bool(
            response.tool_calls
            and response.tool_calls[0].get("name") == _multiply_probe.name
        )
        usage_reporting = response.usage_metadata is not None
    except Exception as exc:  # provider behavior is the subject of this probe
        failures["tool_calling"] = _failure_name(exc)

    try:
        result = _with_probe_retry(
            chat_model.with_structured_output(_StructuredOutputProbe)
        ).invoke("Return capability structured_output and supported true.")
        structured_output = bool(
            isinstance(result, _StructuredOutputProbe) and result.supported
        )
    except Exception as exc:  # provider behavior is the subject of this probe
        failures["structured_output"] = _failure_name(exc)

    try:
        chunks = list(chat_model.stream("Reply with the single word ready."))
        streaming = bool(chunks)
        usage_reporting = usage_reporting or any(
            chunk.usage_metadata is not None for chunk in chunks
        )
    except Exception as exc:  # provider behavior is the subject of this probe
        failures["streaming"] = _failure_name(exc)

    try:
        evidence = BuiltinWebSearchProvider(model).search(
            "Find exactly one current public Bitcoin news source. Return its title "
            "and complete public HTTPS URL."
        )
        builtin_web_search_invoked = True
        citation_count = len(evidence)
    except Exception as exc:  # provider behavior is the subject of this probe
        failures["builtin_web_search"] = _failure_name(exc)

    return ModelCapabilities(
        tool_calling=tool_calling,
        structured_output=structured_output,
        streaming=streaming,
        usage_reporting=usage_reporting,
        builtin_web_search_invoked=builtin_web_search_invoked,
        builtin_web_search_citation_count=citation_count,
        failures=tuple(
            CapabilityFailure(capability=name, error_type=error_type)
            for name, error_type in sorted(failures.items())
        ),
    )


def select_search_provider(
    capabilities: ModelCapabilities,
    *,
    tavily_configured: bool,
    tavily_connected: bool,
    requested_provider: SearchProvider | None = None,
) -> SearchProvider:
    required_capabilities = (
        "tool_calling",
        "structured_output",
        "streaming",
        "usage_reporting",
    )
    missing = [
        name for name in required_capabilities if not getattr(capabilities, name)
    ]
    if missing:
        raise SearchReadinessError(
            "Required model capabilities failed: " + ", ".join(missing)
        )

    builtin_ready = (
        capabilities.builtin_web_search_invoked
        and capabilities.builtin_web_search_citation_count > 0
    )
    if requested_provider is SearchProvider.TAVILY:
        if not tavily_configured:
            raise SearchReadinessError("Tavily is not configured")
        if not tavily_connected:
            raise SearchReadinessError("Tavily connectivity failed")
        return SearchProvider.TAVILY

    if builtin_ready:
        return SearchProvider.BUILTIN

    if requested_provider is SearchProvider.BUILTIN:
        fallback = "configured provider requires built-in web search"
    elif not tavily_configured:
        fallback = "Tavily is not configured"
    elif not tavily_connected:
        fallback = "Tavily connectivity failed"
    else:
        return SearchProvider.TAVILY

    builtin_failure = next(
        (
            failure.error_type
            for failure in capabilities.failures
            if failure.capability == "builtin_web_search"
        ),
        None,
    )
    if capabilities.builtin_web_search_invoked:
        reason = "built-in web search returned no verifiable URL citation"
    else:
        reason = "built-in web search was not invoked"
    if builtin_failure is not None:
        reason = f"{reason} ({builtin_failure})"
    raise SearchReadinessError(f"{reason}; {fallback}")


def establish_search_readiness(
    *,
    model: ChatOpenAI,
    model_name: str,
    base_url: str | None,
    tavily_api_key: str | None,
    capability_probe: Callable[[ChatOpenAI], ModelCapabilities] | None = None,
    tavily_probe: Callable[[str], bool] | None = None,
    requested_provider: SearchProvider | None = None,
    ddgs_metasearch_probe: Callable[[str | None], bool] | None = None,
    search_http_proxy: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> SearchReadiness:
    """Run one fresh startup probe and freeze a strict-environment choice."""

    capabilities = (capability_probe or probe_openai_capabilities)(model)
    tavily_configured = bool(tavily_api_key)
    tavily_connected = False
    ddgs_metasearch_connected = False

    missing_model_capabilities = [
        name
        for name in (
            "tool_calling",
            "structured_output",
            "streaming",
            "usage_reporting",
        )
        if not getattr(capabilities, name)
    ]
    if missing_model_capabilities:
        select_search_provider(
            capabilities,
            tavily_configured=tavily_configured,
            tavily_connected=False,
        )

    builtin_ready = (
        capabilities.builtin_web_search_invoked
        and capabilities.builtin_web_search_citation_count > 0
    )
    if requested_provider is SearchProvider.DDGS_METASEARCH:
        connectivity_probe = ddgs_metasearch_probe or probe_ddgs_metasearch_connectivity
        try:
            ddgs_metasearch_connected = bool(connectivity_probe(search_http_proxy))
        except Exception as exc:
            error_type = getattr(exc, "error_type", None) or type(exc).__name__
            raise SearchReadinessError(
                f"DDGS metasearch connectivity failed: {error_type}"
            ) from exc
        if not ddgs_metasearch_connected:
            raise SearchReadinessError("DDGS metasearch connectivity failed")
    elif requested_provider is SearchProvider.TAVILY:
        if not tavily_configured:
            raise SearchReadinessError("Tavily is not configured")
        connectivity_probe = tavily_probe or probe_tavily_connectivity
        try:
            tavily_connected = bool(connectivity_probe(tavily_api_key or ""))
        except Exception as exc:
            error_type = getattr(exc, "error_type", None) or type(exc).__name__
            raise SearchReadinessError(
                f"Tavily connectivity failed: {error_type}"
            ) from exc
    elif requested_provider is None and not builtin_ready and tavily_configured:
        connectivity_probe = tavily_probe or probe_tavily_connectivity
        try:
            tavily_connected = bool(connectivity_probe(tavily_api_key or ""))
        except Exception as exc:
            error_type = getattr(exc, "error_type", None) or type(exc).__name__
            raise SearchReadinessError(
                f"Tavily connectivity failed: {error_type}"
            ) from exc

    selected_provider = (
        SearchProvider.DDGS_METASEARCH
        if requested_provider is SearchProvider.DDGS_METASEARCH
        else select_search_provider(
            capabilities,
            tavily_configured=tavily_configured,
            tavily_connected=tavily_connected,
            requested_provider=requested_provider,
        )
    )
    clock = now or _utc_now
    return SearchReadiness(
        status="ready",
        selected_provider=selected_provider,
        probed_at=clock(),
        model=model_name,
        endpoint=_sanitize_endpoint(base_url),
        capabilities=capabilities,
        tavily_configured=tavily_configured,
        tavily_connected=tavily_connected,
        ddgs_metasearch_connected=ddgs_metasearch_connected,
    )


async def establish_search_readiness_async(
    *,
    model: ChatOpenAI,
    model_name: str,
    base_url: str | None,
    tavily_api_key: str | None,
    capability_probe: Callable[[ChatOpenAI], ModelCapabilities] | None = None,
    tavily_probe: Callable[[str], Awaitable[bool]] | None = None,
    requested_provider: SearchProvider | None = None,
    ddgs_metasearch_probe: Callable[[str | None], Awaitable[bool]] | None = None,
    search_http_proxy: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> SearchReadiness:
    """Run startup selection while awaiting the official async Tavily API."""

    capabilities = await asyncio.to_thread(
        capability_probe or probe_openai_capabilities,
        model,
    )
    tavily_configured = bool(tavily_api_key)
    tavily_connected = False
    ddgs_metasearch_connected = False

    missing_model_capabilities = [
        name
        for name in (
            "tool_calling",
            "structured_output",
            "streaming",
            "usage_reporting",
        )
        if not getattr(capabilities, name)
    ]
    if missing_model_capabilities:
        select_search_provider(
            capabilities,
            tavily_configured=tavily_configured,
            tavily_connected=False,
        )

    builtin_ready = (
        capabilities.builtin_web_search_invoked
        and capabilities.builtin_web_search_citation_count > 0
    )
    if requested_provider is SearchProvider.DDGS_METASEARCH:
        connectivity_probe = (
            ddgs_metasearch_probe or probe_ddgs_metasearch_connectivity_async
        )
        try:
            ddgs_metasearch_connected = bool(
                await connectivity_probe(search_http_proxy)
            )
        except Exception as exc:
            error_type = getattr(exc, "error_type", None) or type(exc).__name__
            raise SearchReadinessError(
                f"DDGS metasearch connectivity failed: {error_type}"
            ) from exc
        if not ddgs_metasearch_connected:
            raise SearchReadinessError("DDGS metasearch connectivity failed")
    elif requested_provider is SearchProvider.TAVILY:
        if not tavily_configured:
            raise SearchReadinessError("Tavily is not configured")
        connectivity_probe = tavily_probe or probe_tavily_connectivity_async
        try:
            tavily_connected = bool(await connectivity_probe(tavily_api_key or ""))
        except Exception as exc:
            error_type = getattr(exc, "error_type", None) or type(exc).__name__
            raise SearchReadinessError(
                f"Tavily connectivity failed: {error_type}"
            ) from exc
    elif requested_provider is None and not builtin_ready and tavily_configured:
        connectivity_probe = tavily_probe or probe_tavily_connectivity_async
        try:
            tavily_connected = bool(await connectivity_probe(tavily_api_key or ""))
        except Exception as exc:
            error_type = getattr(exc, "error_type", None) or type(exc).__name__
            raise SearchReadinessError(
                f"Tavily connectivity failed: {error_type}"
            ) from exc

    selected_provider = (
        SearchProvider.DDGS_METASEARCH
        if requested_provider is SearchProvider.DDGS_METASEARCH
        else select_search_provider(
            capabilities,
            tavily_configured=tavily_configured,
            tavily_connected=tavily_connected,
            requested_provider=requested_provider,
        )
    )
    clock = now or _utc_now
    return SearchReadiness(
        status="ready",
        selected_provider=selected_provider,
        probed_at=clock(),
        model=model_name,
        endpoint=_sanitize_endpoint(base_url),
        capabilities=capabilities,
        tavily_configured=tavily_configured,
        tavily_connected=tavily_connected,
        ddgs_metasearch_connected=ddgs_metasearch_connected,
    )


def probe_tavily_connectivity(api_key: str) -> bool:
    evidence = TavilySearchProvider(api_key=api_key).search(
        "Find one current public Bitcoin market news source."
    )
    return bool(evidence)


async def probe_tavily_connectivity_async(api_key: str) -> bool:
    evidence = await TavilySearchProvider(api_key=api_key).asearch(
        "Find one current public Bitcoin market news source."
    )
    return bool(evidence)


def probe_ddgs_metasearch_connectivity(proxy: str | None) -> bool:
    evidence = DdgsMetasearchProvider(proxy=proxy).search("current Bitcoin market news")
    return bool(evidence)


async def probe_ddgs_metasearch_connectivity_async(proxy: str | None) -> bool:
    return await asyncio.to_thread(probe_ddgs_metasearch_connectivity, proxy)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _sanitize_endpoint(base_url: str | None) -> str | None:
    if not base_url:
        return None
    try:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        port_number = parsed.port
    except ValueError:
        return None
    hostname = parsed.hostname
    if ":" in hostname:
        hostname = f"[{hostname}]"
    port = f":{port_number}" if port_number is not None else ""
    return f"{parsed.scheme}://{hostname}{port}"
