from typing import Any

import pytest

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.commands.provision import run_provisioning


class RecordingProvisioningService:
    def __init__(self) -> None:
        self.actor: ActorContext | None = None
        self.options: dict[str, Any] | None = None

    async def provision_actor(
        self,
        actor: ActorContext,
        **options: Any,
    ) -> None:
        self.actor = actor
        self.options = options


@pytest.mark.asyncio
async def test_provisioning_command_uses_explicit_tenant_actor_and_membership() -> None:
    service = RecordingProvisioningService()

    await run_provisioning(
        service,
        tenant_id="tenant-acme",
        tenant_name="Acme",
        workspace_id="research",
        workspace_name="Research",
        user_id="oidc|alice",
        user_display_name="Alice",
        role="analyst",
        permissions=("analysis:read", "analysis:write"),
    )

    assert service.actor == ActorContext(
        tenant_id="tenant-acme",
        workspace_id="research",
        user_id="oidc|alice",
        roles=("analyst",),
        permissions=("analysis:read", "analysis:write"),
    )
    assert service.options == {
        "tenant_name": "Acme",
        "workspace_name": "Research",
        "user_display_name": "Alice",
    }
