import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_docker_context_excludes_local_langgraph_state() -> None:
    deployment_secret_patterns = {
        "**/*.pem",
        "**/*.key",
        "**/*.p12",
        "**/*.pfx",
        "**/secrets/",
        "**/credentials/",
    }
    patterns = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "**/.langgraph_api/" in patterns
    assert "**/*.pckl" in patterns
    assert {
        "**/.env*",
        "**/.coverage*",
        "**/.next/",
        "**/.venv/",
        "**/venv/",
        "**/node_modules/",
        "**/coverage/",
        "**/htmlcov/",
        "**/build/",
        "**/dist/",
        "**/test-results/",
        "**/playwright-report/",
        "**/.DS_Store",
        "**/Thumbs.db",
        "**/._*",
        *deployment_secret_patterns,
    } <= patterns

    gitignore_patterns = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert ".coverage" in gitignore_patterns
    assert ".coverage.*" in gitignore_patterns
    assert {"coverage/", "htmlcov/", "build/", "dist/", "*.pckl"} <= (
        gitignore_patterns
    )
    assert "**/node_modules/" in gitignore_patterns
    assert deployment_secret_patterns <= gitignore_patterns

    ignored_paths = (
        "backend/.venv/bin/python",
        "backend/venv/bin/python",
        "frontend/coverage/index.html",
        "backend/htmlcov/index.html",
        "backend/build/lib/module.py",
        "backend/dist/package.whl",
        "backend/state.pckl",
        "node_modules/.vite/vitest/results.json",
        "frontend/node_modules/.cache/result.json",
        "frontend/Thumbs.db",
        "frontend/._metadata",
        "ops/tls/private/deploy.pem",
        "ops/signing/private/deploy.key",
        "ops/signing/archive/deploy.p12",
        "ops/signing/archive/deploy.pfx",
        "ops/production/secrets/provider-token.txt",
        "ops/production/credentials/provider.json",
    )
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", *ignored_paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ignored.returncode == 0, ignored.stderr
    assert set(ignored.stdout.splitlines()) == set(ignored_paths)


