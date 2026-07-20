import asyncio

import pytest

from crypto_alert_v2.auth.agent_healthcheck import AgentReadinessMonitor
from crypto_alert_v2.config import Settings


@pytest.mark.asyncio
async def test_monitor_fails_closed_then_recovers_and_expires_stale_success() -> None:
    now = [100.0]
    calls = 0

    async def check(_: Settings) -> None:
        nonlocal calls
        calls += 1

    settings = Settings(_env_file=None, app_environment="production")
    stop = asyncio.Event()
    monitor = AgentReadinessMonitor(
        settings,
        check=check,
        interval_seconds=3600,
        probe_timeout_seconds=1,
        failure_threshold=3,
        stale_after_seconds=30,
        host="127.0.0.1",
        port=0,
        clock=lambda: now[0],
    )

    task = asyncio.create_task(monitor.run(stop_event=stop))
    await _wait_until(lambda: calls == 1)
    assert monitor.liveness is True
    assert monitor.readiness is True
    assert monitor.address is not None

    async def fail(_: Settings) -> None:
        raise RuntimeError("semantic Agent failure")

    monitor._check = fail
    assert await monitor.probe_once() is False
    assert await monitor.probe_once() is False
    assert monitor.readiness is True
    assert await monitor.probe_once() is False
    assert monitor.readiness is False

    monitor._check = check
    assert await monitor.probe_once() is True
    assert monitor.readiness is True
    now[0] += 31
    assert monitor.readiness is False
    assert await monitor.probe_once() is True
    assert monitor.readiness is True

    stop.set()
    await task
    assert monitor.liveness is False
    assert monitor.readiness is False


@pytest.mark.asyncio
async def test_monitor_http_readiness_waits_for_first_success() -> None:
    release = asyncio.Event()

    async def check(_: Settings) -> None:
        await release.wait()

    settings = Settings(_env_file=None, app_environment="production")
    stop = asyncio.Event()
    monitor = AgentReadinessMonitor(
        settings,
        check=check,
        interval_seconds=3600,
        probe_timeout_seconds=5,
        host="127.0.0.1",
        port=0,
    )
    task = asyncio.create_task(monitor.run(stop_event=stop))
    await _wait_until(lambda: monitor.address is not None)
    host, port = monitor.address or ("", 0)

    status = await _http_status(host, port, "/readyz")
    assert status == 503

    release.set()
    await _wait_until(lambda: monitor.readiness)
    assert await _http_status(host, port, "/livez") == 200
    assert await _http_status(host, port, "/readyz") == 200

    stop.set()
    await task


@pytest.mark.asyncio
async def test_monitor_never_reports_live_when_health_listener_cannot_bind() -> None:
    async def check(_: Settings) -> None:
        raise AssertionError("probe must not start without the health listener")

    occupied = await asyncio.start_server(lambda *_: None, "127.0.0.1", 0)
    port = int(occupied.sockets[0].getsockname()[1])
    monitor = AgentReadinessMonitor(
        Settings(_env_file=None, app_environment="production"),
        check=check,
        host="127.0.0.1",
        port=port,
    )

    try:
        with pytest.raises(OSError):
            await monitor.run()
    finally:
        occupied.close()
        await occupied.wait_closed()

    assert monitor.liveness is False
    assert monitor.readiness is False


async def _wait_until(predicate, *, timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


async def _http_status(host: str, port: int, path: str) -> int:
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(
        f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode(
            "ascii"
        )
    )
    await writer.drain()
    status_line = await reader.readline()
    while await reader.readline() not in {b"\r\n", b"\n", b""}:
        pass
    await reader.read()
    writer.close()
    await writer.wait_closed()
    return int(status_line.decode("ascii").split()[1])
