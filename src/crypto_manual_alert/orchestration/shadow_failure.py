from __future__ import annotations

from crypto_manual_alert.lead.agent import LeadAgent
from crypto_manual_alert.orchestration.harness import load_harness_policy


def failed_shadow_swarm_audit(
    exc: Exception,
    *,
    symbol: str = "UNKNOWN",
    trace_id: str = "shadow_failure",
    worker_mode: str = "local_audit",
) -> dict[str, object]:
    policy = load_harness_policy("shadow_audit")
    lead_agent = LeadAgent(policy=policy)
    lead_plan = lead_agent.plan_tasks(
        symbol=symbol,
        trace_id=trace_id,
        worker_mode=worker_mode,
        base_input_view={"shadow_error": type(exc).__name__},
    )
    failed_contribution = {
        "contribution_id": "shadow_swarm:shadow_swarm_audit",
        "agent_name": "shadow_swarm_audit",
        "status": "failed",
        "required": True,
        "summary": f"{type(exc).__name__}: {exc}",
        "claims": [],
        "constraints": {"decision_effect": "none"},
        "conflicts": ["shadow_swarm.audit_failed"],
        "missing_facts": ["shadow_swarm_audit"],
        "input_ref": f"trace:{trace_id}:shadow_swarm_failure",
        "output_hash": None,
        "failure_policy_applied": "hard_block",
        "trace_ref": f"{trace_id}:shadow_swarm_audit",
        "migration_stage": "shadow_swarm_audit_failure",
    }
    return {
        "mode": "shadow",
        "decision_effect": "none",
        "lead_plan": lead_plan.to_public_dict(),
        "worker_count": 0,
        "failed_workers": ["shadow_swarm_audit"],
        "worker_results": [],
        "lead_synthesis": lead_agent.synthesize(
            lead_plan,
            agent_contributions=[failed_contribution],
        ).to_public_dict(),
        "harness_validation": {
            "passed": False,
            "severity": "hard_fail",
            "violations": [
                {
                    "agent_name": "shadow_swarm_audit",
                    "rule_id": "shadow_swarm.audit_failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            ],
        },
    }
