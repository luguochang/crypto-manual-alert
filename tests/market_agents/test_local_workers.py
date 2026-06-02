from __future__ import annotations

from crypto_manual_alert.orchestration.contracts import SubTask


def test_compat_worker_classes_are_same_objects_as_market_agent_classes():
    from crypto_manual_alert.agent_swarm.local_workers.data_quality import (
        DataQualityLocalWorker as CompatDataQualityLocalWorker,
    )
    from crypto_manual_alert.agent_swarm.local_workers.execution_risk import (
        ExecutionRiskLocalWorker as CompatExecutionRiskLocalWorker,
    )
    from crypto_manual_alert.agent_swarm.local_workers.market_sentiment import (
        MarketSentimentLocalWorker as CompatMarketSentimentLocalWorker,
        SentimentCrowdingLocalWorker as CompatSentimentCrowdingLocalWorker,
    )
    from crypto_manual_alert.agent_swarm.local_workers.root_cause import (
        RootCauseLocalWorker as CompatRootCauseLocalWorker,
    )
    from crypto_manual_alert.market_agents.data_quality import DataQualityLocalWorker
    from crypto_manual_alert.market_agents.execution_risk import ExecutionRiskLocalWorker
    from crypto_manual_alert.market_agents.root_cause import RootCauseLocalWorker
    from crypto_manual_alert.market_agents.sentiment_crowding import (
        MarketSentimentLocalWorker,
        SentimentCrowdingLocalWorker,
    )

    assert CompatRootCauseLocalWorker is RootCauseLocalWorker
    assert CompatDataQualityLocalWorker is DataQualityLocalWorker
    assert CompatExecutionRiskLocalWorker is ExecutionRiskLocalWorker
    assert CompatMarketSentimentLocalWorker is SentimentCrowdingLocalWorker
    assert CompatSentimentCrowdingLocalWorker is SentimentCrowdingLocalWorker
    assert MarketSentimentLocalWorker is SentimentCrowdingLocalWorker
    assert SentimentCrowdingLocalWorker.__name__ == "SentimentCrowdingLocalWorker"


def test_local_workers_package_exports_sentiment_crowding_compat_alias():
    import crypto_manual_alert.agent_swarm.local_workers as compat_package

    assert compat_package.SentimentCrowdingLocalWorker.__name__ == "SentimentCrowdingLocalWorker"
    assert compat_package.MarketSentimentLocalWorker is compat_package.SentimentCrowdingLocalWorker


def test_compat_common_helpers_are_same_objects_as_market_agent_helpers():
    import crypto_manual_alert.agent_swarm.local_workers.common as compat_common
    import crypto_manual_alert.market_agents.common as market_common

    helper_names = (
        "claim",
        "contribution",
        "data_freshness",
        "execution_hard_block",
        "hash_payload",
        "mapping",
        "missing_execution_facts",
        "point_source",
        "required_confirmations",
        "research_snippets",
        "research_titles",
    )

    for helper_name in helper_names:
        assert getattr(compat_common, helper_name) is getattr(market_common, helper_name)


def test_compat_registry_builder_is_same_object_as_market_agent_builder():
    from crypto_manual_alert.agent_swarm.local_workers.registry import (
        build_local_shadow_workers as compat_build_local_shadow_workers,
    )
    from crypto_manual_alert.market_agents.registry import build_local_shadow_workers

    assert compat_build_local_shadow_workers is build_local_shadow_workers


def test_compat_and_market_registry_build_equivalent_worker_maps():
    from crypto_manual_alert.agent_swarm.local_workers.registry import (
        build_local_shadow_workers as compat_build_local_shadow_workers,
    )
    from crypto_manual_alert.market_agents.data_quality import DataQualityLocalWorker
    from crypto_manual_alert.market_agents.derivatives import DerivativesAgent
    from crypto_manual_alert.market_agents.execution_risk import ExecutionRiskLocalWorker
    from crypto_manual_alert.market_agents.live_fact import LiveFactAgent
    from crypto_manual_alert.market_agents.macro_event import MacroEventAgent
    from crypto_manual_alert.market_agents.registry import build_local_shadow_workers
    from crypto_manual_alert.market_agents.root_cause import RootCauseLocalWorker
    from crypto_manual_alert.market_agents.sentiment_crowding import SentimentCrowdingLocalWorker

    compat_workers = compat_build_local_shadow_workers()
    market_workers = build_local_shadow_workers()

    assert tuple(compat_workers) == tuple(market_workers) == (
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    )
    assert {name: type(worker) for name, worker in compat_workers.items()} == {
        name: type(worker) for name, worker in market_workers.items()
    } == {
        "LiveFactAgent": LiveFactAgent,
        "DerivativesAgent": DerivativesAgent,
        "MacroEventAgent": MacroEventAgent,
        "RootCauseAgent": RootCauseLocalWorker,
        "MarketSentimentAgent": SentimentCrowdingLocalWorker,
        "DataQualityAgent": DataQualityLocalWorker,
        "ExecutionRiskAgent": ExecutionRiskLocalWorker,
    }


