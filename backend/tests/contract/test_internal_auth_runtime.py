import importlib
import json
import os
import socket
import subprocess
import sys
import time
from base64 import urlsafe_b64encode
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import UUID

from cryptography.hazmat.primitives import serialization
import jwt
import pytest
from pydantic import SecretStr

from crypto_alert_v2.config import Settings


def _cursor_key_secret(seed: bytes = b"c") -> str:
    return urlsafe_b64encode(seed * 32).decode("ascii").rstrip("=")


def _development_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_environment": "development",
        "development_bootstrap_enabled": True,
        "development_bootstrap_profile": "local-proof",
        "development_bootstrap_subject": "compose-user",
        "development_bootstrap_tenant_id": "compose-tenant",
        "development_bootstrap_workspace_id": "compose-workspace",
        "development_bootstrap_roles": ("member",),
        "development_bootstrap_permissions": ("analysis:read",),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_custom_http_app_constructs_product_app_for_agent_server_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("crypto_alert_v2.http.app")
    settings = Settings(
        _env_file=None,
        app_environment="test",
        internal_jwt_audience="standalone-product-audience",
        agent_server_internal_jwt_audience="official-agent-audience",
    )
    product = module.FastAPI()
    captured_audiences: list[str] = []

    def product_factory(*, token_audience: str):
        captured_audiences.append(token_audience)
        return product

    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        module,
        "create_default_product_app",
        product_factory,
        raising=False,
    )

    application = module.create_app()

    assert captured_audiences == ["official-agent-audience"]
    assert application.state.product_app is product


