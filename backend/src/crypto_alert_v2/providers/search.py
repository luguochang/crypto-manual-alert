import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
import ipaddress
from typing import Any, Protocol
from urllib.parse import urlsplit

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from pydantic import BaseModel, ConfigDict, HttpUrl, ValidationError

from crypto_alert_v2.domain.models import ResearchBundle
from crypto_alert_v2.providers.errors import (
    ResearchUnavailable,
    TRANSIENT_MODEL_ERRORS,
)
from crypto_alert_v2.providers.retry_policy import SearchRetryPolicy


SearchEvidenceUnavailable = ResearchUnavailable

_RESERVED_EVIDENCE_HOSTS = frozenset(
    {
        "localhost",
        "local",
        "test",
        "invalid",
        "internal",
        "example",
        "example.com",
        "example.net",
        "example.org",
    }
)


class WebEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str
    final_url: HttpUrl
    redirect_chain: tuple[HttpUrl, ...] = ()
    http_status: int | None = None
    fetched_at: datetime
    published_at: datetime | None = None
    content_hash: str
    parser_version: str = "openai-responses-citation-v1"
    title: str
    author: str | None = None
    source: str
    excerpt: str
    evidence_relation: str


@dataclass(frozen=True, slots=True)
class ResearchResult:
    bundle: ResearchBundle
    evidence: tuple[WebEvidence, ...]


class BuiltinWebSearchProvider:
    def __init__(
        self,
        model: ChatOpenAI,
        *,
        retry_policy: SearchRetryPolicy | None = None,
    ) -> None:
        self._model = model
        self._retry_policy = retry_policy or SearchRetryPolicy()

    def search(
        self, query: str, config: RunnableConfig | None = None
    ) -> list[WebEvidence]:
        prompt = (
            "You must use web search. Cite only provider-returned URL citation "
            "annotations. Use no more than four sources and stop once those sources "
            "are found.\n\n"
            f"{query}"
        )
        search_tool_type = "web_search"

        def invoke(remaining_seconds: float, _: int) -> list[WebEvidence]:
            nonlocal search_tool_type
            try:
                bound_search = self._model.bind_tools(
                    [{"type": search_tool_type}]
                )
                response = bound_search.invoke(
                    prompt,
                    config=config,
                    timeout=remaining_seconds,
                )
            except Exception as exc:
                raise _normalize_search_error(
                    exc,
                    provider="builtin_web_search",
                    label="built-in web search",
                ) from exc
            try:
                return parse_builtin_search_response(
                    query=query,
                    response=response,
                    fetched_at=datetime.now(UTC),
                )
            except ResearchUnavailable as exc:
                if exc.error_type in {
                    "UnverifiedServerToolCall",
                    "MissingProviderCitation",
                }:
                    search_tool_type = "web_search_preview"
                raise ResearchUnavailable(
                    str(exc),
                    provider="builtin_web_search",
                    retryable=True,
                    error_type=exc.error_type or type(exc).__name__,
                ) from exc

        return self._retry_policy.execute(
            invoke,
            provider="builtin_web_search",
            correlation_id=_search_correlation_id(config),
        )


class SearchTool(Protocol):
    def invoke(
        self, input: dict[str, str], config: RunnableConfig | None = None
    ) -> Any: ...


class TavilySearchProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        tool: SearchTool | None = None,
        retry_policy: SearchRetryPolicy | None = None,
    ) -> None:
        if tool is None:
            if not api_key:
                raise ResearchUnavailable(
                    "Tavily API key is required",
                    provider="tavily",
                    retryable=False,
                    error_type="MissingConfiguration",
                )
            tool = TavilySearch(
                tavily_api_key=api_key,
                max_results=8,
                topic="finance",
                search_depth="advanced",
                include_raw_content=False,
                handle_tool_error=False,
            )
        self._tool = tool
        self._retry_policy = retry_policy or SearchRetryPolicy()

    def search(
        self, query: str, config: RunnableConfig | None = None
    ) -> list[WebEvidence]:
        def invoke(remaining_seconds: float, _: int) -> list[WebEvidence]:
            try:
                response = _invoke_tavily_tool(
                    self._tool,
                    {"query": query},
                    config=config,
                    timeout=remaining_seconds,
                )
            except Exception as exc:
                raise _normalize_search_error(
                    exc,
                    provider="tavily",
                    label="Tavily search",
                ) from exc
            return parse_tavily_response(
                query=query,
                response=response,
                fetched_at=datetime.now(UTC),
            )

        return self._retry_policy.execute(
            invoke,
            provider="tavily",
            correlation_id=_search_correlation_id(config),
        )

    async def asearch(
        self, query: str, config: RunnableConfig | None = None
    ) -> list[WebEvidence]:
        async def invoke(
            remaining_seconds: float,
            _: int,
        ) -> list[WebEvidence]:
            try:
                response = await _ainvoke_tavily_tool(
                    self._tool,
                    {"query": query},
                    config=config,
                    timeout=remaining_seconds,
                )
            except Exception as exc:
                raise _normalize_search_error(
                    exc,
                    provider="tavily",
                    label="Tavily search",
                ) from exc
            return parse_tavily_response(
                query=query,
                response=response,
                fetched_at=datetime.now(UTC),
            )

        return await self._retry_policy.execute_async(
            invoke,
            provider="tavily",
            correlation_id=_search_correlation_id(config),
        )


class DuckDuckGoSearchProvider:
    """No-key search through a maintained client behind a LangChain tool."""

    def __init__(
        self,
        *,
        proxy: str | None = None,
        tool: SearchTool | None = None,
        retry_policy: SearchRetryPolicy | None = None,
    ) -> None:
        self._proxy = proxy
        self._tool = tool
        self._retry_policy = retry_policy or SearchRetryPolicy()

    def search(
        self, query: str, config: RunnableConfig | None = None
    ) -> list[WebEvidence]:
        def invoke(remaining_seconds: float, _: int) -> list[WebEvidence]:
            tool = self._tool or _create_duckduckgo_tool(
                proxy=self._proxy,
                timeout=remaining_seconds,
            )
            try:
                response = tool.invoke({"query": query}, config=config)
            except Exception as exc:
                raise _normalize_search_error(
                    exc,
                    provider="duckduckgo",
                    label="DuckDuckGo search",
                ) from exc
            return parse_duckduckgo_response(
                query=query,
                response=response,
                fetched_at=datetime.now(UTC),
            )

        return self._retry_policy.execute(
            invoke,
            provider="duckduckgo",
            correlation_id=_search_correlation_id(config),
        )


def _content_hash(*parts: str) -> str:
    payload = "\n".join(parts).encode("utf-8")
    return sha256(payload).hexdigest()


def parse_builtin_search_response(
    *,
    query: str,
    response: AIMessage,
    fetched_at: datetime,
) -> list[WebEvidence]:
    blocks: list[Any] = response.content_blocks
    if not _successful_web_search(blocks):
        raise ResearchUnavailable(
            "built-in web search requires a completed server web_search call and "
            "provider URL citation",
            provider="builtin_web_search",
            retryable=False,
            error_type="UnverifiedServerToolCall",
        )

    evidence: list[WebEvidence] = []
    seen_urls: set[str] = set()

    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = str(block.get("text") or "").strip()
        for annotation in block.get("annotations") or []:
            if not isinstance(annotation, dict):
                continue
            if annotation.get("type") not in {"citation", "url_citation"}:
                continue
            url = str(annotation.get("url") or "").strip()
            if not _is_public_https_url(url) or url in seen_urls:
                continue
            title = str(annotation.get("title") or url).strip()
            seen_urls.add(url)
            try:
                item = WebEvidence(
                    query=query,
                    final_url=url,
                    fetched_at=fetched_at,
                    content_hash=_content_hash(url, title, text),
                    title=title,
                    source="openai_builtin_web_search",
                    excerpt=text[:1000],
                    evidence_relation="supports",
                )
            except ValidationError:
                continue
            evidence.append(item)

    if not evidence:
        raise ResearchUnavailable(
            "built-in web search returned no verified provider URL citation",
            provider="builtin_web_search",
            retryable=False,
            error_type="MissingProviderCitation",
        )
    return evidence


