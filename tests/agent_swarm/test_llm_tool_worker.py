from __future__ import annotations

import json

import pytest

from crypto_manual_alert.agent_swarm.runtime import AgentRunner
from crypto_manual_alert.orchestration.harness import load_harness_policy, validate_agent_contributions
from crypto_manual_alert.agent_swarm.llm_tool_worker import LlmToolShadowWorker, LlmWorkerOutputError
from crypto_manual_alert.orchestration.contracts import SubTask
from crypto_manual_alert.skills.executor import SkillExecutor
from crypto_manual_alert.skills.facade import RealtimeSearchSkill


class CapturingLlmClient:
    def __init__(self, response: str):
        self.response = response
        self.requests = []
        self.timeouts = []

    def complete(self, payload, *, timeout_seconds=None):
        self.requests.append(payload)
        self.timeouts.append(timeout_seconds)
        return self.response


def _subtask(agent_name: str = "RootCauseAgent", requested_tools: tuple[str, ...] = ("web_search",)) -> SubTask:
    return SubTask(
        task_id=f"shadow:{agent_name}",
        agent_name=agent_name,
        role="root_cause_analysis",
        input_ref="trace:trace-1:shadow_swarm_input",
        input_view={"symbol": "ETH-USDT-SWAP"},
        required=True,
        timeout_seconds=30,
        failure_policy="soft_downgrade",
        trace_ref=f"trace-1:shadow:{agent_name}",
        requested_tools=requested_tools,
    )


def test_llm_tool_shadow_worker_builds_audit_only_contribution():
    client = CapturingLlmClient(
        json.dumps(
            {
                "summary": "ETF flow and funding require confirmation.",
                "claims": [
                    {
                        "claim": "funding crowding is possible",
                        "claim_type": "inference",
                        "side": "neutral",
                        "evidence_ids": ["research.results.macro_context[0]"],
                        "confidence": "low",
                        "freshness": "mixed",
                    }
                ],
                "constraints": {"confidence_cap": 0.58},
                "conflicts": ["search_derived_only"],
                "missing_facts": ["mark", "order_book"],
            }
        )
    )
    subtask = _subtask(requested_tools=("root_cause_search",))

    contribution = LlmToolShadowWorker(client=client).run(subtask, {"symbol": "ETH-USDT-SWAP"})

    assert contribution.agent_name == "RootCauseAgent"
    assert contribution.status == "ok"
    assert contribution.input_ref == "trace:trace-1:shadow_swarm_input"
    assert contribution.trace_ref == "trace-1:shadow:RootCauseAgent"
    assert contribution.output_hash.startswith("sha256:")
    assert contribution.migration_stage == "llm_tool_shadow_worker"
    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["requested_tools"] == ["root_cause_search"]
    assert contribution.constraints["confidence_cap"] == 0.58
    assert contribution.missing_facts == ["mark", "order_book"]
    request_payload = client.requests[0]
    assert client.timeouts == [30]
    assert request_payload["decision_effect"] == "none"
    assert request_payload["agent_name"] == "RootCauseAgent"
    assert "final_action" not in json.dumps(request_payload, ensure_ascii=False)


def test_llm_tool_shadow_worker_does_not_allow_constraints_to_override_decision_effect():
    client = CapturingLlmClient(
        json.dumps(
            {
                "summary": "malicious constraint override rejected",
                "constraints": {"decision_effect": "production_final_input"},
            }
        )
    )

    contribution = LlmToolShadowWorker(client=client).run(_subtask(), {"symbol": "ETH-USDT-SWAP"})

    assert contribution.constraints["decision_effect"] == "none"


def test_llm_tool_shadow_worker_invalid_json_is_wrapped_by_agent_runner():
    client = CapturingLlmClient("not json")
    subtask = _subtask(requested_tools=("root_cause_search",))
    request = subtask.to_agent_run_request(run_id="shadow:trace-1")
    worker = LlmToolShadowWorker(client=client).as_runtime_worker(subtask)

    output = AgentRunner().run_one(request, worker)

    assert output.result.status == "failed"
    assert output.result.error == {
        "type": "LlmWorkerOutputError",
        "message": "LLM worker output must be a JSON object",
    }
    assert output.contribution.status == "failed"
    assert "worker_error:LlmWorkerOutputError" in output.contribution.conflicts


def test_llm_tool_shadow_runtime_worker_uses_agent_run_request_timeout():
    client = CapturingLlmClient(json.dumps({"summary": "runtime timeout checked"}))
    subtask = _subtask(requested_tools=("root_cause_search",))
    request = subtask.to_agent_run_request(run_id="shadow:trace-1")
    request = request.__class__(
        **{
            **request.__dict__,
            "timeout_seconds": 7,
        }
    )

    output = AgentRunner().run_one(request, LlmToolShadowWorker(client=client).as_runtime_worker(subtask))

    assert output.result.status == "ok"
    assert client.timeouts == [7]


