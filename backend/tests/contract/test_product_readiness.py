import importlib
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from crypto_alert_v2.config import Settings


class ReadyService:
    def __init__(self) -> None:
        self.database_checks = 0

    async def check_database(self) -> None:
        self.database_checks += 1


class UnusedTokenVerifier:
    def verify_authorization(self, authorization: str | None) -> dict[str, Any]:
        del authorization
        raise AssertionError("readiness must not invoke request authentication")


class UnusedMembershipAuthority:
    async def discover(self, identity: object) -> tuple[object, ...]:
        del identity
        raise AssertionError("readiness must not discover memberships")

    async def authorize(self, identity: object, context_id: object) -> object:
        del identity, context_id
        raise AssertionError("readiness must not authorize memberships")

    async def select(
        self, identity: object, context_id: object
    ) -> tuple[object, object]:
        del identity, context_id
        raise AssertionError("readiness must not select memberships")


def _production_app(module: Any, *, service: ReadyService, settings: Settings) -> Any:
    verifier = UnusedTokenVerifier()
    return module.create_app(
        service=service,
        mode="production",
        settings=settings,
        token_verifier=verifier,
        identity_token_verifier=verifier,
        membership_authority=UnusedMembershipAuthority(),
    )


@pytest.mark.asyncio
async def test_production_readiness_requires_database_agent_and_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("crypto_alert_v2.api.app")
    service = ReadyService()
    checked: list[str] = []

    async def check(url: str, *, unavailable_detail: str) -> None:
        del unavailable_detail
        checked.append(url)

    monkeypatch.setattr(module, "_require_http_readiness", check)
    settings = Settings(
        _env_file=None,
        app_environment="production",
        agent_readiness_url="http://agent-monitor:9091/readyz",
        worker_readiness_url="http://worker:9090/readyz",
    )
    transport = httpx.ASGITransport(
        app=_production_app(module, service=service, settings=settings)
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://product"
    ) as client:
        response = await client.get("/api/v2/readiness")

    assert response.status_code == 200
    assert service.database_checks == 1
    assert checked == [
        "http://agent-monitor:9091/readyz",
        "http://worker:9090/readyz",
    ]


@pytest.mark.asyncio
async def test_agent_monitor_failure_forces_product_unready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("crypto_alert_v2.api.app")

    async def check(url: str, *, unavailable_detail: str) -> None:
        if "agent-monitor" in url:
            raise HTTPException(status_code=503, detail=unavailable_detail)

    monkeypatch.setattr(module, "_require_http_readiness", check)
    settings = Settings(
        _env_file=None,
        app_environment="production",
        agent_readiness_url="http://agent-monitor:9091/readyz",
        worker_readiness_url="http://worker:9090/readyz",
    )
    transport = httpx.ASGITransport(
        app=_production_app(module, service=ReadyService(), settings=settings)
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://product"
    ) as client:
        response = await client.get("/api/v2/readiness")

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent Server is not ready."}


@pytest.mark.asyncio
async def test_production_readiness_fails_closed_without_agent_monitor_url() -> None:
    module = importlib.import_module("crypto_alert_v2.api.app")
    settings = Settings(
        _env_file=None,
        app_environment="production",
        worker_readiness_url="http://worker:9090/readyz",
    )
    transport = httpx.ASGITransport(
        app=_production_app(module, service=ReadyService(), settings=settings)
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://product"
    ) as client:
        response = await client.get("/api/v2/readiness")

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent readiness URL is not configured."}
