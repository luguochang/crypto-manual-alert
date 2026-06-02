from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from crypto_manual_alert.agent_swarm.llm_tool_worker import LlmShadowClient, LlmToolShadowWorker, SkillToolExecutor
from crypto_manual_alert.agent_swarm.shadow_llm_client import build_fixture_shadow_client_factory
from crypto_manual_alert.market_agents.registry import build_local_shadow_workers
from crypto_manual_alert.orchestration.contracts import LeadPlan, WorkerAgent
from crypto_manual_alert.orchestration.harness import HarnessPolicy, load_harness_policy
from crypto_manual_alert.skills.executor import SkillExecutor
from crypto_manual_alert.skills.registry import build_default_skill_registry, build_skill_registry_from_config


class WorkerRegistryConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class WorkerImplementation:
    """One registered worker implementation.

    The registry names worker implementations explicitly. It does not run
    workers, make decisions, or grant tool permissions.
    """

    agent_name: str
    worker: WorkerAgent
    implementation_kind: str = "local_audit"

    def to_public_dict(self) -> dict[str, str]:
        return {
            "agent_name": self.agent_name,
            "implementation_kind": self.implementation_kind,
        }


@dataclass(frozen=True)
class WorkerImplementationRegistry:
    """Worker implementation registry for controlled agent runs.

    This registry is the extension point for future LLM/tool workers. The
    current production path uses only local shadow audit workers with
    decision_effect=none.
    """

    mode: str
    decision_effect: str
    implementations: Mapping[str, WorkerImplementation]

    @property
    def agent_names(self) -> tuple[str, ...]:
        return tuple(self.implementations)

    def worker_map_for_plan(self, lead_plan: LeadPlan) -> dict[str, WorkerAgent]:
        return {
            task.agent_name: self.implementations[task.agent_name].worker
            for task in lead_plan.tasks
            if task.agent_name in self.implementations
        }

    def without(self, agent_name: str) -> "WorkerImplementationRegistry":
        return WorkerImplementationRegistry(
            mode=self.mode,
            decision_effect=self.decision_effect,
            implementations={
                name: implementation
                for name, implementation in self.implementations.items()
                if name != agent_name
            },
        )

    def with_implementation(self, implementation: WorkerImplementation) -> "WorkerImplementationRegistry":
        return WorkerImplementationRegistry(
            mode=self.mode,
            decision_effect=self.decision_effect,
            implementations={**self.implementations, implementation.agent_name: implementation},
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "decision_effect": self.decision_effect,
            "workers": [implementation.to_public_dict() for implementation in self.implementations.values()],
        }


def build_local_shadow_worker_registry() -> WorkerImplementationRegistry:
    workers = build_local_shadow_workers()
    return WorkerImplementationRegistry(
        mode="shadow_audit",
        decision_effect="none",
        implementations={
            agent_name: WorkerImplementation(agent_name, worker)
            for agent_name, worker in workers.items()
        },
    )


def build_shadow_worker_registry(
    config: object | None = None,
    *,
    llm_client_factory: Callable[[str], LlmShadowClient] | None = None,
    tool_executor: SkillToolExecutor | None = None,
) -> WorkerImplementationRegistry:
    worker_mode = str(getattr(getattr(config, "shadow", None), "worker_mode", "local_audit"))
    if worker_mode == "local_audit":
        return build_local_shadow_worker_registry()
    if worker_mode == "llm_tool_shadow":
        if llm_client_factory is not None:
            return build_llm_tool_shadow_worker_registry(
                llm_client_factory,
                tool_executor=tool_executor,
                policy=load_harness_policy("shadow_audit"),
            )
        if str(getattr(getattr(config, "decision", None), "engine", "")) == "fixture":
            return build_llm_tool_shadow_worker_registry(
                build_fixture_shadow_client_factory(),
                tool_executor=tool_executor or SkillExecutor(registry=build_skill_registry_from_config(config)),
                policy=load_harness_policy("shadow_audit"),
            )
        raise WorkerRegistryConfigurationError(
            "shadow.worker_mode=llm_tool_shadow requires an explicit LLM client factory; "
            "fixture decision engine is the only config-only local mode"
        )
    raise WorkerRegistryConfigurationError(f"Unsupported shadow.worker_mode: {worker_mode}")


def build_llm_tool_shadow_worker_registry(
    llm_client_factory: Callable[[str], LlmShadowClient],
    *,
    tool_executor: SkillToolExecutor | None = None,
    policy: HarnessPolicy | None = None,
) -> WorkerImplementationRegistry:
    active_policy = policy or load_harness_policy("shadow_audit")
    active_tool_executor = tool_executor or SkillExecutor(registry=build_default_skill_registry())
    local_workers = build_local_shadow_workers()
    implementations: dict[str, WorkerImplementation] = {
        "LiveFactAgent": WorkerImplementation(
            "LiveFactAgent",
            LlmToolShadowWorker(
                client=llm_client_factory("LiveFactAgent"),
                tool_executor=active_tool_executor,
                max_tool_calls=active_policy.max_tool_calls,
            ),
            implementation_kind="llm_tool_shadow",
        ),
        "DerivativesAgent": WorkerImplementation(
            "DerivativesAgent",
            local_workers["DerivativesAgent"],
            implementation_kind="local_audit",
        ),
        "MacroEventAgent": WorkerImplementation(
            "MacroEventAgent",
            local_workers["MacroEventAgent"],
            implementation_kind="local_audit",
        ),
    }
    implementations.update(
        {
            agent_name: WorkerImplementation(
                agent_name,
                LlmToolShadowWorker(
                    client=llm_client_factory(agent_name),
                    tool_executor=active_tool_executor,
                    max_tool_calls=active_policy.max_tool_calls,
                ),
                implementation_kind="llm_tool_shadow",
            )
            for agent_name in (
                "RootCauseAgent",
                "MarketSentimentAgent",
                "DataQualityAgent",
                "ExecutionRiskAgent",
            )
        }
    )
    return WorkerImplementationRegistry(
        mode="shadow_audit",
        decision_effect="none",
        implementations=implementations,
    )
