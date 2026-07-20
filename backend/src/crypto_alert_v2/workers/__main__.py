from __future__ import annotations

import argparse
import asyncio
from uuid import uuid4

import httpx
from langgraph_sdk import get_client
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2 import __version__
from crypto_alert_v2.api.agent_server import AgentServerRunner
from crypto_alert_v2.commands.dispatcher import CommandDispatcher
from crypto_alert_v2.auth.worker_authorization import (
    create_agent_server_authorization_provider,
)
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.notifications.credentials import (
    notification_credential_cipher_from_environment,
)
from crypto_alert_v2.monitors.agent_server_cron import AgentServerCronAdapter
from crypto_alert_v2.notifications.resolver import DatabaseNotificationAdapterResolver
from crypto_alert_v2.observability.callbacks import (
    initialize_langfuse_client,
    initialize_langsmith_client,
)
from crypto_alert_v2.observability.config import runtime_config_from_settings
from crypto_alert_v2.observability.planning import (
    plan_observability_delivery_intents,
)
from crypto_alert_v2.observability.tenant_policy import resolve_tenant_policy
from crypto_alert_v2.observability.verification import create_official_verifier
from crypto_alert_v2.projections.reconciler import ProductProjectionReconciler
from crypto_alert_v2.projections.domain_events import DomainEventProjectionWorker
from crypto_alert_v2.testing.failure_injection import (
    failure_injection_from_settings,
    install_database_failure_injection,
)
from crypto_alert_v2.workers.notification import OutboxWorker
from crypto_alert_v2.workers.lifecycle import LifecycleWorker
from crypto_alert_v2.workers.monitor import MonitorCronWorker
from crypto_alert_v2.workers.observability import (
    ObservabilityVerificationWorker,
    SqlAlchemyObservabilityVerificationStore,
)
from crypto_alert_v2.workers.runtime import WorkerRuntime


class _CommandWorkerAdapter:
    def __init__(self, dispatcher: CommandDispatcher) -> None:
        self._dispatcher = dispatcher

    async def dispatch_once(self) -> bool:
        return await self._dispatcher.dispatch_once()

    async def release_owned_leases(self) -> None:
        await self._dispatcher.release_owned_leases()


