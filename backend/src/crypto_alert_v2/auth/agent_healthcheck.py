import asyncio
from collections.abc import Awaitable, Callable, Mapping
import json
import logging
import signal
import time
from typing import Any

import httpx
from langgraph_sdk import get_client
from pydantic import ValidationError

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.auth.internal_token import InternalTokenIssuer
from crypto_alert_v2.config import Settings, get_settings
from crypto_alert_v2.providers.capability_probe import SearchProvider, SearchReadiness


AuthenticatedJsonFetcher = Callable[..., Awaitable[Mapping[str, Any]]]
AgentCheck = Callable[[Settings], Awaitable[None]]
logger = logging.getLogger(__name__)


def validate_search_readiness_payload(
    payload: object,
    *,
    expected_provider: SearchProvider | None = None,
) -> SearchReadiness:
    try:
        readiness = SearchReadiness.model_validate(payload)
    except (ValidationError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "Agent Server returned invalid or unsanitized search readiness"
        ) from exc
    if readiness.status != "ready":
        raise RuntimeError(
            "Agent Server returned invalid or unsanitized search readiness"
        )
    if (
        expected_provider is not None
        and readiness.selected_provider is not expected_provider
    ):
        raise RuntimeError(
            "Agent Server returned invalid or unsanitized search readiness"
        )
    return readiness


def validate_product_health_payload(payload: object) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping) or dict(payload) != {
        "status": "ok",
        "version": "2.0.0",
    }:
        raise RuntimeError("Agent Server returned invalid Product health")
    return payload


async def _fetch_authenticated_json(
    *,
    url: str,
    headers: Mapping[str, str],
) -> Mapping[str, Any]:
    async with httpx.AsyncClient(
        timeout=5.0,
        follow_redirects=False,
    ) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, Mapping):
        raise RuntimeError("Agent Server readiness response must be an object")
    return payload


async def check_agent_server(
    settings: Settings,
    *,
    client_factory: Callable[..., Any] = get_client,
    readiness_fetcher: AuthenticatedJsonFetcher = _fetch_authenticated_json,
) -> None:
    if settings.app_environment.strip().lower() != "production":
        raise RuntimeError("Agent Server healthcheck requires production mode")
    if not all(
        (
            settings.agent_healthcheck_subject,
            settings.agent_healthcheck_tenant_id,
            settings.agent_healthcheck_workspace_id,
            settings.agent_healthcheck_roles,
            settings.agent_healthcheck_permissions,
        )
    ):
        raise RuntimeError(
            "Agent Server healthcheck requires an explicit probe principal"
        )
    private_key = settings.internal_jwt_private_key
    key_id = settings.internal_jwt_key_id
    if private_key is None or key_id is None:
        raise RuntimeError("Agent Server healthcheck signing is not configured")
    actor = ActorContext(
        tenant_id=settings.agent_healthcheck_tenant_id,
        workspace_id=settings.agent_healthcheck_workspace_id,
        user_id=settings.agent_healthcheck_subject,
        roles=settings.agent_healthcheck_roles,
        permissions=settings.agent_healthcheck_permissions,
    )
    issuer = InternalTokenIssuer(
        private_key=private_key.get_secret_value(),
        key_id=key_id,
        issuer=settings.internal_jwt_issuer,
        audience=settings.agent_server_internal_jwt_audience,
        ttl_seconds=60,
    )
    token = issuer.issue(
        subject=actor.user_id,
        tenant_id=actor.tenant_id,
        workspace_id=actor.workspace_id,
        roles=actor.roles,
        permissions=actor.permissions,
        token_use="healthcheck",
    )
    headers = {"authorization": f"Bearer {token}"}
    client = client_factory(
        url=settings.agent_server_url,
        api_key=None,
        headers=headers,
    )
    assistants = await client.assistants.search(limit=100)
    if not any(
        assistant.get("graph_id") == settings.agent_assistant_id
        for assistant in assistants
    ):
        raise RuntimeError(f"{settings.agent_assistant_id} is not registered")
    readiness_payload = await readiness_fetcher(
        url=settings.agent_server_url.rstrip("/") + "/app/system/readiness",
        headers=headers,
    )
    validate_search_readiness_payload(
        readiness_payload,
        expected_provider=SearchProvider(settings.search_provider),
    )
    product_health_payload = await readiness_fetcher(
        url=settings.agent_server_url.rstrip("/") + "/app/api/v2/health",
        headers=headers,
    )
    validate_product_health_payload(product_health_payload)


