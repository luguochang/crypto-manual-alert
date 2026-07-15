import json
from types import SimpleNamespace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest

from crypto_alert_v2.auth.agent_server import (
    authenticate,
    deny_unhandled,
    scope_store,
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
@pytest.mark.parametrize(
    ("action", "value", "logical_namespace"),
    (
        (
            "put",
            {
                "namespace": ("preferences",),
                "key": "theme",
                "value": {"mode": "dark"},
                "index": None,
            },
            ("preferences",),
        ),
        ("get", {"namespace": ("preferences",), "key": "theme"}, ("preferences",)),
        (
            "search",
            {
                "namespace": ("memories",),
                "filter": None,
                "limit": 10,
                "offset": 0,
                "query": None,
            },
            ("memories",),
        ),
        ("delete", {"namespace": ("preferences",), "key": "theme"}, ("preferences",)),
        (
            "list_namespaces",
            {
                "namespace": None,
                "suffix": None,
                "max_depth": None,
                "limit": 10,
                "offset": 0,
            },
            (),
        ),
    ),
)
async def test_store_operations_use_server_owned_private_namespace(
    action: str,
    value: dict[str, object],
    logical_namespace: tuple[str, ...],
) -> None:
    context = SimpleNamespace(resource="store", action=action, user=User())

    result = await scope_store(context, value)

    assert result is None
    assert value["namespace"] == (
        "tenant",
        "tenant-1",
        "workspace",
        "workspace-1",
        "scope",
        "private",
        "principal",
        "oidc|user-1",
        "agent-memory",
        *logical_namespace,
    )


@pytest.mark.asyncio
async def test_store_namespace_separates_users_in_the_same_workspace() -> None:
    first_value = {"namespace": ("preferences",), "key": "theme"}
    second_value = {"namespace": ("preferences",), "key": "theme"}
    peer = SimpleNamespace(
        identity="oidc|user-2",
        permissions=User.permissions,
    )

    await scope_store(SimpleNamespace(user=User()), first_value)
    await scope_store(SimpleNamespace(user=peer), second_value)

    assert first_value["namespace"] != second_value["namespace"]
    assert first_value["namespace"][7] == "oidc|user-1"
    assert second_value["namespace"][7] == "oidc|user-2"


@pytest.mark.asyncio
async def test_store_namespace_separates_same_subject_across_identity_issuers() -> None:
    first_value = {"namespace": ("preferences",), "key": "theme"}
    second_value = {"namespace": ("preferences",), "key": "theme"}
    base_permissions = (
        "analysis:read",
        "tenant:tenant-1",
        "workspace:workspace-1",
        "trusted-service",
    )
    first = SimpleNamespace(
        identity="shared-subject",
        permissions=(*base_permissions, "identity-issuer:https://idp-a.example"),
    )
    second = SimpleNamespace(
        identity="shared-subject",
        permissions=(*base_permissions, "identity-issuer:https://idp-b.example"),
    )

    await scope_store(SimpleNamespace(user=first), first_value)
    await scope_store(SimpleNamespace(user=second), second_value)

    first_principal = first_value["namespace"][7]
    second_principal = second_value["namespace"][7]
    assert first_principal != second_principal
    assert first_principal.startswith("identity-sha256:")
    assert second_principal.startswith("identity-sha256:")
    assert "shared-subject" not in first_value["namespace"]
    assert "shared-subject" not in second_value["namespace"]


@pytest.mark.asyncio
async def test_store_denies_client_owned_authority_components() -> None:
    untrusted_namespace = (
        "scope",
        "workspace",
        "principal",
        "oidc|user-2",
        "purpose",
        "preferences",
    )
    value = {"namespace": untrusted_namespace}

    with pytest.raises(Exception) as error:
        await scope_store(SimpleNamespace(user=User()), value)

    assert getattr(error.value, "status_code", None) == 403
    assert value["namespace"] == untrusted_namespace


@pytest.mark.asyncio
async def test_store_denies_an_actor_without_complete_server_scope() -> None:
    user = SimpleNamespace(
        identity="oidc|user-1",
        permissions=("analysis:read", "tenant:tenant-1"),
    )

    with pytest.raises(Exception) as error:
        await scope_store(SimpleNamespace(user=user), {"namespace": ()})

    assert getattr(error.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_unhandled_agent_server_resources_are_denied() -> None:
    assert await deny_unhandled(SimpleNamespace(user=User()), {}) is False
