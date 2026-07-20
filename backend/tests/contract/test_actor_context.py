import pytest

from crypto_alert_v2.auth.context import (
    ActorContext,
    configured_development_actor,
    resolve_actor_context,
)
from crypto_alert_v2.config import Settings


DEVELOPMENT_ACTOR = ActorContext(
    tenant_id="compose-tenant",
    workspace_id="compose-workspace",
    user_id="compose-user",
    roles=("member",),
    permissions=("analysis:read", "analysis:write"),
)


def test_configured_development_actor_strips_identity_fields() -> None:
    settings = Settings(
        _env_file=None,
        app_environment="development",
        development_bootstrap_enabled=True,
        development_bootstrap_profile="local-proof",
        development_bootstrap_subject=" compose-user \t",
        development_bootstrap_tenant_id=" compose-tenant \t",
        development_bootstrap_workspace_id=" compose-workspace \t",
        development_bootstrap_roles=(" member \t", " operator "),
        development_bootstrap_permissions=(
            " analysis:read \t",
            " analysis:write ",
        ),
    )

    actor = configured_development_actor(settings)

    assert actor == ActorContext(
        tenant_id="compose-tenant",
        workspace_id="compose-workspace",
        user_id="compose-user",
        identity_issuer="crypto-alert-v2-development",
        roles=("member", "operator"),
        permissions=("analysis:read", "analysis:write"),
    )


def test_untrusted_payload_cannot_override_development_identity() -> None:
    actor = resolve_actor_context(
        mode="development",
        authenticated_claims=None,
        untrusted_payload={
            "tenant_id": "attacker",
            "workspace_id": "attacker",
            "user_id": "attacker",
            "roles": ["admin"],
        },
        host="127.0.0.1:8011",
        origin="http://127.0.0.1:3001",
        peer_host="127.0.0.1",
        development_actor=DEVELOPMENT_ACTOR,
    )

    assert actor.tenant_id == "compose-tenant"
    assert actor.workspace_id == "compose-workspace"
    assert actor.user_id == "compose-user"
    assert actor.roles == ("member",)
    assert "admin" not in actor.roles


def test_development_identity_accepts_bare_ipv6_loopback_peer() -> None:
    actor = resolve_actor_context(
        mode="development",
        authenticated_claims=None,
        untrusted_payload={},
        host="[::1]:8011",
        origin="http://[::1]:3001",
        peer_host="::1",
        development_actor=DEVELOPMENT_ACTOR,
    )

    assert actor is DEVELOPMENT_ACTOR


def test_development_identity_rejects_remote_ipv6_peer() -> None:
    with pytest.raises(PermissionError, match="loopback"):
        resolve_actor_context(
            mode="development",
            authenticated_claims=None,
            untrusted_payload={},
            host="[::1]:8011",
            origin="http://[::1]:3001",
            peer_host="2001:db8::10",
            development_actor=DEVELOPMENT_ACTOR,
        )


def test_development_identity_rejects_non_loopback_host() -> None:
    with pytest.raises(PermissionError, match="loopback"):
        resolve_actor_context(
            mode="development",
            authenticated_claims=None,
            untrusted_payload={},
            host="product.example.com",
            origin="https://product.example.com",
            peer_host="203.0.113.10",
            development_actor=DEVELOPMENT_ACTOR,
        )


def test_development_identity_rejects_spoofed_loopback_host_from_remote_peer() -> None:
    with pytest.raises(PermissionError, match="loopback"):
        resolve_actor_context(
            mode="development",
            authenticated_claims=None,
            untrusted_payload={},
            host="127.0.0.1:8011",
            origin=None,
            peer_host="203.0.113.10",
            development_actor=DEVELOPMENT_ACTOR,
        )


def test_production_requires_verified_claims() -> None:
    with pytest.raises(PermissionError, match="authenticated"):
        resolve_actor_context(
            mode="production",
            authenticated_claims=None,
            untrusted_payload={},
            host="product.example.com",
            origin="https://product.example.com",
            peer_host="203.0.113.10",
        )


def test_production_actor_is_owned_by_verified_claims() -> None:
    actor = resolve_actor_context(
        mode="production",
        authenticated_claims={
            "tenant_id": "tenant-1",
            "workspace_id": "workspace-1",
            "sub": "user-1",
            "roles": ["member"],
            "permissions": ["analysis:read", "analysis:write"],
        },
        untrusted_payload={"tenant_id": "attacker"},
        host="product.example.com",
        origin="https://product.example.com",
        peer_host="203.0.113.10",
    )

    assert actor == ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
