import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
import ipaddress
import re
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from pydantic import BaseModel, ConfigDict, HttpUrl, ValidationError

from crypto_alert_v2.domain.models import ModelExecutionAudit, ResearchBundle
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
    model_audit: ModelExecutionAudit | None = None


class BuiltinWebSearchProvider:
    def __init__(
        self,
        model: ChatOpenAI,
        *,
        retry_policy: SearchRetryPolicy | None = None,
        result_requirements: str | None = None,
        allow_completed_open_page_evidence: bool = False,
        evidence_validator: Callable[[list[WebEvidence]], None] | None = None,
    ) -> None:
        self._model = model
        self._retry_policy = retry_policy or SearchRetryPolicy()
        self._result_requirements = " ".join((result_requirements or "").split())
        if len(self._result_requirements) > 1000:
            raise ValueError(
                "built-in search result requirements exceed 1000 characters"
            )
        self._allow_completed_open_page_evidence = allow_completed_open_page_evidence
        self._evidence_validator = evidence_validator

    def search(
        self, query: str, config: RunnableConfig | None = None
    ) -> list[WebEvidence]:
        provider_query = _compact_search_query(query)
        if self._allow_completed_open_page_evidence:
            prompt = (
                f"{self._result_requirements}\n\n"
                "Use the web_search tool, open exactly one public source page, and "
                "include that exact opened HTTPS URL in the final sentence.\n\n"
                f"Question: {provider_query}"
            )
        else:
            prompt = (
                "You must use web search. Cite only provider-returned URL citation "
                "annotations. Write one short factual bullet per source and keep each "
                "citation on the same bullet as the claim it supports. Use no more than "
                "four sources and stop once those sources are found.\n\n"
                f"Search query: {provider_query}"
            )
            if self._result_requirements:
                prompt = f"{prompt}\n\nResult requirements: {self._result_requirements}"
        search_tool_type = "web_search"

        def invoke(remaining_seconds: float, _: int) -> list[WebEvidence]:
            nonlocal search_tool_type
            try:
                bound_search = self._model.bind_tools(
                    [{"type": search_tool_type}],
                    tool_choice=search_tool_type,
                    parallel_tool_calls=False,
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
                evidence = parse_builtin_search_response(
                    query=query,
                    response=response,
                    fetched_at=datetime.now(UTC),
                    allow_completed_open_page_evidence=(
                        self._allow_completed_open_page_evidence
                    ),
                )
                if self._evidence_validator is not None:
                    self._evidence_validator(evidence)
                return evidence
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
        evidence_validator: Callable[[list[WebEvidence]], None] | None = None,
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
        self._evidence_validator = evidence_validator

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
            evidence = parse_tavily_response(
                query=query,
                response=response,
                fetched_at=datetime.now(UTC),
            )
            if self._evidence_validator is not None:
                self._evidence_validator(evidence)
            return evidence

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
            evidence = parse_tavily_response(
                query=query,
                response=response,
                fetched_at=datetime.now(UTC),
            )
            if self._evidence_validator is not None:
                self._evidence_validator(evidence)
            return evidence

        return await self._retry_policy.execute_async(
            invoke,
            provider="tavily",
            correlation_id=_search_correlation_id(config),
        )


class DdgsMetasearchProvider:
    """No-key automatic metasearch through DDGS behind a LangChain tool."""

    def __init__(
        self,
        *,
        proxy: str | None = None,
        tool: SearchTool | None = None,
        retry_policy: SearchRetryPolicy | None = None,
        evidence_validator: Callable[[list[WebEvidence]], None] | None = None,
        result_kind: Literal["news", "text"] = "news",
    ) -> None:
        if result_kind not in {"news", "text"}:
            raise ValueError("DDGS metasearch result kind must be news or text")
        self._proxy = proxy
        self._tool = tool
        self._retry_policy = retry_policy or SearchRetryPolicy()
        self._evidence_validator = evidence_validator
        self._result_kind = result_kind

    def search(
        self, query: str, config: RunnableConfig | None = None
    ) -> list[WebEvidence]:
        provider_query = _compact_search_query(query)

        def invoke(remaining_seconds: float, _: int) -> list[WebEvidence]:
            tool = self._tool or _create_ddgs_metasearch_tool(
                proxy=self._proxy,
                timeout=remaining_seconds,
                result_kind=self._result_kind,
            )
            try:
                response = tool.invoke({"query": provider_query}, config=config)
            except Exception as exc:
                raise _normalize_search_error(
                    exc,
                    provider="ddgs_metasearch",
                    label="DDGS metasearch",
                ) from exc
            evidence = parse_ddgs_metasearch_response(
                query=query,
                response=response,
                fetched_at=datetime.now(UTC),
            )
            if self._evidence_validator is not None:
                self._evidence_validator(evidence)
            return evidence

        return self._retry_policy.execute(
            invoke,
            provider="ddgs_metasearch",
            correlation_id=_search_correlation_id(config),
        )


def _compact_search_query(query: str) -> str:
    """Keep provider URLs bounded while preserving the original evidence query."""

    normalized = " ".join(query.split())
    if len(normalized) <= 160 and all(ord(char) < 128 for char in normalized):
        return normalized

    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]*", normalized)
    asset = next(
        (token.upper() for token in tokens if token.upper() in {"BTC", "ETH", "SOL"}),
        None,
    )
    terms = [
        "current",
        *([asset] if asset else []),
        "cryptocurrency",
        "market",
        "macro",
        "news",
    ]
    if not asset:
        for token in tokens:
            if token.lower() not in {term.lower() for term in terms}:
                terms.append(token)
                break

    return " ".join(terms)[:160].rstrip()


