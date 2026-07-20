from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import crypto_alert_v2.workers.__main__ as worker_main


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class FakeHttpClient:
    def __init__(self, **kwargs: Any) -> None:
        del kwargs
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeRunner:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class FakeDispatcher:
    instances: list["FakeDispatcher"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.instances.append(self)

    async def dispatch_once(self) -> bool:
        return False

    async def release_owned_leases(self) -> None:
        return None


class FakeNotificationWorker:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class FakeMonitorCronAdapter:
    instances: list["FakeMonitorCronAdapter"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.instances.append(self)


class FakeMonitorCronWorker:
    instances: list["FakeMonitorCronWorker"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.instances.append(self)


class FakeLifecycleWorker:
    instances: list["FakeLifecycleWorker"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.instances.append(self)


class FakeProjectionReconciler:
    instances: list["FakeProjectionReconciler"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.instances.append(self)


class FakeDomainEventWorker:
    instances: list["FakeDomainEventWorker"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.instances.append(self)


class FakeRuntime:
    instances: list["FakeRuntime"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.run_once_calls = 0
        self.instances.append(self)

    async def run_once(self) -> dict[str, bool]:
        self.run_once_calls += 1
        return {name: False for name in self.kwargs["workers"]}


@pytest.mark.asyncio
async def test_projection_reconciler_shares_one_runtime_and_agent_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    http_client = FakeHttpClient()
    session_factory = object()
    agent_client = object()
    authorization_provider = object()
    FakeDispatcher.instances.clear()
    FakeProjectionReconciler.instances.clear()
    FakeDomainEventWorker.instances.clear()
    FakeMonitorCronAdapter.instances.clear()
    FakeMonitorCronWorker.instances.clear()
    FakeLifecycleWorker.instances.clear()
    FakeRuntime.instances.clear()
    monkeypatch.setattr(
        worker_main,
        "get_settings",
        lambda: SimpleNamespace(
            product_database_url="postgresql+asyncpg://unused",
            agent_server_url="http://agent-server.test",
            agent_assistant_id="crypto-analysis",
            app_environment="test",
            langsmith_tracing=False,
            langsmith_api_key=None,
            langsmith_project="crypto-alert-v2-test",
            langfuse_enabled=False,
            langfuse_public_key=None,
            langfuse_secret_key=None,
            langfuse_host=None,
            observability_verification_lease_seconds=30,
            observability_verification_deadline_seconds=3_600,
            observability_verification_retry_seconds=5.0,
            observability_verification_max_attempts=30,
            monitor_cron_lease_seconds=90,
            monitor_cron_retry_seconds=7.5,
            monitor_cron_max_attempts=12,
            worker_health_host="127.0.0.1",
            worker_health_port=9090,
            worker_readiness_failure_threshold=4,
            worker_readiness_stale_after_seconds=45.0,
        ),
    )
    monkeypatch.setattr(
        worker_main, "create_async_engine", lambda *args, **kwargs: engine
    )
    monkeypatch.setattr(
        worker_main,
        "async_sessionmaker",
        lambda *args, **kwargs: session_factory,
    )
    monkeypatch.setattr(worker_main.httpx, "AsyncClient", lambda **kwargs: http_client)
    monkeypatch.setattr(
        worker_main,
        "notification_credential_cipher_from_environment",
        lambda: None,
    )
    monkeypatch.setattr(worker_main, "get_client", lambda **kwargs: agent_client)
    monkeypatch.setattr(
        worker_main,
        "create_agent_server_authorization_provider",
        lambda settings: authorization_provider,
    )
    monkeypatch.setattr(worker_main, "AgentServerRunner", FakeRunner)
    monkeypatch.setattr(worker_main, "CommandDispatcher", FakeDispatcher)
    monkeypatch.setattr(worker_main, "OutboxWorker", FakeNotificationWorker)
    monkeypatch.setattr(worker_main, "AgentServerCronAdapter", FakeMonitorCronAdapter)
    monkeypatch.setattr(worker_main, "MonitorCronWorker", FakeMonitorCronWorker)
    monkeypatch.setattr(worker_main, "LifecycleWorker", FakeLifecycleWorker)
    monkeypatch.setattr(
        worker_main,
        "ProductProjectionReconciler",
        FakeProjectionReconciler,
    )
    monkeypatch.setattr(
        worker_main,
        "DomainEventProjectionWorker",
        FakeDomainEventWorker,
    )
    monkeypatch.setattr(worker_main, "WorkerRuntime", FakeRuntime)

    await worker_main._run_default(
        worker_id="worker-1",
        once=True,
        poll_interval=0.1,
        shutdown_budget_seconds=1,
    )

    assert len(FakeRuntime.instances) == 1
    runtime = FakeRuntime.instances[0]
    assert list(runtime.kwargs["workers"]) == [
        "projections",
        "domain_events",
        "commands",
        "notifications",
        "monitor_crons",
        "observability",
        "lifecycle",
    ]
    assert runtime.kwargs["readiness_failure_threshold"] == 4
    assert runtime.kwargs["readiness_stale_after_seconds"] == 45.0
    assert runtime.kwargs["health_host"] == "127.0.0.1"
    assert runtime.kwargs["health_port"] == 9090
    assert runtime.run_once_calls == 1
    assert len(FakeDispatcher.instances) == 1
    assert len(FakeProjectionReconciler.instances) == 1
    assert len(FakeDomainEventWorker.instances) == 1
    assert len(FakeMonitorCronAdapter.instances) == 1
    assert len(FakeMonitorCronWorker.instances) == 1
    assert len(FakeLifecycleWorker.instances) == 1
    runner = FakeDispatcher.instances[0].kwargs["runner"]
    assert FakeProjectionReconciler.instances[0].kwargs["runner"] is runner
    assert (
        FakeProjectionReconciler.instances[0].kwargs["session_factory"]
        is session_factory
    )
    assert (
        FakeDomainEventWorker.instances[0].kwargs["session_factory"] is session_factory
    )
    monitor_adapter = FakeMonitorCronAdapter.instances[0]
    monitor_worker = FakeMonitorCronWorker.instances[0]
    assert monitor_worker.kwargs == {
        "session_factory": session_factory,
        "adapter": monitor_adapter,
        "worker_id": "worker-1:monitor-cron",
        "lease_seconds": 90,
        "retry_seconds": 7.5,
        "max_attempts": 12,
    }
    assert monitor_adapter.kwargs["assistant_id"] == "crypto-analysis"
    assert monitor_adapter.kwargs["client"] is agent_client
    assert monitor_adapter.kwargs["authorization_provider"] is authorization_provider
    assert monitor_adapter.kwargs["include_end_time"] is False
    assert FakeLifecycleWorker.instances[0].kwargs == {
        "session_factory": session_factory,
        "worker_id": "worker-1:lifecycle",
    }
    assert runtime.kwargs["workers"]["monitor_crons"] is monitor_worker
    assert runtime.kwargs["workers"]["lifecycle"] is FakeLifecycleWorker.instances[0]
    assert engine.disposed is True
    assert http_client.closed is True
