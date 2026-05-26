from __future__ import annotations

from html.parser import HTMLParser
import time
from typing import Any
from urllib.parse import quote_plus

import httpx

from crypto_manual_alert.config import Config
from crypto_manual_alert.research_pipeline.llm_support import duration_ms, openai_settings
from crypto_manual_alert.research_pipeline.models import ResearchQuery, SearchResult
from crypto_manual_alert.research_pipeline.prompts import USER_FACING_LANGUAGE_RULE
from crypto_manual_alert.telemetry.llm import extract_responses_telemetry
from crypto_manual_alert.telemetry.observability import record_llm_interaction


class DisabledSearchAdapter:
    def search(self, query: ResearchQuery) -> list[SearchResult]:
        return []


class FixtureSearchAdapter:
    def __init__(self, results_by_name: dict[str, list[dict[str, str]]]):
        self.results_by_name = results_by_name

    def search(self, query: ResearchQuery) -> list[SearchResult]:
        return [SearchResult(**item) for item in self.results_by_name.get(query.name, [])]


class DuckDuckGoHtmlSearchAdapter:
    def __init__(self, config: Config):
        self.max_results = config.research.max_results_per_query
        self.timeout = config.research.request_timeout_seconds

    def search(self, query: ResearchQuery) -> list[SearchResult]:
        url = f"https://duckduckgo.com/html/?q={quote_plus(query.query)}"
        response = httpx.get(url, timeout=self.timeout, headers={"User-Agent": "crypto-manual-alert/0.1"})
        response.raise_for_status()
        parser = _DuckDuckGoParser(max_results=self.max_results)
        parser.feed(response.text)
        return parser.results


class ResponsesWebSearchAdapter:
    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.base_url, self.model, self.api_key = openai_settings(config, "responses_web_search")
        self.timeout = config.research.request_timeout_seconds
        self.client = client

    def search(self, query: ResearchQuery) -> list[SearchResult]:
        payload = {
            "model": self.model,
            "input": _responses_web_search_prompt(query),
            "tools": [{"type": "web_search"}],
            "max_output_tokens": 700,
        }
        client = self.client or httpx.Client(timeout=self.timeout)
        close_client = self.client is None
        started_perf = time.perf_counter()
        try:
            try:
                response = client.post(
                    f"{self.base_url}/v1/responses",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                telemetry = extract_responses_telemetry(data)
                record_llm_interaction(
                    component="research.web_search",
                    provider="openai_compatible_responses",
                    model=self.model,
                    endpoint="/v1/responses",
                    request_payload=payload,
                    response_payload=data,
                    status="ok",
                    duration_ms=duration_ms(started_perf, time.perf_counter()),
                    prompt_tokens=telemetry.prompt_tokens,
                    completion_tokens=telemetry.completion_tokens,
                    total_tokens=telemetry.total_tokens,
                    cost_usd=telemetry.cost_usd,
                    finish_reason=telemetry.finish_reason,
                    retry_count=0,
                    metadata={"query_name": query.name},
                )
            except Exception as exc:
                record_llm_interaction(
                    component="research.web_search",
                    provider="openai_compatible_responses",
                    model=self.model,
                    endpoint="/v1/responses",
                    request_payload=payload,
                    response_payload=None,
                    status="error",
                    error=exc,
                    duration_ms=duration_ms(started_perf, time.perf_counter()),
                    retry_count=0,
                    metadata={"query_name": query.name},
                )
                raise
        finally:
            if close_client:
                client.close()
        web_search_requests = _web_search_request_count(data)
        if web_search_requests <= 0:
            raise RuntimeError("responses API returned no actual web_search usage")
        text = _responses_output_text(data)
        if not text:
            raise RuntimeError("responses API returned empty web_search output")
        return [
            SearchResult(
                title=f"Responses web search: {query.name}",
                url="responses://web_search",
                snippet=f"web_search_requests={web_search_requests}; {text}",
                source="responses-web-search",
            )
        ]


def _responses_web_search_prompt(query: ResearchQuery) -> str:
    return (
        "Use web search for the following crypto research task. "
        "Return a concise evidence summary with source names and URLs. "
        "Do not provide trading advice here; only summarize current facts. "
        "All user-facing explanatory text must be Simplified Chinese (简体中文); keep source names, URLs, symbols, "
        "and technical field names in canonical format. "
        f"Task name: {query.name}\n"
        f"Purpose: {query.purpose}\n"
        f"Search query: {query.query}\n"
        "Required output: facts, timestamps if available, source URLs, and uncertainty, written in Simplified Chinese."
    )


def _web_search_request_count(data: dict[str, Any]) -> int:
    try:
        return int(((data.get("tool_usage") or {}).get("web_search") or {}).get("num_requests") or 0)
    except (TypeError, ValueError):
        return 0


def _responses_output_text(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") == "output_text":
                chunks.append(str(content.get("text") or ""))
    return "\n".join(chunk for chunk in chunks if chunk).strip()


class _DuckDuckGoParser(HTMLParser):
    def __init__(self, max_results: int):
        super().__init__()
        self.max_results = max_results
        self.results: list[SearchResult] = []
        self._in_result_link = False
        self._in_snippet = False
        self._current_title: list[str] = []
        self._current_url = ""
        self._pending_snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name: value or "" for name, value in attrs}
        classes = attrs_dict.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._in_result_link = True
            self._current_title = []
            self._current_url = attrs_dict.get("href", "")
        elif "result__snippet" in classes:
            self._in_snippet = True
            self._pending_snippet = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_result_link:
            self._in_result_link = False
        if self._in_snippet and tag in {"a", "div"}:
            self._in_snippet = False
            if self._current_title and len(self.results) < self.max_results:
                self.results.append(
                    SearchResult(
                        title=" ".join("".join(self._current_title).split()),
                        url=self._current_url,
                        snippet=" ".join("".join(self._pending_snippet).split()),
                    )
                )
                self._current_title = []
                self._current_url = ""
                self._pending_snippet = []

    def handle_data(self, data: str) -> None:
        if self._in_result_link:
            self._current_title.append(data)
        elif self._in_snippet:
            self._pending_snippet.append(data)