def test_llm_tool_shadow_worker_executable_fields_are_caught_by_harness():
    client = CapturingLlmClient(
        json.dumps(
            {
                "summary": "bad worker leaked executable action",
                "claims": [],
                "constraints": {"main_action": "open long"},
                "conflicts": [],
                "missing_facts": [],
            }
        )
    )
    subtask = _subtask(requested_tools=("root_cause_search",))

    contribution = LlmToolShadowWorker(client=client).run(subtask, {"symbol": "ETH-USDT-SWAP"})
    result = validate_agent_contributions([contribution], policy=load_harness_policy("shadow_audit"))

    assert result.passed is False
    assert result.violations == [
        {
            "agent_name": "RootCauseAgent",
            "rule_id": "agent.non_final.executable_fields",
            "fields": ["main_action"],
        }
    ]


def test_llm_tool_shadow_worker_rejects_missing_summary():
    client = CapturingLlmClient(json.dumps({"claims": []}))

    with pytest.raises(LlmWorkerOutputError, match="summary is required"):
        LlmToolShadowWorker(client=client).run(_subtask(), {"symbol": "ETH-USDT-SWAP"})


def test_llm_tool_shadow_worker_rejects_legacy_tool_requests():
    client = CapturingLlmClient(
        json.dumps(
            {
                "summary": "needs search",
                "tool_requests": [
                    {"tool_name": "web_search", "arguments": {"query": "ETH ETF flow today"}}
                ],
            }
        )
    )

    with pytest.raises(LlmWorkerOutputError, match="legacy tool calls are no longer supported"):
        LlmToolShadowWorker(client=client, tool_executor=object(), max_tool_calls=1).run(
            _subtask(requested_tools=("root_cause_search",)),
            {"symbol": "ETH-USDT-SWAP"},
        )

    request_payload = client.requests[0]
    assert "tool_requests" not in request_payload["allowed_output_contract"]["optional_keys"]


def test_llm_tool_shadow_worker_records_skill_executor_artifact_refs_only():
    from datetime import datetime, timezone

    now = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
    client = CapturingLlmClient(
        json.dumps(
            {
                "summary": "search checked through skill executor",
                "claims": [],
                "skill_requests": [
                    {"skill_name": "realtime_search", "arguments": {"query": "ETH ETF flow today"}}
                ],
            }
        )
    )
    executor = SkillExecutor(registry={"realtime_search": RealtimeSearchSkill()}, clock=lambda: now)
    subtask = _subtask(requested_tools=("realtime_search",))

    contribution = LlmToolShadowWorker(client=client, tool_executor=executor, max_tool_calls=1).run(
        subtask,
        {
            "symbol": "ETH-USDT-SWAP",
            "trace_id": "trace-1",
            "search_results": [
                {
                    "title": "ETH ETF flow",
                    "url": "https://example.test/eth-etf",
                    "snippet_ref": "research.results.eth_etf[0].snippet_redacted",
                    "snippet": "RAW SNIPPET MUST NOT ENTER CONTRIBUTION",
                }
            ],
        },
    )

    public = contribution.to_public_dict()
    assert public["tool_call_artifact_refs"] == [
        {
            "tool_call_id": "tool:trace-1:RootCauseAgent:realtime_search:1",
            "skill_name": "realtime_search",
            "status": "ok",
            "source_type": "search_derived",
            "source_tier": "search",
            "retrieved_at": "2026-07-04T10:00:00+00:00",
            "freshness_status": "fresh",
            "result_ref": "skill_result:trace-1:RootCauseAgent:realtime_search:1",
            "output_hash": public["tool_call_artifact_refs"][0]["output_hash"],
            "can_satisfy_execution_fact": False,
        }
    ]
    rendered = json.dumps(public, ensure_ascii=False)
    assert "RAW SNIPPET" not in rendered
    assert "evidence_candidates" not in rendered
    assert "tool_audit_results" not in contribution.constraints


def test_llm_tool_shadow_worker_strips_model_forged_tool_artifacts_from_constraints():
    client = CapturingLlmClient(
        json.dumps(
            {
                "summary": "model tries to forge tool refs",
                "claims": [],
                "constraints": {
                    "tool_call_artifact_refs": [{"raw": "RAW FORGED ARTIFACT"}],
                    "tool_call_artifacts": [{"raw": "RAW FORGED ARTIFACT"}],
                    "tool_audit_results": [{"error_message": "RAW ERROR"}],
                    "requested_tools": ["place_order"],
                    "requested_skills": ["place_order"],
                    "tool_execution_mode": "forged",
                    "decision_effect": "production_final_input",
                },
            }
        )
    )

    contribution = LlmToolShadowWorker(client=client).run(_subtask(requested_tools=()), {"symbol": "ETH-USDT-SWAP"})

    assert contribution.constraints == {
        "requested_tools": [],
        "tool_execution_mode": "disabled",
        "decision_effect": "none",
    }
    rendered = json.dumps(contribution.to_public_dict(), ensure_ascii=False)
    assert "RAW FORGED ARTIFACT" not in rendered
    assert "RAW ERROR" not in rendered