@pytest.mark.parametrize(
    ("token_audience", "expected_audience"),
    [
        (None, "standalone-product-audience"),
        ("official-agent-audience", "official-agent-audience"),
    ],
)
def test_default_product_app_preserves_or_overrides_standalone_audience(
    token_audience: str | None,
    expected_audience: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("crypto_alert_v2.api.app")
    settings = Settings(
        _env_file=None,
        app_environment="production",
        internal_jwt_public_keys={"test-key": "test-public-key"},
        internal_jwt_audience="standalone-product-audience",
        product_inbox_cursor_key=_cursor_key_secret(),
    )
    captured_audiences: list[str] = []

    class RecordingEngine:
        async def dispose(self) -> None:
            return None

    class RecordingVerifier:
        def __init__(self, **kwargs: object) -> None:
            captured_audiences.append(str(kwargs["audience"]))

    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        module,
        "notification_credential_cipher_from_environment",
        lambda: object(),
    )
    monkeypatch.setattr(
        module,
        "create_async_engine",
        lambda *_args, **_kwargs: RecordingEngine(),
    )
    monkeypatch.setattr(
        module,
        "async_sessionmaker",
        lambda *_args, **_kwargs: "session-factory",
    )
    monkeypatch.setattr(
        module,
        "ProductAnalysisService",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(module, "InternalTokenVerifier", RecordingVerifier)

    kwargs = {} if token_audience is None else {"token_audience": token_audience}
    module.create_default_app(**kwargs)

    assert captured_audiences == [
        expected_audience,
        "crypto-alert-identity-discovery",
    ]


def test_production_inbox_cursor_key_is_independent_and_required() -> None:
    module = importlib.import_module("crypto_alert_v2.api.app")
    without_product_key = Settings(
        _env_file=None,
        app_environment="production",
        agent_server_local_token="agent-local-token-must-not-be-reused",
        internal_jwt_private_key="jwt-private-key-must-not-be-reused",
    )
    with pytest.raises(ValueError, match="Product Inbox cursors"):
        module._configured_inbox_cursor_key(without_product_key)

    configured = without_product_key.model_copy(
        update={"product_inbox_cursor_key": SecretStr(_cursor_key_secret(b"d"))}
    )
    first = module._configured_inbox_cursor_key(configured)
    second = module._configured_inbox_cursor_key(configured)
    assert first is not None
    assert len(first) == 32
    assert first == second
    for weak_key in ("x", urlsafe_b64encode(b"short").decode("ascii")):
        with pytest.raises(ValueError, match="Product Inbox cursor key"):
            module._configured_inbox_cursor_key(
                configured.model_copy(
                    update={"product_inbox_cursor_key": SecretStr(weak_key)}
                )
            )


async def _seeded_actors_for_default_app(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> list[object]:
    module = importlib.import_module("crypto_alert_v2.api.app")
    seeded_actors: list[object] = []

    class RecordingEngine:
        async def dispose(self) -> None:
            return None

    class RecordingService:
        def __init__(self, **_: object) -> None:
            pass

        async def bootstrap_actor(self, actor: object) -> None:
            seeded_actors.append(actor)

    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        module,
        "notification_credential_cipher_from_environment",
        lambda: object(),
    )
    monkeypatch.setattr(
        module,
        "create_async_engine",
        lambda *_args, **_kwargs: RecordingEngine(),
    )
    monkeypatch.setattr(
        module,
        "async_sessionmaker",
        lambda *_args, **_kwargs: "session-factory",
    )
    monkeypatch.setattr(module, "ProductAnalysisService", RecordingService)

    product = module.create_default_app()
    async with product.router.lifespan_context(product):
        pass
    return seeded_actors


def test_settings_load_internal_jwt_keys_from_files(
    tmp_path,
    monkeypatch,
) -> None:
    private_key_file = tmp_path / "private.pem"
    public_key_file = tmp_path / "public.pem"
    cursor_key_file = tmp_path / "cursor-key"
    private_key_file.write_text("private-key")
    public_key_file.write_text("public-key")
    cursor_key_file.write_text("cursor-key-material")
    monkeypatch.setenv("INTERNAL_JWT_KID", "compose-ephemeral")
    monkeypatch.setenv("INTERNAL_JWT_PRIVATE_KEY_FILE", str(private_key_file))
    monkeypatch.setenv("INTERNAL_JWT_PUBLIC_KEY_FILE", str(public_key_file))
    monkeypatch.setenv("PRODUCT_INBOX_CURSOR_KEY_FILE", str(cursor_key_file))

    settings = Settings(_env_file=None, app_environment="test")

    assert settings.internal_jwt_private_key is not None
    assert settings.internal_jwt_private_key.get_secret_value() == "private-key"
    assert settings.internal_jwt_public_keys == {"compose-ephemeral": "public-key"}
    assert settings.product_inbox_cursor_key is not None
    assert settings.product_inbox_cursor_key.get_secret_value() == "cursor-key-material"


def test_settings_merges_public_key_file_into_existing_keyring(
    tmp_path,
    monkeypatch,
) -> None:
    public_key_file = tmp_path / "public.pem"
    public_key_file.write_text("new-public-key")
    monkeypatch.setenv(
        "INTERNAL_JWT_PUBLIC_KEYS",
        json.dumps({"old": "old-public-key"}),
    )
    monkeypatch.setenv("INTERNAL_JWT_KID", "new")
    monkeypatch.setenv("INTERNAL_JWT_PUBLIC_KEY_FILE", str(public_key_file))

    settings = Settings(
        _env_file=None,
        app_environment="test",
    )

    assert settings.internal_jwt_public_keys == {
        "old": "old-public-key",
        "new": "new-public-key",
    }


def test_settings_accepts_matching_public_key_file_for_existing_kid(
    tmp_path,
) -> None:
    public_key_file = tmp_path / "public.pem"
    public_key_file.write_text("same-public-key")

    settings = Settings(
        _env_file=None,
        app_environment="test",
        internal_jwt_public_keys={"new": "same-public-key", "old": "old-key"},
        INTERNAL_JWT_KID="new",
        internal_jwt_public_key_file=str(public_key_file),
    )

    assert settings.internal_jwt_public_keys == {
        "new": "same-public-key",
        "old": "old-key",
    }


def test_settings_rejects_conflicting_public_key_file_for_existing_kid(
    tmp_path,
) -> None:
    public_key_file = tmp_path / "public.pem"
    public_key_file.write_text("file-key-material")

    with pytest.raises(
        ValueError,
        match="INTERNAL_JWT_PUBLIC_KEYS contains conflicting key material",
    ):
        Settings(
            _env_file=None,
            app_environment="test",
            internal_jwt_public_keys={"new": "configured-key-material"},
            INTERNAL_JWT_KID="new",
            internal_jwt_public_key_file=str(public_key_file),
        )


def test_development_key_pair_is_matching_and_stable(tmp_path) -> None:
    module = importlib.import_module("crypto_alert_v2.auth.development_keys")

    private_key_file, public_key_file = module.ensure_development_key_pair(tmp_path)
    first_private = private_key_file.read_bytes()
    first_public = public_key_file.read_bytes()
    private_key = serialization.load_pem_private_key(
        first_private,
        password=None,
    )
    public_key = serialization.load_pem_public_key(first_public)

    assert private_key.public_key().public_numbers() == public_key.public_numbers()
    assert module.ensure_development_key_pair(tmp_path) == (
        private_key_file,
        public_key_file,
    )
    assert private_key_file.read_bytes() == first_private
    assert public_key_file.read_bytes() == first_public


def test_development_key_pair_can_split_private_and_public_volumes(
    tmp_path,
) -> None:
    module = importlib.import_module("crypto_alert_v2.auth.development_keys")
    private_directory = tmp_path / "private"
    public_directory = tmp_path / "public"

    private_key_file, public_key_file = module.ensure_development_key_pair(
        private_directory,
        public_directory=public_directory,
    )

    assert private_key_file == private_directory / "private.pem"
    assert public_key_file == public_directory / "public.pem"
    assert not (private_directory / "public.pem").exists()
    assert not (public_directory / "private.pem").exists()


def test_development_cursor_key_is_private_and_stable(tmp_path) -> None:
    module = importlib.import_module("crypto_alert_v2.auth.development_keys")
    key_file = module.ensure_development_cursor_key(tmp_path)
    first_key = key_file.read_text()

    assert len(first_key) >= 43
    assert key_file.stat().st_mode & 0o777 == 0o600
    assert module.ensure_development_cursor_key(tmp_path) == key_file
    assert key_file.read_text() == first_key


def test_development_key_cli_populates_compose_volume(tmp_path) -> None:
    private_directory = tmp_path / "private"
    public_directory = tmp_path / "public"
    cursor_key_directory = tmp_path / "cursor"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "crypto_alert_v2.auth.development_keys",
            str(private_directory),
            "--public-directory",
            str(public_directory),
            "--cursor-key-directory",
            str(cursor_key_directory),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (
        (private_directory / "private.pem")
        .read_text()
        .startswith("-----BEGIN PRIVATE KEY-----")
    )
    assert (
        (public_directory / "public.pem")
        .read_text()
        .startswith("-----BEGIN PUBLIC KEY-----")
    )
    assert len((cursor_key_directory / "key").read_text()) >= 43


def test_explicit_development_bootstrap_builds_server_owned_actor() -> None:
    module = importlib.import_module("crypto_alert_v2.auth.development_bootstrap")
    settings = Settings(
        _env_file=None,
        app_environment="development",
        development_bootstrap_enabled=True,
        development_bootstrap_profile="local-proof",
        development_bootstrap_subject="compose-user",
        development_bootstrap_identity_issuer="crypto-alert-v2-compose",
        development_bootstrap_context_id="99999999-9999-4999-8999-999999999999",
        development_bootstrap_tenant_id="compose-tenant",
        development_bootstrap_workspace_id="compose-workspace",
        development_bootstrap_roles=("member",),
        development_bootstrap_permissions=(
            "analysis:read",
            "analysis:write",
        ),
    )

    actor = module.development_actor(settings)

    assert actor.model_dump() == {
        "tenant_id": "compose-tenant",
        "workspace_id": "compose-workspace",
        "user_id": "compose-user",
        "identity_issuer": "crypto-alert-v2-compose",
        "context_id": UUID("99999999-9999-4999-8999-999999999999"),
        "roles": ("member",),
        "permissions": ("analysis:read", "analysis:write"),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "overrides"),
    (
        ("local-environment", {"app_environment": "local"}),
        ("test-environment", {"app_environment": "test"}),
        ("disabled", {"development_bootstrap_enabled": False}),
        ("missing-profile", {"development_bootstrap_profile": ""}),
        ("missing-subject", {"development_bootstrap_subject": ""}),
        ("missing-tenant", {"development_bootstrap_tenant_id": ""}),
        ("missing-workspace", {"development_bootstrap_workspace_id": ""}),
        ("missing-roles", {"development_bootstrap_roles": ()}),
        ("missing-permissions", {"development_bootstrap_permissions": ()}),
        ("whitespace-subject", {"development_bootstrap_subject": " \t "}),
        ("whitespace-tenant", {"development_bootstrap_tenant_id": " \t "}),
        (
            "whitespace-workspace",
            {"development_bootstrap_workspace_id": " \t "},
        ),
        ("whitespace-roles", {"development_bootstrap_roles": (" \t ",)}),
        (
            "whitespace-permissions",
            {"development_bootstrap_permissions": (" \t ",)},
        ),
    ),
)
async def test_default_app_does_not_seed_without_complete_local_proof_identity(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    overrides: dict[str, object],
) -> None:
    del case
    settings = _development_settings(**overrides)

    seeded_actors = await _seeded_actors_for_default_app(monkeypatch, settings)

    assert seeded_actors == []


