from __future__ import annotations

import os
from typing import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.membership import (
    AuthenticatedIdentity,
    DatabaseMembershipAuthority,
)
from crypto_alert_v2.commands.provision import run_provisioning
from crypto_alert_v2.persistence.base import Base


DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    os.getenv("REAL_DATABASE_TESTS") != "1" or not DATABASE_URL,
    reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
)


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield factory
    finally:
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_provisioned_user_is_discoverable_only_by_exact_oidc_identity(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    suffix = uuid4().hex
    issuer = "https://identity.example.com/realms/hosted/"
    subject = f"hosted-subject-{suffix}"
    service = ProductAnalysisService(session_factory=session_factory)

    await run_provisioning(
        service,
        tenant_id=f"tenant-{suffix}",
        tenant_name="Hosted Tenant",
        workspace_id=f"workspace-{suffix}",
        workspace_name="Hosted Workspace",
        user_id=subject,
        identity_issuer=issuer,
        user_display_name="Hosted User",
        role="member",
        permissions=("analysis:read",),
    )

    authority = DatabaseMembershipAuthority(session_factory=session_factory)
    contexts = await authority.discover(
        AuthenticatedIdentity(issuer=issuer, subject=subject)
    )

    assert len(contexts) == 1
    assert contexts[0].tenant_id == f"tenant-{suffix}"
    assert contexts[0].workspace_id == f"workspace-{suffix}"
    assert (
        await authority.discover(
            AuthenticatedIdentity(issuer=issuer.removesuffix("/"), subject=subject)
        )
        == ()
    )
    assert (
        await authority.discover(
            AuthenticatedIdentity(issuer=issuer, subject=f"{subject}-other")
        )
        == ()
    )
