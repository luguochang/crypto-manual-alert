from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from crypto_manual_alert.skills.facade import RealtimeSearchSkill, SkillTaskContext
from crypto_manual_alert.skills.source_freshness import SourceFreshness
from crypto_manual_alert.skills.tool_budget import ToolBudget
from crypto_manual_alert.skills.tool_call_artifact import ToolCallArtifact


def test_tool_artifact_boundaries_are_exported_from_skills_package():
    import crypto_manual_alert.skills as skills

    assert skills.ToolCallArtifact is ToolCallArtifact
    assert skills.ToolBudget is ToolBudget
    assert skills.SourceFreshness is SourceFreshness


def test_tool_call_artifact_wraps_skill_result_as_ref_hash_and_freshness_only():
    retrieved_at = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
    result = RealtimeSearchSkill().run(
        SkillTaskContext(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            symbol="ETH-USDT-SWAP",
            trace_id="trace-skill",
            query="ETH ETF flow today",
            input_view={
                "search_results": [
                    {
                        "title": "ETH ETF flow",
                        "url": "https://example.test/eth-etf",
                        "snippet_ref": "research.results.eth_etf[0].snippet_redacted",
                        "snippet": "RAW SNIPPET MUST NOT ENTER ARTIFACT",
                    }
                ]
            },
        )
    )

    artifact = ToolCallArtifact.from_skill_result(
        result,
        tool_call_id="tool:trace-skill:RootCauseAgent:realtime_search:1",
        result_ref="skill_result:trace-skill:RootCauseAgent:realtime_search:1",
        retrieved_at=retrieved_at,
        source_tier="search",
        freshness_status="fresh",
    )

    public = artifact.to_public_dict()

    assert public == {
        "tool_call_id": "tool:trace-skill:RootCauseAgent:realtime_search:1",
        "skill_name": "realtime_search",
        "status": "ok",
        "source_type": "search_derived",
        "source_tier": "search",
        "retrieved_at": "2026-07-04T10:00:00+00:00",
        "freshness_status": "fresh",
        "result_ref": "skill_result:trace-skill:RootCauseAgent:realtime_search:1",
        "output_hash": public["output_hash"],
        "can_satisfy_execution_fact": False,
    }
    assert public["output_hash"].startswith("sha256:")
    rendered = json.dumps(public, ensure_ascii=False)
    assert "RAW SNIPPET" not in rendered
    assert "evidence_candidates" not in rendered


def test_tool_call_artifact_rejects_search_derived_execution_fact_claim():
    retrieved_at = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="execution fact"):
        ToolCallArtifact(
            tool_call_id="tool:trace-skill:RootCauseAgent:realtime_search:1",
            skill_name="realtime_search",
            status="ok",
            source_type="search_derived",
            source_tier="search",
            retrieved_at=retrieved_at,
            freshness_status="fresh",
            result_ref="skill_result:trace-skill:RootCauseAgent:realtime_search:1",
            output_hash="sha256:abc",
            can_satisfy_execution_fact=True,
        )


def test_source_freshness_classifies_fresh_stale_and_unknown_inputs():
    now = datetime(2026, 7, 4, 10, 1, tzinfo=timezone.utc)

    assert SourceFreshness(retrieved_at=now - timedelta(seconds=30), now=now, max_age_seconds=60).status == "fresh"
    assert SourceFreshness(retrieved_at=now - timedelta(seconds=90), now=now, max_age_seconds=60).status == "stale"
    assert SourceFreshness(retrieved_at=None, now=now, max_age_seconds=60).status == "unknown"


def test_tool_budget_tracks_per_worker_skill_calls_and_deadline():
    now = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
    budget = ToolBudget(max_calls=1, deadline_at=now + timedelta(seconds=10))

    ticket = budget.reserve(worker_name="RootCauseAgent", skill_name="realtime_search", now=now)

    assert ticket == {
        "worker_name": "RootCauseAgent",
        "skill_name": "realtime_search",
        "remaining_calls": 0,
    }
    with pytest.raises(ValueError, match="budget exceeded"):
        budget.reserve(worker_name="RootCauseAgent", skill_name="root_cause_search", now=now)
    with pytest.raises(ValueError, match="deadline expired"):
        ToolBudget(max_calls=1, deadline_at=now - timedelta(seconds=1)).reserve(
            worker_name="RootCauseAgent",
            skill_name="realtime_search",
            now=now,
        )