@pytest.mark.asyncio
async def test_default_app_seeds_complete_local_proof_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _development_settings()

    seeded_actors = await _seeded_actors_for_default_app(monkeypatch, settings)

    assert [actor.model_dump() for actor in seeded_actors] == [
        {
            "tenant_id": "compose-tenant",
            "workspace_id": "compose-workspace",
            "user_id": "compose-user",
            "identity_issuer": "crypto-alert-v2-development",
            "context_id": None,
            "roles": ("member",),
            "permissions": ("analysis:read",),
        }
    ]


def test_production_mode_cannot_enable_development_bootstrap() -> None:
    module = importlib.import_module("crypto_alert_v2.auth.development_bootstrap")
    settings = Settings(
        _env_file=None,
        app_environment="production",
        development_bootstrap_enabled=True,
        development_bootstrap_subject="compose-user",
        development_bootstrap_tenant_id="compose-tenant",
        development_bootstrap_workspace_id="compose-workspace",
        development_bootstrap_roles=("member",),
        development_bootstrap_permissions=("analysis:read",),
    )

    with pytest.raises(RuntimeError, match="not explicitly enabled"):
        module.development_actor(settings)


def test_development_bootstrap_flag_requires_local_proof_profile() -> None:
    module = importlib.import_module("crypto_alert_v2.auth.development_bootstrap")
    settings = Settings(
        _env_file=None,
        app_environment="development",
        development_bootstrap_enabled=True,
        development_bootstrap_subject="compose-user",
        development_bootstrap_tenant_id="compose-tenant",
        development_bootstrap_workspace_id="compose-workspace",
        development_bootstrap_roles=("member",),
        development_bootstrap_permissions=("analysis:read",),
    )

    with pytest.raises(RuntimeError, match="local-proof"):
        module.development_actor(settings)


