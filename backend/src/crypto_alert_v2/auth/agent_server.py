from __future__ import annotations

import hmac
import ipaddress
from typing import Any

from langgraph_sdk import Auth

from crypto_alert_v2.auth.internal_token import InternalTokenVerifier
from crypto_alert_v2.config import get_settings


auth = Auth()


@auth.authenticate
async def authenticate(
    request: Any, authorization: str | None
) -> Auth.types.MinimalUserDict:
    settings = get_settings()
    mode = settings.app_environment.strip().lower()
    if mode in {"local", "test", "development"}:
        peer = getattr(getattr(request, "client", None), "host", "")
        if not _is_loopback(peer):
            raise Auth.exceptions.HTTPException(status_code=401, detail="Unauthorized")
        local_token = settings.agent_server_local_token
        if local_token is None:
            raise Auth.exceptions.HTTPException(status_code=401, detail="Unauthorized")
        expected = f"Bearer {local_token.get_secret_value()}"
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise Auth.exceptions.HTTPException(status_code=401, detail="Unauthorized")
        return _user(
            subject="dev-user",
            tenant_id="dev-tenant",
            workspace_id="dev-workspace",
            permissions=("analysis:read", "analysis:write"),
        )

    try:
        verifier = InternalTokenVerifier(
            public_keys=settings.internal_jwt_public_keys,
            issuer=settings.internal_jwt_issuer,
            audience=settings.agent_server_internal_jwt_audience,
            max_ttl_seconds=settings.internal_jwt_max_ttl_seconds,
        )
        claims = verifier.verify_authorization(authorization)
    except (PermissionError, ValueError) as exc:
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Unauthorized"
        ) from exc
    return _user(
        subject=str(claims["sub"]),
        tenant_id=str(claims["tenant_id"]),
        workspace_id=str(claims["workspace_id"]),
        permissions=tuple(str(value) for value in claims.get("permissions", ())),
    )


@auth.on
async def deny_unhandled(ctx: Auth.types.AuthContext, value: Any) -> bool:
    del ctx, value
    return False


@auth.on.threads.create
async def scope_thread_create(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.threads.create.value,
) -> None:
    tenant_id, workspace_id = _actor_scope(ctx)
    value["metadata"] = {
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "user_id": ctx.user.identity,
    }


@auth.on.threads
async def scope_thread_access(
    ctx: Auth.types.AuthContext,
    value: dict[str, Any],
) -> Auth.types.FilterType:
    del value
    tenant_id, workspace_id = _actor_scope(ctx)
    return {
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "user_id": ctx.user.identity,
    }


@auth.on.assistants.read
async def allow_assistant_read(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.assistants.read.value,
) -> bool:
    del value
    return "analysis:read" in ctx.user.permissions


@auth.on.assistants.search
async def allow_assistant_search(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.assistants.search.value,
) -> bool:
    del value
    return "analysis:read" in ctx.user.permissions


@auth.on.store
async def scope_store(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.store.value,
) -> None:
    tenant_id, workspace_id = _actor_scope(ctx)
    supplied = tuple(value.get("namespace") or ())
    prefix = ("tenant", tenant_id, "workspace", workspace_id)
    value["namespace"] = prefix + supplied


def _actor_scope(ctx: Auth.types.AuthContext) -> tuple[str, str]:
    permissions = tuple(ctx.user.permissions)
    tenant_id = _tag(permissions, "tenant:")
    workspace_id = _tag(permissions, "workspace:")
    if tenant_id is None or workspace_id is None:
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    return tenant_id, workspace_id


def _tag(permissions: tuple[str, ...], prefix: str) -> str | None:
    for permission in permissions:
        if permission.startswith(prefix) and len(permission) > len(prefix):
            return permission.removeprefix(prefix)
    return None


def _user(
    *,
    subject: str,
    tenant_id: str,
    workspace_id: str,
    permissions: tuple[str, ...],
) -> Auth.types.MinimalUserDict:
    return {
        "identity": subject,
        "permissions": [
            *permissions,
            f"tenant:{tenant_id}",
            f"workspace:{workspace_id}",
        ],
        "is_authenticated": True,
    }


def _is_loopback(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


__all__ = [
    "auth",
    "authenticate",
    "deny_unhandled",
    "scope_store",
    "scope_thread_access",
    "scope_thread_create",
]