def _content_hash(*parts: str) -> str:
    payload = "\n".join(parts).encode("utf-8")
    return sha256(payload).hexdigest()


def _citation_excerpt(
    text: str,
    annotation: Mapping[str, Any],
    *,
    title: str,
    single_citation: bool,
) -> str:
    """Return only the provider text attributable to one citation.

    Responses Web Search can attach several URL citations to one aggregate text
    block. Persisting that entire block once per URL makes distinct sources appear
    to contain the same evidence. Prefer the official annotation span and fall back
    to its containing bullet/sentence. When the provider supplies no offsets, the
    citation title is the only source-specific text we can safely attribute.
    """

    start = annotation.get("start_index")
    end = annotation.get("end_index")
    if not isinstance(start, int) or isinstance(start, bool):
        return (_clean_citation_text(text) if single_citation else title)[:1000]
    if not isinstance(end, int) or isinstance(end, bool):
        return (_clean_citation_text(text) if single_citation else title)[:1000]
    if start < 0 or end <= start or start >= len(text):
        return (_clean_citation_text(text) if single_citation else title)[:1000]

    bounded_end = min(end, len(text))
    annotated = _clean_citation_text(text[start:bounded_end])
    if len(annotated) >= 24:
        return annotated[:1000]

    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", bounded_end)
    if line_end < 0:
        line_end = len(text)
    line = _clean_citation_text(text[line_start:line_end])
    if line:
        return line[:1000]
    return title[:1000]


def _clean_citation_text(value: str) -> str:
    normalized = " ".join(value.split()).strip()
    normalized = re.sub(r"^(?:[-*]|\d+[.)])\s+", "", normalized)
    return normalized.strip()