@pytest.mark.asyncio
async def test_development_bootstrap_delegates_to_product_service() -> None:
    module = importlib.import_module("crypto_alert_v2.auth.development_bootstrap")
    settings = Settings(
        _env_file=None,
        app_environment="development",
        development_bootstrap_enabled=True,
        development_bootstrap_profile="local-proof",
        development_bootstrap_subject="compose-user",
        development_bootstrap_tenant_id="compose-tenant",
        development_bootstrap_workspace_id="compose-workspace",
        development_bootstrap_roles=("member",),
        development_bootstrap_permissions=("analysis:read",),
    )

    class RecordingService:
        actors = []

        async def bootstrap_actor(self, actor) -> None:
            self.actors.append(actor)

    service = RecordingService()
    await module.bootstrap_development_membership(settings, service)

    assert [actor.user_id for actor in service.actors] == ["compose-user"]


@pytest.mark.asyncio
async def test_default_development_bootstrap_releases_database_engine(
    monkeypatch,
) -> None:
    module = importlib.import_module("crypto_alert_v2.auth.development_bootstrap")
    settings = Settings(
        _env_file=None,
        app_environment="development",
        product_database_url="postgresql+asyncpg://compose/database",
        development_bootstrap_enabled=True,
        development_bootstrap_profile="local-proof",
        development_bootstrap_subject="compose-user",
        development_bootstrap_tenant_id="compose-tenant",
        development_bootstrap_workspace_id="compose-workspace",
        development_bootstrap_roles=("member",),
        development_bootstrap_permissions=("analysis:read",),
    )

    class RecordingEngine:
        disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    class RecordingService:
        actors = []

        async def bootstrap_actor(self, actor) -> None:
            self.actors.append(actor)

    engine = RecordingEngine()
    service = RecordingService()
    engine_factory_calls = []
    session_factory = object()
    monkeypatch.setattr(
        module,
        "create_async_engine",
        lambda url, pool_pre_ping: (
            engine_factory_calls.append((url, pool_pre_ping)) or engine
        ),
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "async_sessionmaker",
        lambda created_engine, expire_on_commit: session_factory,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "ProductAnalysisService",
        lambda *, session_factory: service,
        raising=False,
    )

    await module.run_default(settings)

    assert engine_factory_calls == [("postgresql+asyncpg://compose/database", True)]
    assert [actor.user_id for actor in service.actors] == ["compose-user"]
    assert engine.disposed is True


