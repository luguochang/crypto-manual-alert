from __future__ import annotations

import json
from datetime import datetime, timezone

from crypto_manual_alert.decision.final_prompt import build_legacy_final_prompt_packet
from crypto_manual_alert.domain import DataPoint, MarketSnapshot
from crypto_manual_alert.research_pipeline import ResearchAudit, ResearchPlan, ResearchQuery, SearchResult


class StubSkillRuntime:
    def build_prompt_packet(self, snapshot, context=None):
        return {
            "market_snapshot": snapshot.to_public_dict(),
            "skill": {"name": "crypto-macro-decision"},
        }


def test_legacy_final_prompt_packet_redacts_research_snippets_from_research_and_snapshot():
    raw_snippet = "raw search body must not enter final prompt"
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime.now(timezone.utc),
        points={
            "web_eth_price_context": DataPoint(
                name="web_eth_price_context",
                value=[
                    {
                        "title": "ETH context",
                        "url": "https://example.test/eth",
                        "snippet": raw_snippet,
                        "source": "search-derived",
                    }
                ],
                timestamp_ms=1,
                source="search-derived",
            )
        },
        unavailable=[],
    )
    research_audit = ResearchAudit(
        plan=ResearchPlan(
            queries=[ResearchQuery(name="eth_price_context", query="eth", purpose="test")],
            reason="test",
        ),
        results={
            "eth_price_context": [
                SearchResult(
                    title="ETH context",
                    url="https://example.test/eth",
                    snippet=raw_snippet,
                )
            ]
        },
        leader_summary={
            "leader_finalizer": {
                "evidence_brief": [{"snippet": raw_snippet}],
            }
        },
    )

    packet = build_legacy_final_prompt_packet(
        skill_runtime=StubSkillRuntime(),
        snapshot=snapshot,
        skill_context=None,
        research_audit=research_audit,
    )

    rendered = json.dumps(packet, ensure_ascii=False)
    assert raw_snippet not in rendered
    assert packet["research"]["results"]["eth_price_context"][0] == {
        "title": "ETH context",
        "url": "https://example.test/eth",
        "source": "search-derived",
        "snippet_ref": "research.results.eth_price_context[0].snippet_redacted",
    }
    assert packet["research"]["leader_summary"]["leader_finalizer"]["evidence_brief"] == [
        {"snippet": "research.leader_summary.leader_finalizer.evidence_brief[0].snippet.redacted"}
    ]
    assert packet["market_snapshot"]["points"]["web_eth_price_context"]["value"] == [
        {
            "title": "ETH context",
            "url": "https://example.test/eth",
            "source": "search-derived",
            "snippet_ref": "market_snapshot.points.web_eth_price_context[0].snippet_redacted",
        }
    ]
