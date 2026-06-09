from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import time
from typing import Any, Protocol

import httpx

from crypto_manual_alert.research_pipeline.llm_support import duration_ms, openai_settings
from crypto_manual_alert.telemetry.llm import extract_responses_telemetry
from crypto_manual_alert.telemetry.observability import record_llm_interaction


@dataclass(frozen=True)
class SearchProviderRequest:
    symbol: str
    query: str
    trace_id: str
    task_id: str
    max_results: int = 5


class SearchProvider(Protocol):
    def search(self, request: SearchProviderRequest) -> list[dict[str, str]]:
        """Return redacted search result references for a controlled skill call."""


@dataclass(frozen=True)
class FixtureSearchProvider:
    def search(self, request: SearchProviderRequest) -> list[dict[str, str]]:
        return [
            {
                "title": f"fixture search: {request.query}",
                "url": f"fixture://realtime_search/{request.symbol}",
                "snippet_ref": "fixture.realtime_search[0].snippet_redacted",
                "source_type": "search_derived",
            }
        ]


@dataclass(frozen=True)
class ResponsesWebSearchProvider:
    base_url: str
    model: str
    api_key: str = field(repr=False)
    timeout_seconds: int = 8
    max_results: int = 3
    client: httpx.Client | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not self.base_url:
            raise ValueError("base_url is required for responses_web_search")
        if not self.model:
            raise ValueError("model is required for responses_web_search")
        if not self.api_key:
            raise ValueError("api_key is required for responses_web_search")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive for responses_web_search")
        if self.max_results < 1:
            raise ValueError("max_results must be positive for responses_web_search")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    @classmethod
    def from_config(cls, config: object) -> "ResponsesWebSearchProvider":
        base_url, model, api_key = openai_settings(config, "skill_providers.realtime_search=responses_web_search")
        research = getattr(config, "research", None)
        return cls(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=int(getattr(research, "request_timeout_seconds", 8)),
            max_results=int(getattr(research, "max_results_per_query", 3)),
        )

    def search(self, request: SearchProviderRequest) -> list[dict[str, str]]:
        payload = {
            "model": self.model,
            "input": _responses_web_search_prompt(request, max_results=min(request.max_results, self.max_results)),
            "tools": [{"type": "web_search"}],
            "max_output_tokens": 700,
        }
        client = self.client or httpx.Client(timeout=self.timeout_seconds)
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
                if not isinstance(data, dict):
                    raise RuntimeError("responses API returned a non-object payload")
                telemetry = extract_responses_telemetry(data)
                record_llm_interaction(
                    component="skills.realtime_search.web_search",
                    provider="openai_compatible_responses",
                    model=self.model,
                    endpoint="/v1/responses",
                    request_payload=payload,
                    response_payload=data,
                    status="ok",
                    duration_ms=duration_ms(started_perf),
                    prompt_tokens=telemetry.prompt_tokens,
                    completion_tokens=telemetry.completion_tokens,
                    total_tokens=telemetry.total_tokens,
                    cost_usd=telemetry.cost_usd,
                    finish_reason=telemetry.finish_reason,
                    retry_count=0,
                    metadata={"trace_id": request.trace_id, "task_id": request.task_id},
                )
            except Exception as exc:
                record_llm_interaction(
                    component="skills.realtime_search.web_search",
                    provider="openai_compatible_responses",
                    model=self.model,
                    endpoint="/v1/responses",
                    request_payload=payload,
                    response_payload=None,
                    status="error",
                    error=exc,
                    duration_ms=duration_ms(started_perf),
                    retry_count=0,
                    metadata={"trace_id": request.trace_id, "task_id": request.task_id},
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
            {
                "title": f"Responses web search: {request.symbol}",
                "url": "responses://web_search",
                "snippet_ref": _snippet_ref(request.trace_id, 0, text),
                "source_type": "search_derived",
            }
        ]


def _responses_web_search_prompt(request: SearchProviderRequest, *, max_results: int) -> str:
    return (
        "Use web search for this controlled realtime_search skill call. "
        "Return concise current facts with source names, URLs, and timestamps when available. "
        "Do not give trading advice or final actions. "
        "All user-facing explanatory text should be Simplified Chinese; keep source names, URLs, symbols, "
        "and technical field names in canonical format.\n"
        f"Symbol: {request.symbol}\n"
        f"Task id: {request.task_id}\n"
        f"Search query: {request.query}\n"
        f"Maximum source summaries: {max_results}\n"
        "Required output: facts, source URLs, timestamps if available, and uncertainty."
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


def _snippet_ref(trace_id: str, index: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"responses.realtime_search.{trace_id}.{index}.snippet_sha256:{digest}"
