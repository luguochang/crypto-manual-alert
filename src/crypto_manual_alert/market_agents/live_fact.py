from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.orchestration.contracts import SubTask

from .common import claim, contribution, data_freshness, mapping, missing_execution_facts, point_source, source_type


CORE_EXECUTION_FACTS = ("mark", "index", "order_book")


class LiveFactAgent:
    def run(self, subtask: SubTask, input_view: dict[str, Any]) -> AgentContribution:
        snapshot = mapping(input_view.get("snapshot"))
        facts_gate = mapping(input_view.get("facts_gate"))
        points = mapping(snapshot.get("points"))
        missing_facts = missing_execution_facts(input_view)
        coverage = {name: name in points and name not in missing_facts for name in CORE_EXECUTION_FACTS}
        source_tiers = {name: source_type(point_source(points, name)) for name in CORE_EXECUTION_FACTS}
        freshness = data_freshness(points)
        claims = [
            claim(
                f"core fact {name} coverage={str(coverage[name]).lower()} source={source_tiers[name]}",
                f"snapshot.points.{name}",
                "neutral",
            )
            for name in CORE_EXECUTION_FACTS
        ]
        constraints = {
            "decision_effect": "none",
            "core_fact_coverage": coverage,
            "source_tiers": source_tiers,
            "freshness": freshness,
            "blocked_action_classes": list(facts_gate.get("blocked_action_classes") or []),
            "required_confirmations": [f"confirm {name}" for name in missing_facts],
        }
        conflicts = [f"missing_execution_fact:{name}" for name in missing_facts]
        return contribution(
            subtask,
            status="ok",
            summary=f"live fact audit missing={','.join(missing_facts) or 'none'}",
            claims=claims,
            constraints=constraints,
            conflicts=conflicts,
            missing_facts=missing_facts,
        )