def parse_builtin_search_response(
    *,
    query: str,
    response: AIMessage,
    fetched_at: datetime,
    allow_completed_open_page_evidence: bool = False,
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
        annotations = block.get("annotations") or []
        citation_count = sum(
            1
            for annotation in annotations
            if isinstance(annotation, dict)
            and annotation.get("type") in {"citation", "url_citation"}
        )
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
            if annotation.get("type") not in {"citation", "url_citation"}:
                continue
            url = str(annotation.get("url") or "").strip()
            if not _is_public_https_url(url) or url in seen_urls:
                continue
            title = str(annotation.get("title") or url).strip()
            excerpt = _citation_excerpt(
                text,
                annotation,
                title=title,
                single_citation=citation_count == 1,
            )
            seen_urls.add(url)
            try:
                item = WebEvidence(
                    query=query,
                    final_url=url,
                    fetched_at=fetched_at,
                    content_hash=_content_hash(url, title, excerpt),
                    title=title,
                    source="openai_builtin_web_search",
                    excerpt=excerpt,
                    evidence_relation="supports",
                )
            except ValidationError:
                continue
            evidence.append(item)

    if allow_completed_open_page_evidence:
        for opened_page in _completed_open_page_evidence(
            query=query,
            blocks=blocks,
            fetched_at=fetched_at,
        ):
            opened_url = str(opened_page.final_url)
            evidence = [item for item in evidence if str(item.final_url) != opened_url]
            evidence.append(opened_page)
    if not evidence:
        raise ResearchUnavailable(
            "built-in web search returned no verified provider URL citation",
            provider="builtin_web_search",
            retryable=False,
            error_type="MissingProviderCitation",
        )
    return evidence


def _completed_open_page_evidence(
    *,
    query: str,
    blocks: list[Any],
    fetched_at: datetime,
) -> list[WebEvidence]:
    normalized = [_unwrap_content_block(block) for block in blocks]
    open_page_calls: dict[str, str] = {}
    for block in normalized:
        if (
            not isinstance(block, Mapping)
            or block.get("type") != "server_tool_call"
            or block.get("name") != "web_search"
            or not isinstance(block.get("args"), Mapping)
        ):
            continue
        args = block["args"]
        call_id = block.get("id")
        url = args.get("url")
        if (
            args.get("type") == "open_page"
            and isinstance(call_id, str)
            and isinstance(url, str)
            and _is_public_https_url(url)
        ):
            open_page_calls[call_id] = url
    completed_urls = {
        open_page_calls[str(block.get("tool_call_id"))]
        for block in normalized
        if isinstance(block, Mapping)
        and block.get("type") == "server_tool_result"
        and block.get("status") in {"completed", "success"}
        and str(block.get("tool_call_id")) in open_page_calls
    }
    if not completed_urls:
        return []

    evidence: list[WebEvidence] = []
    seen_urls: set[str] = set()
    for block in normalized:
        if not isinstance(block, Mapping) or block.get("type") != "text":
            continue
        text = _clean_citation_text(str(block.get("text") or ""))
        matching_urls = [url for url in completed_urls if url in text]
        if len(matching_urls) != 1 or not text:
            continue
        url = matching_urls[0]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        hostname = urlsplit(url).hostname or url
        evidence.append(
            WebEvidence(
                query=query,
                final_url=url,
                fetched_at=fetched_at,
                content_hash=_content_hash(url, hostname, text),
                parser_version="openai-responses-open-page-v1",
                title=hostname,
                source="openai_builtin_web_search",
                excerpt=text[:1000],
                evidence_relation="supports",
            )
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


def parse_ddgs_metasearch_response(
    *,
    query: str,
    response: Any,
    fetched_at: datetime,
) -> list[WebEvidence]:
    if not isinstance(response, list):
        raise ResearchUnavailable(
            "DDGS metasearch returned an invalid response",
            provider="ddgs_metasearch",
            retryable=True,
            error_type="InvalidProviderResponse",
        )

    evidence: list[WebEvidence] = []
    seen_urls: set[str] = set()
    for raw in response:
        if not isinstance(raw, Mapping):
            continue
        url = str(raw.get("url") or raw.get("link") or raw.get("href") or "").strip()
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
                parser_version="ddgs-metasearch-v1",
                title=title,
                author=str(raw.get("source") or "").strip() or None,
                source="ddgs_metasearch",
                excerpt=excerpt[:1000],
                evidence_relation="supports",
            )
        except ValidationError:
            continue
        seen_urls.add(url)
        evidence.append(item)

    if not evidence:
        raise ResearchUnavailable(
            "DDGS metasearch returned no valid public HTTPS evidence",
            provider="ddgs_metasearch",
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


def _create_ddgs_metasearch_tool(
    *,
    proxy: str | None,
    timeout: float,
    result_kind: Literal["news", "text"],
) -> BaseTool:
    def search_ddgs_metasearch(query: str) -> list[dict[str, Any]]:
        from ddgs import DDGS

        client = DDGS(proxy=proxy, timeout=max(1, int(timeout)))
        if result_kind == "text":
            return client.text(query, max_results=8, backend="auto")
        return client.news(query, max_results=8, backend="auto")

    return StructuredTool.from_function(
        func=search_ddgs_metasearch,
        name="ddgs_metasearch",
        description=(
            f"Search current public {result_kind} results with DDGS automatic "
            "metasearch and return provider URLs, "
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
    if any(
        marker in name for marker in ("timeout", "connection", "connector", "ratelimit")
    ):
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
    parsed = _parse_retry_after_value(direct)
    if parsed is not None:
        return parsed
    body = getattr(exc, "body", None)
    if isinstance(body, Mapping):
        candidates = [body.get("retry_after"), body.get("retry_after_seconds")]
        nested_error = body.get("error")
        if isinstance(nested_error, Mapping):
            candidates.extend(
                [
                    nested_error.get("retry_after"),
                    nested_error.get("retry_after_seconds"),
                ]
            )
        for candidate in candidates:
            parsed = _parse_retry_after_value(candidate)
            if parsed is not None:
                return parsed
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


def _parse_retry_after_value(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
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
