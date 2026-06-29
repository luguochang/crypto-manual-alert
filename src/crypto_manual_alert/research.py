from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import os
from typing import Any, Protocol
from urllib.parse import quote_plus

import httpx

from .config import Config
from .domain import DataPoint, MarketSnapshot
from .observability import record_llm_interaction


CORE_MARKET_POINTS = ("last", "mark", "index", "funding_rate", "open_interest", "order_book", "candles")
SEARCH_CONFIDENCE_CAP = "confidence_cap:0.58:检索派生的衍生品数据不能替代交易所原生执行事实"
USER_FACING_LANGUAGE_RULE = (
    "All user-facing explanatory text must be Simplified Chinese (简体中文). "
    "Keep JSON keys, source labels, URLs, symbol names, and error class names in canonical format."
)
LEADER_REVIEW_KEYS = (
    "leader_finalizer",
    "bull_reviewer",
    "bear_reviewer",
    "data_quality_reviewer",
    "execution_risk_reviewer",
)


@dataclass(frozen=True)
class ResearchQuery:
    name: str
    query: str
    purpose: str
    required: bool = True


@dataclass(frozen=True)
class ResearchPlan:
    queries: list[ResearchQuery]
    reason: str
    planner: str = "static"

    def to_public_dict(self) -> dict[str, Any]:
        return {"planner": self.planner, "reason": self.reason, "queries": [query.__dict__ for query in self.queries]}


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = "search-derived"

    def to_public_dict(self) -> dict[str, Any]:
        return self.__dict__


@dataclass(frozen=True)
class ResearchAudit:
    plan: ResearchPlan
    results: dict[str, list[SearchResult]] = field(default_factory=dict)
    unavailable: list[str] = field(default_factory=list)
    leader_summary: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_public_dict(),
            "results": {name: [result.to_public_dict() for result in results] for name, results in self.results.items()},
            "unavailable": list(self.unavailable),
            "leader_summary": self.leader_summary,
        }


class ResearchPlanner(Protocol):
    def plan(self, snapshot: MarketSnapshot, skill_context: dict[str, Any] | None = None) -> ResearchPlan:
        """Build web-search tasks for missing market facts."""


class SearchAdapter(Protocol):
    def search(self, query: ResearchQuery) -> list[SearchResult]:
        """Run one controlled search query."""


class LeaderResearchSynthesizer(Protocol):
    def synthesize(self, snapshot: MarketSnapshot, audit: ResearchAudit) -> ResearchAudit:
        """Summarize parallel research and adversarial review."""


class StaticResearchPlanner:
    def __init__(self, max_queries: int = 6):
        self.max_queries = max_queries

    def plan(self, snapshot: MarketSnapshot, skill_context: dict[str, Any] | None = None) -> ResearchPlan:
        base = _base_asset(snapshot.symbol)
        missing = ", ".join(_missing_core_points(snapshot)) or "none"
        queries = [
            ResearchQuery(
                name=f"{base.lower()}_price_context",
                query=f"{snapshot.symbol} {base} perpetual mark price index price latest",
                purpose="当交易所 ticker/mark 数据缺失时，补充价格上下文。",
            ),
            ResearchQuery(
                name=f"{base.lower()}_derivatives_context",
                query=f"{base} perpetual funding open interest liquidation heatmap long short ratio latest",
                purpose="从公开来源补充资金费率、持仓量、清算热图和多空拥挤度。",
            ),
            ResearchQuery(
                name="btc_direction_anchor",
                query="BTC perpetual funding open interest liquidation heatmap latest market structure",
                purpose="在判断 ETH/SOL 前检查 BTC 方向锚和衍生品结构。",
            ),
            ResearchQuery(
                name="macro_context",
                query="crypto market today VIX DXY US Treasury yields ETF flows Bitcoin Ethereum latest",
                purpose="检查可能主导加密方向的宏观、ETF、稳定币和风险偏好因素。",
            ),
        ]
        return ResearchPlan(
            queries=queries[: self.max_queries],
            reason=(
                "交易所原生核心行情缺失、陈旧或不可用；"
                f"missing_core_points={missing}；使用受控 web fallback 作为降级证据。"
            ),
        )


