from __future__ import annotations

from hashlib import sha256
import hmac
import ipaddress
from typing import Any
from uuid import UUID

from langgraph_sdk import Auth

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.auth.internal_token import InternalTokenVerifier
from crypto_alert_v2.auth.membership import (
    AuthenticatedIdentity,
    database_membership_authority,
)
from crypto_alert_v2.auth.store_namespace import rewrite_namespace
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.monitors.models import MonitorIngressRequest


auth = Auth()

_STORE_AUTHORITY_COMPONENTS = frozenset(
    {"tenant", "workspace", "user", "scope", "principal", "purpose"}
)
_STORE_PURPOSE = "agent-memory"
_THREAD_AUTHORITY_METADATA = frozenset(
    {"tenant_id", "workspace_id", "user_id", "identity_issuer", "context_id"}
)
_THREAD_READ_ACTIONS = frozenset({"read", "search"})
_THREAD_WRITE_ACTIONS = frozenset({"create_run", "delete", "update"})
_CRON_REFERENCE_METADATA = frozenset(
    {"monitor_id", "schedule_version", "cron_binding_id"}
)
_CRON_AUTHORITY_METADATA = frozenset(
    {"tenant_id", "workspace_id", "user_id", "identity_issuer", "context_id"}
)
_CRON_CREATE_PAYLOAD_FIELDS = frozenset(
    {
        "assistant_id",
        "config",
        "schedule",
        "input",
        "metadata",
        "enabled",
        "timezone",
        "end_time",
        "stream_mode",
        "stream_subgraphs",
        "stream_resumable",
        "durability",
        "checkpoint_during",
        "interrupt_before",
        "interrupt_after",
        "on_run_completed",
        "multitask_strategy",
    }
)
_CRON_UPDATE_PAYLOAD_FIELDS = _CRON_CREATE_PAYLOAD_FIELDS - {"assistant_id"}


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
    token_use = str(claims["token_use"])
    if token_use == "user":
        try:
            actor = await database_membership_authority(
                settings.product_database_url
            ).authorize(
                AuthenticatedIdentity(
                    issuer=str(claims["identity_issuer"]),
                    subject=str(claims["sub"]),
                ),
                UUID(str(claims["context_id"])),
            )
        except PermissionError as exc:
            raise Auth.exceptions.HTTPException(
                status_code=403, detail="Forbidden"
            ) from exc
        return _user(
            subject=actor.user_id,
            tenant_id=actor.tenant_id,
            workspace_id=actor.workspace_id,
            permissions=actor.permissions,
            identity_issuer=actor.identity_issuer,
            context_id=actor.context_id,
        )
    if token_use == "identity_discovery":
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    return _user(
        subject=str(claims["sub"]),
        tenant_id=str(claims["tenant_id"]),
        workspace_id=str(claims["workspace_id"]),
        permissions=tuple(str(value) for value in claims.get("permissions", ())),
        identity_issuer=str(claims["identity_issuer"]),
        context_id=(
            UUID(str(claims["context_id"]))
            if claims.get("context_id") is not None
            else None
        ),
        trusted_service=True,
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
    permissions = await _authorized_permissions(ctx)
    _require_permission(permissions, "analysis:write")
    tenant_id, workspace_id = _scope_from_permissions(permissions)
    identity_issuer = _tag(permissions, "identity-issuer:")
    context_id = _tag(permissions, "auth-context:")
    supplied_metadata = value.get("metadata")
    if supplied_metadata is None:
        supplied_metadata = {}
        value["metadata"] = supplied_metadata
    elif not isinstance(supplied_metadata, dict):
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    preserved_metadata = {
        key: item
        for key, item in supplied_metadata.items()
        if key not in _THREAD_AUTHORITY_METADATA
    }
    scoped_metadata = {
        **preserved_metadata,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "user_id": ctx.user.identity,
        **({"identity_issuer": identity_issuer} if identity_issuer is not None else {}),
        **({"context_id": context_id} if context_id is not None else {}),
    }
    supplied_metadata.clear()
    supplied_metadata.update(scoped_metadata)


@auth.on.threads
async def scope_thread_access(
    ctx: Auth.types.AuthContext,
    value: dict[str, Any],
) -> Auth.types.FilterType:
    del value
    permissions = await _authorized_permissions(ctx)
    action = str(getattr(ctx, "action", ""))
    if action in _THREAD_READ_ACTIONS:
        _require_permission(permissions, "analysis:read")
    elif action in _THREAD_WRITE_ACTIONS:
        _require_permission(permissions, "analysis:write")
    else:
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    tenant_id, workspace_id = _scope_from_permissions(permissions)
    identity_issuer = _tag(permissions, "identity-issuer:")
    context_id = _tag(permissions, "auth-context:")
    return {
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "user_id": ctx.user.identity,
        **({"identity_issuer": identity_issuer} if identity_issuer is not None else {}),
        **({"context_id": context_id} if context_id is not None else {}),
    }


@auth.on.assistants.read
async def allow_assistant_read(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.assistants.read.value,
) -> bool:
    del value
    return "analysis:read" in await _authorized_permissions(ctx)


@auth.on.assistants.search
async def allow_assistant_search(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.assistants.search.value,
) -> bool:
    del value
    return "analysis:read" in await _authorized_permissions(ctx)


@auth.on.crons.create
async def scope_cron_create(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.crons.create.value,
) -> None:
    permissions = await _authorized_permissions(ctx)
    _require_permission(permissions, "analysis:write")
    authority = _cron_authority(ctx, permissions)
    payload = value.get("payload")
    if not isinstance(payload, dict):
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    _require_cron_payload_fields(payload, allowed=_CRON_CREATE_PAYLOAD_FIELDS)
    _require_server_cron_config(payload, cron_id=value.get("cron_id"))
    _scope_monitor_cron_payload(payload, authority)
    _bind_cron_run_permissions(payload, permissions)
    value["user_id"] = ctx.user.identity


@auth.on.crons.read
async def scope_cron_read(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.crons.read.value,
) -> Auth.types.FilterType:
    del value
    return await _cron_access_filter(ctx, required_permission="analysis:read")


@auth.on.crons.search
async def scope_cron_search(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.crons.search.value,
) -> Auth.types.FilterType:
    del value
    return await _cron_access_filter(ctx, required_permission="analysis:read")


@auth.on.crons.update
async def scope_cron_update(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.crons.update.value,
) -> Auth.types.FilterType:
    permissions = await _authorized_permissions(ctx)
    _require_permission(permissions, "analysis:write")
    authority = _cron_authority(ctx, permissions)
    payload = value.get("payload")
    if payload is not None:
        if not isinstance(payload, dict):
            raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
        _require_cron_payload_fields(payload, allowed=_CRON_UPDATE_PAYLOAD_FIELDS)
        _require_server_cron_config(payload, cron_id=value.get("cron_id"))
        has_input = "input" in payload
        has_metadata = "metadata" in payload
        if has_input != has_metadata:
            raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
        if has_input:
            _scope_monitor_cron_payload(payload, authority)
    return authority


@auth.on.crons.delete
async def scope_cron_delete(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.crons.delete.value,
) -> Auth.types.FilterType:
    del value
    return await _cron_access_filter(ctx, required_permission="analysis:write")


@auth.on.store
async def scope_store(
    ctx: Auth.types.AuthContext,
    value: Auth.types.on.store.value,
) -> None:
    permissions = await _authorized_permissions(ctx)
    tenant_id, workspace_id = _scope_from_permissions(permissions)
    identity = ctx.user.identity
    identity_issuer = _tag(permissions, "identity-issuer:")
    supplied_value = value.get("namespace")
    if supplied_value is None:
        supplied: tuple[str, ...] = ()
    elif isinstance(supplied_value, (list, tuple)):
        supplied = tuple(supplied_value)
    else:
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    if (
        not isinstance(identity, str)
        or not identity
        or any(
            not isinstance(part, str) or not part or part in _STORE_AUTHORITY_COMPONENTS
            for part in supplied
        )
    ):
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    principal_id = _store_principal(identity, identity_issuer)
    actor = ActorContext(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_id=principal_id,
        roles=(),
        permissions=(),
    )
    try:
        value["namespace"] = rewrite_namespace(
            actor,
            scope="private",
            principal_id=principal_id,
            namespace=(_STORE_PURPOSE, *supplied),
        )
    except (PermissionError, ValueError) as exc:
        raise Auth.exceptions.HTTPException(
            status_code=403, detail="Forbidden"
        ) from exc


async def _cron_access_filter(
    ctx: Auth.types.AuthContext,
    *,
    required_permission: str,
) -> Auth.types.FilterType:
    permissions = await _authorized_permissions(ctx)
    _require_permission(permissions, required_permission)
    return _cron_authority(ctx, permissions)


def _cron_authority(
    ctx: Auth.types.AuthContext,
    permissions: tuple[str, ...],
) -> dict[str, str]:
    tenant_id, workspace_id = _scope_from_permissions(permissions)
    identity = ctx.user.identity
    if not isinstance(identity, str) or not identity:
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    identity_issuer = _tag(permissions, "identity-issuer:")
    context_id = _tag(permissions, "auth-context:")
    if (identity_issuer is None) != (context_id is None):
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    return {
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "user_id": identity,
        **(
            {"identity_issuer": identity_issuer, "context_id": context_id}
            if identity_issuer is not None and context_id is not None
            else {}
        ),
    }


def _scope_monitor_cron_payload(
    payload: dict[str, Any],
    authority: dict[str, str],
) -> None:
    raw_input = payload.get("input")
    if not isinstance(raw_input, dict) or set(raw_input) != {"request"}:
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    raw_request = raw_input.get("request")
    if not isinstance(raw_request, dict):
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    try:
        request = MonitorIngressRequest.model_validate(raw_request)
    except ValueError as exc:
        raise Auth.exceptions.HTTPException(
            status_code=403, detail="Forbidden"
        ) from exc

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict) or not _CRON_REFERENCE_METADATA.issubset(
        metadata
    ):
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    if set(metadata) - _CRON_REFERENCE_METADATA - _CRON_AUTHORITY_METADATA:
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    references = request.reference_metadata()
    if any(
        type(metadata.get(key)) is not type(expected) or metadata.get(key) != expected
        for key, expected in references.items()
    ):
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    metadata.clear()
    metadata.update({**references, **authority})


