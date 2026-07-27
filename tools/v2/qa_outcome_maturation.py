"""Mature one existing local QA Artifact through the real OKX provider."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.config import get_settings
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    OutcomeObservation,
    Task,
)
from crypto_alert_v2.providers.okx import OkxProvider
from crypto_alert_v2.workers.memory_outcome import OutcomeMaturationWorker


async def main() -> None:
    settings = get_settings()
    if settings.product_database_url is None:
        raise RuntimeError("PRODUCT_DATABASE_URL is not configured")
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        row = (
            await session.execute(
                select(ArtifactVersion, Artifact, Task)
                .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
                .join(Task, Task.id == ArtifactVersion.task_id)
                .where(
                    Artifact.artifact_type == "analysis_report",
                    ArtifactVersion.status == "committed",
                )
                .order_by(ArtifactVersion.created_at.desc())
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError("no committed analysis Artifact exists")
        version, _, task = row
        analysis = version.content["analysis"]
        horizon = str(analysis.get("horizon") or task.request_payload["horizon"])
        observation = await session.scalar(
            select(OutcomeObservation).where(
                OutcomeObservation.artifact_version_id == version.id,
                OutcomeObservation.horizon == horizon,
            )
        )
        if observation is None:
            observation = OutcomeObservation(
                id=uuid4(),
                tenant_id=version.tenant_id,
                workspace_id=version.workspace_id,
                owner_user_id=version.owner_user_id,
                artifact_version_id=version.id,
                task_id=version.task_id,
                run_id=version.run_id,
                action=analysis["main_action"],
                baseline="decision",
                predicted_probability=analysis.get("probability"),
                horizon=horizon,
                source="exchange_native",
                maturation_at=now - timedelta(seconds=1),
                available_at=now - timedelta(seconds=1),
            )
            session.add(observation)
        else:
            observation.status = "scheduled"
            observation.maturation_at = now - timedelta(seconds=1)
            observation.available_at = now - timedelta(seconds=1)
            observation.lease_owner = None
            observation.lease_expires_at = None

    with OkxProvider(proxy=settings.market_data_http_proxy) as provider:
        worker = OutcomeMaturationWorker(
            session_factory=factory,
            provider=provider,
            worker_id="qa-outcome-worker",
        )
        processed = await worker.dispatch_once()

    async with factory() as session:
        result = await session.scalar(
            select(OutcomeObservation).where(OutcomeObservation.id == observation.id)
        )
        if result is None:
            raise RuntimeError("outcome observation disappeared")
        print(
            json.dumps(
                {
                    "processed": processed,
                    "status": result.status,
                    "source": result.source,
                    "source_hash_present": bool(result.source_hash),
                    "observed_at_present": result.observed_at is not None,
                    "metric_keys": sorted((result.metrics or {}).keys()),
                },
                sort_keys=True,
            )
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
