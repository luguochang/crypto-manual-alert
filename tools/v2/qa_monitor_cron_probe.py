"""Probe one local QA Monitor Cron command through the official SDK adapter."""

from __future__ import annotations

import asyncio
import json

from langgraph_sdk import get_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.auth.worker_authorization import (
    create_agent_server_authorization_provider,
)
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.monitors.agent_server_cron import AgentServerCronAdapter
from crypto_alert_v2.persistence.models import MonitorCronCommand
from crypto_alert_v2.workers.monitor import MonitorCronWorker


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    adapter = AgentServerCronAdapter(
        client=get_client(url=settings.agent_server_url),
        assistant_id=settings.agent_assistant_id,
        authorization_provider=create_agent_server_authorization_provider(settings),
        include_end_time=settings.app_environment in {"staging", "production"},
    )
    worker = MonitorCronWorker(
        session_factory=factory,
        adapter=adapter,
        worker_id="qa-cron-probe",
    )
    async with factory() as session:
        command = await session.scalar(
            select(MonitorCronCommand)
            .where(MonitorCronCommand.status.in_(("pending", "failed")))
            .order_by(MonitorCronCommand.created_at.desc())
            .limit(1)
        )
    if command is None:
        raise RuntimeError("no pending Monitor Cron command")
    context = await worker._load_context(command)
    try:
        remote = await worker._apply_remote(context)
        result = {"ok": True, "cron_id_present": bool(remote.cron_id)}
    except Exception as exc:
        result = {
            "ok": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    print(json.dumps(result, sort_keys=True))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
