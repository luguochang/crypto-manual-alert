from __future__ import annotations

import asyncio
import json

import pytest

from crypto_alert_v2.workers.runtime import WorkerRuntime


async def _request_health(
    address: tuple[str, int], path: str
) -> tuple[int, dict[str, bool]]:
    reader, writer = await asyncio.open_connection(*address)
    writer.write(
        f"GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
    )
    await writer.drain()
    response = await reader.read()
    writer.close()
    await writer.wait_closed()
    headers, body = response.split(b"\r\n\r\n", 1)
    status_code = int(headers.split(b" ", 2)[1])
    return status_code, json.loads(body)


async def _wait_for_readiness(runtime: WorkerRuntime, expected: bool) -> None:
    while runtime.readiness is not expected:
        await asyncio.sleep(0.005)


class BlockingLeaseWorker:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.release_calls = 0
        self.claims_after_stop = 0

    async def dispatch_once(self) -> bool:
        self.entered.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise

    async def release_owned_leases(self) -> None:
        self.release_calls += 1


class RecordingWorker:
    def __init__(self, stop: asyncio.Event) -> None:
        self.stop = stop
        self.calls = 0

    async def dispatch_once(self) -> bool:
        self.calls += 1
        self.stop.set()
        return True

    async def release_owned_leases(self) -> None:
        return None


class RecoveringWorker:
    def __init__(self, stop: asyncio.Event) -> None:
        self.stop = stop
        self.calls = 0

    async def dispatch_once(self) -> bool:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient database outage")
        self.stop.set()
        return True

    async def release_owned_leases(self) -> None:
        return None


class HangingShutdownWorker:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.finish = asyncio.Event()

    async def dispatch_once(self) -> bool:
        self.entered.set()
        try:
            await self.finish.wait()
        except asyncio.CancelledError:
            await self.finish.wait()
        return False

    async def release_owned_leases(self) -> None:
        try:
            await self.finish.wait()
        except asyncio.CancelledError:
            await self.finish.wait()


class DependencyRecoveryWorker:
    def __init__(self) -> None:
        self.actions: asyncio.Queue[str] = asyncio.Queue()
        self.completed_iterations: asyncio.Queue[str] = asyncio.Queue()

    async def dispatch_once(self) -> bool:
        action = await self.actions.get()
        self.completed_iterations.put_nowait(action)
        if action == "failure":
            raise ConnectionError("database unavailable")
        return False

    async def release_owned_leases(self) -> None:
        return None


class GatedIterationWorker:
    def __init__(self, allow_iteration: asyncio.Event) -> None:
        self.allow_iteration = allow_iteration
        self.entered = asyncio.Event()
        self.completed = asyncio.Event()

    async def dispatch_once(self) -> bool:
        self.entered.set()
        await self.allow_iteration.wait()
        self.completed.set()
        return False

    async def release_owned_leases(self) -> None:
        return None


class RecoverableHungWorker:
    def __init__(self) -> None:
        self.calls = 0
        self.hung = asyncio.Event()
        self.release_hang = asyncio.Event()
        self.recovered = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def dispatch_once(self) -> bool:
        self.calls += 1
        if self.calls == 1:
            return True
        self.hung.set()
        try:
            await self.release_hang.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        self.recovered.set()
        return False

    async def release_owned_leases(self) -> None:
        return None


@pytest.mark.asyncio
async def test_runtime_stops_claiming_releases_leases_and_meets_shutdown_budget() -> (
    None
):
    stop = asyncio.Event()
    worker = BlockingLeaseWorker()
    runtime = WorkerRuntime(
        workers={"notification": worker},
        poll_interval=0,
        shutdown_budget_seconds=0.05,
    )

    task = asyncio.create_task(runtime.run(stop_event=stop))
    await asyncio.wait_for(worker.entered.wait(), timeout=1)
    assert runtime.liveness is True
    assert runtime.readiness is False

    stop.set()
    await asyncio.wait_for(task, timeout=0.5)

    assert worker.cancelled.is_set()
    assert worker.release_calls == 1
    assert runtime.readiness is False
    assert runtime.liveness is False


@pytest.mark.asyncio
async def test_runtime_health_server_exposes_liveness_and_readiness() -> None:
    stop = asyncio.Event()
    worker = BlockingLeaseWorker()
    runtime = WorkerRuntime(
        workers={"notification": worker},
        poll_interval=0,
        shutdown_budget_seconds=0.1,
        health_host="127.0.0.1",
        health_port=0,
    )
    task = asyncio.create_task(runtime.run(stop_event=stop))
    await asyncio.wait_for(worker.entered.wait(), timeout=1)

    address = runtime.health_address
    assert address is not None
    live_status, live_body = await _request_health(address, "/livez")
    ready_status, ready_body = await _request_health(address, "/readyz")
    assert live_status == 200
    assert ready_status == 503
    assert live_body == {"live": True, "ready": False}
    assert ready_body == {"live": True, "ready": False}

    stop.set()
    await asyncio.wait_for(task, timeout=0.5)


@pytest.mark.asyncio
async def test_runtime_never_reports_live_when_health_listener_cannot_bind() -> None:
    occupied = await asyncio.start_server(lambda *_: None, "127.0.0.1", 0)
    port = int(occupied.sockets[0].getsockname()[1])
    runtime = WorkerRuntime(
        workers={"notification": BlockingLeaseWorker()},
        health_host="127.0.0.1",
        health_port=port,
    )

    try:
        with pytest.raises(OSError):
            await runtime.run()
    finally:
        occupied.close()
        await occupied.wait_closed()

    assert runtime.liveness is False
    assert runtime.readiness is False


