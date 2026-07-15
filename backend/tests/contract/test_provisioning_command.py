import sys
from typing import Any

import pytest

from crypto_alert_v2.auth.context import ActorContext
import crypto_alert_v2.commands.provision as provision_module
from crypto_alert_v2.commands.provision import main, run_provisioning


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
        identity_issuer="https://identity.example.com/realms/acme/",
        user_display_name="Alice",
        role="analyst",
        permissions=("analysis:read", "analysis:write"),
    )

    assert service.actor == ActorContext(
        tenant_id="tenant-acme",
        workspace_id="research",
        user_id="oidc|alice",
        identity_issuer="https://identity.example.com/realms/acme/",
        roles=("analyst",),
        permissions=("analysis:read", "analysis:write"),
    )
    assert service.options == {
        "tenant_name": "Acme",
        "workspace_name": "Research",
        "user_display_name": "Alice",
    }


def test_provisioning_cli_requires_identity_issuer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "crypto-alert-provision",
            "--tenant-id",
            "tenant-acme",
            "--tenant-name",
            "Acme",
            "--workspace-id",
            "research",
            "--workspace-name",
            "Research",
            "--user-id",
            "alice-subject",
            "--user-display-name",
            "Alice",
            "--permission",
            "analysis:read",
        ],
    )

    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 2


def test_provisioning_cli_preserves_the_exact_hosted_identity_issuer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def record_args(args: Any) -> None:
        captured.update(vars(args))

    monkeypatch.setattr(provision_module, "_run_default", record_args)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "crypto-alert-provision",
            "--tenant-id",
            "tenant-acme",
            "--tenant-name",
            "Acme",
            "--workspace-id",
            "research",
            "--workspace-name",
            "Research",
            "--identity-issuer",
            "https://identity.example.com/realms/acme/",
            "--user-id",
            "alice-subject",
            "--user-display-name",
            "Alice",
            "--permission",
            "analysis:read",
        ],
    )

    main()

    assert captured["identity_issuer"] == "https://identity.example.com/realms/acme/"


@pytest.mark.asyncio
async def test_provisioning_rejects_a_non_hosted_identity_issuer() -> None:
    with pytest.raises(ValueError, match="hosted HTTPS URL"):
        await run_provisioning(
            RecordingProvisioningService(),
            tenant_id="tenant-acme",
            tenant_name="Acme",
            workspace_id="research",
            workspace_name="Research",
            user_id="alice-subject",
            identity_issuer="http://localhost:8080/realms/acme",
            user_display_name="Alice",
            role="analyst",
            permissions=("analysis:read",),
        )
