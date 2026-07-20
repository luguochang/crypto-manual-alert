import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest

from crypto_alert_v2.auth.agent_server import (
    authenticate,
    deny_unhandled,
    scope_cron_create,
    scope_cron_delete,
    scope_cron_read,
    scope_cron_search,
    scope_cron_update,
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
    value = {
        "metadata": {
            "tenant_id": "attacker",
            "workspace_id": "attacker",
            "user_id": "attacker",
            "identity_issuer": "attacker",
            "context_id": "attacker",
            "graph_id": "crypto_analysis",
            "task_id": "task-1",
            "product_run_id": "run-1",
        }
    }
    original_metadata = value["metadata"]
    context = SimpleNamespace(user=User())

    result = await scope_thread_create(context, value)

    assert result is None
    assert value["metadata"] is original_metadata
    assert value["metadata"] == {
        "graph_id": "crypto_analysis",
        "task_id": "task-1",
        "product_run_id": "run-1",
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "user_id": "oidc|user-1",
    }


@pytest.mark.asyncio
async def test_thread_access_is_filtered_to_actor_scope() -> None:
    context = SimpleNamespace(action="read", user=User())

    result = await scope_thread_access(context, {})

    assert result == {
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "user_id": "oidc|user-1",
    }


@pytest.mark.asyncio
async def test_thread_access_uses_restored_auth_context_permissions() -> None:
    context = SimpleNamespace(
        action="create_run",
        permissions=User.permissions,
        user=SimpleNamespace(identity="oidc|user-1"),
    )

    result = await scope_thread_access(context, {})

    assert result == {
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "user_id": "oidc|user-1",
    }


@pytest.mark.asyncio
async def test_thread_create_requires_analysis_write() -> None:
    user = SimpleNamespace(
        identity="oidc|user-1",
        permissions=(
            "analysis:read",
            "tenant:tenant-1",
            "workspace:workspace-1",
        ),
    )

    with pytest.raises(Exception) as error:
        await scope_thread_create(SimpleNamespace(user=user), {"metadata": {}})

    assert getattr(error.value, "status_code", None) == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create_run", "delete", "update"])
async def test_thread_mutations_require_analysis_write(action: str) -> None:
    user = SimpleNamespace(
        identity="oidc|user-1",
        permissions=(
            "analysis:read",
            "tenant:tenant-1",
            "workspace:workspace-1",
        ),
    )

    with pytest.raises(Exception) as error:
        await scope_thread_access(SimpleNamespace(action=action, user=user), {})

    assert getattr(error.value, "status_code", None) == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["read", "search"])