def test_llm_tool_shadow_worker_passes_remaining_deadline_to_each_skill_call():
    now = {"value": 100.0}

    class Artifact:
        def __init__(self, index: int, skill_name: str):
            self.index = index
            self.skill_name = skill_name

        def to_public_dict(self):
            return {
                "tool_call_id": f"tool:trace-1:RootCauseAgent:{self.skill_name}:{self.index}",
                "skill_name": self.skill_name,
                "status": "ok",
                "source_type": "search_derived",
                "source_tier": "search",
                "retrieved_at": "2026-07-04T10:00:00+00:00",
                "freshness_status": "fresh",
                "result_ref": f"skill_result:trace-1:RootCauseAgent:{self.skill_name}:{self.index}",
                "output_hash": f"sha256:skill-{self.index}",
                "can_satisfy_execution_fact": False,
            }

    class SkillExecutor:
        def __init__(self):
            self.calls = []

        def execute(self, *, worker_name, context, budget):
            self.calls.append((worker_name, context.skill_name, context.query, context.timeout_seconds))
            now["value"] += 10.0
            return Artifact(len(self.calls), context.skill_name)

    client = CapturingLlmClient(
        json.dumps(
            {
                "summary": "search checked",
                "skill_requests": [
                    {"skill_name": "root_cause_search", "arguments": {"query": "first"}},
                    {"skill_name": "root_cause_search", "arguments": {"query": "second"}},
                ],
            }
        )
    )
    executor = SkillExecutor()

    contribution = LlmToolShadowWorker(
        client=client,
        tool_executor=executor,
        max_tool_calls=2,
        clock=lambda: now["value"],
    ).run(_subtask(requested_tools=("root_cause_search",)), {"symbol": "ETH-USDT-SWAP"})

    assert executor.calls == [
        ("RootCauseAgent", "root_cause_search", "first", 30),
        ("RootCauseAgent", "root_cause_search", "second", 20),
    ]
    assert [ref["tool_call_id"] for ref in contribution.tool_call_artifact_refs] == [
        "tool:trace-1:RootCauseAgent:root_cause_search:1",
        "tool:trace-1:RootCauseAgent:root_cause_search:2",
    ]
    assert "tool_audit_results" not in contribution.constraints


def test_llm_tool_shadow_worker_rejects_skill_requests_over_budget():
    class NeverCalledSkillExecutor:
        def execute(self, *, worker_name, context, budget):  # pragma: no cover
            raise AssertionError("skill executor should not run when request count exceeds budget")

    client = CapturingLlmClient(
        json.dumps(
            {
                "summary": "too many searches",
                "skill_requests": [
                    {"skill_name": "root_cause_search", "arguments": {"query": "first"}},
                    {"skill_name": "root_cause_search", "arguments": {"query": "second"}},
                ],
            }
        )
    )

    with pytest.raises(LlmWorkerOutputError, match="skill request count exceeds budget"):
        LlmToolShadowWorker(
            client=client,
            tool_executor=NeverCalledSkillExecutor(),
            max_tool_calls=1,
        ).run(_subtask(requested_tools=("root_cause_search",)), {"symbol": "ETH-USDT-SWAP"})


def test_llm_tool_shadow_worker_stops_tool_loop_when_request_deadline_is_spent():
    now = {"value": 100.0}

    class SlowLlmClient(CapturingLlmClient):
        def complete(self, payload, *, timeout_seconds=None):
            now["value"] += 31.0
            return super().complete(payload, timeout_seconds=timeout_seconds)

    class NeverCalledSkillExecutor:
        def execute(self, *, worker_name, context, budget):  # pragma: no cover
            raise AssertionError("tool executor should not be called after deadline expires")

    client = SlowLlmClient(
        json.dumps(
            {
                "summary": "deadline spent",
                "skill_requests": [
                    {"skill_name": "root_cause_search", "arguments": {"query": "late"}},
                ],
            }
        )
    )

    with pytest.raises(LlmWorkerOutputError, match="skill request deadline expired"):
        LlmToolShadowWorker(
            client=client,
            tool_executor=NeverCalledSkillExecutor(),
            max_tool_calls=1,
            clock=lambda: now["value"],
        ).run(_subtask(requested_tools=("root_cause_search",)), {"symbol": "ETH-USDT-SWAP"})


def test_llm_tool_shadow_worker_rejects_non_artifact_skill_executor_result():
    class BadSkillExecutor:
        def execute(self, *, worker_name, context, budget):
            return {"raw_payload": "RAW FAILURE MUST NOT ENTER CONTRIBUTION"}

    client = CapturingLlmClient(
        json.dumps(
            {
                "summary": "search attempted",
                "skill_requests": [{"skill_name": "root_cause_search", "arguments": {"query": "x"}}],
            }
        )
    )

    with pytest.raises(LlmWorkerOutputError, match="skill executor result must be a ToolCallArtifact"):
        LlmToolShadowWorker(client=client, tool_executor=BadSkillExecutor(), max_tool_calls=1).run(
            _subtask(requested_tools=("root_cause_search",)),
            {"symbol": "ETH-USDT-SWAP"},
        )
