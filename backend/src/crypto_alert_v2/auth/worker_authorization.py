from __future__ import annotations

from collections.abc import Callable

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.auth.internal_token import InternalTokenIssuer
from crypto_alert_v2.config import Settings


def create_agent_server_authorization_provider(
    settings: Settings,
) -> Callable[[ActorContext], str]:
    mode = settings.app_environment.strip().lower()
    if mode in {"local", "test", "development"}:
        local_token = settings.agent_server_local_token
        if local_token is None:
            raise RuntimeError("worker local token is not configured")
        secret = local_token.get_secret_value()
        return lambda actor: f"Bearer {secret}"

    private_key_value = settings.internal_jwt_private_key
    key_id = settings.internal_jwt_key_id
    if private_key_value is None or key_id is None:
        raise RuntimeError("worker internal JWT signing is not configured")
    issuer = InternalTokenIssuer(
        private_key=private_key_value.get_secret_value(),
        key_id=key_id,
        issuer=settings.internal_jwt_issuer,
        audience=settings.agent_server_internal_jwt_audience,
        ttl_seconds=60,
    )

    def issue(actor: ActorContext) -> str:
        token = issuer.issue(
            subject=actor.user_id,
            tenant_id=actor.tenant_id,
            workspace_id=actor.workspace_id,
            roles=actor.roles,
            permissions=actor.permissions,
            token_use="worker",
            identity_issuer=actor.identity_issuer,
            context_id=actor.context_id,
        )
        return f"Bearer {token}"

    return issue


__all__ = ["create_agent_server_authorization_provider"]