def _require_cron_payload_fields(
    payload: dict[str, Any],
    *,
    allowed: frozenset[str],
) -> None:
    if set(payload) - allowed:
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")


def _require_server_cron_config(
    payload: dict[str, Any],
    *,
    cron_id: object,
) -> None:
    config = payload.get("config")
    if config is None:
        return
    if not isinstance(config, dict) or set(config) - {"configurable"}:
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    configurable = config.get("configurable")
    if configurable is None:
        return
    if not isinstance(configurable, dict) or set(configurable) - {"cron_id"}:
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    configured_cron_id = configurable.get("cron_id")
    if configured_cron_id is not None and (
        cron_id is None or str(configured_cron_id) != str(cron_id)
    ):
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")


def _bind_cron_run_permissions(
    payload: dict[str, Any],
    permissions: tuple[str, ...],
) -> None:
    config = payload.get("config")
    if config is None:
        config = {}
        payload["config"] = config
    configurable = config.get("configurable")
    if configurable is None:
        configurable = {}
        config["configurable"] = configurable
    configurable["langgraph_auth_permissions"] = list(permissions)


def _scope_from_permissions(permissions: tuple[str, ...]) -> tuple[str, str]:
    tenant_id = _tag(permissions, "tenant:")
    workspace_id = _tag(permissions, "workspace:")
    if tenant_id is None or workspace_id is None:
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    return tenant_id, workspace_id


