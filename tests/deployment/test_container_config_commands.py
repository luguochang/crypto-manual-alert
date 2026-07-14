import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]

V2_SERVICES = {
    "postgres",
    "migrate",
    "internal-jwt-keys",
    "development-bootstrap",
    "agent-server",
    "agent-server-readiness",
    "command-worker",
    "frontend",
}
BACKEND_IMAGE_SERVICES = V2_SERVICES - {"postgres", "frontend"}
DEPLOYMENT_SECRET_PATTERNS = {
    "**/*.pem",
    "**/*.key",
    "**/*.p12",
    "**/*.pfx",
    "**/secrets/",
    "**/credentials/",
}
NESTED_DEPLOYMENT_SECRET_PATHS = (
    "ops/tls/private/deploy.pem",
    "ops/signing/private/deploy.key",
    "ops/signing/archive/deploy.p12",
    "ops/signing/archive/deploy.pfx",
    "ops/production/secrets/provider-token.txt",
    "ops/production/credentials/provider.json",
)


def _load_compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def _structured_volumes(service: dict) -> dict[str, dict]:
    return {
        volume["target"]: volume
        for volume in service.get("volumes", [])
        if isinstance(volume, dict)
    }


def test_backend_dockerfile_builds_locked_v2_runtime_and_defaults_to_product_api():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ARG PYTHON_BASE_IMAGE=python:3.12-slim" in dockerfile
    assert "FROM ${PYTHON_BASE_IMAGE}" in dockerfile
    assert "WORKDIR /app/backend" in dockerfile
    assert "COPY backend/pyproject.toml backend/uv.lock ./" in dockerfile
    assert "uv sync --frozen --no-dev --no-install-project" in dockerfile
    assert "COPY backend ./" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert dockerfile.index("COPY backend/pyproject.toml backend/uv.lock ./") < (
        dockerfile.index("COPY backend ./")
    )
    assert "EXPOSE 8011 8123" in dockerfile
    assert (
        'CMD ["uvicorn", "crypto_alert_v2.api.app:app", "--host", '
        '"0.0.0.0", "--port", "8011"]'
    ) in dockerfile
    assert "crypto_manual_alert" not in dockerfile
    assert "crypto-alert" not in dockerfile


