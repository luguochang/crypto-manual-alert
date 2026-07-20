from __future__ import annotations

import asyncio
from collections.abc import Mapping
import json
import logging
import signal
from typing import Protocol


class DurableWorker(Protocol):
    async def dispatch_once(self) -> bool: ...

    async def release_owned_leases(self) -> None: ...


logger = logging.getLogger(__name__)


class WorkerRuntime:
    def __init__(
        self,
        *,
        workers: Mapping[str, DurableWorker],
        poll_interval: float = 0.5,
        shutdown_budget_seconds: float = 10.0,
        readiness_failure_threshold: int = 3,
        readiness_stale_after_seconds: float = 30.0,
        health_host: str | None = None,
        health_port: int | None = None,
    ) -> None:
        if not workers:
            raise ValueError("at least one durable worker is required")
        if any(not name.strip() for name in workers):
            raise ValueError("worker names are required")
        if poll_interval < 0:
            raise ValueError("poll_interval cannot be negative")
        if shutdown_budget_seconds <= 0:
            raise ValueError("shutdown_budget_seconds must be positive")
        if readiness_failure_threshold < 1:
            raise ValueError("readiness_failure_threshold must be positive")
        if readiness_stale_after_seconds <= 0:
            raise ValueError("readiness_stale_after_seconds must be positive")
        if (health_host is None) != (health_port is None):
            raise ValueError("health_host and health_port must be configured together")
        if health_port is not None and not 0 <= health_port <= 65535:
            raise ValueError("health_port must be between 0 and 65535")
        self._workers = dict(workers)
        self._poll_interval = poll_interval
        self._shutdown_budget_seconds = shutdown_budget_seconds
        self._readiness_failure_threshold = readiness_failure_threshold
        self._readiness_stale_after_seconds = readiness_stale_after_seconds
        self._health_host = health_host
        self._health_port = health_port
        self._health_server: asyncio.AbstractServer | None = None
        self._consecutive_failures = dict.fromkeys(self._workers, 0)
        self._completed_successful_iteration = dict.fromkeys(self._workers, False)
        self._iteration_started_at: dict[str, float | None] = dict.fromkeys(
            self._workers
        )
        self._reported_stale_workers: set[str] = set()
        self._stopping = True
        self._liveness = False
        self._readiness = False

    @property
    def liveness(self) -> bool:
        return self._liveness

    @property
    def readiness(self) -> bool:
        return self._readiness

    def health(self) -> dict[str, bool]:
        return {"live": self._liveness, "ready": self._readiness}

    @property
    def health_address(self) -> tuple[str, int] | None:
        if self._health_server is None or not self._health_server.sockets:
            return None
        address = self._health_server.sockets[0].getsockname()
        return str(address[0]), int(address[1])

    async def run(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        self._consecutive_failures = dict.fromkeys(self._workers, 0)
        self._completed_successful_iteration = dict.fromkeys(self._workers, False)
        self._iteration_started_at = dict.fromkeys(self._workers)
        self._reported_stale_workers.clear()
        self._stopping = False
        self._readiness = False
        if self._health_host is not None and self._health_port is not None:
            self._health_server = await asyncio.start_server(
                self._handle_health_client,
                self._health_host,
                self._health_port,
                limit=8192,
            )
        self._liveness = True
        tasks = {
            name: asyncio.create_task(
                self._run_loop(name, worker, stop),
                name=f"durable-worker:{name}",
            )
            for name, worker in self._workers.items()
        }
        readiness_monitor = asyncio.create_task(
            self._monitor_readiness(stop),
            name="durable-worker-readiness-monitor",
        )
        try:
            await stop.wait()
        finally:
            self._stopping = True
            self._readiness = False
            if self._health_server is not None:
                self._health_server.close()
                await self._health_server.wait_closed()
                self._health_server = None
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self._shutdown_budget_seconds
            runtime_tasks = set(tasks.values()) | {readiness_monitor}
            for task in runtime_tasks:
                if not task.done():
                    task.cancel()
            release_tasks = {
                asyncio.create_task(
                    self._release_worker(name, worker),
                    name=f"durable-worker-release:{name}",
                )
                for name, worker in self._workers.items()
            }
            shutdown_tasks = runtime_tasks | release_tasks
            remaining = max(0.0, deadline - loop.time())
            _, pending = await asyncio.wait(shutdown_tasks, timeout=remaining)
            for task in pending:
                task.cancel()
            if pending:
                for task in pending:
                    task.add_done_callback(_consume_task_result)
                await asyncio.sleep(0)
            self._liveness = False

    async def _handle_health_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2.0)
            request_line = request.split(b"\r\n", 1)[0].decode("ascii", "replace")
            parts = request_line.split(" ")
            method, path = (parts[0], parts[1]) if len(parts) >= 2 else ("", "")
            if method != "GET":
                status_code, reason = 405, "Method Not Allowed"
            elif path in {"/livez", "/healthz"}:
                status_code, reason = (
                    (200, "OK") if self._liveness else (503, "Service Unavailable")
                )
            elif path == "/readyz":
                status_code, reason = (
                    (200, "OK") if self._readiness else (503, "Service Unavailable")
                )
            else:
                status_code, reason = 404, "Not Found"
            body = json.dumps(self.health(), separators=(",", ":")).encode("ascii")
            response = (
                f"HTTP/1.1 {status_code} {reason}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii") + body
            writer.write(response)
            await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError):
            return
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def run_once(self) -> dict[str, bool]:
        self._liveness = True
        self._readiness = True
        try:
            return {
                name: await worker.dispatch_once()
                for name, worker in self._workers.items()
            }
        finally:
            self._readiness = False
            self._liveness = False

    def install_signal_handlers(self, stop_event: asyncio.Event) -> None:
        loop = asyncio.get_running_loop()
        for handled_signal in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(handled_signal, stop_event.set)
            except NotImplementedError:
                signal.signal(
                    handled_signal, lambda *_: loop.call_soon_threadsafe(stop_event.set)
                )

    async def _run_loop(
        self,
        name: str,
        worker: DurableWorker,
        stop_event: asyncio.Event,
    ) -> None:
        loop = asyncio.get_running_loop()
        while not stop_event.is_set():
            failed = False
            self._iteration_started_at[name] = loop.time()
            try:
                handled = await worker.dispatch_once()
                self._consecutive_failures[name] = 0
                self._completed_successful_iteration[name] = True
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                handled = False
                failed = True
                self._consecutive_failures[name] += 1
                logger.error(
                    "durable worker iteration failed",
                    extra={"worker_name": name, "error_type": type(exc).__name__},
                )
            finally:
                self._iteration_started_at[name] = None
            self._refresh_readiness()
            if handled or stop_event.is_set():
                continue
            try:
                delay = (
                    max(self._poll_interval, 0.01) if failed else self._poll_interval
                )
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
            except TimeoutError:
                pass

    async def _monitor_readiness(self, stop_event: asyncio.Event) -> None:
        interval = min(max(self._readiness_stale_after_seconds / 2, 0.01), 1.0)
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except TimeoutError:
                self._refresh_readiness()

    def _refresh_readiness(self) -> None:
        now = asyncio.get_running_loop().time()
        stale_workers = {
            name
            for name, started_at in self._iteration_started_at.items()
            if started_at is not None
            and now - started_at >= self._readiness_stale_after_seconds
        }
        if not self._stopping:
            for name in stale_workers - self._reported_stale_workers:
                logger.error(
                    "durable worker iteration progress became stale",
                    extra={
                        "worker_name": name,
                        "stale_after_seconds": self._readiness_stale_after_seconds,
                    },
                )
        self._reported_stale_workers = stale_workers
        self._readiness = (
            not self._stopping
            and not stale_workers
            and all(self._completed_successful_iteration.values())
            and all(
                failures < self._readiness_failure_threshold
                for failures in self._consecutive_failures.values()
            )
        )

    @staticmethod
    async def _release_worker(name: str, worker: DurableWorker) -> None:
        try:
            await worker.release_owned_leases()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "durable worker lease release failed",
                extra={"worker_name": name, "error_type": type(exc).__name__},
            )


def _consume_task_result(task: asyncio.Task[object]) -> None:
    if task.cancelled():
        return
    try:
        task.exception()
    except (asyncio.CancelledError, Exception):
        return


__all__ = ["DurableWorker", "WorkerRuntime"]