def _successful_web_search(blocks: list[Any]) -> bool:
    normalized = [_unwrap_content_block(block) for block in blocks]
    if any(
        isinstance(block, dict)
        and block.get("type") == "web_search_call"
        and block.get("status") in {"completed", "success"}
        for block in normalized
    ):
        return True
    calls = {
        str(block.get("id"))
        for block in normalized
        if isinstance(block, dict)
        and block.get("type") == "server_tool_call"
        and block.get("name") == "web_search"
        and block.get("id")
    }
    return any(
        isinstance(block, dict)
        and block.get("type") == "server_tool_result"
        and str(block.get("tool_call_id")) in calls
        and block.get("status") in {"completed", "success"}
        for block in normalized
    ) or any(
        isinstance(block, dict)
        and block.get("type") == "server_tool_call"
        and block.get("name") == "web_search"
        and block.get("status") in {"completed", "success"}
        for block in normalized
    )


def _unwrap_content_block(block: Any) -> Any:
    if (
        isinstance(block, dict)
        and block.get("type") == "non_standard"
        and isinstance(block.get("value"), dict)
    ):
        return block["value"]
    return block


def _is_public_https_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or hostname in _RESERVED_EVIDENCE_HOSTS
            or any(
                hostname.endswith(f".{reserved}")
                for reserved in _RESERVED_EVIDENCE_HOSTS
            )
        ):
            return False
        try:
            return ipaddress.ip_address(hostname).is_global
        except ValueError:
            return True
    except ValueError:
        return False


def parse_tavily_response(
    *,
    query: str,
    response: Any,
    fetched_at: datetime,
) -> list[WebEvidence]:
    if not isinstance(response, dict):
        raise ResearchUnavailable(
            "Tavily search returned an invalid response",
            provider="tavily",
            retryable=True,
            error_type="InvalidProviderResponse",
        )
    if response.get("error") is not None:
        error = response["error"]
        if isinstance(error, Exception):
            raise _normalize_search_error(
                error,
                provider="tavily",
                label="Tavily search",
            )
        raise ResearchUnavailable(
            "Tavily search failed",
            provider="tavily",
            retryable=False,
            error_type="ProviderError",
        )
    results = response.get("results")
    if not isinstance(results, list) or not results:
        raise ResearchUnavailable(
            "Tavily search returned no results",
            provider="tavily",
            retryable=True,
            error_type="EmptyProviderResponse",
        )

    evidence: list[WebEvidence] = []
    seen_urls: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            continue
        url = str(result.get("url") or "").strip()
        title = str(result.get("title") or "").strip()
        excerpt = str(result.get("content") or "").strip()
        if (
            not _is_public_https_url(url)
            or not title
            or not excerpt
            or url in seen_urls
        ):
            continue
        seen_urls.add(url)
        try:
            item = WebEvidence(
                query=query,
                final_url=url,
                fetched_at=fetched_at,
                content_hash=_content_hash(url, title, excerpt),
                title=title,
                source="tavily",
                excerpt=excerpt[:1000],
                evidence_relation="supports",
            )
        except ValidationError:
            continue
        evidence.append(item)
    if not evidence:
        raise ResearchUnavailable(
            "Tavily search returned no valid URL/title/snippet evidence",
            provider="tavily",
            retryable=True,
            error_type="InvalidProviderEvidence",
        )
    return evidence


