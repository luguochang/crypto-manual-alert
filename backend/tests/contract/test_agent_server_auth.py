import json
from types import SimpleNamespace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest

from crypto_alert_v2.auth.agent_server import (
    authenticate,
    deny_unhandled,
    scope_thread_access,
    scope_thread_create,
)
from crypto_alert_v2.auth.internal_token import InternalTokenIssuer
from crypto_alert_v2.config import get_settings


class User:
    identity = "oidc|user-1"
    permissions = (
        "analysis:read",
        "analysis:write",
        "tenant:tenant-1",
        "workspace:workspace-1",
    )


@pytest.fixture(autouse=True)
def local_auth_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENVIRONMENT", "local")
    monkeypatch.setenv("AGENT_SERVER_LOCAL_TOKEN", "test-local-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_local_agent_auth_requires_loopback_peer_and_exact_token() -> None:
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

    user = await authenticate(request, "Bearer test-local-token")

    assert user["identity"] == "dev-user"
    assert "tenant:dev-tenant" in user["permissions"]


@pytest.mark.asyncio
async def test_local_agent_auth_rejects_remote_peer_even_with_known_token() -> None:
    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.10"))

    with pytest.raises(Exception) as error:
        await authenticate(request, "Bearer test-local-token")

    assert getattr(error.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_local_agent_auth_has_no_hardcoded_default_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_SERVER_LOCAL_TOKEN")
    get_settings.cache_clear()
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

    with pytest.raises(Exception) as error:
        await authenticate(request, "Bearer local-agent-dev-only")

    assert getattr(error.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_internal_jwt_authenticates_docker_bridge_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("INTERNAL_JWT_KID", "compose-ephemeral")
    monkeypatch.setenv(
        "INTERNAL_JWT_PUBLIC_KEYS",
        json.dumps({"compose-ephemeral": public_pem}),
    )
    monkeypatch.setenv("INTERNAL_JWT_ISSUER", "compose-local")
    monkeypatch.setenv(
        "AGENT_SERVER_INTERNAL_JWT_AUDIENCE",
        "crypto-alert-agent-server",
    )
    get_settings.cache_clear()
    issuer = InternalTokenIssuer(
        private_key=private_pem,
        key_id="compose-ephemeral",
        issuer="compose-local",
        audience="crypto-alert-agent-server",
    )
    authorization = f"Bearer {issuer.issue(subject='dev-user', tenant_id='dev-tenant', workspace_id='dev-workspace', roles=('member',), permissions=('analysis:read',))}"
    request = SimpleNamespace(client=SimpleNamespace(host="172.24.0.8"))

    user = await authenticate(request, authorization)

    assert user["identity"] == "dev-user"
    assert "tenant:dev-tenant" in user["permissions"]


@pytest.mark.asyncio
async def test_thread_create_overwrites_untrusted_ownership_metadata() -> None:
    value = {"metadata": {"tenant_id": "attacker", "user_id": "attacker"}}
    context = SimpleNamespace(user=User())

    result = await scope_thread_create(context, value)

    assert result is None
    assert value["metadata"] == {
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "user_id": "oidc|user-1",
    }


@pytest.mark.asyncio
async def test_thread_access_is_filtered_to_actor_scope() -> None:
    context = SimpleNamespace(user=User())

    result = await scope_thread_access(context, {})

    assert result == {
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "user_id": "oidc|user-1",
    }


@pytest.mark.asyncio
async def test_unhandled_agent_server_resources_are_denied() -> None:
    assert await deny_unhandled(SimpleNamespace(user=User()), {}) is False
