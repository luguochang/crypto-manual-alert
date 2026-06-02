from __future__ import annotations

from crypto_manual_alert.agent_swarm.shadow_runner import build_default_lead_plan
from crypto_manual_alert.agent_swarm.registry import (
    WorkerImplementation,
    build_local_shadow_worker_registry,
    build_shadow_worker_registry,
)
from crypto_manual_alert.skills.executor import SkillExecutor


class PlaceholderWorker:
    pass


def test_local_shadow_worker_registry_exposes_named_implementations():
    registry = build_local_shadow_worker_registry()

    assert registry.agent_names == (
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    )
    assert registry.to_public_dict() == {
        "mode": "shadow_audit",
        "decision_effect": "none",
        "workers": [
            {"agent_name": "LiveFactAgent", "implementation_kind": "local_audit"},
            {"agent_name": "DerivativesAgent", "implementation_kind": "local_audit"},
            {"agent_name": "MacroEventAgent", "implementation_kind": "local_audit"},
            {"agent_name": "RootCauseAgent", "implementation_kind": "local_audit"},
            {"agent_name": "MarketSentimentAgent", "implementation_kind": "local_audit"},
            {"agent_name": "DataQualityAgent", "implementation_kind": "local_audit"},
            {"agent_name": "ExecutionRiskAgent", "implementation_kind": "local_audit"},
        ],
    }


def test_local_shadow_worker_registry_builds_worker_map_for_lead_plan():
    registry = build_local_shadow_worker_registry()
    lead_plan = build_default_lead_plan(symbol="ETH-USDT-SWAP", trace_id="trace-1")

    worker_map = registry.worker_map_for_plan(lead_plan)

    assert tuple(worker_map) == tuple(task.agent_name for task in lead_plan.tasks)


def test_local_shadow_worker_registry_can_omit_missing_implementations_for_shadow_audit():
    registry = build_local_shadow_worker_registry().without("MarketSentimentAgent")
    lead_plan = build_default_lead_plan(symbol="ETH-USDT-SWAP", trace_id="trace-1")

    worker_map = registry.worker_map_for_plan(lead_plan)

    assert "RootCauseAgent" in worker_map
    assert "MarketSentimentAgent" not in worker_map


def test_worker_registry_accepts_explicit_llm_tool_adapter_registration():
    registry = build_local_shadow_worker_registry().with_implementation(
        WorkerImplementation(
            agent_name="RootCauseAgent",
            worker=PlaceholderWorker(),
            implementation_kind="llm_tool_shadow",
        )
    )

    by_agent = {
        item["agent_name"]: item
        for item in registry.to_public_dict()["workers"]
    }
    assert by_agent["RootCauseAgent"] == {
        "agent_name": "RootCauseAgent",
        "implementation_kind": "llm_tool_shadow",
    }


def test_shadow_worker_registry_defaults_to_local_audit_from_config():
    class ShadowConfig:
        worker_mode = "local_audit"

    class Config:
        shadow = ShadowConfig()

    registry = build_shadow_worker_registry(Config())

    assert {item["implementation_kind"] for item in registry.to_public_dict()["workers"]} == {"local_audit"}


def test_shadow_worker_registry_registers_llm_tool_workers_with_explicit_client_factory():
    class ShadowConfig:
        worker_mode = "llm_tool_shadow"

    class Config:
        shadow = ShadowConfig()

    class Client:
        def __init__(self, agent_name: str):
            self.agent_name = agent_name

        def complete(self, payload):
            return '{"summary":"shadow llm audit"}'

    created_clients: list[str] = []

    def client_factory(agent_name: str):
        created_clients.append(agent_name)
        return Client(agent_name)

    registry = build_shadow_worker_registry(Config(), llm_client_factory=client_factory)

    assert registry.decision_effect == "none"
    assert registry.agent_names == (
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    )
    assert created_clients == [
        "LiveFactAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    ]
    assert {item["implementation_kind"] for item in registry.to_public_dict()["workers"]} == {
        "local_audit",
        "llm_tool_shadow",
    }


def test_shadow_worker_registry_injects_explicit_tool_executor_into_llm_tool_workers():
    class ShadowConfig:
        worker_mode = "llm_tool_shadow"

    class Config:
        shadow = ShadowConfig()

    class Client:
        def complete(self, payload):
            return '{"summary":"shadow llm audit"}'

    class ToolExecutor:
        pass

    tool_executor = ToolExecutor()

    registry = build_shadow_worker_registry(
        Config(),
        llm_client_factory=lambda _agent_name: Client(),
        tool_executor=tool_executor,
    )

    assert {
        implementation.worker.tool_executor
        for implementation in registry.implementations.values()
        if implementation.implementation_kind == "llm_tool_shadow"
    } == {tool_executor}


def test_shadow_worker_registry_defaults_llm_tool_workers_to_skill_executor():
    class ShadowConfig:
        worker_mode = "llm_tool_shadow"

    class Config:
        shadow = ShadowConfig()

    class Client:
        def complete(self, payload):
            return '{"summary":"shadow llm audit"}'

    registry = build_shadow_worker_registry(
        Config(),
        llm_client_factory=lambda _agent_name: Client(),
    )

    executors = [
        implementation.worker.tool_executor
        for implementation in registry.implementations.values()
        if implementation.implementation_kind == "llm_tool_shadow"
    ]
    assert len(executors) == 5
    assert all(executor is executors[0] for executor in executors)
    assert isinstance(executors[0], SkillExecutor)