def parse_duckduckgo_response(
    *,
    query: str,
    response: Any,
    fetched_at: datetime,
) -> list[WebEvidence]:
    if not isinstance(response, list):
        raise ResearchUnavailable(
            "DuckDuckGo search returned an invalid response",
            provider="duckduckgo",
            retryable=True,
            error_type="InvalidProviderResponse",
        )

    evidence: list[WebEvidence] = []
    seen_urls: set[str] = set()
    for raw in response:
        if not isinstance(raw, Mapping):
            continue
        url = str(raw.get("url") or raw.get("link") or "").strip()
        if not _is_public_https_url(url) or url in seen_urls:
            continue
        title = str(raw.get("title") or url).strip()
        excerpt = str(raw.get("body") or raw.get("snippet") or "").strip()
        if not excerpt:
            continue
        published_at = _provider_datetime(raw.get("date"), fetched_at=fetched_at)
        try:
            item = WebEvidence(
                query=query,
                final_url=url,
                fetched_at=fetched_at,
                published_at=published_at,
                content_hash=_content_hash(url, title, excerpt),
                parser_version="langchain-ddgs-v1",
                title=title,
                author=str(raw.get("source") or "").strip() or None,
                source="duckduckgo",
                excerpt=excerpt[:1000],
                evidence_relation="supports",
            )
        except ValidationError:
            continue
        seen_urls.add(url)
        evidence.append(item)

    if not evidence:
        raise ResearchUnavailable(
            "DuckDuckGo search returned no valid public HTTPS evidence",
            provider="duckduckgo",
            retryable=True,
            error_type="EmptyEvidence",
        )
    return evidence


def _provider_datetime(value: Any, *, fetched_at: datetime) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    return parsed if parsed <= fetched_at else None


def _create_duckduckgo_tool(
    *,
    proxy: str | None,
    timeout: float,
) -> BaseTool:
    def search_duckduckgo(query: str) -> list[dict[str, Any]]:
        from ddgs import DDGS

        return DDGS(proxy=proxy, timeout=max(1, int(timeout))).news(
            query,
            max_results=8,
        )

    return StructuredTool.from_function(
        func=search_duckduckgo,
        name="duckduckgo_search",
        description=(
            "Search current public news with DuckDuckGo and return provider URLs, "
            "titles, excerpts, publication timestamps, and source names."
        ),
    )


def _invoke_tavily_tool(
    tool: SearchTool,
    input: dict[str, str],
    *,
    config: RunnableConfig | None,
    timeout: float,
) -> Any:
    async_invoke = getattr(tool, "ainvoke", None)
    if not callable(async_invoke):
        return tool.invoke(input, config=config)

    async def invoke() -> Any:
        return await asyncio.wait_for(
            async_invoke(input, config=config),
            timeout=timeout,
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(invoke())
    raise ResearchUnavailable(
        "Tavily synchronous search cannot run on an active event loop",
        provider="tavily",
        retryable=False,
        error_type="ActiveEventLoop",
    )


async def _ainvoke_tavily_tool(
    tool: SearchTool,
    input: dict[str, str],
    *,
    config: RunnableConfig | None,
    timeout: float,
) -> Any:
    async_invoke = getattr(tool, "ainvoke", None)
    if not callable(async_invoke):
        raise ResearchUnavailable(
            "Tavily tool does not support asynchronous invocation",
            provider="tavily",
            retryable=False,
            error_type="AsyncUnsupported",
        )
    return await asyncio.wait_for(
        async_invoke(input, config=config),
        timeout=timeout,
    )


def _normalize_search_error(
    exc: Exception,
    *,
    provider: str,
    label: str,
) -> ResearchUnavailable:
    if isinstance(exc, ResearchUnavailable):
        return exc
    return ResearchUnavailable(
        f"{label} failed: {type(exc).__name__}",
        provider=provider,
        retryable=_is_retryable_search_error(exc),
        retry_after_seconds=_retry_after_seconds(exc),
        error_type=type(exc).__name__,
    )


def _is_retryable_search_error(exc: Exception) -> bool:
    if isinstance(exc, TRANSIENT_MODEL_ERRORS):
        return True
    if type(exc).__module__.startswith("ddgs."):
        return True
    name = type(exc).__name__.lower()
    if any(marker in name for marker in ("timeout", "connection", "ratelimit")):
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "error 408",
            "error 429",
            "error 500",
            "error 502",
            "error 503",
            "error 504",
        )
    )


def _retry_after_seconds(exc: Exception) -> float | None:
    direct = getattr(exc, "retry_after", None)
    if direct is not None:
        try:
            return max(0.0, float(direct))
        except (TypeError, ValueError):
            pass
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(str(value))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _search_correlation_id(config: RunnableConfig | None) -> str | None:
    if not isinstance(config, Mapping):
        return None
    metadata = config.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get("correlation_id")
    if not isinstance(value, str) or not value.strip():
        return None
    return value