async def test_thread_reads_require_analysis_read(action: str) -> None:
    user = SimpleNamespace(
        identity="oidc|user-1",
        permissions=(
            "analysis:write",
            "tenant:tenant-1",
            "workspace:workspace-1",
        ),
    )

    with pytest.raises(Exception) as error:
        await scope_thread_access(SimpleNamespace(action=action, user=user), {})

    assert getattr(error.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_unknown_thread_action_is_denied() -> None:
    with pytest.raises(Exception) as error:
        await scope_thread_access(SimpleNamespace(action="unknown", user=User()), {})

    assert getattr(error.value, "status_code", None) == 403


def test_isolated_settings_can_disable_dotenv_loading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("MODEL_NAME=must-not-load\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("CRYPTO_ALERT_DISABLE_DOTENV", "1")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.model_name == "gpt-5.5"


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


def _monitor_ingress_payload() -> dict[str, object]:
    return {
        "input": {
            "request": {
                "task_type": "monitor_ingress",
                "monitor_id": "11111111-1111-4111-8111-111111111111",
                "schedule_version": 4,
                "cron_binding_id": "22222222-2222-4222-8222-222222222222",
            }
        },
        "metadata": {
            "monitor_id": "11111111-1111-4111-8111-111111111111",
            "schedule_version": 4,
            "cron_binding_id": "22222222-2222-4222-8222-222222222222",
        },
    }


@pytest.mark.asyncio
async def test_cron_create_scopes_stable_references_to_authenticated_actor() -> None:
    payload = _monitor_ingress_payload()
    payload["config"] = {}
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata.update(
        {
            "tenant_id": "attacker-tenant",
            "workspace_id": "attacker-workspace",
            "user_id": "attacker-user",
        }
    )
    value = {
        "payload": payload,
        "schedule": "*/15 * * * *",
        "user_id": "attacker-user",
    }

    result = await scope_cron_create(SimpleNamespace(user=User()), value)

    assert result is None
    assert payload["metadata"] is metadata
    assert metadata == {
        "monitor_id": "11111111-1111-4111-8111-111111111111",
        "schedule_version": 4,
        "cron_binding_id": "22222222-2222-4222-8222-222222222222",
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "user_id": "oidc|user-1",
    }
    assert payload["config"] == {
        "configurable": {"langgraph_auth_permissions": list(User.permissions)}
    }
    assert value["user_id"] == "oidc|user-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("config", ({}, {"configurable": {}}, None))
async def test_cron_create_accepts_empty_server_injected_config(
    config: object,
) -> None:
    payload = _monitor_ingress_payload()
    payload["config"] = config

    await scope_cron_create(
        SimpleNamespace(user=User()),
        {"payload": payload, "schedule": "*/15 * * * *"},
    )

    configured = payload["config"]
    assert isinstance(configured, dict)
    configurable = configured["configurable"]
    assert isinstance(configurable, dict)
    assert configurable["langgraph_auth_permissions"] == list(User.permissions)


@pytest.mark.asyncio
async def test_cron_create_accepts_matching_server_generated_cron_id() -> None:
    cron_id = "33333333-3333-4333-8333-333333333333"
    payload = _monitor_ingress_payload()
    payload["config"] = {"configurable": {"cron_id": cron_id}}

    await scope_cron_create(
        SimpleNamespace(user=User()),
        {
            "payload": payload,
            "schedule": "*/15 * * * *",
            "cron_id": UUID(cron_id),
        },
    )

    configured = payload["config"]
    assert isinstance(configured, dict)
    configurable = configured["configurable"]
    assert isinstance(configurable, dict)
    assert configurable == {
        "cron_id": cron_id,
        "langgraph_auth_permissions": list(User.permissions),
    }


@pytest.mark.asyncio
async def test_cron_create_rejects_mismatched_server_generated_cron_id() -> None:
    payload = _monitor_ingress_payload()
    payload["config"] = {
        "configurable": {"cron_id": "33333333-3333-4333-8333-333333333333"}
    }

    with pytest.raises(Exception) as error:
        await scope_cron_create(
            SimpleNamespace(user=User()),
            {
                "payload": payload,
                "schedule": "*/15 * * * *",
                "cron_id": UUID("44444444-4444-4444-8444-444444444444"),
            },
        )

    assert getattr(error.value, "status_code", None) == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "forbidden_key",
    (
        "thesis",
        "condition",
        "query",
        "symbol",
        "channels",
        "entitlement",
        "artifact",
        "secret",
    ),
)
async def test_cron_create_rejects_business_data_in_input(
    forbidden_key: str,
) -> None:
    payload = _monitor_ingress_payload()
    cron_input = payload["input"]
    assert isinstance(cron_input, dict)
    request = cron_input["request"]
    assert isinstance(request, dict)
    request[forbidden_key] = "must-not-cross"

    with pytest.raises(Exception) as error:
        await scope_cron_create(
            SimpleNamespace(user=User()),
            {"payload": payload, "schedule": "*/15 * * * *"},
        )

    assert getattr(error.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_cron_create_rejects_non_reference_metadata() -> None:
    payload = _monitor_ingress_payload()
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["destination_id"] = "must-stay-in-product"

    with pytest.raises(Exception) as error:
        await scope_cron_create(
            SimpleNamespace(user=User()),
            {"payload": payload, "schedule": "*/15 * * * *"},
        )

    assert getattr(error.value, "status_code", None) == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("alternate_channel", ("context", "config", "webhook"))
async def test_cron_create_rejects_alternate_data_channels(
    alternate_channel: str,
) -> None:
    payload = _monitor_ingress_payload()
    payload[alternate_channel] = {"secret": "must-not-cross"}

    with pytest.raises(Exception) as error:
        await scope_cron_create(
            SimpleNamespace(user=User()),
            {"payload": payload, "schedule": "*/15 * * * *"},
        )

    assert getattr(error.value, "status_code", None) == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", (scope_cron_read, scope_cron_search))
async def test_cron_reads_require_read_permission_and_apply_actor_scope(
    handler: object,
) -> None:
    assert callable(handler)

    result = await handler(SimpleNamespace(user=User()), {})

    assert result == {
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "user_id": "oidc|user-1",
    }
    write_only_user = SimpleNamespace(
        identity="oidc|user-1",
        permissions=(
            "analysis:write",
            "tenant:tenant-1",
            "workspace:workspace-1",
        ),
    )
    with pytest.raises(Exception) as error:
        await handler(SimpleNamespace(user=write_only_user), {})
    assert getattr(error.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_cron_update_rescopes_reference_metadata() -> None:
    payload = _monitor_ingress_payload()
    payload["config"] = {}
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["tenant_id"] = "attacker-tenant"
    value = {"cron_id": "cron-1", "payload": payload}

    result = await scope_cron_update(SimpleNamespace(user=User()), value)

    assert result == {
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "user_id": "oidc|user-1",
    }
    assert metadata["tenant_id"] == "tenant-1"
    assert metadata["workspace_id"] == "workspace-1"
    assert metadata["user_id"] == "oidc|user-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "value"),
    (
        (scope_cron_create, {"payload": _monitor_ingress_payload()}),
        (scope_cron_update, {"cron_id": "cron-1", "payload": {"enabled": False}}),
        (scope_cron_delete, {"cron_id": "cron-1"}),
    ),
)
async def test_cron_mutations_require_write_permission(
    handler: object,
    value: dict[str, object],
) -> None:
    assert callable(handler)
    read_only_user = SimpleNamespace(
        identity="oidc|user-1",
        permissions=(
            "analysis:read",
            "tenant:tenant-1",
            "workspace:workspace-1",
        ),
    )

    with pytest.raises(Exception) as error:
        await handler(SimpleNamespace(user=read_only_user), value)

    assert getattr(error.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_cron_delete_is_filtered_to_actor_scope() -> None:
    result = await scope_cron_delete(
        SimpleNamespace(user=User()),
        {"cron_id": "cron-1"},
    )

    assert result == {
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "user_id": "oidc|user-1",
    }
