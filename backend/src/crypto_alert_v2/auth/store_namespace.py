from typing import Literal

from crypto_alert_v2.auth.context import ActorContext


Scope = Literal["private", "workspace", "restricted"]


def rewrite_namespace(
    actor: ActorContext,
    *,
    scope: Scope,
    principal_id: str,
    namespace: tuple[str, ...],
) -> tuple[str, ...]:
    if not namespace or any(not part for part in namespace):
        raise ValueError("namespace must contain non-empty components")
    if scope == "private" and principal_id != actor.user_id:
        raise PermissionError("private namespace must use the current user")
    if scope == "workspace" and principal_id != actor.workspace_id:
        raise PermissionError("workspace namespace must use the current workspace")
    if scope == "restricted" and "memory:restricted" not in actor.permissions:
        raise PermissionError("restricted namespace permission is required")
    return (
        "tenant",
        actor.tenant_id,
        "workspace",
        actor.workspace_id,
        "scope",
        scope,
        "principal",
        principal_id,
        *namespace,
    )
