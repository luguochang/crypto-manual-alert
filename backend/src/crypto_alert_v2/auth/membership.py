from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.persistence.models import Membership, Tenant, User, Workspace


AUTH_CONTEXT_NOT_FOUND = "auth_context_not_found"


@dataclass(frozen=True, slots=True)
class AuthenticatedIdentity:
    issuer: str
    subject: str


@dataclass(frozen=True, slots=True)
class MembershipContext:
    context_id: UUID
    tenant_id: str
    tenant_name: str
    workspace_id: str
    workspace_name: str
    role: str
    permissions: tuple[str, ...]
    version: str


class MembershipAuthority(Protocol):
    async def discover(
        self, identity: AuthenticatedIdentity
    ) -> tuple[MembershipContext, ...]: ...

    async def authorize(
        self,
        identity: AuthenticatedIdentity,
        context_id: UUID,
    ) -> ActorContext: ...

    async def select(
        self,
        identity: AuthenticatedIdentity,
        context_id: UUID,
    ) -> tuple[ActorContext, MembershipContext]: ...


class DatabaseMembershipAuthority:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def discover(
        self, identity: AuthenticatedIdentity
    ) -> tuple[MembershipContext, ...]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    _membership_statement(identity)
                    .order_by(Tenant.name, Workspace.name, Membership.id)
                )
            ).all()
        return tuple(_membership_context(row) for row in rows)

    async def authorize(
        self,
        identity: AuthenticatedIdentity,
        context_id: UUID,
    ) -> ActorContext:
        actor, _ = await self.select(identity, context_id)
        return actor

    async def select(
        self,
        identity: AuthenticatedIdentity,
        context_id: UUID,
    ) -> tuple[ActorContext, MembershipContext]:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    _membership_statement(identity).where(Membership.id == context_id)
                )
            ).one_or_none()
        if row is None:
            raise PermissionError(AUTH_CONTEXT_NOT_FOUND)
        actor = ActorContext(
            tenant_id=row[6],
            workspace_id=row[7],
            user_id=identity.subject,
            identity_issuer=identity.issuer,
            context_id=row[0],
            roles=(row[3],),
            permissions=tuple(row[4]),
        )
        return actor, _membership_context(row)


def _membership_statement(identity: AuthenticatedIdentity):
    return (
        select(
            Membership.id,
            Tenant.name,
            Workspace.name,
            Membership.role,
            Membership.permissions,
            Membership.updated_at,
            Tenant.external_id,
            Workspace.external_id,
        )
        .select_from(Membership)
        .join(
            Tenant,
            Membership.tenant_id == Tenant.id,
        )
        .join(
            Workspace,
            and_(
                Membership.workspace_id == Workspace.id,
                Workspace.tenant_id == Tenant.id,
            ),
        )
        .join(
            User,
            and_(
                Membership.user_id == User.id,
                User.tenant_id == Tenant.id,
            ),
        )
        .where(
            User.identity_issuer == identity.issuer,
            User.external_subject == identity.subject,
            Membership.is_active.is_(True),
        )
    )


def _membership_context(row: object) -> MembershipContext:
    values = row
    return MembershipContext(
        context_id=values[0],
        tenant_id=values[6],
        tenant_name=values[1],
        workspace_id=values[7],
        workspace_name=values[2],
        role=values[3],
        permissions=tuple(values[4]),
        version=values[5].isoformat(),
    )


@lru_cache(maxsize=4)
def database_membership_authority(database_url: str) -> DatabaseMembershipAuthority:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return DatabaseMembershipAuthority(
        session_factory=async_sessionmaker(engine, expire_on_commit=False)
    )


__all__ = [
    "AUTH_CONTEXT_NOT_FOUND",
    "AuthenticatedIdentity",
    "DatabaseMembershipAuthority",
    "MembershipAuthority",
    "MembershipContext",
    "database_membership_authority",
]
