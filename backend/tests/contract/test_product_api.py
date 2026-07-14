from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest

from crypto_alert_v2.api.app import create_app
from crypto_alert_v2.api.service import (
    IdempotencyConflictError,
    ProductAnalysisService,
    _public_error,
)
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.config import Settings


class FakeProductService:
    def __init__(self) -> None:
        self.actor: ActorContext | None = None
        self.submission: Any = None
        self.idempotency_key: str | None = None
        self.selected_run_id: UUID | None = None
        self.cancelled_task_id: str | None = None
        self.cancel_idempotency_key: str | None = None
        self.dispatch_calls = 0

    async def create_analysis(
        self,
        actor: ActorContext,
        submission: Any,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self.actor = actor
        self.submission = submission
        self.idempotency_key = idempotency_key
        return {
            "task_id": "task-1",
            "status": "queued",
            "symbol": submission.symbol,
            "horizon": submission.horizon,
            "created_at": datetime(2026, 7, 13, tzinfo=UTC),
            "artifact": None,
            "errors": [],
        }

    async def get_task(
        self,
        actor: ActorContext,
        task_id: str,
        *,
        run_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.selected_run_id = run_id
        if task_id != "task-1":
            return None
        return {
            "task_id": task_id,
            "status": "failed",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "created_at": datetime(2026, 7, 13, tzinfo=UTC),
            "artifact": None,
            "errors": [
                {
                    "code": "provider_unavailable",
                    "message": "Market data provider is unavailable.",
                    "retryable": True,
                }
            ],
        }

    async def list_runs(self, actor: ActorContext, *, limit: int) -> dict[str, Any]:
        self.actor = actor
        return {
            "items": [
                {
                    "run_id": "11111111-1111-4111-8111-111111111111",
                    "task_id": "22222222-2222-4222-8222-222222222222",
                    "attempt": 1,
                    "status": "succeeded",
                    "symbol": "BTC-USDT-SWAP",
                    "horizon": "4h",
                    "created_at": datetime(2026, 7, 13, tzinfo=UTC),
                    "finished_at": datetime(2026, 7, 13, 0, 5, tzinfo=UTC),
                    "main_action": "no_trade",
                }
            ],
            "limit": limit,
        }

    async def cancel_task(
        self,
        actor: ActorContext,
        task_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        self.actor = actor
        self.cancelled_task_id = task_id
        self.cancel_idempotency_key = idempotency_key
        if task_id != "task-1":
            return None
        return {
            "task_id": task_id,
            "status": "running",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "created_at": datetime(2026, 7, 13, tzinfo=UTC),
            "completed_at": None,
            "cancel_requested_at": datetime(2026, 7, 13, 0, 1, tzinfo=UTC),
            "artifact": None,
            "errors": [],
        }

    async def dispatch_task(self, actor: ActorContext, task_id: str) -> None:
        del actor, task_id
        self.dispatch_calls += 1


class AcceptingTokenVerifier:
    def verify_authorization(self, authorization: str | None) -> dict[str, object]:
        assert authorization == "Bearer signed-internal-token"
        return {
            "tenant_id": "tenant-1",
            "workspace_id": "workspace-1",
            "sub": "oidc|user-1",
            "roles": ["member"],
            "permissions": ["analysis:read", "analysis:write"],
        }


class RejectingMissingAuthorizationVerifier:
    def verify_authorization(self, authorization: str | None) -> dict[str, object]:
        if authorization is None:
            raise PermissionError("Authorization header is required")
        raise AssertionError("this verifier only exercises missing Authorization")


class ConflictingProductService(FakeProductService):
    async def create_analysis(
        self,
        actor: ActorContext,
        submission: Any,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        del actor, submission, idempotency_key
        raise IdempotencyConflictError(
            "Idempotency-Key was already used with a different analysis payload."
        )


class UnprovisionedProductService(FakeProductService):
    async def create_analysis(
        self,
        actor: ActorContext,
        submission: Any,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        del actor, submission, idempotency_key
        raise PermissionError("actor membership was not found")


def _development_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_environment": "development",
        "development_bootstrap_enabled": True,
        "development_bootstrap_profile": "local-proof",
        "development_bootstrap_subject": "compose-user",
        "development_bootstrap_tenant_id": "compose-tenant",
        "development_bootstrap_workspace_id": "compose-workspace",
        "development_bootstrap_roles": ("member",),
        "development_bootstrap_permissions": (
            "analysis:read",
            "analysis:write",
        ),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _development_app(service: FakeProductService) -> object:
    settings = _development_settings()
    return create_app(
        service=service,
        mode=settings.app_environment,
        settings=settings,
    )


def test_public_error_preserves_only_safe_provider_diagnostics() -> None:
    public_errors = _public_error(
        {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": "research_unavailable",
                    "provider": "builtin_web_search",
                    "error_type": "UnverifiedServerToolCall",
                    "attempt": 3,
                    "retryable": True,
                    "endpoint": "must-not-cross-product-api",
                    "correlation_id": "must-not-cross-product-api",
                    "raw_response": "must-not-leak",
                    "authorization": "must-not-leak",
                }
            ],
        }
    )

    assert public_errors == [
        {
            "code": "research_unavailable",
            "message": "检索服务没有返回可验证来源，当前未生成分析结果。",
            "retryable": True,
            "provider": "builtin_web_search",
            "error_type": "UnverifiedServerToolCall",
            "attempt": 3,
        }
    ]


def test_product_service_has_no_in_process_dispatch_path() -> None:
    assert not hasattr(ProductAnalysisService, "dispatch_task")


@pytest.mark.asyncio
async def test_create_analysis_uses_server_owned_actor() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={
                "origin": "http://127.0.0.1:3001",
                "idempotency-key": "analysis-admission-1",
            },
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
                "tenant_id": "attacker",
                "user_id": "attacker",
                "roles": ["admin"],
            },
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert service.actor is not None
    assert service.actor.tenant_id == "compose-tenant"
    assert service.actor.user_id == "compose-user"
    assert service.actor.roles == ("member",)
    assert service.idempotency_key == "analysis-admission-1"
    assert service.dispatch_calls == 0


@pytest.mark.asyncio
async def test_list_runs_uses_server_owned_actor_and_typed_projection() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get("/api/v2/runs", params={"limit": 25})

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "run_id": "11111111-1111-4111-8111-111111111111",
                "task_id": "22222222-2222-4222-8222-222222222222",
                "attempt": 1,
                "status": "succeeded",
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "created_at": "2026-07-13T00:00:00Z",
                "finished_at": "2026-07-13T00:05:00Z",
                "main_action": "no_trade",
            }
        ],
        "limit": 25,
    }
    assert service.actor is not None
    assert service.actor.tenant_id == "compose-tenant"
    assert service.actor.workspace_id == "compose-workspace"
    assert service.actor.user_id == "compose-user"