async def _run_default(
    *,
    worker_id: str,
    once: bool,
    poll_interval: float,
    shutdown_budget_seconds: float,
) -> None:
    settings = get_settings()
    observability_runtime = runtime_config_from_settings(
        settings,
        release=__version__,
    )
    failure_injection = failure_injection_from_settings(settings)
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    remove_database_failure_injection = install_database_failure_injection(
        engine,
        failure_injection,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    http_client = httpx.AsyncClient(timeout=8.0)
    langsmith_client = None
    langfuse_client = None
    try:
        credential_cipher = notification_credential_cipher_from_environment()
        if (
            settings.app_environment in {"staging", "production"}
            and credential_cipher is None
        ):
            raise ValueError(
                "NOTIFICATION_CREDENTIAL_KEY is required in staging and production"
            )
        adapter_resolver = (
            DatabaseNotificationAdapterResolver(
                session_factory=session_factory,
                credential_cipher=credential_cipher,
                http_client=http_client,
                failure_injection=failure_injection,
            )
            if credential_cipher is not None
            else None
        )
        agent_client = get_client(url=settings.agent_server_url)
        authorization_provider = create_agent_server_authorization_provider(settings)
        runner = AgentServerRunner(
            client=agent_client,
            assistant_id=settings.agent_assistant_id,
            authorization_provider=authorization_provider,
        )
        command_dispatcher = CommandDispatcher(
            session_factory=session_factory,
            runner=runner,
            worker_id=f"{worker_id}:command",
            observability_intent_planner=lambda **kwargs: (
                plan_observability_delivery_intents(
                    runtime=observability_runtime,
                    verification_deadline_seconds=(
                        settings.observability_verification_deadline_seconds
                    ),
                    **kwargs,
                )
            ),
        )
        notification_worker = OutboxWorker(
            session_factory=session_factory,
            adapters={},
            adapter_resolver=adapter_resolver,
            worker_id=f"{worker_id}:notification",
        )
        monitor_cron_worker = MonitorCronWorker(
            session_factory=session_factory,
            adapter=AgentServerCronAdapter(
                client=agent_client,
                assistant_id=settings.agent_assistant_id,
                authorization_provider=authorization_provider,
                include_end_time=settings.app_environment in {"staging", "production"},
            ),
            worker_id=f"{worker_id}:monitor-cron",
            lease_seconds=settings.monitor_cron_lease_seconds,
            retry_seconds=settings.monitor_cron_retry_seconds,
            max_attempts=settings.monitor_cron_max_attempts,
        )
        projection_reconciler = ProductProjectionReconciler(
            session_factory=session_factory,
            runner=runner,
            worker_id=f"{worker_id}:projection",
        )
        domain_event_worker = DomainEventProjectionWorker(
            session_factory=session_factory,
        )
        hosted_verifiers = {}
        if observability_runtime.langsmith_enabled:
            langsmith_client = initialize_langsmith_client(
                observability_runtime,
                resolve_tenant_policy({}),
            )
            hosted_verifiers["langsmith"] = create_official_verifier(
                "langsmith",
                langsmith_client,
            )
        if observability_runtime.langfuse_enabled:
            langfuse_client = initialize_langfuse_client(observability_runtime)
            hosted_verifiers["langfuse"] = create_official_verifier(
                "langfuse",
                langfuse_client,
            )
        observability_worker = ObservabilityVerificationWorker(
            store=SqlAlchemyObservabilityVerificationStore(session_factory),
            verifiers=hosted_verifiers,
            worker_id=f"{worker_id}:observability",
            langsmith_project=observability_runtime.langsmith_project,
            lease_seconds=settings.observability_verification_lease_seconds,
            retry_seconds=settings.observability_verification_retry_seconds,
            max_attempts=settings.observability_verification_max_attempts,
        )
        lifecycle_worker = LifecycleWorker(
            session_factory=session_factory,
            worker_id=f"{worker_id}:lifecycle",
        )
        runtime_options = {
            "poll_interval": poll_interval,
            "shutdown_budget_seconds": shutdown_budget_seconds,
            "readiness_failure_threshold": (
                settings.worker_readiness_failure_threshold
            ),
            "readiness_stale_after_seconds": (
                settings.worker_readiness_stale_after_seconds
            ),
        }
        if hasattr(settings, "worker_health_host") and hasattr(
            settings, "worker_health_port"
        ):
            runtime_options.update(
                {
                    "health_host": settings.worker_health_host,
                    "health_port": settings.worker_health_port,
                }
            )
        runtime = WorkerRuntime(
            workers={
                "projections": projection_reconciler,
                "domain_events": domain_event_worker,
                "commands": _CommandWorkerAdapter(command_dispatcher),
                "notifications": notification_worker,
                "monitor_crons": monitor_cron_worker,
                "observability": observability_worker,
                "lifecycle": lifecycle_worker,
            },
            **runtime_options,
        )
        if once:
            await runtime.run_once()
            return
        stop_event = asyncio.Event()
        runtime.install_signal_handlers(stop_event)
        await runtime.run(stop_event=stop_event)
    finally:
        remove_database_failure_injection()
        if langsmith_client is not None:
            await asyncio.to_thread(langsmith_client.close, timeout=2.0)
        if langfuse_client is not None:
            await asyncio.to_thread(langfuse_client.shutdown)
        await http_client.aclose()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run durable Product worker loops")
    parser.add_argument("--worker-id", default=f"worker-{uuid4().hex[:12]}")
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--shutdown-budget-seconds", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        _run_default(
            worker_id=args.worker_id,
            once=args.once,
            poll_interval=args.poll_interval,
            shutdown_budget_seconds=args.shutdown_budget_seconds,
        )
    )


if __name__ == "__main__":
    main()


__all__ = ["main"]
