from __future__ import annotations

import argparse
import asyncio
from typing import Protocol
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.config import get_settings


class ProvisioningService(Protocol):
    async def provision_actor(
        self,
        actor: ActorContext,
        *,
        tenant_name: str,
        workspace_name: str,
        user_display_name: str,
    ) -> None: ...


async def run_provisioning(
    service: ProvisioningService,
    *,
    tenant_id: str,
    tenant_name: str,
    workspace_id: str,
    workspace_name: str,
    user_id: str,
    identity_issuer: str,
    user_display_name: str,
    role: str,
    permissions: tuple[str, ...],
) -> None:
    actor = ActorContext(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_id=user_id,
        identity_issuer=_hosted_identity_issuer(identity_issuer),
        roles=(role,),
        permissions=permissions,
    )
    await service.provision_actor(
        actor,
        tenant_name=tenant_name,
        workspace_name=workspace_name,
        user_display_name=user_display_name,
    )


async def _run_default(args: argparse.Namespace) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    service = ProductAnalysisService(
        session_factory=async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        await run_provisioning(
            service,
            tenant_id=args.tenant_id,
            tenant_name=args.tenant_name,
            workspace_id=args.workspace_id,
            workspace_name=args.workspace_name,
            user_id=args.user_id,
            identity_issuer=args.identity_issuer,
            user_display_name=args.user_display_name,
            role=args.role,
            permissions=tuple(args.permission),
        )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision a Product tenant workspace membership"
    )
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--workspace-name", required=True)
    parser.add_argument(
        "--identity-issuer",
        required=True,
        type=_hosted_identity_issuer,
        help="Exact hosted OIDC issuer URL for the user subject",
    )
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--user-display-name", required=True)
    parser.add_argument("--role", default="member")
    parser.add_argument(
        "--permission",
        action="append",
        choices=("analysis:read", "analysis:write"),
        default=[],
        required=True,
    )
    asyncio.run(_run_default(parser.parse_args()))


def _hosted_identity_issuer(value: str) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "identity issuer must be a hosted HTTPS URL without credentials, query, or fragment"
        )
    return normalized


if __name__ == "__main__":
    main()


__all__ = ["main", "run_provisioning"]