@pytest.mark.asyncio
async def test_get_task_forwards_an_explicit_historical_run_selection() -> None:
    service = FakeProductService()
    run_id = "11111111-1111-4111-8111-111111111111"
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8011",
    ) as client:
        response = await client.get(
            "/api/v2/tasks/task-1",
            params={"run_id": run_id},
        )

    assert response.status_code == 200
    assert service.selected_run_id == UUID(run_id)


@pytest.mark.asyncio
async def test_cancel_task_persists_a_server_owned_product_command() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8011",
    ) as client:
        response = await client.post(
            "/api/v2/tasks/task-1/cancel",
            headers={"idempotency-key": "cancel-task-1"},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "running"
    assert response.json()["cancel_requested_at"] == "2026-07-13T00:01:00Z"
    assert service.cancelled_task_id == "task-1"
    assert service.cancel_idempotency_key == "cancel-task-1"
    assert service.actor is not None
    assert service.actor.tenant_id == "compose-tenant"


@pytest.mark.asyncio
async def test_cancel_task_returns_404_without_leaking_cross_tenant_existence() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8011",
    ) as client:
        response = await client.post(
            "/api/v2/tasks/not-visible/cancel",
            headers={"idempotency-key": "cancel-not-visible"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    (
        {},
        {"idempotency-key": "contains spaces"},
        {"idempotency-key": "x" * 256},
    ),
)
async def test_create_analysis_requires_an_allowed_idempotency_key(
    headers: dict[str, str],
) -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=create_app(service=service, mode="local"))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers=headers,
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 422
    assert service.actor is None


@pytest.mark.asyncio
async def test_create_analysis_returns_explicit_409_for_payload_conflict() -> None:
    transport = httpx.ASGITransport(
        app=_development_app(ConflictingProductService()),
        raise_app_exceptions=False,
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": "analysis-conflict-1"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Idempotency-Key was already used with a different analysis payload."
        )
    }


