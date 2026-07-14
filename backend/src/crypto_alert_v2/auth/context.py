import ipaddress
from typing import TYPE_CHECKING, Any, Mapping
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from crypto_alert_v2.config import Settings


class ActorContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    roles: tuple[str, ...]
    permissions: tuple[str, ...]


def configured_development_actor(settings: "Settings") -> ActorContext | None:
    if (
        settings.app_environment.strip().lower() != "development"
        or not settings.development_bootstrap_enabled
        or settings.development_bootstrap_profile != "local-proof"
    ):
        return None
    subject = settings.development_bootstrap_subject.strip()
    tenant_id = settings.development_bootstrap_tenant_id.strip()
    workspace_id = settings.development_bootstrap_workspace_id.strip()
    roles = tuple(value.strip() for value in settings.development_bootstrap_roles)
    permissions = tuple(
        value.strip() for value in settings.development_bootstrap_permissions
    )
    if not all((subject, tenant_id, workspace_id)):
        return None
    if not roles or not all(roles) or not permissions or not all(permissions):
        return None
    return ActorContext(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_id=subject,
        roles=roles,
        permissions=permissions,
    )


def _is_loopback(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        pass
    parsed = urlparse(value if "://" in value else f"//{value}")
    hostname = parsed.hostname
    if hostname == "localhost":
        return True
    if hostname is None:
        return False
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def resolve_actor_context(
    *,
    mode: str,
    authenticated_claims: Mapping[str, Any] | None,
    untrusted_payload: Mapping[str, Any],
    host: str,
    origin: str | None,
    peer_host: str,
    development_actor: ActorContext | None = None,
) -> ActorContext:
    del untrusted_payload
    normalized_mode = mode.strip().lower()
    if normalized_mode == "development" and development_actor is not None:
        if (
            not _is_loopback(peer_host)
            or not _is_loopback(host)
            or (origin is not None and not _is_loopback(origin))
        ):
            raise PermissionError("development identity is restricted to loopback")
        return development_actor

    if authenticated_claims is None:
        raise PermissionError("authenticated verified claims are required")
    return ActorContext(
        tenant_id=str(authenticated_claims["tenant_id"]),
        workspace_id=str(authenticated_claims["workspace_id"]),
        user_id=str(authenticated_claims["sub"]),
        roles=tuple(str(value) for value in authenticated_claims.get("roles", ())),
        permissions=tuple(
            str(value) for value in authenticated_claims.get("permissions", ())
        ),
    )
