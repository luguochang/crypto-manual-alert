from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest
from pydantic import SecretStr

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.commands.worker import _authorization_provider, run_worker
from crypto_alert_v2.config import Settings


class RecordingDispatcher:
    def __init__(self, results: list[bool]) -> None:
        self._results = iter(results)
        self.calls = 0

    async def dispatch_once(self) -> bool:
        self.calls += 1
        return next(self._results)


@pytest.mark.asyncio
async def test_worker_once_processes_at_most_one_command() -> None:
    dispatcher = RecordingDispatcher([True, True])

    await run_worker(dispatcher, once=True, poll_interval=0)

    assert dispatcher.calls == 1


def test_worker_internal_token_targets_agent_server_audience() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    settings = Settings(
        _env_file=None,
        app_environment="production",
        internal_jwt_private_key=SecretStr(private_pem),
        INTERNAL_JWT_KID="compose-ephemeral",
        internal_jwt_issuer="compose-local",
        internal_jwt_audience="crypto-alert-product-api",
        agent_server_internal_jwt_audience="crypto-alert-agent-server",
    )
    actor = ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )

    authorization = _authorization_provider(settings)(actor)
    claims = jwt.decode(
        authorization.removeprefix("Bearer "),
        options={"verify_signature": False},
    )

    assert claims["aud"] == "crypto-alert-agent-server"


def test_local_worker_requires_explicit_local_token() -> None:
    settings = Settings(
        _env_file=None,
        app_environment="local",
        agent_server_local_token=None,
    )

    with pytest.raises(RuntimeError, match="local token is not configured"):
        _authorization_provider(settings)
