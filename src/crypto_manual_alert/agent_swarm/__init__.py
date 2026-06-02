"""Controlled agent-swarm building blocks.

This package contains audit-only worker orchestration primitives. Production
decision execution remains in the legacy workflow until the release gates allow
a separate manual switch review.
"""

from typing import Any

__all__ = [
    "AgentPoolTask",
    "AgentRunRequest",
    "AgentRunResult",
    "AgentRunner",
    "ControlledAgentPoolRunner",
    "LeadPlan",
    "ShadowSwarmAudit",
    "ShadowSwarmRunner",
    "SubTask",
    "WorkerAgent",
    "WorkerResult",
    "build_default_lead_plan",
]

_EXPORT_MODULES = {
    "AgentPoolTask": "crypto_manual_alert.agent_swarm.pool_runner",
    "AgentRunRequest": "crypto_manual_alert.orchestration.runtime",
    "AgentRunResult": "crypto_manual_alert.orchestration.runtime",
    "AgentRunner": "crypto_manual_alert.agent_swarm.runtime",
    "ControlledAgentPoolRunner": "crypto_manual_alert.agent_swarm.pool_runner",
    "LeadPlan": "crypto_manual_alert.orchestration.contracts",
    "ShadowSwarmAudit": "crypto_manual_alert.orchestration.contracts",
    "ShadowSwarmRunner": "crypto_manual_alert.agent_swarm.shadow_runner",
    "SubTask": "crypto_manual_alert.orchestration.contracts",
    "WorkerAgent": "crypto_manual_alert.orchestration.contracts",
    "WorkerResult": "crypto_manual_alert.orchestration.contracts",
    "build_default_lead_plan": "crypto_manual_alert.lead.default_plan",
}

_SUBMODULES = {
    "contracts",
    "default_lead_plan",
    "harness",
    "local_workers",
    "llm_tool_worker",
    "pool_runner",
    "registry",
    "runtime",
    "shadow_llm_client",
    "shadow_orchestration",
    "shadow_runner",
    "tool_executor",
    "workers",
}


def __getattr__(name: str) -> Any:
    import importlib

    if name in _SUBMODULES:
        return importlib.import_module(f"{__name__}.{name}")
    if name not in _EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(_EXPORT_MODULES[name])
    return getattr(module, name)
