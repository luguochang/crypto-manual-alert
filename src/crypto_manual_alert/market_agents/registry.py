from __future__ import annotations

from crypto_manual_alert.orchestration.contracts import WorkerAgent

from .data_quality import DataQualityLocalWorker
from .derivatives import DerivativesAgent
from .execution_risk import ExecutionRiskLocalWorker
from .live_fact import LiveFactAgent
from .macro_event import MacroEventAgent
from .root_cause import RootCauseLocalWorker
from .sentiment_crowding import SentimentCrowdingLocalWorker


def build_local_shadow_workers() -> dict[str, WorkerAgent]:
    """Build audit-only market workers for shadow swarm."""

    return {
        "LiveFactAgent": LiveFactAgent(),
        "DerivativesAgent": DerivativesAgent(),
        "MacroEventAgent": MacroEventAgent(),
        "RootCauseAgent": RootCauseLocalWorker(),
        "MarketSentimentAgent": SentimentCrowdingLocalWorker(),
        "DataQualityAgent": DataQualityLocalWorker(),
        "ExecutionRiskAgent": ExecutionRiskLocalWorker(),
    }
