from __future__ import annotations

import json
from typing import Any

import httpx

from crypto_manual_alert.config import Config
from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.research_pipeline.evidence import (
    missing_core_points as _missing_core_points,
)
from crypto_manual_alert.research_pipeline.llm_support import openai_settings as _openai_settings
from crypto_manual_alert.research_pipeline.llm_support import post_chat_completion
from crypto_manual_alert.research_pipeline.models import ResearchPlan, ResearchQuery
from crypto_manual_alert.research_pipeline.prompts import USER_FACING_LANGUAGE_RULE
from crypto_manual_alert.research_pipeline.protocols import ResearchPlanner
from crypto_manual_alert.research_pipeline.redaction import redact_snippets_for_prompt


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
        content = post_chat_completion(
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


def _base_asset(symbol: str) -> str:
    return symbol.split("-", 1)[0].upper()


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


_redact_snippets_for_prompt = redact_snippets_for_prompt