@pytest.mark.asyncio
async def test_restarted_runtime_processes_durable_work_once() -> None:
    stop = asyncio.Event()
    worker = RecordingWorker(stop)
    runtime = WorkerRuntime(
        workers={"notification": worker},
        poll_interval=0,
        shutdown_budget_seconds=0.1,
    )

    await runtime.run(stop_event=stop)

    assert worker.calls == 1


@pytest.mark.asyncio
async def test_worker_iteration_failure_is_logged_and_loop_recovers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop = asyncio.Event()
    worker = RecoveringWorker(stop)
    runtime = WorkerRuntime(
        workers={"notification": worker},
        poll_interval=0,
        shutdown_budget_seconds=0.1,
    )

    with caplog.at_level("ERROR", logger="crypto_alert_v2.workers.runtime"):
        await asyncio.wait_for(runtime.run(stop_event=stop), timeout=0.5)

    assert worker.calls == 2
    record = next(
        item
        for item in caplog.records
        if item.message == "durable worker iteration failed"
    )
    assert record.worker_name == "notification"
    assert record.error_type == "RuntimeError"


@pytest.mark.asyncio
async def test_shutdown_budget_is_a_hard_deadline_for_tasks_and_lease_release() -> None:
    stop = asyncio.Event()
    worker = HangingShutdownWorker()
    runtime = WorkerRuntime(
        workers={"notification": worker},
        poll_interval=0,
        shutdown_budget_seconds=0.03,
    )
    task = asyncio.create_task(runtime.run(stop_event=stop))
    await asyncio.wait_for(worker.entered.wait(), timeout=0.5)
    started = asyncio.get_running_loop().time()

    stop.set()
    await asyncio.wait_for(task, timeout=0.15)
    elapsed = asyncio.get_running_loop().time() - started
    worker.finish.set()
    await asyncio.sleep(0)

    assert elapsed < 0.1
    assert runtime.liveness is False
    assert runtime.readiness is False


@pytest.mark.asyncio
async def test_dependency_failures_degrade_and_success_restores_readiness() -> None:
    stop = asyncio.Event()
    worker = DependencyRecoveryWorker()
    worker.actions.put_nowait("success")
    runtime = WorkerRuntime(
        workers={"notification": worker},
        poll_interval=0,
        shutdown_budget_seconds=0.1,
        readiness_failure_threshold=3,
    )
    task = asyncio.create_task(runtime.run(stop_event=stop))

    assert await asyncio.wait_for(worker.completed_iterations.get(), timeout=0.5) == (
        "success"
    )
    assert runtime.readiness is True

    for _ in range(2):
        worker.actions.put_nowait("failure")
        assert await asyncio.wait_for(
            worker.completed_iterations.get(), timeout=0.5
        ) == ("failure")
        assert runtime.readiness is True

    worker.actions.put_nowait("failure")
    assert await asyncio.wait_for(worker.completed_iterations.get(), timeout=0.5) == (
        "failure"
    )
    assert runtime.readiness is False

    worker.actions.put_nowait("success")
    assert await asyncio.wait_for(worker.completed_iterations.get(), timeout=0.5) == (
        "success"
    )
    assert runtime.readiness is True

    stop.set()
    await asyncio.wait_for(task, timeout=0.5)


@pytest.mark.asyncio
async def test_readiness_waits_for_every_worker_loop_to_complete_an_iteration() -> None:
    stop = asyncio.Event()
    allow_fast_iteration = asyncio.Event()
    allow_fast_iteration.set()
    allow_blocked_iteration = asyncio.Event()
    fast_worker = GatedIterationWorker(allow_fast_iteration)
    blocked_worker = GatedIterationWorker(allow_blocked_iteration)
    runtime = WorkerRuntime(
        workers={"fast": fast_worker, "blocked": blocked_worker},
        poll_interval=1,
        shutdown_budget_seconds=0.1,
    )
    task = asyncio.create_task(runtime.run(stop_event=stop))

    await asyncio.wait_for(fast_worker.completed.wait(), timeout=0.5)
    await asyncio.wait_for(blocked_worker.entered.wait(), timeout=0.5)
    assert runtime.readiness is False

    allow_blocked_iteration.set()
    await asyncio.wait_for(blocked_worker.completed.wait(), timeout=0.5)
    await asyncio.sleep(0)
    assert runtime.readiness is True

    stop.set()
    await asyncio.wait_for(task, timeout=0.5)


@pytest.mark.asyncio
async def test_stale_iteration_degrades_without_cancelling_and_recovers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop = asyncio.Event()
    worker = RecoverableHungWorker()
    runtime = WorkerRuntime(
        workers={"commands": worker},
        poll_interval=1,
        shutdown_budget_seconds=0.1,
        readiness_stale_after_seconds=0.03,
    )

    with caplog.at_level("ERROR", logger="crypto_alert_v2.workers.runtime"):
        task = asyncio.create_task(runtime.run(stop_event=stop))
        await asyncio.wait_for(worker.hung.wait(), timeout=0.5)
        assert runtime.readiness is True

        await asyncio.wait_for(_wait_for_readiness(runtime, False), timeout=0.5)
        assert worker.cancelled.is_set() is False
        assert task.done() is False
        assert runtime.liveness is True

        worker.release_hang.set()
        await asyncio.wait_for(worker.recovered.wait(), timeout=0.5)
        await asyncio.wait_for(_wait_for_readiness(runtime, True), timeout=0.5)
        await asyncio.sleep(0.06)
        assert runtime.readiness is True
        assert worker.calls == 2

        stop.set()
        await asyncio.wait_for(task, timeout=0.5)

    stale_records = [
        record
        for record in caplog.records
        if record.message == "durable worker iteration progress became stale"
    ]
    assert len(stale_records) == 1
    assert stale_records[0].worker_name == "commands"
