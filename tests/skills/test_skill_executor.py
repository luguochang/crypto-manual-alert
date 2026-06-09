from __future__ import annotations

from datetime import datetime, timezone
import json

from crypto_manual_alert.skills.executor import SkillExecutor
from crypto_manual_alert.skills.facade import RealtimeSearchSkill, SkillTaskContext
from crypto_manual_alert.skills.tool_budget import ToolBudget
from crypto_manual_alert.skills.tool_call_artifact import ToolCallArtifact


def test_skill_executor_is_exported_from_skills_package():
    import crypto_manual_alert.skills as skills

    assert skills.SkillExecutor is SkillExecutor


def test_skill_executor_returns_tool_call_artifact_not_raw_skill_result():
    now = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
    executor = SkillExecutor(
        registry={"realtime_search": RealtimeSearchSkill()},
        clock=lambda: now,
    )
    budget = ToolBudget(max_calls=1, deadline_at=now)
    context = SkillTaskContext(
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
                    "snippet": "RAW SNIPPET MUST NOT ENTER WORKER",
                }
            ]
        },
    )

    artifact = executor.execute(
        worker_name="RootCauseAgent",
        context=context,
        budget=budget,
    )

    assert isinstance(artifact, ToolCallArtifact)
    public = artifact.to_public_dict()
    assert public["tool_call_id"] == "tool:trace-skill:RootCauseAgent:realtime_search:1"
    assert public["skill_name"] == "realtime_search"
    assert public["status"] == "ok"
    assert public["source_type"] == "search_derived"
    assert public["source_tier"] == "search"
    assert public["freshness_status"] == "fresh"
    assert public["can_satisfy_execution_fact"] is False
    assert public["result_ref"] == "skill_result:trace-skill:RootCauseAgent:realtime_search:1"
    rendered = json.dumps(public, ensure_ascii=False)
    assert "RAW SNIPPET" not in rendered
    assert "evidence_candidates" not in rendered


def test_skill_executor_rejects_unregistered_skill_before_worker_gets_result():
    now = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
    executor = SkillExecutor(registry={}, clock=lambda: now)

    try:
        executor.execute(
            worker_name="RootCauseAgent",
            context=SkillTaskContext(
                skill_name="realtime_search",
                task_id="skill:realtime_search",
                symbol="ETH-USDT-SWAP",
                trace_id="trace-skill",
                query="ETH ETF flow today",
                input_view={},
            ),
            budget=ToolBudget(max_calls=1, deadline_at=now),
        )
    except ValueError as exc:
        assert "skill is not registered" in str(exc)
    else:
        raise AssertionError("unregistered skill should be rejected")


def test_skill_executor_converts_skill_exception_to_failed_tool_artifact():
    class TimeoutSkill:
        def run(self, _context):
            raise TimeoutError("provider timed out with raw payload that must not leak")

    now = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
    executor = SkillExecutor(registry={"realtime_search": TimeoutSkill()}, clock=lambda: now)

    artifact = executor.execute(
        worker_name="LiveFactAgent",
        context=SkillTaskContext(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            symbol="ETH-USDT-SWAP",
            trace_id="trace-timeout",
            query="ETH ETF flow today",
            input_view={},
        ),
        budget=ToolBudget(max_calls=1, deadline_at=now),
    )

    public = artifact.to_public_dict()
    assert public["status"] == "failed"
    assert public["skill_name"] == "realtime_search"
    assert public["source_type"] == "search_derived"
    assert public["source_tier"] == "search"
    assert public["freshness_status"] == "unknown"
    assert public["can_satisfy_execution_fact"] is False
    assert public["error_type"] == "TimeoutError"
    assert public["error_hash"].startswith("sha256:")
    rendered = json.dumps(public, ensure_ascii=False)
    assert "raw payload" not in rendered
    assert "provider timed out" not in rendered