class OpenAICompatibleResearchPlanner:
    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.max_queries = config.research.max_queries
        self.base_url, self.model, self.api_key = _openai_settings(config, "llm research planner")
        self.timeout = config.research.request_timeout_seconds
        self.client = client

    def plan(self, snapshot: MarketSnapshot, skill_context: dict[str, Any] | None = None) -> ResearchPlan:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the leader research planner for a crypto manual-alert system. "
                        "Split missing or stale market evidence into independent web research tasks. "
                        "Return strict JSON only with keys: reason, queries. "
                        "queries must be an array of objects: name, query, purpose, required. "
                        f"{USER_FACING_LANGUAGE_RULE} The reason and purpose fields must be Simplified Chinese. "
                        "Do not make a trading decision and do not place orders."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "skill": _compact_skill_context(skill_context),
                            "market_snapshot": snapshot.to_public_dict(),
                            "missing_core_points": _missing_core_points(snapshot),
                            "max_queries": self.max_queries,
                            "required_domains": [
                                "perp mark/index/order book context",
                                "funding/open interest/crowding",
                                "liquidation heatmap or forced positioning",
                                "BTC direction anchor",
                                "macro/ETF/stablecoin event context",
                            ],
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": 900,
        }
        content = _post_chat_completion(
            self.base_url,
            self.api_key,
            self.timeout,
            payload,
            self.client,
            component="research.plan",
        )
        return _parse_research_plan(content, self.max_queries)