def _require_permission(permissions: tuple[str, ...], required: str) -> None:
    if required not in permissions:
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")


async def _authorized_permissions(
    ctx: Auth.types.AuthContext,
) -> tuple[str, ...]:
    context_permissions = getattr(ctx, "permissions", None)
    permissions = tuple(
        context_permissions
        if context_permissions is not None
        else getattr(ctx.user, "permissions", ())
    )
    if "trusted-service" in permissions:
        return permissions
    context_id = _tag(permissions, "auth-context:")
    identity_issuer = _tag(permissions, "identity-issuer:")
    if context_id is None and identity_issuer is None:
        return permissions
    if context_id is None or identity_issuer is None:
        raise Auth.exceptions.HTTPException(status_code=403, detail="Forbidden")
    settings = get_settings()
    try:
        actor = await database_membership_authority(
            settings.product_database_url
        ).authorize(
            AuthenticatedIdentity(
                issuer=identity_issuer,
                subject=ctx.user.identity,
            ),
            UUID(context_id),
        )
    except (PermissionError, ValueError) as exc:
        raise Auth.exceptions.HTTPException(
            status_code=403, detail="Forbidden"
        ) from exc
    return (
        *actor.permissions,
        f"tenant:{actor.tenant_id}",
        f"workspace:{actor.workspace_id}",
        f"identity-issuer:{actor.identity_issuer}",
        f"auth-context:{actor.context_id}",
    )


def _tag(permissions: tuple[str, ...], prefix: str) -> str | None:
    for permission in permissions:
        if permission.startswith(prefix) and len(permission) > len(prefix):
            return permission.removeprefix(prefix)
    return None


def _store_principal(identity: str, identity_issuer: str | None) -> str:
    if identity_issuer is None:
        return identity
    digest = sha256(f"{identity_issuer}\0{identity}".encode()).hexdigest()
    return f"identity-sha256:{digest}"


def _user(
    *,
    subject: str,
    tenant_id: str,
    workspace_id: str,
    permissions: tuple[str, ...],
    identity_issuer: str | None = None,
    context_id: UUID | None = None,
    trusted_service: bool = False,
) -> Auth.types.MinimalUserDict:
    identity_tags = (
        [f"identity-issuer:{identity_issuer}", f"auth-context:{context_id}"]
        if identity_issuer is not None and context_id is not None
        else []
    )
    return {
        "identity": subject,
        "permissions": [
            *permissions,
            f"tenant:{tenant_id}",
            f"workspace:{workspace_id}",
            *identity_tags,
            *(["trusted-service"] if trusted_service else []),
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
    "scope_cron_create",
    "scope_cron_delete",
    "scope_cron_read",
    "scope_cron_search",
    "scope_cron_update",
    "scope_store",
    "scope_thread_access",
    "scope_thread_create",
]