@pytest.mark.asyncio
async def test_production_missing_auth_returns_401_not_500() -> None:
    transport = httpx.ASGITransport(
        app=create_app(
            service=FakeProductService(),
            mode="production",
            token_verifier=RejectingMissingAuthorizationVerifier(),
        )
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="https://product.example.com"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": "production-missing-auth"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 401


@pytest.mark.parametrize("environment", ("staging", "production"))
def test_hosted_runtime_requires_token_verifier_at_startup(environment: str) -> None:
    with pytest.raises(ValueError, match="token_verifier"):
        create_app(service=FakeProductService(), mode=environment)


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ("local", "test", "development"))
async def test_non_explicit_development_runtime_does_not_bypass_jwt(
    environment: str,
) -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=create_app(service=service, mode=environment))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": f"{environment}-missing-auth"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 401
    assert service.actor is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "overrides"),
    (
        ("local-environment", {"app_environment": "local"}),
        ("test-environment", {"app_environment": "test"}),
        ("disabled", {"development_bootstrap_enabled": False}),
        ("missing-profile", {"development_bootstrap_profile": ""}),
        ("missing-subject", {"development_bootstrap_subject": ""}),
        ("missing-tenant", {"development_bootstrap_tenant_id": ""}),
        ("missing-workspace", {"development_bootstrap_workspace_id": ""}),
        ("missing-roles", {"development_bootstrap_roles": ()}),
        ("missing-permissions", {"development_bootstrap_permissions": ()}),
        ("whitespace-subject", {"development_bootstrap_subject": " \t "}),
        ("whitespace-tenant", {"development_bootstrap_tenant_id": " \t "}),
        (
            "whitespace-workspace",
            {"development_bootstrap_workspace_id": " \t "},
        ),
        ("whitespace-roles", {"development_bootstrap_roles": (" \t ",)}),
        (
            "whitespace-permissions",
            {"development_bootstrap_permissions": (" \t ",)},
        ),
    ),
)
async def test_incomplete_development_bootstrap_does_not_bypass_jwt(
    case: str,
    overrides: dict[str, object],
) -> None:
    del case
    settings = _development_settings(**overrides)
    service = FakeProductService()
    transport = httpx.ASGITransport(
        app=create_app(
            service=service,
            mode=settings.app_environment,
            settings=settings,
        )
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": "incomplete-development-bootstrap"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 401
    assert service.actor is None


@pytest.mark.asyncio
async def test_complete_local_proof_development_runtime_uses_configured_actor() -> None:
    settings = _development_settings()
    service = FakeProductService()
    transport = httpx.ASGITransport(
        app=create_app(
            service=service,
            mode=settings.app_environment,
            settings=settings,
        )
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": "explicit-development-bootstrap"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 202
    assert service.actor == ActorContext(
        tenant_id="compose-tenant",
        workspace_id="compose-workspace",
        user_id="compose-user",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )


@pytest.mark.asyncio
async def test_loopback_request_metadata_does_not_override_remote_peer() -> None:
    settings = _development_settings()
    service = FakeProductService()
    transport = httpx.ASGITransport(
        app=create_app(
            service=service,
            mode=settings.app_environment,
            settings=settings,
        ),
        client=("203.0.113.10", 4321),
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={
                "host": "127.0.0.1:8011",
                "origin": "http://127.0.0.1:3001",
                "idempotency-key": "spoofed-loopback-metadata",
            },
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 403
    assert service.actor is None


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ("staging", "production"))
async def test_hosted_runtime_requires_jwt(environment: str) -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(
        app=create_app(
            service=service,
            mode=environment,
            token_verifier=RejectingMissingAuthorizationVerifier(),
        )
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="https://product.example.com"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": f"{environment}-missing-jwt"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 401
    assert service.actor is None


@pytest.mark.asyncio
async def test_production_uses_verified_internal_token_claims() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(
        app=create_app(
            service=service,
            mode="production",
            token_verifier=AcceptingTokenVerifier(),
        )
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="https://product.example.com"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={
                "authorization": "Bearer signed-internal-token",
                "idempotency-key": "production-analysis-1",
            },
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
                "tenant_id": "attacker",
                "user_id": "attacker",
            },
        )

    assert response.status_code == 202
    assert service.actor is not None
    assert service.actor.tenant_id == "tenant-1"
    assert service.actor.workspace_id == "workspace-1"
    assert service.actor.user_id == "oidc|user-1"


@pytest.mark.asyncio
async def test_unprovisioned_production_actor_returns_403_not_500() -> None:
    transport = httpx.ASGITransport(
        app=create_app(
            service=UnprovisionedProductService(),
            mode="production",
            token_verifier=AcceptingTokenVerifier(),
        )
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="https://product.example.com"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={
                "authorization": "Bearer signed-internal-token",
                "idempotency-key": "unprovisioned-analysis-1",
            },
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
            },
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Actor is not provisioned for this workspace."}


@pytest.mark.asyncio
async def test_task_view_returns_readable_failure_not_raw_graph_state() -> None:
    service = FakeProductService()
    transport = httpx.ASGITransport(app=_development_app(service))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get(
            "/api/v2/tasks/task-1",
            headers={"origin": "http://127.0.0.1:3001"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["errors"][0]["code"] == "provider_unavailable"
    assert body["market_snapshot"] is None
    assert body["web_evidence"] == []
    assert "state" not in body
    assert "messages" not in body


@pytest.mark.asyncio
async def test_health_is_explicit() -> None:
    transport = httpx.ASGITransport(
        app=create_app(service=FakeProductService(), mode="local")
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get("/api/v2/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "2.0.0"}
