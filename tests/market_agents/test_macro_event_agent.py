from __future__ import annotations

from crypto_manual_alert.orchestration.contracts import SubTask
from crypto_manual_alert.orchestration.harness import load_harness_policy, validate_agent_contributions


def test_macro_event_agent_reports_active_event_and_macro_surprise_without_final_action():
    from crypto_manual_alert.market_agents.macro_event import MacroEventAgent

    contribution = MacroEventAgent().run(_task(), _input_view())

    assert contribution.agent_name == "MacroEventAgent"
    assert contribution.status == "ok"
    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["event_status"] == {
        "status": "active_market_reaction",
        "refreshed_at": "2026-07-02T12:33:00+00:00",
        "source": "event_pool",
        "point_status": "ok",
    }
    assert contribution.constraints["macro_event"] == {
        "event_name": "US June NFP",
        "consensus": "180k",
        "actual": "145k",
        "surprise": "cooler_than_expected",
        "market_reaction": {"dxy": "down", "yields": "down", "btc": "up"},
        "released_at": "2026-07-02T12:30:00+00:00",
        "source": "official",
        "point_status": "ok",
    }
    assert contribution.constraints["surprise"] == "cooler_than_expected"
    assert contribution.constraints["market_reaction"] == {"dxy": "down", "yields": "down", "btc": "up"}
    assert contribution.constraints["event_compression"] == "active_macro_event"
    assert contribution.constraints["missing_event_facts"] == []
    assert contribution.constraints["missing_macro_facts"] == []
    assert contribution.constraints["blocked_action_classes"] == []
    assert contribution.constraints["required_confirmations"] == []
    assert contribution.missing_facts == []
    assert all(claim["side"] == "neutral" for claim in contribution.claims)

    public = contribution.to_public_dict()
    assert public["task_id"] == "shadow:MacroEventAgent"
    assert public["input_ref"] == "trace:trace-macro:shadow_swarm_input"
    assert public["output_hash"].startswith("sha256:")
    assert public["trace_ref"] == "trace-macro:shadow:MacroEventAgent"
    assert public["evidence_ids"] == [
        "snapshot.points.active_event_status",
        "snapshot.points.macro_event",
    ]
    assert "main_action" not in public
    assert "entry" not in public
    assert "stop" not in public
    assert "target" not in public
    assert "leverage" not in public
    assert "position_size" not in public
    assert "risk_verdict" not in public

    validation = validate_agent_contributions([contribution], policy=load_harness_policy("shadow_audit"))
    assert validation.passed is True


def test_macro_event_agent_caps_confidence_when_macro_surprise_is_incomplete():
    from crypto_manual_alert.market_agents.macro_event import MacroEventAgent

    input_view = _input_view()
    macro_value = input_view["snapshot"]["points"]["macro_event"]["value"]
    assert isinstance(macro_value, dict)
    macro_value.pop("market_reaction")

    contribution = MacroEventAgent().run(_task(), input_view)

    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["event_compression"] == "macro_surprise_incomplete"
    assert contribution.constraints["missing_macro_facts"] == ["macro_event.market_reaction"]
    assert contribution.constraints["confidence_cap"] == 0.58
    assert "facts_gate:macro_surprise_incomplete" in contribution.constraints["confidence_cap_reasons"]
    assert contribution.constraints["required_confirmations"] == ["confirm macro_event.market_reaction"]
    assert contribution.missing_facts == ["macro_event.market_reaction"]
    assert "missing_macro_fact:macro_event.market_reaction" in contribution.conflicts
    assert "main_action" not in contribution.to_public_dict()


def test_macro_event_agent_propagates_event_status_hard_block():
    from crypto_manual_alert.market_agents.macro_event import MacroEventAgent

    input_view = _input_view()
    points = input_view["snapshot"]["points"]
    assert isinstance(points, dict)
    points.pop("active_event_status")
    input_view["facts_gate"] = {
        "passed": False,
        "severity": "hard_fail",
        "missing_event_facts": ["active_event_status"],
        "blocked_action_classes": ["opening", "trigger", "flip"],
        "confidence_cap": 0.55,
        "confidence_cap_reasons": ["facts_gate:event_status_stale"],
    }

    contribution = MacroEventAgent().run(_task(), input_view)

    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["event_status"] == {}
    assert contribution.constraints["event_compression"] == "event_status_missing"
    assert contribution.constraints["missing_event_facts"] == ["active_event_status"]
    assert contribution.constraints["blocked_action_classes"] == ["opening", "trigger", "flip"]
    assert contribution.constraints["confidence_cap"] == 0.55
    assert contribution.constraints["confidence_cap_reasons"] == ["facts_gate:event_status_stale"]
    assert contribution.constraints["required_confirmations"] == ["confirm active_event_status"]
    assert contribution.missing_facts == ["active_event_status"]
    assert "missing_event_fact:active_event_status" in contribution.conflicts


def test_market_agent_registry_includes_macro_event_agent_after_derivatives_agent():
    from crypto_manual_alert.market_agents.macro_event import MacroEventAgent
    from crypto_manual_alert.market_agents.registry import build_local_shadow_workers

    workers = build_local_shadow_workers()

    assert tuple(workers)[:3] == ("LiveFactAgent", "DerivativesAgent", "MacroEventAgent")
    assert type(workers["MacroEventAgent"]) is MacroEventAgent


def _task() -> SubTask:
    return SubTask(
        task_id="shadow:MacroEventAgent",
        agent_name="MacroEventAgent",
        role="macro_event_audit",
        input_ref="trace:trace-macro:shadow_swarm_input",
        input_view={"symbol": "ETH-USDT-SWAP", "trace_id": "trace-macro"},
        required=True,
        timeout_seconds=10,
        failure_policy="soft_downgrade",
        trace_ref="trace-macro:shadow:MacroEventAgent",
    )


def _input_view() -> dict[str, object]:
    return {
        "symbol": "ETH-USDT-SWAP",
        "trace_id": "trace-macro",
        "snapshot": {
            "points": {
                "active_event_status": {
                    "source": "event_pool_refreshed",
                    "status": "ok",
                    "value": {
                        "status": "active_market_reaction",
                        "refreshed_at": "2026-07-02T12:33:00+00:00",
                    },
                },
                "macro_event": {
                    "source": "bls_official",
                    "status": "ok",
                    "value": {
                        "event_name": "US June NFP",
                        "consensus": "180k",
                        "actual": "145k",
                        "surprise": "cooler_than_expected",
                        "market_reaction": {"dxy": "down", "yields": "down", "btc": "up"},
                        "released_at": "2026-07-02T12:30:00+00:00",
                    },
                },
            },
        },
        "facts_gate": {
            "passed": True,
            "missing_event_facts": [],
            "missing_macro_facts": [],
            "blocked_action_classes": [],
        },
    }