def test_frontend_dockerfile_builds_locked_next_runtime_without_public_upstreams():
    dockerfile = (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")

    assert "ARG NODE_BASE_IMAGE=node:22-alpine" in dockerfile
    assert dockerfile.count("FROM ${NODE_BASE_IMAGE}") == 3
    assert "COPY frontend/package.json frontend/package-lock.json ./" in dockerfile
    assert "RUN npm ci" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert "ENV NODE_ENV=production" in dockerfile
    assert "NEXT_TELEMETRY_DISABLED=1" in dockerfile
    assert "COPY --from=builder /app/frontend/.next ./.next" in dockerfile
    assert "EXPOSE 3001" in dockerfile
    assert (
        'CMD ["npm", "exec", "next", "--", "start", "--hostname", '
        '"0.0.0.0", "--port", "3001"]'
    ) in dockerfile
    assert "NEXT_PUBLIC_" not in dockerfile


def test_compose_declares_only_the_complete_v2_local_proof_topology():
    compose = _load_compose()
    services = compose["services"]

    assert compose["name"] == "crypto-manual-alert-v2"
    assert set(services) == V2_SERVICES
    assert {"manual-alert", "api"}.isdisjoint(services)


def test_compose_builds_overridable_backend_and_frontend_images():
    services = _load_compose()["services"]

    assert {name for name, service in services.items() if "build" in service} == {
        "migrate",
        "frontend",
    }
    assert services["migrate"]["build"] == {
        "context": ".",
        "dockerfile": "Dockerfile",
        "args": {
            "PYTHON_BASE_IMAGE": "${PYTHON_BASE_IMAGE:-python:3.12-slim}",
        },
    }
    for service_name in BACKEND_IMAGE_SERVICES:
        assert (
            services[service_name]["image"]
            == "crypto-manual-alert-v2-backend:local"
        )

    assert services["frontend"]["build"] == {
        "context": ".",
        "dockerfile": "Dockerfile.frontend",
        "args": {"NODE_BASE_IMAGE": "${NODE_BASE_IMAGE:-node:22-alpine}"},
    }
    assert services["frontend"]["image"] == "crypto-manual-alert-v2-frontend:local"


def test_compose_commands_address_the_v2_runtime_entrypoints():
    services = _load_compose()["services"]

    assert services["migrate"]["command"] == [
        "alembic",
        "-c",
        "alembic.ini",
        "upgrade",
        "head",
    ]
    assert services["internal-jwt-keys"]["command"] == [
        "python",
        "-m",
        "crypto_alert_v2.auth.development_keys",
        "/run/internal-jwt-private",
        "--public-directory",
        "/run/internal-jwt-public",
    ]
    assert services["development-bootstrap"]["command"] == [
        "python",
        "-m",
        "crypto_alert_v2.auth.development_bootstrap",
    ]
    assert services["agent-server"]["command"] == [
        "langgraph",
        "dev",
        "--config",
        "langgraph.json",
        "--host",
        "0.0.0.0",
        "--port",
        "8123",
        "--no-browser",
        "--no-reload",
    ]
    assert services["agent-server-readiness"]["command"] == [
        "python",
        "-m",
        "crypto_alert_v2.auth.agent_healthcheck",
    ]
    assert services["command-worker"]["command"] == [
        "python",
        "-m",
        "crypto_alert_v2.commands.worker",
        "--worker-id",
        "compose-worker",
    ]


def test_compose_healthchecks_cover_the_v2_product_path():
    services = _load_compose()["services"]

    postgres_healthcheck = " ".join(services["postgres"]["healthcheck"]["test"])
    assert "pg_isready" in postgres_healthcheck

    agent_healthcheck = services["agent-server"]["healthcheck"]["test"][-1]
    assert "socket.create_connection(('127.0.0.1', 8123)" in agent_healthcheck
    assert "authorization" not in agent_healthcheck.lower()

    frontend_healthcheck = services["frontend"]["healthcheck"]["test"][-1]
    for required_path in (
        "/api/product/api/v2/health",
        "/api/product/api/v2/runs?limit=1",
        "/work",
    ):
        assert required_path in frontend_healthcheck
    assert "responses.every((response) => response.ok)" in frontend_healthcheck


def test_compose_authenticated_readiness_retries_boundedly_before_worker_start():
    services = _load_compose()["services"]
    readiness = services["agent-server-readiness"]
    readiness_environment = readiness["environment"]

    assert readiness["restart"] == "on-failure:12"
    assert services["command-worker"]["depends_on"]["agent-server-readiness"] == {
        "condition": "service_completed_successfully"
    }
    assert {
        name: value
        for name, value in readiness_environment.items()
        if name.startswith("AGENT_HEALTHCHECK_")
    } == {
        "AGENT_HEALTHCHECK_SUBJECT": "probe-user",
        "AGENT_HEALTHCHECK_TENANT_ID": "probe-tenant",
        "AGENT_HEALTHCHECK_WORKSPACE_ID": "probe-workspace",
        "AGENT_HEALTHCHECK_ROLES": '["operator"]',
        "AGENT_HEALTHCHECK_PERMISSIONS": '["analysis:read"]',
    }
    for service_name, service in services.items():
        if service_name != "agent-server-readiness":
            assert not any(
                name.startswith("AGENT_HEALTHCHECK_")
                for name in service.get("environment", {})
            )

    agent_liveness = services["agent-server"]["healthcheck"]["test"][-1].lower()
    assert "socket.create_connection" in agent_liveness
    assert "authorization" not in agent_liveness
    assert "bearer" not in agent_liveness


def test_compose_publishes_only_loopback_http_endpoints():
    services = _load_compose()["services"]

    assert services["agent-server"]["ports"] == [
        "127.0.0.1:${AGENT_SERVER_PORT:-8123}:8123"
    ]
    assert services["frontend"]["ports"] == [
        "127.0.0.1:${FRONTEND_PORT:-3001}:3001"
    ]
    for service_name in V2_SERVICES - {"agent-server", "frontend"}:
        assert "ports" not in services[service_name]
    assert "8011" not in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def test_compose_secret_env_file_is_optional_and_limited_to_secret_consumers():
    services = _load_compose()["services"]

    env_file_services = {
        name for name, service in services.items() if "env_file" in service
    }
    assert env_file_services == {"agent-server", "command-worker"}
    for service_name in env_file_services:
        assert services[service_name]["env_file"] == [
            {"path": "backend/.env", "required": False}
        ]


def test_compose_keeps_backend_upstreams_and_credentials_off_the_browser_surface():
    compose_source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    services = _load_compose()["services"]
    frontend_environment = services["frontend"]["environment"]

    assert frontend_environment["PRODUCT_API_BASE_URL"] == (
        "http://agent-server:8123/app"
    )
    assert frontend_environment["AGENT_SERVER_URL"] == "http://agent-server:8123"
    assert "INTERNAL_JWT_AUDIENCE" not in frontend_environment
    assert services["agent-server"]["environment"]["PRODUCT_DATABASE_URL"].startswith(
        "postgresql+asyncpg://"
    )
    assert not any(name.startswith("NEXT_PUBLIC_") for name in frontend_environment)
    for forbidden in (
        "NEXT_PUBLIC_API_BASE_URL",
        "AGENT_SERVER_LOCAL_TOKEN",
        "local-agent-dev-only",
        "host.docker.internal",
        "OKX_API_KEY",
        "OKX_API_SECRET",
        "OKX_API_PASSPHRASE",
    ):
        assert forbidden not in compose_source


def test_compose_separates_development_bootstrap_from_production_services():
    services = _load_compose()["services"]

    for service_name in (
        "agent-server",
        "agent-server-readiness",
        "command-worker",
    ):
        assert services[service_name]["environment"]["APP_ENVIRONMENT"] == "production"

    for service_name in ("development-bootstrap", "frontend"):
        environment = services[service_name]["environment"]
        assert environment["APP_ENVIRONMENT"] == "development"
        assert environment["DEVELOPMENT_BOOTSTRAP_ENABLED"] == "true"
        assert environment["DEVELOPMENT_BOOTSTRAP_PROFILE"] == "local-proof"

    readiness_environment = services["agent-server-readiness"]["environment"]
    assert not any(
        name.startswith("DEVELOPMENT_BOOTSTRAP_") for name in readiness_environment
    )
    assert services["agent-server"]["environment"]["MARKET_DATA_HTTP_PROXY"] == (
        "${MARKET_DATA_HTTP_PROXY:-}"
    )
    for service_name in V2_SERVICES - {"agent-server"}:
        assert "MARKET_DATA_HTTP_PROXY" not in services[service_name].get(
            "environment", {}
        )


def test_compose_internal_jwt_keys_follow_least_privilege_mounts():
    services = _load_compose()["services"]

    expected_mounts = {
        "agent-server": {"/run/internal-jwt-public": "internal-jwt-public"},
        "agent-server-readiness": {
            "/run/internal-jwt-private": "internal-jwt-private"
        },
        "command-worker": {"/run/internal-jwt-private": "internal-jwt-private"},
        "frontend": {"/run/internal-jwt-private": "internal-jwt-private"},
    }
    for service_name, expected in expected_mounts.items():
        volumes = _structured_volumes(services[service_name])
        assert {target: volume["source"] for target, volume in volumes.items()} == (
            expected
        )
        assert all(volume["read_only"] is True for volume in volumes.values())

    private_key_consumers = {
        service_name
        for service_name, service in services.items()
        if service_name != "internal-jwt-keys"
        and any(
            volume["source"] == "internal-jwt-private"
            for volume in _structured_volumes(service).values()
        )
    }
    assert private_key_consumers == {
        "agent-server-readiness",
        "command-worker",
        "frontend",
    }
    assert "INTERNAL_JWT_PRIVATE_KEY_FILE" not in services["agent-server"][
        "environment"
    ]
    assert services["agent-server"]["environment"]["INTERNAL_JWT_MAX_TTL_SECONDS"] == (
        "60"
    )
    assert "INTERNAL_JWT_AUDIENCE" not in services["agent-server"]["environment"]


def test_compose_dependencies_gate_migrations_auth_and_readiness_in_order():
    services = _load_compose()["services"]
    expected_dependencies = {
        "migrate": {"postgres": "service_healthy"},
        "development-bootstrap": {"migrate": "service_completed_successfully"},
        "agent-server": {
            "migrate": "service_completed_successfully",
            "internal-jwt-keys": "service_completed_successfully",
            "development-bootstrap": "service_completed_successfully",
        },
        "agent-server-readiness": {
            "internal-jwt-keys": "service_completed_successfully",
            "agent-server": "service_healthy",
        },
        "command-worker": {
            "migrate": "service_completed_successfully",
            "internal-jwt-keys": "service_completed_successfully",
            "development-bootstrap": "service_completed_successfully",
            "agent-server-readiness": "service_completed_successfully",
        },
        "frontend": {
            "agent-server": "service_healthy",
            "command-worker": "service_started",
        },
    }

    for service_name, expected in expected_dependencies.items():
        actual = {
            dependency: settings["condition"]
            for dependency, settings in services[service_name]["depends_on"].items()
        }
        assert actual == expected
    assert all("profiles" not in service for service in services.values())


def test_container_build_context_and_compose_avoid_secret_or_host_mounts():
    dockerignore_patterns = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    gitignore_patterns = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert {".env", "**/.env*", "**/node_modules/", "**/.next/"} <= (
        dockerignore_patterns
    )
    assert "**/node_modules/" in gitignore_patterns
    assert DEPLOYMENT_SECRET_PATTERNS <= dockerignore_patterns
    assert DEPLOYMENT_SECRET_PATTERNS <= gitignore_patterns

    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", *NESTED_DEPLOYMENT_SECRET_PATHS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ignored.returncode == 0, ignored.stderr
    assert set(ignored.stdout.splitlines()) == set(NESTED_DEPLOYMENT_SECRET_PATHS)

    for service in _load_compose()["services"].values():
        assert service.get("privileged") is not True
        assert service.get("network_mode") != "host"
        assert "cap_add" not in service
        for volume in service.get("volumes", []):
            if isinstance(volume, dict):
                assert volume["type"] == "volume"
            else:
                assert not volume.startswith((".", "/"))


def test_v2_browser_gate_keeps_request_boundaries_and_failure_evidence():
    config = (ROOT / "frontend" / "playwright.config.ts").read_text(
        encoding="utf-8"
    )
    suite_directory = ROOT / "frontend" / "tests" / "e2e-v2"
    official_flow = (suite_directory / "official-stream-main-flow.spec.ts").read_text(
        encoding="utf-8"
    )

    assert 'testDir: "./tests/e2e-v2"' in config
    assert {path.name for path in suite_directory.glob("*.spec.ts")} == {
        "official-stream-main-flow.spec.ts",
        "real-product-flow.spec.ts",
        "runs-product.spec.ts",
        "work-product.spec.ts",
    }
    assert "forbidOnly: true" in config
    assert 'trace: "retain-on-failure"' in config
    assert 'screenshot: "only-on-failure"' in config
    assert 'video: "retain-on-failure"' in config
    assert "forbiddenBrowserRequests" in official_flow
    assert "isPublicHttpsUrl" in official_flow
    assert 'url.protocol !== "https:"' in official_flow
    assert '"localhost"' in official_flow
    assert "first === 10 || first === 127" in official_flow
