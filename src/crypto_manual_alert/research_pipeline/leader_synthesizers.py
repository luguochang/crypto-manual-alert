from __future__ import annotations

import json
from typing import Any

import httpx

from crypto_manual_alert.config import Config
from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.research_pipeline.evidence import missing_core_points as _missing_core_points
from crypto_manual_alert.research_pipeline.llm_support import openai_settings, post_chat_completion
from crypto_manual_alert.research_pipeline.models import ResearchAudit
from crypto_manual_alert.research_pipeline.prompts import LEADER_REVIEW_KEYS, USER_FACING_LANGUAGE_RULE
from crypto_manual_alert.research_pipeline.protocols import LeaderResearchSynthesizer


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
        self.base_url, self.model, self.api_key = openai_settings(config, "llm leader synthesizer")
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
        content = post_chat_completion(
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


def _parse_leader_summary(content: str) -> dict[str, Any]:
    payload = json.loads(content.strip())
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")
    missing = [key for key in LEADER_REVIEW_KEYS if key not in payload]
    if missing:
        raise ValueError(f"llm leader summary missing keys: {', '.join(missing)}")
    return payload


def _evidence_brief(audit: ResearchAudit) -> list[dict[str, str]]:
    brief: list[dict[str, str]] = []
    for name, results in sorted(audit.results.items()):
        for result in results[:3]:
            brief.append({"query": name, "title": result.title, "source": result.source, "snippet": result.snippet[:500]})
    return brief
