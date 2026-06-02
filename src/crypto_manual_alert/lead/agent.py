from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from crypto_manual_alert.lead.synthesis import LeadSynthesisCandidate, build_lead_synthesis_candidate
from crypto_manual_alert.orchestration.contracts import LeadPlan, SubTask
from crypto_manual_alert.orchestration.harness import HarnessPolicy, load_harness_policy


class LeadPlanError(ValueError):
    """Raised when a requested LeadPlan would violate the harness policy."""


@dataclass(frozen=True)
class LeadAgent:
    """Harness-constrained planner and synthesizer.

    LeadAgent selects worker tasks from a fixed policy and synthesizes their
    contributions. It does not run workers, call tools, write journals, send
    notifications, or decide the final trade action.
    """

    policy: HarnessPolicy = field(default_factory=lambda: load_harness_policy("shadow_audit"))

    def plan_tasks(
        self,
        *,
        symbol: str,
        trace_id: str,
        base_input_view: dict[str, Any] | None = None,
        requested_agents: list[str] | tuple[str, ...] | None = None,
        worker_mode: str = "local_audit",
    ) -> LeadPlan:
        enabled_workers = tuple(
            agent_name
            for agent_name in self.policy.agents
            if agent_name.endswith("Agent") and agent_name != "FinalDecisionAgent"
        )
        selected_agents = tuple(requested_agents or enabled_workers)
        self._validate_selected_agents(selected_agents, enabled_workers)

        input_ref = f"trace:{trace_id}:shadow_swarm_input"
        shared_input_view = {"symbol": symbol, "trace_id": trace_id, **copy.deepcopy(base_input_view or {})}
        tasks = tuple(
            SubTask(
                task_id=f"shadow:{agent_name}",
                agent_name=agent_name,
                role=_role_for_agent(agent_name),
                input_ref=input_ref,
                input_view=copy.deepcopy(shared_input_view),
                required=self.policy.agent_policy(agent_name).required,
                timeout_seconds=self.policy.agent_policy(agent_name).timeout_seconds,
                failure_policy="soft_downgrade",
                trace_ref=f"{trace_id}:shadow:{agent_name}",
                requested_tools=self._requested_tools_for_agent(agent_name, worker_mode=worker_mode),
            )
            for agent_name in selected_agents
        )
        return LeadPlan(
            plan_id=f"shadow:{trace_id}",
            mode="shadow",
            decision_effect="none",
            tasks=tasks,
            max_parallel_workers=self.policy.max_parallel_workers,
            deadline_ms=self.policy.deadline_ms,
            max_tool_calls=self.policy.max_tool_calls,
        )

    def synthesize(
        self,
        lead_plan: LeadPlan,
        *,
        agent_contributions: list[dict[str, Any]],
    ) -> LeadSynthesisCandidate:
        required_agents = tuple(task.agent_name for task in lead_plan.tasks if task.required)
        return build_lead_synthesis_candidate(
            agent_contributions=agent_contributions,
            required_agents=required_agents,
        )

    def _validate_selected_agents(self, selected_agents: tuple[str, ...], enabled_workers: tuple[str, ...]) -> None:
        unknown = [agent_name for agent_name in selected_agents if agent_name not in enabled_workers]
        if unknown:
            raise LeadPlanError(f"worker agent is not enabled by harness: {', '.join(unknown)}")

        required_workers = {
            agent_name
            for agent_name in enabled_workers
            if self.policy.agent_policy(agent_name).required
        }
        missing_required = sorted(required_workers - set(selected_agents))
        if missing_required:
            raise LeadPlanError(f"required worker agents missing: {', '.join(missing_required)}")

    def _requested_tools_for_agent(self, agent_name: str, *, worker_mode: str) -> tuple[str, ...]:
        if worker_mode != "llm_tool_shadow":
            return ()
        return self.policy.agent_policy(agent_name).allowed_tools


def _role_for_agent(agent_name: str) -> str:
    roles = {
        "LiveFactAgent": "live_fact_audit",
        "DerivativesAgent": "derivatives_structure_audit",
        "MacroEventAgent": "macro_event_audit",
        "RootCauseAgent": "root_cause_analysis",
        "MarketSentimentAgent": "market_sentiment_analysis",
        "DataQualityAgent": "data_quality_review",
        "ExecutionRiskAgent": "execution_risk_review",
    }
    return roles.get(agent_name, "worker_analysis")
