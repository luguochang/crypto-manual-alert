from __future__ import annotations

import logging
from typing import Any, Callable

from crypto_manual_alert.agent_swarm.llm_tool_worker import LlmShadowClient, SkillToolExecutor
from crypto_manual_alert.agent_swarm.registry import build_shadow_worker_registry
from crypto_manual_alert.agent_swarm.shadow_inputs import build_shadow_audit_payload, build_shadow_worker_input_view
from crypto_manual_alert.agent_swarm.shadow_runner import ShadowSwarmRunner
from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.lead.agent import LeadAgent
from crypto_manual_alert.orchestration.shadow_failure import failed_shadow_swarm_audit
from crypto_manual_alert.orchestration.harness import load_harness_policy
from crypto_manual_alert.research_pipeline import ResearchAudit
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder


logger = logging.getLogger(__name__)


def run_shadow_swarm_audit(
    *,
    symbol: str,
    trace_id: str,
    recorder: ObservabilityRecorder,
    snapshot: MarketSnapshot | None,
    research_audit: ResearchAudit | None,
    config: object | None = None,
    llm_client_factory: Callable[[str], LlmShadowClient] | None = None,
    tool_executor: SkillToolExecutor | None = None,
    audit_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run shadow worker orchestration and return an audit-only payload.

    The payload has no production decision effect. Any orchestration failure is
    normalized into the same audit envelope so callers do not need their own
    shadow failure handling.
    """

    try:
        return _run_shadow_swarm_audit(
            symbol=symbol,
            trace_id=trace_id,
            recorder=recorder,
            snapshot=snapshot,
            research_audit=research_audit,
            config=config,
            llm_client_factory=llm_client_factory,
            tool_executor=tool_executor,
            audit_payload=audit_payload,
        )
    except Exception as exc:  # noqa: BLE001 - shadow audit must not alter the production decision.
        logger.exception("shadow swarm audit failed")
        worker_mode = str(getattr(getattr(config, "shadow", None), "worker_mode", "local_audit"))
        return failed_shadow_swarm_audit(
            exc,
            symbol=symbol,
            trace_id=trace_id,
            worker_mode=worker_mode,
        )


def _run_shadow_swarm_audit(
    *,
    symbol: str,
    trace_id: str,
    recorder: ObservabilityRecorder,
    snapshot: MarketSnapshot | None,
    research_audit: ResearchAudit | None,
    config: object | None = None,
    llm_client_factory: Callable[[str], LlmShadowClient] | None = None,
    tool_executor: SkillToolExecutor | None = None,
    audit_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit_payload = build_shadow_audit_payload(
        trace_id=trace_id,
        snapshot=snapshot,
        research_audit=research_audit,
        audit_payload=audit_payload,
    )
    policy = load_harness_policy("shadow_audit")
    lead_agent = LeadAgent(policy=policy)
    worker_mode = str(getattr(getattr(config, "shadow", None), "worker_mode", "local_audit"))
    lead_plan = lead_agent.plan_tasks(
        symbol=symbol,
        trace_id=trace_id,
        worker_mode=worker_mode,
        base_input_view=build_shadow_worker_input_view(
            snapshot=snapshot,
            research_audit=research_audit,
            audit_payload=audit_payload,
        ),
    )
    worker_registry = build_shadow_worker_registry(
        config,
        llm_client_factory=llm_client_factory,
        tool_executor=tool_executor,
    )
    shadow_audit = ShadowSwarmRunner(
        workers=worker_registry.worker_map_for_plan(lead_plan),
        recorder=recorder,
        trace_id=trace_id,
    ).run(lead_plan)
    payload = shadow_audit.to_public_dict()
    payload["lead_synthesis"] = lead_agent.synthesize(
        lead_plan,
        agent_contributions=[result.contribution.to_public_dict() for result in shadow_audit.worker_results],
    ).to_public_dict()
    return payload