def test_compat_and_market_worker_paths_emit_equivalent_outputs():
    from crypto_manual_alert.agent_swarm.local_workers.data_quality import (
        DataQualityLocalWorker as CompatDataQualityLocalWorker,
    )
    from crypto_manual_alert.agent_swarm.local_workers.execution_risk import (
        ExecutionRiskLocalWorker as CompatExecutionRiskLocalWorker,
    )
    from crypto_manual_alert.agent_swarm.local_workers.market_sentiment import (
        MarketSentimentLocalWorker as CompatMarketSentimentLocalWorker,
    )
    from crypto_manual_alert.agent_swarm.local_workers.root_cause import (
        RootCauseLocalWorker as CompatRootCauseLocalWorker,
    )
    from crypto_manual_alert.market_agents.data_quality import DataQualityLocalWorker
    from crypto_manual_alert.market_agents.execution_risk import ExecutionRiskLocalWorker
    from crypto_manual_alert.market_agents.root_cause import RootCauseLocalWorker
    from crypto_manual_alert.market_agents.sentiment_crowding import SentimentCrowdingLocalWorker

    cases = [
        ("RootCauseAgent", CompatRootCauseLocalWorker(), RootCauseLocalWorker()),
        ("MarketSentimentAgent", CompatMarketSentimentLocalWorker(), SentimentCrowdingLocalWorker()),
        ("DataQualityAgent", CompatDataQualityLocalWorker(), DataQualityLocalWorker()),
        ("ExecutionRiskAgent", CompatExecutionRiskLocalWorker(), ExecutionRiskLocalWorker()),
    ]

    for agent_name, compat_worker, market_worker in cases:
        task = _task(agent_name)

        assert compat_worker.run(task, _input_view()).to_public_dict() == market_worker.run(
            task, _input_view()
        ).to_public_dict()


def test_market_agent_registry_uses_canonical_sentiment_crowding_worker():
    from crypto_manual_alert.market_agents.registry import build_local_shadow_workers
    from crypto_manual_alert.market_agents.sentiment_crowding import SentimentCrowdingLocalWorker

    workers = build_local_shadow_workers()

    assert type(workers["MarketSentimentAgent"]) is SentimentCrowdingLocalWorker
    assert type(workers["MarketSentimentAgent"]).__name__ == "SentimentCrowdingLocalWorker"


def _task(agent_name: str) -> SubTask:
    return SubTask(
        task_id=f"shadow:{agent_name}",
        agent_name=agent_name,
        role="audit",
        input_ref="trace:trace-4c:shadow_swarm_input",
        input_view={"symbol": "ETH-USDT-SWAP", "trace_id": "trace-4c"},
        required=True,
        timeout_seconds=10,
        failure_policy="soft_downgrade",
        trace_ref=f"trace-4c:shadow:{agent_name}",
    )


def _input_view() -> dict[str, object]:
    return {
        "symbol": "ETH-USDT-SWAP",
        "trace_id": "trace-4c",
        "snapshot": {
            "unavailable": ["order_book: ConnectTimeout"],
            "points": {
                "mark": {"source": "okx_public", "status": "ok", "value": 3500},
                "index": {"source": "okx_public", "status": "ok", "value": 3498},
            },
        },
        "research": {
            "results": {
                "macro_context": [
                    {
                        "title": "ETF inflow surprise",
                        "snippet": "ETH sentiment improved after ETF inflows.",
                        "source": "fixture-search",
                    }
                ],
                "derivatives_context": [
                    {
                        "title": "Funding turns hot",
                        "snippet": "Funding and leverage show crowded longs.",
                        "source": "fixture-search",
                    }
                ],
            }
        },
        "facts_gate": {
            "passed": False,
            "missing_execution_facts": ["order_book"],
            "blocked_action_classes": ["opening", "trigger", "flip"],
            "severity": "hard_fail",
        },
    }