class FallbackResearchPlanner:
    def __init__(self, primary: ResearchPlanner, fallback: ResearchPlanner):
        self.primary = primary
        self.fallback = fallback

    def plan(self, snapshot: MarketSnapshot, skill_context: dict[str, Any] | None = None) -> ResearchPlan:
        try:
            return self.primary.plan(snapshot, skill_context)
        except Exception as exc:  # noqa: BLE001 - Leader 规划失败时必须降级，不能让主流程直接中断。
            plan = self.fallback.plan(snapshot, skill_context)
            return ResearchPlan(
                queries=plan.queries,
                planner=plan.planner,
                reason=f"{plan.reason}；LLM planner 降级原因：{type(exc).__name__}: {exc}",
            )


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
        self.base_url, self.model, self.api_key = _openai_settings(config, "responses_web_search")
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
        try:
            try:
                response = client.post(
                    f"{self.base_url}/v1/responses",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                record_llm_interaction(
                    component="research.web_search",
                    provider="openai_compatible_responses",
                    model=self.model,
                    endpoint="/v1/responses",
                    request_payload=payload,
                    response_payload=data,
                    status="ok",
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


def needs_research_fallback(
    snapshot: MarketSnapshot,
    max_age_seconds: int | None = None,
    candle_max_age_seconds: int | None = None,
) -> bool:
    if _missing_core_points(snapshot):
        return True
    if max_age_seconds is not None and _stale_core_points(snapshot, max_age_seconds, candle_max_age_seconds):
        return True
    unavailable_text = " ".join(snapshot.unavailable).lower()
    return any(token in unavailable_text for token in ("connecttimeout", "timeout", "unavailable"))


class StaticLeaderResearchSynthesizer:
    def synthesize(self, snapshot: MarketSnapshot, audit: ResearchAudit) -> ResearchAudit:
        source_count = sum(len(results) for results in audit.results.values())
        gaps = list(audit.unavailable)
        gaps.extend(f"missing_core:{name}" for name in _missing_core_points(snapshot))
        summary = {
            "leader_finalizer": {
                "summary": f"已为 {snapshot.symbol} 收集 {source_count} 条检索派生证据。",
                "evidence_names": sorted(audit.results),
                "evidence_brief": _evidence_brief(audit),
                "missing_or_failed": gaps,
            },
            "bull_reviewer": {
                "root_cause_chain": "只有当新的交易所 mark/index/order_book 确认触发价后，检索证据才可能支持上行。",
                "confirmation": "OKX 原生执行事实与 BTC 方向锚同时支持多头假设。",
                "weakness": "单靠检索派生上下文不能证明多头具备可执行性。",
            },
            "bear_reviewer": {
                "root_cause_chain": "只有当 BTC 结构、资金费率/OI 和新鲜执行事实同时确认压力后，检索证据才可能支持下行。",
                "confirmation": "OKX mark 跌破失效位，同时 BTC 方向锚走弱。",
                "weakness": "缺少当前拥挤度和清算上下文时做空，容易追到已经衰竭的波动。",
            },
            "data_quality_reviewer": {
                "quality": "检索派生证据属于降级证据；核心事实缺失或陈旧时必须保留置信度上限。",
                "confidence_cap_hint": 0.58,
                "gaps": gaps,
            },
            "execution_risk_reviewer": {
                "risk": "触发价、止损和流动性没有被交易所原生数据验证前，只能阻断或低置信度提醒。",
                "manual_only": True,
            },
        }
        return ResearchAudit(plan=audit.plan, results=audit.results, unavailable=audit.unavailable, leader_summary=summary)


class OpenAICompatibleLeaderResearchSynthesizer:
    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.base_url, self.model, self.api_key = _openai_settings(config, "llm leader synthesizer")
        self.timeout = config.research.request_timeout_seconds
        self.client = client

    def synthesize(self, snapshot: MarketSnapshot, audit: ResearchAudit) -> ResearchAudit:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the leader agent for a crypto manual-alert research workflow. "
                        "Summarize the parallel researcher outputs, identify conflicts and gaps, "
                        "then run adversarial review with exactly these top-level keys: "
                        "leader_finalizer, bull_reviewer, bear_reviewer, data_quality_reviewer, execution_risk_reviewer. "
                        f"{USER_FACING_LANGUAGE_RULE} All summaries, root-cause chains, confirmations, gaps, "
                        "risks, conflicts, and reviewer conclusions must be Simplified Chinese. "
                        "Return strict JSON only. Do not make the final trade decision and do not place orders."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "market_snapshot": snapshot.to_public_dict(),
                            "research_audit": audit.to_public_dict(),
                            "required_review_keys": list(LEADER_REVIEW_KEYS),
                            "review_rules": [
                                "bull_reviewer must state the strongest long root-cause chain and confirmation trigger.",
                                "bear_reviewer must state the strongest short root-cause chain and confirmation trigger.",
                                "data_quality_reviewer must audit freshness, source quality, conflicts, and confidence cap.",
                                "execution_risk_reviewer must audit entry, stop, liquidity, manual-only execution, and hard blocks.",
                            ],
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": 1200,
        }
        content = _post_chat_completion(
            self.base_url,
            self.api_key,
            self.timeout,
            payload,
            self.client,
            component="leader.review",
        )
        summary = _parse_leader_summary(content)
        return ResearchAudit(plan=audit.plan, results=audit.results, unavailable=audit.unavailable, leader_summary=summary)


class FallbackLeaderResearchSynthesizer:
    def __init__(self, primary: LeaderResearchSynthesizer, fallback: LeaderResearchSynthesizer):
        self.primary = primary
        self.fallback = fallback

    def synthesize(self, snapshot: MarketSnapshot, audit: ResearchAudit) -> ResearchAudit:
        try:
            return self.primary.synthesize(snapshot, audit)
        except Exception as exc:  # noqa: BLE001 - Leader 审查失败时保留证据并使用静态审查兜底。
            fallback_audit = self.fallback.synthesize(snapshot, audit)
            summary = dict(fallback_audit.leader_summary)
            finalizer = dict(summary.get("leader_finalizer") or {})
            finalizer["llm_leader_fallback"] = f"{type(exc).__name__}: {exc}"
            summary["leader_finalizer"] = finalizer
            return ResearchAudit(
                plan=audit.plan,
                results=audit.results,
                unavailable=[*audit.unavailable, f"llm_leader_fallback: {type(exc).__name__}: {exc}"],
                leader_summary=summary,
            )


def execute_research(plan: ResearchPlan, adapter: SearchAdapter, max_workers: int = 4) -> ResearchAudit:
    results: dict[str, list[SearchResult]] = {}
    unavailable: list[str] = []
    if not plan.queries:
        return ResearchAudit(plan=plan)
    worker_count = max(1, min(max_workers, len(plan.queries)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_query = {executor.submit(adapter.search, query): query for query in plan.queries}
        for future in as_completed(future_to_query):
            query = future_to_query[future]
            try:
                query_results = future.result()
            except Exception as exc:  # noqa: BLE001 - 搜索降级失败只能进入 unavailable，不能中断主流程。
                unavailable.append(f"{query.name}: {type(exc).__name__}: {exc}")
                continue
            if query_results:
                results[query.name] = query_results
            elif query.required:
                unavailable.append(f"{query.name}: no search results")
    return ResearchAudit(plan=plan, results=dict(sorted(results.items())), unavailable=sorted(unavailable))


def synthesize_search_evidence(snapshot: MarketSnapshot, audit: ResearchAudit) -> MarketSnapshot:
    points = dict(snapshot.points)
    unavailable = list(snapshot.unavailable)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    for name, results in audit.results.items():
        if not results:
            continue
        point_name = f"web_{name}"
        points[point_name] = DataPoint(
            name=point_name,
            value=[result.to_public_dict() for result in results],
            timestamp_ms=now_ms,
            source="search-derived",
        )

    # 搜索结果只能补充上下文，不能冒充 mark/index/order_book 等交易所原生执行事实。
    if any(point not in points for point in ("mark", "index", "order_book")) and SEARCH_CONFIDENCE_CAP not in unavailable:
        unavailable.append(SEARCH_CONFIDENCE_CAP)
    unavailable.extend(audit.unavailable)
    return MarketSnapshot(symbol=snapshot.symbol, fetched_at=snapshot.fetched_at, points=points, unavailable=unavailable)


def build_research_planner(config: Config) -> ResearchPlanner:
    static = StaticResearchPlanner(max_queries=config.research.max_queries)
    if config.research.planner == "llm":
        return FallbackResearchPlanner(OpenAICompatibleResearchPlanner(config), static)
    return static


def build_leader_synthesizer(config: Config) -> LeaderResearchSynthesizer:
    static = StaticLeaderResearchSynthesizer()
    if config.research.leader_mode == "llm":
        return FallbackLeaderResearchSynthesizer(OpenAICompatibleLeaderResearchSynthesizer(config), static)
    return static


def build_search_adapter(config: Config) -> SearchAdapter:
    if config.research.search_provider == "disabled":
        return DisabledSearchAdapter()
    if config.research.search_provider == "fixture":
        return FixtureSearchAdapter({})
    if config.research.search_provider == "duckduckgo_html":
        return DuckDuckGoHtmlSearchAdapter(config)
    if config.research.search_provider == "responses_web_search":
        return ResponsesWebSearchAdapter(config)
    raise ValueError(f"Unsupported research.search_provider: {config.research.search_provider}")


def candle_max_age_seconds(candle_bar: str, stale_seconds: int) -> int:
    return _bar_to_seconds(candle_bar) + stale_seconds


def _base_asset(symbol: str) -> str:
    return symbol.split("-", 1)[0].upper()


def _missing_core_points(snapshot: MarketSnapshot) -> list[str]:
    return [point for point in CORE_MARKET_POINTS if point not in snapshot.points]


def _stale_core_points(
    snapshot: MarketSnapshot,
    max_age_seconds: int,
    candle_max_age_seconds: int | None = None,
) -> list[str]:
    stale: list[str] = []
    for name in CORE_MARKET_POINTS:
        point = snapshot.points.get(name)
        if point is None:
            continue
        threshold = candle_max_age_seconds if name == "candles" and candle_max_age_seconds else max_age_seconds
        age = point.age_seconds(snapshot.fetched_at)
        if age is None or age > threshold:
            stale.append(name)
    return stale


def _bar_to_seconds(candle_bar: str) -> int:
    normalized = candle_bar.strip().upper()
    if normalized.endswith("H"):
        return int(normalized[:-1] or "1") * 3600
    if normalized.endswith("M"):
        return int(normalized[:-1] or "1") * 60
    if normalized.endswith("D"):
        return int(normalized[:-1] or "1") * 86400
    return 3600


def _openai_settings(config: Config, component: str) -> tuple[str, str, str]:
    if not config.decision.openai_base_url:
        raise ValueError(f"decision.openai_base_url is required for {component}")
    if not config.decision.openai_model:
        raise ValueError(f"decision.openai_model is required for {component}")
    api_key = os.getenv(config.decision.openai_api_key_env, "")
    if not api_key:
        raise ValueError(f"{config.decision.openai_api_key_env} is required for {component}")
    return config.decision.openai_base_url.rstrip("/"), config.decision.openai_model, api_key


def _post_chat_completion(
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    payload: dict[str, Any],
    injected_client: httpx.Client | None,
    component: str,
) -> str:
    client = injected_client or httpx.Client(timeout=timeout_seconds)
    close_client = injected_client is None
    try:
        response = client.post(
            f"{base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        record_llm_interaction(
            component=component,
            provider="openai_compatible",
            model=str(payload.get("model") or ""),
            endpoint="/v1/chat/completions",
            request_payload=payload,
            response_payload=data,
            status="ok",
        )
        return str(data["choices"][0]["message"]["content"])
    except Exception as exc:
        record_llm_interaction(
            component=component,
            provider="openai_compatible",
            model=str(payload.get("model") or ""),
            endpoint="/v1/chat/completions",
            request_payload=payload,
            response_payload=None,
            status="error",
            error=exc,
        )
        raise
    finally:
        if close_client:
            client.close()


def _parse_research_plan(content: str, max_queries: int) -> ResearchPlan:
    payload = _json_object(content)
    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list) or not raw_queries:
        raise ValueError("llm research planner must return non-empty queries")
    queries: list[ResearchQuery] = []
    for raw in raw_queries[:max_queries]:
        if not isinstance(raw, dict):
            raise ValueError("llm research query must be an object")
        queries.append(
            ResearchQuery(
                name=str(raw["name"]),
                query=str(raw["query"]),
                purpose=str(raw["purpose"]),
                required=bool(raw.get("required", True)),
            )
        )
    return ResearchPlan(queries=queries, reason=str(payload.get("reason") or "LLM leader 已规划研究任务。"), planner="llm")


def _parse_leader_summary(content: str) -> dict[str, Any]:
    payload = _json_object(content)
    missing = [key for key in LEADER_REVIEW_KEYS if key not in payload]
    if missing:
        raise ValueError(f"llm leader summary missing keys: {', '.join(missing)}")
    return payload


def _json_object(content: str) -> dict[str, Any]:
    payload = json.loads(content.strip())
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")
    return payload


def _compact_skill_context(skill_context: dict[str, Any] | None) -> dict[str, Any]:
    if not skill_context:
        return {}
    references = skill_context.get("references") or {}
    return {
        "name": skill_context.get("name"),
        "sha256": skill_context.get("sha256"),
        "required_references": list(references) if isinstance(references, dict) else skill_context.get("required_references"),
        "rules_hint": "Use crypto-macro-decision live fact gate, derivatives checklist, and no-auto-trading boundary.",
    }


def _evidence_brief(audit: ResearchAudit) -> list[dict[str, str]]:
    brief: list[dict[str, str]] = []
    for name, results in sorted(audit.results.items()):
        for result in results[:3]:
            brief.append({"query": name, "title": result.title, "source": result.source, "snippet": result.snippet[:500]})
    return brief


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