class AgentReadinessMonitor:
    def __init__(
        self,
        settings: Settings,
        *,
        check: AgentCheck = check_agent_server,
        interval_seconds: float | None = None,
        probe_timeout_seconds: float | None = None,
        failure_threshold: int | None = None,
        stale_after_seconds: float | None = None,
        host: str | None = None,
        port: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._check = check
        self._interval_seconds = (
            settings.agent_readiness_interval_seconds
            if interval_seconds is None
            else interval_seconds
        )
        self._probe_timeout_seconds = (
            settings.agent_readiness_probe_timeout_seconds
            if probe_timeout_seconds is None
            else probe_timeout_seconds
        )
        self._failure_threshold = (
            settings.agent_readiness_failure_threshold
            if failure_threshold is None
            else failure_threshold
        )
        self._stale_after_seconds = (
            settings.agent_readiness_stale_after_seconds
            if stale_after_seconds is None
            else stale_after_seconds
        )
        self._host = settings.agent_readiness_host if host is None else host
        self._port = settings.agent_readiness_port if port is None else port
        if self._interval_seconds <= 0 or self._probe_timeout_seconds <= 0:
            raise ValueError("Agent readiness timing must be positive")
        if self._failure_threshold < 1 or self._stale_after_seconds <= 0:
            raise ValueError("Agent readiness threshold and freshness must be positive")
        self._clock = clock
        self._live = False
        self._successful_once = False
        self._consecutive_failures = 0
        self._last_success_at: float | None = None
        self._server: asyncio.AbstractServer | None = None

    @property
    def liveness(self) -> bool:
        return self._live

    @property
    def readiness(self) -> bool:
        if (
            not self._live
            or not self._successful_once
            or self._last_success_at is None
            or self._consecutive_failures >= self._failure_threshold
        ):
            return False
        return self._clock() - self._last_success_at <= self._stale_after_seconds

    @property
    def address(self) -> tuple[str, int] | None:
        if self._server is None or not self._server.sockets:
            return None
        host, port, *_ = self._server.sockets[0].getsockname()
        return str(host), int(port)

    def health(self) -> dict[str, bool]:
        return {"live": self.liveness, "ready": self.readiness}

    async def probe_once(self) -> bool:
        try:
            await asyncio.wait_for(
                self._check(self._settings),
                timeout=self._probe_timeout_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._consecutive_failures += 1
            logger.error(
                "Agent readiness probe failed",
                extra={
                    "error_type": type(exc).__name__,
                    "consecutive_failures": self._consecutive_failures,
                },
            )
            return False
        self._successful_once = True
        self._consecutive_failures = 0
        self._last_success_at = self._clock()
        return True

    async def run(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        self._server = await asyncio.start_server(
            self._handle_health_client,
            self._host,
            self._port,
            limit=8192,
        )
        self._live = True
        try:
            while not stop.is_set():
                await self.probe_once()
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self._interval_seconds)
                except TimeoutError:
                    pass
        finally:
            self._live = False
            if self._server is not None:
                self._server.close()
                await self._server.wait_closed()
                self._server = None

    async def _handle_health_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            parts = request_line.decode("ascii", errors="replace").strip().split()
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=2.0)
                if line in {b"\r\n", b"\n", b""}:
                    break
            method = parts[0] if len(parts) == 3 else ""
            path = parts[1].split("?", 1)[0] if len(parts) == 3 else ""
            if method != "GET":
                status_code, reason = 405, "Method Not Allowed"
            elif path == "/livez":
                status_code, reason = (
                    (200, "OK") if self.liveness else (503, "Service Unavailable")
                )
            elif path in {"/readyz", "/healthz"}:
                status_code, reason = (
                    (200, "OK") if self.readiness else (503, "Service Unavailable")
                )
            else:
                status_code, reason = 404, "Not Found"
            body = json.dumps(self.health(), separators=(",", ":")).encode("ascii")
            headers = (
                f"HTTP/1.1 {status_code} {reason}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            writer.write(headers + body)
            await writer.drain()
        except (TimeoutError, ConnectionError, OSError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass


async def run_monitor(settings: Settings) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for event in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(event, stop.set)
        except NotImplementedError:
            pass
    await AgentReadinessMonitor(settings).run(stop_event=stop)


if __name__ == "__main__":
    asyncio.run(run_monitor(get_settings()))


__all__ = [
    "check_agent_server",
    "AgentReadinessMonitor",
    "run_monitor",
    "validate_product_health_payload",
    "validate_search_readiness_payload",
]
