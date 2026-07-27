import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_local_integration_uses_aegra_without_commercial_entitlement() -> None:
    script = (ROOT / "tools" / "v2" / "start_integration_stack.sh").read_text()

    assert "aegra.json" in script
    assert "verify_agent_image.sh" in script
    assert "LANGGRAPH_CLOUD_LICENSE_KEY" not in script
    assert "agent-server-image.lock" not in script


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
            "NOTIFICATION_CREDENTIAL_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            "NOTIFICATION_CREDENTIAL_DECRYPT_KEYS": '{"v0":"old-key-placeholder"}',
            "INTERNAL_JWT_PUBLIC_KEYS": '{"old":"old-public-key-placeholder"}',
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
        "integration-secret-files",
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

    assert services["command-worker"]["command"] == [
        "python",
        "-m",
        "crypto_alert_v2.workers",
        "--worker-id",
        "compose-worker",
    ]
    assert services["frontend"]["environment"]["PRODUCT_API_BASE_URL"] == (
        "http://langgraph-api:8000/app"
    )
    assert services["frontend"]["environment"]["AGENT_SERVER_URL"] == (
        "http://langgraph-api:8000"
    )
    assert (
        services["frontend"]["environment"]["AGENT_SERVER_INTERNAL_JWT_AUDIENCE"]
        == "crypto-alert-agent-server"
    )
    assert not any(
        name.startswith("NEXT_PUBLIC_") and "AGENT_SERVER" in name
        for name in services["frontend"]["environment"]
    )
    assert services["langgraph-api"]["environment"]["PRODUCT_DATABASE_URL"].startswith(
        "postgresql+asyncpg://"
    )
    assert services["langgraph-api"]["command"] == [
        "aegra",
        "serve",
        "--config",
        "aegra.json",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    aegra_environment = services["langgraph-api"]["environment"]
    assert aegra_environment["REDIS_BROKER_ENABLED"] == "true"
    assert aegra_environment["REDIS_URL"] == "redis://langgraph-redis:6379/0"
    assert aegra_environment["WORKER_COUNT"] == "1"
    assert aegra_environment["N_JOBS_PER_WORKER"] == "2"
    assert aegra_environment["LEASE_DURATION_SECONDS"] == "30"
    assert aegra_environment["HEARTBEAT_INTERVAL_SECONDS"] == "10"
    assert aegra_environment["REAPER_INTERVAL_SECONDS"] == "15"
    assert aegra_environment["STUCK_PENDING_THRESHOLD_SECONDS"] == "120"
    assert "LANGGRAPH_CLOUD_LICENSE_KEY" not in aegra_environment
    assert services["langgraph-api"]["environment"]["SEARCH_PROVIDER"] == (
        "builtin_web_search"
    )
    assert services["langgraph-api"]["environment"]["SEARCH_HTTP_PROXY"] == ""
    secret_store_environment = services["integration-secret-files"]["environment"]
    assert secret_store_environment["NOTIFICATION_CREDENTIAL_KEY"] == (
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    )
    assert secret_store_environment["NOTIFICATION_CREDENTIAL_DECRYPT_KEYS"] == (
        '{"v0":"old-key-placeholder"}'
    )
    for service_name in ("langgraph-api", "command-worker"):
        environment = services[service_name]["environment"]
        assert environment["INTEGRATION_SECRET_STORE"] == "file"
        assert environment["INTEGRATION_SECRET_FILE_DIR"] == "/run/integration-secrets"
        assert "NOTIFICATION_CREDENTIAL_KEY" not in environment
        assert "NOTIFICATION_CREDENTIAL_DECRYPT_KEYS" not in environment
        assert environment["INTERNAL_JWT_PUBLIC_KEYS"] == (
            '{"old":"old-public-key-placeholder"}'
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
        "DEVELOPMENT_BOOTSTRAP_IDENTITY_ISSUER": "crypto-alert-v2-compose",
        "DEVELOPMENT_BOOTSTRAP_CONTEXT_ID": "99999999-9999-4999-8999-999999999999",
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
    assert services["langgraph-api-readiness"]["restart"] == "unless-stopped"
    readiness_environment = services["langgraph-api-readiness"]["environment"]
    assert readiness_environment["AGENT_SERVER_URL"] == "http://langgraph-api:8000"
    assert readiness_environment["SEARCH_PROVIDER"] == "builtin_web_search"
    assert readiness_environment["AGENT_HEALTHCHECK_EXPECTED_SEARCH_PROVIDER"] == (
        "builtin_web_search"
    )
    assert readiness_environment["AGENT_READINESS_HOST"] == "0.0.0.0"
    assert readiness_environment["AGENT_READINESS_PORT"] == "9091"
    assert readiness_environment["AGENT_HEALTHCHECK_SUBJECT"] == "probe-user"
    assert readiness_environment["AGENT_HEALTHCHECK_TENANT_ID"] == "probe-tenant"
    assert readiness_environment["AGENT_HEALTHCHECK_WORKSPACE_ID"] == "probe-workspace"
    assert readiness_environment["AGENT_HEALTHCHECK_ROLES"] == '["operator"]'
    assert readiness_environment["AGENT_HEALTHCHECK_PERMISSIONS"] == (
        '["analysis:read"]'
    )
    assert not any(
        name.startswith("DEVELOPMENT_BOOTSTRAP_") for name in readiness_environment
    )
    assert {
        name for name in readiness_environment if name.startswith("AGENT_HEALTHCHECK_")
    } == {
        "AGENT_HEALTHCHECK_SUBJECT",
        "AGENT_HEALTHCHECK_TENANT_ID",
        "AGENT_HEALTHCHECK_WORKSPACE_ID",
        "AGENT_HEALTHCHECK_ROLES",
        "AGENT_HEALTHCHECK_PERMISSIONS",
        "AGENT_HEALTHCHECK_EXPECTED_SEARCH_PROVIDER",
    }
    for service_name, service in services.items():
        if service_name != "langgraph-api-readiness":
            assert not any(
                name.startswith("AGENT_HEALTHCHECK_")
                for name in service.get("environment", {})
            )
    agent_liveness = services["langgraph-api"]["healthcheck"]["test"]
    assert agent_liveness[:3] == ["CMD", "python", "-c"]
    assert "http://127.0.0.1:8000/health" in agent_liveness[-1]
    assert (
        "INTERNAL_JWT_PRIVATE_KEY_FILE" not in services["langgraph-api"]["environment"]
    )
    frontend_healthcheck = services["frontend"]["healthcheck"]["test"]
    assert services["frontend"]["environment"]["PRODUCT_API_TIMEOUT_MS"] == "8000"
    assert "/api/product/api/v2/readiness" in frontend_healthcheck[-1]
    assert "/api/product/api/v2/runs?limit=1" in frontend_healthcheck[-1]
    assert "/work" in frontend_healthcheck[-1]
    worker_healthcheck = services["command-worker"]["healthcheck"]["test"]
    assert worker_healthcheck[:3] == ["CMD", "python", "-c"]
    assert "/readyz" in worker_healthcheck[-1]
    worker_environment = services["command-worker"]["environment"]
    assert worker_environment["WORKER_READINESS_FAILURE_THRESHOLD"] == "3"
    assert worker_environment["WORKER_READINESS_STALE_AFTER_SECONDS"] == "30"
    readiness_healthcheck = services["langgraph-api-readiness"]["healthcheck"]["test"]
    assert readiness_healthcheck[:3] == ["CMD", "python", "-c"]
    assert "http://127.0.0.1:9091/readyz" in readiness_healthcheck[-1]
    assert services["langgraph-api"]["environment"]["AGENT_READINESS_URL"] == (
        "http://langgraph-api-readiness:9091/readyz"
    )
    assert (
        services["langgraph-api"]["environment"]["AGENT_SERVER_INTERNAL_JWT_AUDIENCE"]
        == "crypto-alert-agent-server"
    )
    assert services["langgraph-api"]["environment"]["MARKET_DATA_HTTP_PROXY"] == (
        "http://proxy.example:7890"
    )
    assert (
        services["langgraph-api"]["environment"]["PRODUCT_INBOX_CURSOR_KEY_FILE"]
        == "/run/product-inbox-cursor-key/key"
    )
    for service_name in (
        "development-bootstrap",
        "langgraph-api-readiness",
        "frontend",
    ):
        assert "MARKET_DATA_HTTP_PROXY" not in services[service_name]["environment"]
    assert services["command-worker"]["environment"]["MARKET_DATA_HTTP_PROXY"] == (
        "http://proxy.example:7890"
    )
    assert "INTERNAL_JWT_AUDIENCE" not in services["langgraph-api"]["environment"]
    assert (
        services["langgraph-api"]["environment"]["INTERNAL_JWT_MAX_TTL_SECONDS"] == "60"
    )

    assert _volume_sources(services["command-worker"]) == {
        "/run/internal-jwt-private": "internal-jwt-private",
        "/run/internal-jwt-public": "internal-jwt-public",
        "/run/integration-secrets": "integration-secret-files",
    }
    assert (
        services["command-worker"]["environment"]["INTERNAL_JWT_PUBLIC_KEY_FILE"]
        == "/run/internal-jwt-public/public.pem"
    )
    assert _volume_sources(services["frontend"]) == {
        "/run/internal-jwt-private": "internal-jwt-private"
    }
    assert _volume_sources(services["langgraph-api"]) == {
        "/run/internal-jwt-public": "internal-jwt-public",
        "/run/product-inbox-cursor-key": "product-inbox-cursor-key",
        "/run/integration-secrets": "integration-secret-files",
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
        services["langgraph-api-readiness"]["depends_on"]["langgraph-api"]["condition"]
        == "service_healthy"
    )
    assert (
        services["command-worker"]["depends_on"]["langgraph-api-readiness"]["condition"]
        == "service_healthy"
    )
    assert {
        dependency: settings["condition"]
        for dependency, settings in services["langgraph-api"]["depends_on"].items()
    } == {
        "agent-postgres": "service_healthy",
        "langgraph-redis": "service_healthy",
        "migrate": "service_completed_successfully",
        "internal-jwt-keys": "service_completed_successfully",
        "integration-secret-files": "service_completed_successfully",
        "development-bootstrap": "service_completed_successfully",
    }
    assert (
        services["frontend"]["depends_on"]["langgraph-api"]["condition"]
        == "service_healthy"
    )
    assert (
        services["frontend"]["depends_on"]["command-worker"]["condition"]
        == "service_healthy"
    )

    compose_source = (ROOT / "docker-compose.yml").read_text()
    assert "agent-server:" not in compose_source
    assert "langgraph dev" not in compose_source
    assert "8011" not in compose_source
    assert "AGENT_SERVER_LOCAL_TOKEN" not in compose_source
    assert "LANGGRAPH_CLOUD_LICENSE_KEY" not in compose_source
    assert "aegra serve" not in compose_source
    assert "- aegra" in compose_source
    assert "local-agent-dev-only" not in compose_source
    assert "host.docker.internal:7890" not in compose_source


def test_backend_container_installs_the_v2_locked_project() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "backend/pyproject.toml" in dockerfile
    assert "backend/uv.lock" in dockerfile
    assert "uv sync --frozen" in dockerfile
    assert "COPY src /app/src" not in dockerfile


def test_production_worker_entrypoints_launch_both_durable_loops() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    compose = (ROOT / "docker-compose.yml").read_text()
    worker_main = (ROOT / "backend/src/crypto_alert_v2/workers/__main__.py").read_text()

    assert (
        'CMD ["python", "-m", "crypto_alert_v2.workers", "--worker-id", '
        '"container-worker"]'
    ) in dockerfile
    assert "crypto_alert_v2.commands.worker" not in dockerfile
    assert "crypto_alert_v2.commands.worker" not in compose
    assert '"commands": _CommandWorkerAdapter(command_dispatcher)' in worker_main
    assert '"notifications": notification_worker' in worker_main


def _volume_sources(service: dict) -> dict[str, str]:
    return {volume["target"]: volume["source"] for volume in service.get("volumes", [])}
