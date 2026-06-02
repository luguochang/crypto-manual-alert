from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.contributions import from_leader_summary
from crypto_manual_alert.artifacts.evidence import check_execution_facts, from_market_snapshot, from_research_audit
from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.orchestration.harness import validate_agent_contributions
from crypto_manual_alert.research_pipeline import ResearchAudit


def build_audit_artifacts(
    *,
    trace_id: str,
    snapshot: MarketSnapshot | None,
    research_audit: ResearchAudit | None,
) -> dict[str, Any]:
    """Build structured pre-decision artifacts for gates and agent inputs.

    This module normalizes evidence, facts, legacy reviewer contributions, and
    harness validation. It does not run workers, call LLMs, write context, or
    decide a final trade action.
    """

    evidence_packets = from_market_snapshot(snapshot) if snapshot else []
    if snapshot and research_audit:
        evidence_packets.extend(from_research_audit(snapshot.symbol, research_audit))
    facts_gate = check_execution_facts(evidence_packets)
    leader_summary = research_audit.leader_summary if research_audit else {}
    agent_contributions = (
        from_leader_summary(leader_summary, input_ref=f"trace:{trace_id}:leader_summary", trace_ref=trace_id)
        if leader_summary
        else []
    )
    harness_validation = validate_agent_contributions(agent_contributions)
    return {
        "evidence_packets": [packet.to_public_dict() for packet in evidence_packets],
        "facts_gate": facts_gate.to_public_dict(),
        "harness_validation": harness_validation.to_public_dict(),
        "agent_contributions": [contribution.to_public_dict() for contribution in agent_contributions],
    }
