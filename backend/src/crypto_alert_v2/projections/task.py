from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from crypto_alert_v2.domain.models import MarketSnapshot
from crypto_alert_v2.persistence.repositories import TaskRunSourceRecords
from crypto_alert_v2.providers.search import WebEvidence


class TaskRunSourcesProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    market_snapshot: MarketSnapshot | None = None
    web_evidence: list[WebEvidence] = Field(default_factory=list)


def project_task_run_sources(
    records: TaskRunSourceRecords,
) -> TaskRunSourcesProjection:
    return TaskRunSourcesProjection(
        market_snapshot=records.market_snapshot,
        web_evidence=list(records.web_evidence),
    )