@pytest.mark.asyncio
async def test_agent_healthcheck_uses_official_sdk_with_short_lived_jwt(
    tmp_path,
) -> None:
    key_module = importlib.import_module("crypto_alert_v2.auth.development_keys")
    private_key_file, public_key_file = key_module.ensure_development_key_pair(tmp_path)
    module = importlib.import_module("crypto_alert_v2.auth.agent_healthcheck")
    settings = Settings(
        _env_file=None,
        app_environment="production",
        agent_server_url="http://127.0.0.1:8123",
        agent_assistant_id="crypto_analysis",
        internal_jwt_private_key_file=str(private_key_file),
        internal_jwt_public_key_file=str(public_key_file),
        INTERNAL_JWT_KID="compose-ephemeral",
        internal_jwt_issuer="compose-local",
        agent_server_internal_jwt_audience="crypto-alert-agent-server",
        agent_healthcheck_subject="probe-user",
        agent_healthcheck_tenant_id="probe-tenant",
        agent_healthcheck_workspace_id="probe-workspace",
        agent_healthcheck_roles=("operator",),
        agent_healthcheck_permissions=("analysis:read",),
    )
    client_config = {}

    class Assistants:
        async def search(self, **kwargs):
            assert kwargs == {"limit": 100}
            return [{"graph_id": "crypto_analysis"}]

    class Client:
        assistants = Assistants()

    def client_factory(**kwargs):
        client_config.update(kwargs)
        return Client()

    readiness_requests: list[tuple[str, str]] = []

    async def readiness_fetcher(*, url, headers):
        readiness_requests.append((url, headers["authorization"]))
        if url.endswith("/app/api/v2/health"):
            return {"status": "ok", "version": "2.0.0"}
        return {
            "status": "ready",
            "selected_provider": "builtin_web_search",
            "probed_at": "2026-07-14T09:00:00Z",
            "model": "capability-test",
            "endpoint": "https://model.example",
            "capabilities": {
                "tool_calling": True,
                "structured_output": True,
                "streaming": True,
                "usage_reporting": True,
                "builtin_web_search_invoked": True,
                "builtin_web_search_citation_count": 1,
                "failures": [],
            },
            "tavily_configured": False,
            "tavily_connected": False,
        }

    await module.check_agent_server(
        settings,
        client_factory=client_factory,
        readiness_fetcher=readiness_fetcher,
    )

    assert client_config["url"] == "http://127.0.0.1:8123"
    assert client_config["api_key"] is None
    authorization = client_config["headers"]["authorization"]
    claims = jwt.decode(
        authorization.removeprefix("Bearer "),
        settings.internal_jwt_public_keys["compose-ephemeral"],
        algorithms=["RS256"],
        audience="crypto-alert-agent-server",
        issuer="compose-local",
    )
    assert claims["sub"] == "probe-user"
    assert claims["tenant_id"] == "probe-tenant"
    assert claims["workspace_id"] == "probe-workspace"
    assert claims["exp"] - claims["iat"] == 60
    assert [url for url, _authorization in readiness_requests] == [
        "http://127.0.0.1:8123/app/system/readiness",
        "http://127.0.0.1:8123/app/api/v2/health",
    ]
    assert {header for _url, header in readiness_requests} == {authorization}


