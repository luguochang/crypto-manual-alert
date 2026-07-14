from typing import Protocol

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from crypto_alert_v2.domain.models import ResearchBundle
from crypto_alert_v2.providers.capability_probe import (
    SearchProvider,
    SearchReadinessError,
)
from crypto_alert_v2.providers.search import (
    BuiltinWebSearchProvider,
    DuckDuckGoSearchProvider,
    ResearchResult,
    TavilySearchProvider,
    WebEvidence,
)
from crypto_alert_v2.providers.errors import TRANSIENT_MODEL_ERRORS
from crypto_alert_v2.providers.model import as_chat_completions_model


RESEARCH_PROMPT = """Extract only facts supported by the supplied cited evidence.
Set VIX, US 10-year real yield, DXY, or macro_event_scan to null when the evidence
does not establish them. Every finding source_url must be one of the supplied URLs.
Do not use unstated model knowledge and do not invent a citation.
"""


class EvidenceSearch(Protocol):
    def search(
        self, query: str, config: RunnableConfig | None = None
    ) -> list[WebEvidence]: ...


class CitedResearchCollector:
    def __init__(self, model: ChatOpenAI, search: EvidenceSearch) -> None:
        self._search = search
        self._agent = create_agent(
            model=as_chat_completions_model(model),
            tools=[],
            system_prompt=RESEARCH_PROMPT,
            response_format=ToolStrategy(ResearchBundle),
        ).with_retry(
            retry_if_exception_type=TRANSIENT_MODEL_ERRORS,
            stop_after_attempt=2,
        )

    def collect(
        self, query: str, config: RunnableConfig | None = None
    ) -> ResearchResult:
        evidence = tuple(self._search.search(query, config=config))
        evidence_text = "\n\n".join(
            f"URL: {item.final_url}\nTitle: {item.title}\nExcerpt: {item.excerpt}"
            for item in evidence
        )
        result = self._agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": f"Research query: {query}\n\nCited evidence:\n{evidence_text}",
                    }
                ]
            },
            config=config,
        )
        bundle = result["structured_response"]
        if not isinstance(bundle, ResearchBundle):
            raise TypeError("research agent did not return ResearchBundle")

        cited_urls = {str(item.final_url) for item in evidence}
        unsupported = [
            finding.source_url
            for finding in bundle.findings
            if finding.source_url not in cited_urls
        ]
        if unsupported:
            raise ValueError("research agent returned a source outside cited evidence")
        return ResearchResult(bundle=bundle, evidence=evidence)


class BuiltinResearchCollector(CitedResearchCollector):
    def __init__(self, model: ChatOpenAI) -> None:
        super().__init__(model, BuiltinWebSearchProvider(model))


class TavilyResearchCollector(CitedResearchCollector):
    def __init__(self, model: ChatOpenAI, *, api_key: str) -> None:
        super().__init__(model, TavilySearchProvider(api_key=api_key))


class DuckDuckGoResearchCollector(CitedResearchCollector):
    def __init__(self, model: ChatOpenAI, *, proxy: str | None = None) -> None:
        super().__init__(model, DuckDuckGoSearchProvider(proxy=proxy))


class CapabilityAwareResearchCollector:
    def __init__(
        self,
        model: ChatOpenAI,
        *,
        tavily_api_key: str | None,
        provider: SearchProvider,
        search_http_proxy: str | None = None,
    ) -> None:
        self._model = model
        self._tavily_api_key = tavily_api_key
        self._provider = provider
        self._search_http_proxy = search_http_proxy
        self._selected: CitedResearchCollector | None = None

    def collect(
        self, query: str, config: RunnableConfig | None = None
    ) -> ResearchResult:
        if self._selected is None:
            if self._provider is SearchProvider.BUILTIN:
                self._selected = BuiltinResearchCollector(self._model)
            elif self._provider is SearchProvider.DUCKDUCKGO:
                self._selected = DuckDuckGoResearchCollector(
                    self._model,
                    proxy=self._search_http_proxy,
                )
            else:
                if self._tavily_api_key is None:
                    raise SearchReadinessError(
                        "Tavily was selected but TAVILY_API_KEY is not configured"
                    )
                self._selected = TavilyResearchCollector(
                    self._model,
                    api_key=self._tavily_api_key,
                )
        return self._selected.collect(query, config=config)
