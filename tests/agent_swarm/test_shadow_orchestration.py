from __future__ import annotations

from dataclasses import replace

from crypto_manual_alert.config import load_config
from crypto_manual_alert.domain import DataPoint, MarketSnapshot
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder
from crypto_manual_alert.research_pipeline import ResearchAudit, ResearchPlan, SearchResult
from crypto_manual_alert.agent_swarm.shadow_orchestration import run_shadow_swarm_audit


def test_run_shadow_swarm_audit_builds_lead_plan_and_worker_results(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")

    audit = run_shadow_swarm_audit(
        symbol="ETH-USDT-SWAP",
        trace_id=trace_id,
        recorder=recorder,
        snapshot=None,
        research_audit=None,
    )

    assert audit["mode"] == "shadow"
    assert audit["decision_effect"] == "none"
    assert audit["worker_count"] == 7
    assert audit["failed_workers"] == []
    assert [task["agent_name"] for task in audit["lead_plan"]["tasks"]] == [
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    ]
    assert {result["status"] for result in audit["worker_results"]} <= {"ok", "partial"}
    assert audit["harness_validation"]["passed"] is True
    assert audit["lead_synthesis"]["decision_effect"] == "none"
    assert audit["lead_synthesis"]["included_contribution_ids"] == [
        result["contribution"]["contribution_id"] for result in audit["worker_results"]
    ]


def test_run_shadow_swarm_audit_returns_failed_payload_when_runner_crashes(tmp_path, monkeypatch):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")

    class ExplodingRunner:
        def __init__(self, **kwargs):
            pass

        def run(self, lead_plan):
            raise RuntimeError("worker pool crashed")

    monkeypatch.setattr("crypto_manual_alert.orchestration.shadow_audit.ShadowSwarmRunner", ExplodingRunner)

    audit = run_shadow_swarm_audit(
        symbol="ETH-USDT-SWAP",
        trace_id=trace_id,
        recorder=recorder,
        snapshot=None,
        research_audit=None,
    )

    assert audit["mode"] == "shadow"
    assert audit["decision_effect"] == "none"
    assert audit["worker_count"] == 0
    assert audit["failed_workers"] == ["shadow_swarm_audit"]
    assert audit["worker_results"] == []
    assert [task["agent_name"] for task in audit["lead_plan"]["tasks"]] == [
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    ]
    assert audit["lead_synthesis"]["decision_effect"] == "none"
    assert audit["lead_synthesis"]["included_contribution_ids"] == []
    assert {
        (item["agent_name"], item["reason"])
        for item in audit["lead_synthesis"]["dropped_contributions"]
    } == {
        ("shadow_swarm_audit", "status=failed"),
        ("LiveFactAgent", "missing_required_contribution"),
        ("DerivativesAgent", "missing_required_contribution"),
        ("MacroEventAgent", "missing_required_contribution"),
        ("RootCauseAgent", "missing_required_contribution"),
        ("MarketSentimentAgent", "missing_required_contribution"),
        ("DataQualityAgent", "missing_required_contribution"),
        ("ExecutionRiskAgent", "missing_required_contribution"),
    }
    assert "shadow_swarm.audit_failed" in audit["lead_synthesis"]["conflicts"]
    assert set(audit["lead_synthesis"]["missing_facts"]) == {
        "shadow_swarm_audit",
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    }
    assert audit["harness_validation"] == {
            "passed": False,
            "severity": "hard_fail",
            "violations": [
                {
                    "agent_name": "shadow_swarm_audit",
                    "rule_id": "shadow_swarm.audit_failed",
                    "error_type": "RuntimeError",
                    "error_message": "worker pool crashed",
                }
            ],
    }


def test_run_shadow_swarm_audit_returns_failed_payload_when_llm_worker_mode_has_no_client(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    config = load_config("config/default.yaml")
    shadow = config.shadow.__class__(worker_mode="llm_tool_shadow")
    # Non-fixture decision engine + no explicit LLM client factory => registry must
    # fail closed (fixture engine is the only config-only local fallback). This
    # preserves the test intent: llm_tool_shadow misconfiguration must not silently
    # fall back to a real client.
    decision = replace(config.decision, engine="openai_compatible")
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=decision,
        notification=config.notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
        shadow=shadow,
    )

    audit = run_shadow_swarm_audit(
        symbol="ETH-USDT-SWAP",
        trace_id=trace_id,
        recorder=recorder,
        snapshot=None,
        research_audit=None,
        config=config,
    )

    assert audit["mode"] == "shadow"
    assert audit["decision_effect"] == "none"
    assert audit["failed_workers"] == ["shadow_swarm_audit"]
    assert audit["harness_validation"]["violations"][0]["error_type"] == "WorkerRegistryConfigurationError"
    assert {
        task["agent_name"]: task["requested_tools"]
        for task in audit["lead_plan"]["tasks"]
    } == {
        "LiveFactAgent": ["realtime_search"],
        "DerivativesAgent": [],
        "MacroEventAgent": ["macro_event"],
        "RootCauseAgent": ["root_cause_search"],
        "MarketSentimentAgent": ["market_sentiment"],
        "DataQualityAgent": [],
        "ExecutionRiskAgent": ["liquidity_order_book"],
    }


def test_run_shadow_swarm_audit_runs_llm_tool_workers_with_explicit_client_factory(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    config = load_config("config/default.yaml")
    shadow = config.shadow.__class__(worker_mode="llm_tool_shadow")
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=config.notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
        shadow=shadow,
    )
    requested_agents: list[str] = []

    class Client:
        def __init__(self, agent_name: str):
            self.agent_name = agent_name

        def complete(self, payload, *, timeout_seconds=None):
            requested_agents.append(payload["agent_name"])
            return '{"summary":"shadow llm audit","claims":[],"constraints":{},"conflicts":[],"missing_facts":[]}'

    audit = run_shadow_swarm_audit(
        symbol="ETH-USDT-SWAP",
        trace_id=trace_id,
        recorder=recorder,
        snapshot=None,
        research_audit=None,
        config=config,
        llm_client_factory=lambda agent_name: Client(agent_name),
    )

    assert audit["mode"] == "shadow"
    assert audit["decision_effect"] == "none"
    assert audit["worker_count"] == 7
    assert audit["failed_workers"] == []
    # LiveFactAgent now uses the LLM tool shadow worker (not local_audit), so the
    # explicit client factory is invoked for it too. DerivativesAgent and
    # MacroEventAgent remain local_audit and never call the LLM client.
    assert set(requested_agents) == {
        "LiveFactAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    }
    by_agent = {
        result["agent_name"]: result["contribution"]["migration_stage"]
        for result in audit["worker_results"]
    }
    assert by_agent["DerivativesAgent"] == "shadow_swarm"
    assert by_agent["MacroEventAgent"] == "shadow_swarm"
    assert {
        stage for agent_name, stage in by_agent.items() if agent_name not in {
            "DerivativesAgent",
            "MacroEventAgent",
        }
    } == {"llm_tool_shadow_worker"}


def test_run_shadow_swarm_audit_uses_safe_worker_input_without_raw_search_snippets(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        points={
            "web_macro_context": DataPoint(
                name="web_macro_context",
                value=[
                    {
                        "title": "Macro source",
                        "url": "https://example.test/macro",
                        "snippet": "RAW SEARCH SNIPPET MUST NOT REACH WORKER",
                        "source": "fixture-search",
                    }
                ],
                timestamp_ms=None,
                source="search-derived",
            )
        },
    )
    research_audit = ResearchAudit(
        plan=ResearchPlan(queries=[], reason="fixture"),
        results={
            "macro_context": [
                SearchResult(
                    title="Macro source",
                    url="https://example.test/macro",
                    snippet="RAW SEARCH SNIPPET MUST NOT REACH WORKER",
                    source="fixture-search",
                )
            ]
        },
    )
    captured_payloads: list[dict[str, object]] = []
    config = load_config("config/default.yaml")
    shadow = config.shadow.__class__(worker_mode="llm_tool_shadow")
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=config.notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
        shadow=shadow,
    )

    class Client:
        def complete(self, payload, *, timeout_seconds=None):
            captured_payloads.append(payload)
            return '{"summary":"shadow llm audit","claims":[],"constraints":{},"conflicts":[],"missing_facts":[]}'

    audit = run_shadow_swarm_audit(
        symbol="ETH-USDT-SWAP",
        trace_id=trace_id,
        recorder=recorder,
        snapshot=snapshot,
        research_audit=research_audit,
        config=config,
        llm_client_factory=lambda _agent_name: Client(),
    )

    assert audit["failed_workers"] == []
    rendered = __import__("json").dumps(captured_payloads[0]["input_view"], ensure_ascii=False)
    assert "RAW SEARCH SNIPPET MUST NOT REACH WORKER" not in rendered
    assert "snippet_ref" in rendered


def test_run_shadow_swarm_audit_records_skill_executor_artifacts_with_explicit_executor(tmp_path):
    from datetime import datetime, timezone

    from crypto_manual_alert.skills.executor import SkillExecutor
    from crypto_manual_alert.skills.registry import build_default_skill_registry

    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    config = load_config("config/default.yaml")
    shadow = config.shadow.__class__(worker_mode="llm_tool_shadow")
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=config.notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
        shadow=shadow,
    )

    class Client:
        def complete(self, payload, *, timeout_seconds=None):
            if payload["agent_name"] == "RootCauseAgent":
                assert payload["requested_tools"] == ["root_cause_search"]
                return __import__("json").dumps(
                    {
                        "summary": "root cause checked with skill executor",
                        "skill_requests": [
                            {
                                "skill_name": "root_cause_search",
                                "arguments": {"query": "ETH ETF flow today"},
                            }
                        ],
                    }
                )
            return '{"summary":"shadow llm audit","claims":[],"constraints":{},"conflicts":[],"missing_facts":[]}'

    now = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
    tool_executor = SkillExecutor(registry=build_default_skill_registry(), clock=lambda: now)

    audit = run_shadow_swarm_audit(
        symbol="ETH-USDT-SWAP",
        trace_id=trace_id,
        recorder=recorder,
        snapshot=None,
        research_audit=None,
        config=config,
        llm_client_factory=lambda _agent_name: Client(),
        tool_executor=tool_executor,
    )

    by_agent = {
        result["agent_name"]: result
        for result in audit["worker_results"]
    }

    assert audit["decision_effect"] == "none"
    assert audit["failed_workers"] == []
    assert by_agent["RootCauseAgent"]["contribution"]["tool_call_artifact_refs"] == [
        {
            "tool_call_id": f"tool:{trace_id}:RootCauseAgent:root_cause_search:1",
            "skill_name": "root_cause_search",
            "status": "ok",
            "source_type": "search_derived",
            "source_tier": "search",
            "retrieved_at": "2026-07-04T10:00:00+00:00",
            "freshness_status": "fresh",
            "result_ref": f"skill_result:{trace_id}:RootCauseAgent:root_cause_search:1",
            "output_hash": by_agent["RootCauseAgent"]["contribution"]["tool_call_artifact_refs"][0]["output_hash"],
            "can_satisfy_execution_fact": False,
        }
    ]
    assert "tool_audit_results" not in by_agent["RootCauseAgent"]["contribution"]["constraints"]