@pytest.mark.asyncio
async def test_agent_healthcheck_fails_when_target_graph_is_missing(
    tmp_path,
) -> None:
    key_module = importlib.import_module("crypto_alert_v2.auth.development_keys")
    private_key_file, _ = key_module.ensure_development_key_pair(tmp_path)
    module = importlib.import_module("crypto_alert_v2.auth.agent_healthcheck")
    settings = Settings(
        _env_file=None,
        app_environment="production",
        agent_server_url="http://127.0.0.1:8123",
        agent_assistant_id="crypto_analysis",
        internal_jwt_private_key_file=str(private_key_file),
        INTERNAL_JWT_KID="compose-ephemeral",
        internal_jwt_issuer="compose-local",
        agent_server_internal_jwt_audience="crypto-alert-agent-server",
        agent_healthcheck_subject="probe-user",
        agent_healthcheck_tenant_id="probe-tenant",
        agent_healthcheck_workspace_id="probe-workspace",
        agent_healthcheck_roles=("operator",),
        agent_healthcheck_permissions=("analysis:read",),
    )

    class Assistants:
        async def search(self, **kwargs):
            return [{"graph_id": "some_other_graph"}]

    class Client:
        assistants = Assistants()

    with pytest.raises(RuntimeError, match="crypto_analysis is not registered"):
        await module.check_agent_server(
            settings,
            client_factory=lambda **kwargs: Client(),
        )


@pytest.mark.asyncio
async def test_agent_healthcheck_requires_an_explicit_probe_principal(
    tmp_path,
) -> None:
    key_module = importlib.import_module("crypto_alert_v2.auth.development_keys")
    private_key_file, _ = key_module.ensure_development_key_pair(tmp_path)
    module = importlib.import_module("crypto_alert_v2.auth.agent_healthcheck")
    settings = Settings(
        _env_file=None,
        app_environment="production",
        internal_jwt_private_key_file=str(private_key_file),
        INTERNAL_JWT_KID="compose-ephemeral",
    )

    class Assistants:
        async def search(self, **kwargs):
            return [{"graph_id": "crypto_analysis"}]

    class Client:
        assistants = Assistants()

    with pytest.raises(RuntimeError, match="probe principal"):
        await module.check_agent_server(
            settings,
            client_factory=lambda **kwargs: Client(),
        )


def test_agent_readiness_monitor_stays_unready_without_signer() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    env = {
        "APP_ENVIRONMENT": "production",
        "AGENT_HEALTHCHECK_SUBJECT": "probe-user",
        "AGENT_HEALTHCHECK_TENANT_ID": "probe-tenant",
        "AGENT_HEALTHCHECK_WORKSPACE_ID": "probe-workspace",
        "AGENT_HEALTHCHECK_ROLES": '["operator"]',
        "AGENT_HEALTHCHECK_PERMISSIONS": '["analysis:read"]',
        "AGENT_READINESS_HOST": "127.0.0.1",
        "AGENT_READINESS_PORT": str(port),
        "AGENT_READINESS_INTERVAL_SECONDS": "0.05",
        "AGENT_READINESS_PROBE_TIMEOUT_SECONDS": "0.05",
        "AGENT_READINESS_FAILURE_THRESHOLD": "1",
        "AGENT_READINESS_STALE_AFTER_SECONDS": "1",
        "PATH": os.environ["PATH"],
    }

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "crypto_alert_v2.auth.agent_healthcheck",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            if process.poll() is not None:
                _, stderr = process.communicate()
                raise AssertionError(
                    f"readiness monitor exited before serving health: {stderr}"
                )
            try:
                with urlopen(
                    f"http://127.0.0.1:{port}/livez",
                    timeout=0.2,
                ) as response:
                    assert response.status == 200
                    break
            except (HTTPError, URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise AssertionError(
                        "readiness monitor did not expose liveness"
                    ) from None
                time.sleep(0.02)

        with pytest.raises(HTTPError) as raised:
            urlopen(f"http://127.0.0.1:{port}/readyz", timeout=0.2)
        assert raised.value.code == 503
        assert json.loads(raised.value.read()) == {"live": True, "ready": False}
        assert process.poll() is None
    finally:
        process.terminate()
        try:
            process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=3)

    assert process.returncode == 0