def test_compose_starts_the_complete_v2_vertical_path() -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "config",
            "--no-env-resolution",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=os.environ
        | {
            "COMPOSE_DISABLE_ENV_FILE": "1",
            "MARKET_DATA_HTTP_PROXY": "http://proxy.example:7890",
        },
        capture_output=True,
        text=True,
        check=True,
    )
    config = json.loads(result.stdout)
    services = config["services"]

    assert set(services) == {
        "product-postgres",
        "agent-postgres",
        "langgraph-redis",
        "migrate",
        "internal-jwt-keys",
        "development-bootstrap",
        "langgraph-api",
        "langgraph-api-readiness",
        "command-worker",
        "frontend",
    }
    assert {"postgres", "agent-server", "langgraph-postgres"}.isdisjoint(services)
    assert "ports" not in services["product-postgres"]
    assert "ports" not in services["agent-postgres"]
    assert _volume_sources(services["product-postgres"]) == {
        "/var/lib/postgresql/data": "product-postgres-data"
    }
    assert _volume_sources(services["agent-postgres"]) == {
        "/var/lib/postgresql/data": "agent-postgres-data"
    }

    assert "crypto_alert_v2.commands.worker" in services["command-worker"]["command"]
    assert services["frontend"]["environment"]["PRODUCT_API_BASE_URL"] == (
        "http://langgraph-api:8000/app"
    )
    assert services["frontend"]["environment"]["AGENT_SERVER_URL"] == (
        "http://langgraph-api:8000"
    )
    assert services["frontend"]["environment"][
        "AGENT_SERVER_INTERNAL_JWT_AUDIENCE"
    ] == "crypto-alert-agent-server"
    assert not any(
        name.startswith("NEXT_PUBLIC_") and "AGENT_SERVER" in name
        for name in services["frontend"]["environment"]
    )
    assert services["langgraph-api"]["environment"][
        "PRODUCT_DATABASE_URL"
    ].startswith(
        "postgresql+asyncpg://"
    )
    for service_name in (
        "langgraph-api",
        "langgraph-api-readiness",
        "command-worker",
    ):
        assert services[service_name]["environment"]["APP_ENVIRONMENT"] == (
            "production"
        )
    assert services["frontend"]["environment"]["APP_ENVIRONMENT"] == "development"
    assert services["frontend"]["ports"] == [
        {
            "mode": "ingress",
            "host_ip": "127.0.0.1",
            "target": 3001,
            "published": "3001",
            "protocol": "tcp",
        }
    ]

    assert services["internal-jwt-keys"]["command"] == [
        "python",
        "-m",
        "crypto_alert_v2.auth.development_keys",
        "/run/internal-jwt-private",
        "--public-directory",
        "/run/internal-jwt-public",
        "--cursor-key-directory",
        "/run/product-inbox-cursor-key",
    ]
    assert services["development-bootstrap"]["command"] == [
        "python",
        "-m",
        "crypto_alert_v2.auth.development_bootstrap",
    ]
    assert services["development-bootstrap"]["environment"] == {
        "APP_ENVIRONMENT": "development",
        "DEVELOPMENT_BOOTSTRAP_ENABLED": "true",
        "DEVELOPMENT_BOOTSTRAP_PROFILE": "local-proof",
        "DEVELOPMENT_BOOTSTRAP_PERMISSIONS": '["analysis:read","analysis:write"]',
        "DEVELOPMENT_BOOTSTRAP_ROLES": '["member"]',
        "DEVELOPMENT_BOOTSTRAP_SUBJECT": "dev-user",
        "DEVELOPMENT_BOOTSTRAP_TENANT_ID": "dev-tenant",
        "DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID": "dev-workspace",
        "PRODUCT_DATABASE_URL": services["langgraph-api"]["environment"][
            "PRODUCT_DATABASE_URL"
        ],
    }
    for service_name in (
        "development-bootstrap",
        "frontend",
    ):
        environment = services[service_name]["environment"]
        assert environment["DEVELOPMENT_BOOTSTRAP_ENABLED"] == "true"
        assert environment["DEVELOPMENT_BOOTSTRAP_PROFILE"] == "local-proof"

    assert services["langgraph-api-readiness"]["command"] == [
        "python",
        "-m",
        "crypto_alert_v2.auth.agent_healthcheck",
    ]
    assert services["langgraph-api-readiness"]["restart"] == "on-failure:12"
    readiness_environment = services["langgraph-api-readiness"]["environment"]
    assert readiness_environment["AGENT_SERVER_URL"] == "http://langgraph-api:8000"
    assert readiness_environment["AGENT_HEALTHCHECK_SUBJECT"] == "probe-user"
    assert readiness_environment["AGENT_HEALTHCHECK_TENANT_ID"] == "probe-tenant"
    assert readiness_environment["AGENT_HEALTHCHECK_WORKSPACE_ID"] == "probe-workspace"
    assert readiness_environment["AGENT_HEALTHCHECK_ROLES"] == '["operator"]'
    assert readiness_environment["AGENT_HEALTHCHECK_PERMISSIONS"] == (
        '["analysis:read"]'
    )
    assert not any(
        name.startswith("DEVELOPMENT_BOOTSTRAP_")
        for name in readiness_environment
    )
    assert {
        name
        for name in readiness_environment
        if name.startswith("AGENT_HEALTHCHECK_")
    } == {
        "AGENT_HEALTHCHECK_SUBJECT",
        "AGENT_HEALTHCHECK_TENANT_ID",
        "AGENT_HEALTHCHECK_WORKSPACE_ID",
        "AGENT_HEALTHCHECK_ROLES",
        "AGENT_HEALTHCHECK_PERMISSIONS",
    }
    for service_name, service in services.items():
        if service_name != "langgraph-api-readiness":
            assert not any(
                name.startswith("AGENT_HEALTHCHECK_")
                for name in service.get("environment", {})
            )
    agent_liveness = services["langgraph-api"]["healthcheck"]["test"]
    assert agent_liveness == ["CMD", "python", "/api/healthcheck.py"]
    assert (
        "INTERNAL_JWT_PRIVATE_KEY_FILE"
        not in services["langgraph-api"]["environment"]
    )
    frontend_healthcheck = services["frontend"]["healthcheck"]["test"]
    assert "/api/product/api/v2/health" in frontend_healthcheck[-1]
    assert "/api/product/api/v2/runs?limit=1" in frontend_healthcheck[-1]
    assert "/work" in frontend_healthcheck[-1]
    assert (
        services["langgraph-api"]["environment"][
            "AGENT_SERVER_INTERNAL_JWT_AUDIENCE"
        ]
        == "crypto-alert-agent-server"
    )
    assert services["langgraph-api"]["environment"]["MARKET_DATA_HTTP_PROXY"] == (
        "http://proxy.example:7890"
    )
    assert services["langgraph-api"]["environment"][
        "PRODUCT_INBOX_CURSOR_KEY_FILE"
    ] == "/run/product-inbox-cursor-key/key"
    for service_name in (
        "development-bootstrap",
        "langgraph-api-readiness",
        "command-worker",
        "frontend",
    ):
        assert "MARKET_DATA_HTTP_PROXY" not in services[service_name]["environment"]
    assert "INTERNAL_JWT_AUDIENCE" not in services["langgraph-api"]["environment"]
    assert (
        services["langgraph-api"]["environment"]["INTERNAL_JWT_MAX_TTL_SECONDS"]
        == "60"
    )

    assert _volume_sources(services["command-worker"]) == {
        "/run/internal-jwt-private": "internal-jwt-private",
        "/run/internal-jwt-public": "internal-jwt-public",
    }
    assert services["command-worker"]["environment"][
        "INTERNAL_JWT_PUBLIC_KEY_FILE"
    ] == "/run/internal-jwt-public/public.pem"
    assert _volume_sources(services["frontend"]) == {
        "/run/internal-jwt-private": "internal-jwt-private"
    }
    assert _volume_sources(services["langgraph-api"]) == {
        "/run/internal-jwt-public": "internal-jwt-public",
        "/run/product-inbox-cursor-key": "product-inbox-cursor-key",
    }
    assert _volume_sources(services["langgraph-api-readiness"]) == {
        "/run/internal-jwt-private": "internal-jwt-private"
    }
    private_key_consumers = {
        service_name
        for service_name, service in services.items()
        if service_name != "internal-jwt-keys"
        and "internal-jwt-private" in _volume_sources(service).values()
    }
    assert private_key_consumers == {
        "langgraph-api-readiness",
        "command-worker",
        "frontend",
    }
    assert (
        services["langgraph-api-readiness"]["depends_on"]["langgraph-api"][
            "condition"
        ]
        == "service_healthy"
    )
    assert (
        services["command-worker"]["depends_on"]["langgraph-api-readiness"][
            "condition"
        ]
        == "service_completed_successfully"
    )
    assert {
        dependency: settings["condition"]
        for dependency, settings in services["langgraph-api"]["depends_on"].items()
    } == {
        "agent-postgres": "service_healthy",
        "langgraph-redis": "service_healthy",
        "migrate": "service_completed_successfully",
        "internal-jwt-keys": "service_completed_successfully",
        "development-bootstrap": "service_completed_successfully",
    }
    assert (
        services["frontend"]["depends_on"]["langgraph-api"]["condition"]
        == "service_healthy"
    )

    compose_source = (ROOT / "docker-compose.yml").read_text()
    assert "agent-server:" not in compose_source
    assert "langgraph dev" not in compose_source
    assert "8011" not in compose_source
    assert "AGENT_SERVER_LOCAL_TOKEN" not in compose_source
    assert "local-agent-dev-only" not in compose_source
    assert "host.docker.internal:7890" not in compose_source


def test_backend_container_installs_the_v2_locked_project() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "backend/pyproject.toml" in dockerfile
    assert "backend/uv.lock" in dockerfile
    assert "uv sync --frozen" in dockerfile
    assert "COPY src /app/src" not in dockerfile


def _volume_sources(service: dict) -> dict[str, str]:
    return {volume["target"]: volume["source"] for volume in service.get("volumes", [])}
