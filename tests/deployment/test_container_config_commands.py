from __future__ import annotations

import copy
import os
import re
import subprocess
import tomllib
from json import loads as load_json
from pathlib import Path

import yaml
from pathspec import GitIgnoreSpec


ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = ROOT / "tools" / "v2" / "start_integration_stack.sh"
STOP_SCRIPT = ROOT / "tools" / "v2" / "stop_integration_stack.sh"
VERIFY_AGENT_IMAGE_SCRIPT = ROOT / "tools" / "v2" / "verify_agent_image.sh"
COMPOSE_PROJECT = "crypto-manual-alert-v2"

V2_SERVICES = {
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
BACKEND_IMAGE_SERVICES = {
    "migrate",
    "internal-jwt-keys",
    "development-bootstrap",
    "langgraph-api-readiness",
    "command-worker",
}
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


def _dependency_names(dependencies: list[str]) -> set[str]:
    return {
        re.split(r"[<>=!~\[; ]", dependency, maxsplit=1)[0].lower()
        for dependency in dependencies
    }


def _load_official_dockerfile() -> str:
    from langgraph_cli import config as langgraph_config

    config_path = ROOT / "backend" / "langgraph.json"
    config = langgraph_config.validate_config_file(config_path)
    dockerfile, _ = langgraph_config.config_to_docker(
        config_path,
        config,
        api_version="0.11.0",
    )
    return dockerfile


def _render_scrubbed_compose(extra_env: dict[str, str]) -> dict:
    compose = copy.deepcopy(_load_compose())
    for service in compose["services"].values():
        service.pop("env_file", None)
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            COMPOSE_PROJECT,
            "--project-directory",
            str(ROOT),
            "--file",
            "-",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env={
            "COMPOSE_DISABLE_ENV_FILE": "1",
            "HOME": os.environ["HOME"],
            "PATH": os.environ["PATH"],
        }
        | extra_env,
        input=yaml.safe_dump(compose),
        capture_output=True,
        text=True,
        check=True,
    )
    return load_json(result.stdout)


def _run_stop_script(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    capture = tmp_path / "docker-arguments"
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" >\"$DOCKER_CAPTURE\"\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return subprocess.run(
        ["bash", str(STOP_SCRIPT), *arguments],
        cwd=ROOT,
        env=os.environ
        | {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "DOCKER_CAPTURE": str(capture),
        },
        capture_output=True,
        text=True,
        check=False,
    )


def _run_start_script(
    tmp_path: Path, *, fail_compose_up: bool = False
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'docker' >>\"$DOCKER_CAPTURE\"\n"
        "printf '\\t%s' \"$@\" >>\"$DOCKER_CAPTURE\"\n"
        "printf '\\n' >>\"$DOCKER_CAPTURE\"\n"
        "if [[ \"${1:-}\" == image && \"${2:-}\" == inspect && "
        "\"${3:-}\" != --format ]]; then exit 1; fi\n"
        "if [[ \"${1:-}\" == image && \"${2:-}\" == inspect && "
        "\"${3:-}\" == --format ]]; then\n"
        "  printf '%s\\n' layer-one layer-two\n"
        "  if [[ \"${5:-}\" != *@sha256:* ]]; then printf '%s\\n' agent-layer; fi\n"
        "fi\n"
        "if [[ \"${FAIL_COMPOSE_UP:-0}\" == 1 ]]; then\n"
        "  for argument in \"$@\"; do\n"
        "    if [[ \"$argument\" == up ]]; then exit 42; fi\n"
        "  done\n"
        "fi\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    uv = bin_dir / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'uv' >>\"$UV_CAPTURE\"\n"
        "printf '\\t%s' \"$@\" >>\"$UV_CAPTURE\"\n"
        "printf '\\n' >>\"$UV_CAPTURE\"\n"
        "printf '%s\\n' \"$COMPOSE_PROJECT_NAME\" >\"$PROJECT_CAPTURE\"\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    return subprocess.run(
        ["bash", str(START_SCRIPT)],
        cwd=ROOT,
        env=os.environ
        | {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "DOCKER_CAPTURE": str(tmp_path / "docker-arguments"),
            "UV_CAPTURE": str(tmp_path / "uv-arguments"),
            "PROJECT_CAPTURE": str(tmp_path / "compose-project"),
            "COMPOSE_PROJECT_NAME": "foreign-project",
            "FAIL_COMPOSE_UP": "1" if fail_compose_up else "0",
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_backend_dockerfile_installs_only_the_locked_production_project():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert (
        "FROM python:3.12-slim@sha256:"
        "423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf"
    ) in dockerfile
    assert "PYTHON_BASE_IMAGE" not in dockerfile
    assert "WORKDIR /app/backend" in dockerfile
    assert "COPY backend/pyproject.toml backend/uv.lock ./" in dockerfile
    assert "uv sync --frozen --no-dev --no-install-project" in dockerfile
    assert "COPY backend ./" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert dockerfile.index("COPY backend/pyproject.toml backend/uv.lock ./") < (
        dockerfile.index("COPY backend ./")
    )
    assert "langgraph-runtime-inmem" not in dockerfile
    assert "langgraph dev" not in dockerfile
    assert "8011" not in dockerfile
    assert "uvicorn" not in dockerfile


def test_production_dependency_closure_excludes_cli_api_and_inmem_runtime():
    pyproject = tomllib.loads(
        (ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    )
    production_names = _dependency_names(pyproject["project"]["dependencies"])
    dev_dependencies = pyproject["dependency-groups"]["dev"]

    assert "langgraph-cli" not in production_names
    assert "langgraph-api" not in production_names
    assert "langgraph-cli[inmem]==0.4.31" in dev_dependencies
    assert "langgraph-api==0.11.0" in dev_dependencies

    exported = subprocess.run(
        [
            "uv",
            "export",
            "--project",
            "backend",
            "--frozen",
            "--no-dev",
            "--no-emit-project",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.lower()
    assert "langgraph-cli==" not in exported
    assert "langgraph-api==" not in exported
    assert "langgraph-runtime-inmem==" not in exported


def test_frontend_dockerfile_builds_locked_next_runtime_without_public_upstreams():
    dockerfile = (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")

    assert (
        "FROM node:22-alpine@sha256:"
        "16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2"
    ) in dockerfile
    assert dockerfile.count("FROM node:22-alpine@sha256:") == 3
    assert "NODE_BASE_IMAGE" not in dockerfile
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


def test_compose_declares_the_official_durable_v2_topology():
    compose = _load_compose()
    services = compose["services"]

    assert compose["name"] == COMPOSE_PROJECT
    assert set(services) == V2_SERVICES
    assert services["langgraph-api"]["image"] == (
        "${LANGGRAPH_API_LOCAL_IMAGE:-crypto-manual-alert-v2-langgraph-api:local}"
    )
    assert {
        "postgres",
        "agent-server",
        "product-api",
        "langgraph-postgres",
        "api",
    }.isdisjoint(services)


def test_compose_isolates_product_and_agent_postgres():
    compose = _load_compose()
    services = compose["services"]

    expected = {
        "product-postgres": {
            "POSTGRES_DB": "${PRODUCT_POSTGRES_DB:-crypto_alert_v2}",
            "POSTGRES_USER": "${PRODUCT_POSTGRES_USER:-crypto_alert}",
            "POSTGRES_PASSWORD": "${PRODUCT_POSTGRES_PASSWORD:-crypto_alert_local}",
        },
        "agent-postgres": {
            "POSTGRES_DB": "${AGENT_POSTGRES_DB:-langgraph}",
            "POSTGRES_USER": "${AGENT_POSTGRES_USER:-langgraph}",
            "POSTGRES_PASSWORD": "${AGENT_POSTGRES_PASSWORD:-langgraph_local}",
        },
    }
    for service_name, environment in expected.items():
        service = services[service_name]
        assert service["environment"] == environment
        assert "ports" not in service
        assert "pg_isready" in " ".join(service["healthcheck"]["test"])

    assert services["product-postgres"]["image"] == (
        "postgres:16-alpine@sha256:"
        "57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"
    )
    assert services["agent-postgres"]["image"] == (
        "pgvector/pgvector:pg16@sha256:"
        "1d533553fefe4f12e5d80c7b80622ba0c382abb5758856f52983d8789179f0fb"
    )
    assert services["langgraph-redis"]["image"] == (
        "public.ecr.aws/docker/library/redis:7-alpine@sha256:"
        "6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99"
    )

    assert _structured_volumes(services["product-postgres"])[
        "/var/lib/postgresql/data"
    ]["source"] == "product-postgres-data"
    assert _structured_volumes(services["agent-postgres"])[
        "/var/lib/postgresql/data"
    ]["source"] == "agent-postgres-data"
    assert {"product-postgres-data", "agent-postgres-data"} <= set(
        compose["volumes"]
    )


def test_compose_owns_secure_durable_runtime_fields():
    services = _load_compose()["services"]
    api = services["langgraph-api"]

    assert api["ports"] == ["127.0.0.1:${AGENT_SERVER_PORT:-8123}:8000"]
    assert api["environment"]["POSTGRES_URI"] == (
        "${COMPOSE_AGENT_POSTGRES_URI:-postgres://langgraph:langgraph_local@"
        "agent-postgres:5432/langgraph?sslmode=disable}"
    )
    assert api["environment"]["REDIS_URI"] == "redis://langgraph-redis:6379"
    assert api["pull_policy"] == "never"
    assert "@sha256:" in services["langgraph-redis"]["image"]
    assert "redis-cli ping" in " ".join(
        services["langgraph-redis"]["healthcheck"]["test"]
    )

    rendered = _render_scrubbed_compose({})["services"]["langgraph-api"]
    assert rendered["ports"] == [
        {
            "mode": "ingress",
            "host_ip": "127.0.0.1",
            "target": 8000,
            "published": "8123",
            "protocol": "tcp",
        }
    ]

    result = subprocess.run(
        ["docker", "compose", "config", "--no-env-resolution", "--quiet"],
        cwd=ROOT,
        env=os.environ | {"COMPOSE_DISABLE_ENV_FILE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_official_agent_build_consumes_uv_lock_and_pinned_base_digest():
    config = load_json((ROOT / "backend" / "langgraph.json").read_text())
    assert config["source"] == {"kind": "uv", "root": "."}
    assert "dependencies" not in config

    dockerfile = _load_official_dockerfile()
    assert dockerfile.startswith("FROM langchain/langgraph-api:0.11.0-py3.12")
    assert "# -- Installing dependencies from uv.lock --" in dockerfile
    assert "ADD pyproject.toml /tmp/uv_export/project/pyproject.toml" in dockerfile
    assert "ADD uv.lock /tmp/uv_export/project/uv.lock" in dockerfile
    assert "uv export --package crypto-manual-alert-v2 --frozen" in dockerfile
    assert "ENV UV_NO_DEFAULT_GROUPS=1" in dockerfile
    assert dockerfile.index("ENV UV_NO_DEFAULT_GROUPS=1") < dockerfile.index(
        "RUN uv export --package crypto-manual-alert-v2 --frozen"
    )
    for excluded in (
        "ADD .env ",
        "ADD .coverage ",
        "ADD .langgraph_api ",
        "ADD .pytest_cache ",
        "ADD tests ",
    ):
        assert excluded not in dockerfile

    image_lock = (ROOT / "deploy" / "agent-server-image.lock").read_text(
        encoding="utf-8"
    ).strip()
    assert image_lock == (
        "langchain/langgraph-api@sha256:"
        "e8be3c8fc3f30407c355def446bfee019a86b180dbbd8985d109d21ac3673bba"
    )


def test_compose_builds_pinned_helpers_from_repo_root():
    services = _load_compose()["services"]

    assert {name for name, service in services.items() if "build" in service} == {
        "migrate",
        "frontend",
    }
    assert services["migrate"]["build"] == {
        "context": ".",
        "dockerfile": "Dockerfile",
    }
    for service_name in BACKEND_IMAGE_SERVICES:
        assert services[service_name]["image"] == (
            "crypto-manual-alert-v2-backend:local"
        )
        assert services[service_name]["pull_policy"] == "never"

    assert services["frontend"]["build"] == {
        "context": ".",
        "dockerfile": "Dockerfile.frontend",
    }
    assert services["frontend"]["image"] == (
        "crypto-manual-alert-v2-frontend:local"
    )
    assert services["frontend"]["pull_policy"] == "never"

    for service_name in BACKEND_IMAGE_SERVICES | {"frontend", "langgraph-api"}:
        assert services[service_name]["pull_policy"] == "never"


def test_start_script_builds_locked_official_agent_and_scoped_stack(
    tmp_path: Path,
):
    script = START_SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert "uv run --frozen langgraph build" in script
    assert '--config "$BACKEND_DIR/langgraph.json"' in script
    assert '--api-version "0.11.0"' in script
    assert '--tag "$AGENT_LOCAL_IMAGE"' in script
    assert "--no-pull" in script
    assert "--wait" in script
    assert '--wait-timeout "$START_WAIT_TIMEOUT_SECONDS"' in script
    assert "START_WAIT_TIMEOUT_SECONDS=180" in script
    assert '"$AGENT_IMAGE_VERIFIER" "$AGENT_BASE_IMAGE" "$AGENT_LOCAL_IMAGE"' in script
    assert "cleanup_failed_start" in script
    assert '"$STOP_SCRIPT" || true' in script
    assert 'docker pull "$AGENT_BASE_IMAGE"' in script
    assert 'docker tag "$AGENT_BASE_IMAGE" "$AGENT_BASE_TAG"' in script
    for forbidden in (
        "langgraph dev",
        "langgraph up",
        "8011",
        "source ",
        "backend/.env",
        "printenv",
        "set -x",
    ):
        assert forbidden not in script

    syntax = subprocess.run(
        ["bash", "-n", str(START_SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    result = _run_start_script(tmp_path)
    assert result.returncode == 0, result.stderr
    digest = (
        "langchain/langgraph-api@sha256:"
        "e8be3c8fc3f30407c355def446bfee019a86b180dbbd8985d109d21ac3673bba"
    )
    docker_calls = [
        line.split("\t")
        for line in (tmp_path / "docker-arguments")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("docker\t")
    ]
    assert docker_calls[:4] == [
        ["docker", "image", "inspect", digest],
        ["docker", "pull", digest],
        ["docker", "tag", digest, "langchain/langgraph-api:0.11.0-py3.12"],
        [
            "docker",
            "compose",
            "--project-name",
            COMPOSE_PROJECT,
            "--project-directory",
            str(ROOT),
            "--file",
            str(ROOT / "docker-compose.yml"),
            "build",
            "migrate",
            "frontend",
        ],
    ]
    assert docker_calls[4][0:4] == ["docker", "image", "inspect", "--format"]
    assert docker_calls[4][-1] == digest
    assert docker_calls[5][0:4] == ["docker", "image", "inspect", "--format"]
    assert docker_calls[5][-1] == "crypto-manual-alert-v2-langgraph-api:local"
    assert docker_calls[6][0:3] == ["docker", "run", "--rm"]
    assert docker_calls[6][-3] == "crypto-manual-alert-v2-langgraph-api:local"
    assert docker_calls[6][-2] == "-c"
    assert docker_calls[7] == [
            "docker",
            "compose",
            "--project-name",
            COMPOSE_PROJECT,
            "--project-directory",
            str(ROOT),
            "--file",
            str(ROOT / "docker-compose.yml"),
            "up",
            "--detach",
            "--wait",
            "--wait-timeout",
            "180",
            "--remove-orphans",
    ]
    uv_calls = [
        line.split("\t")
        for line in (tmp_path / "uv-arguments").read_text(encoding="utf-8").splitlines()
    ]
    assert uv_calls == [[
        "uv",
        "run",
        "--frozen",
        "langgraph",
        "build",
        "--config",
        str(ROOT / "backend" / "langgraph.json"),
        "--api-version",
        "0.11.0",
        "--tag",
        "crypto-manual-alert-v2-langgraph-api:local",
        "--no-pull",
    ]]
    assert (tmp_path / "compose-project").read_text(encoding="utf-8").strip() == (
        COMPOSE_PROJECT
    )


def test_start_script_cleans_up_the_scoped_project_after_wait_failure(tmp_path: Path):
    result = _run_start_script(tmp_path, fail_compose_up=True)

    assert result.returncode == 42
    docker_calls = [
        line.split("\t")
        for line in (tmp_path / "docker-arguments")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("docker\t")
    ]
    assert docker_calls[-1] == [
        "docker",
        "compose",
        "--project-name",
        COMPOSE_PROJECT,
        "--project-directory",
        str(ROOT),
        "--file",
        str(ROOT / "docker-compose.yml"),
        "down",
        "--remove-orphans",
    ]


def test_agent_image_verifier_binds_layers_mappings_and_dependencies():
    script = VERIFY_AGENT_IMAGE_SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert ".RootFS.Layers" in script
    assert '"${agent_layers[$index]}" != "${base_layers[$index]}"' in script
    assert "--network none" in script
    assert "--read-only" in script
    assert '"LANGGRAPH_AUTH"' in script
    assert '"LANGGRAPH_HTTP"' in script
    assert '"LANGSERVE_GRAPHS"' in script
    assert '"langgraph-api": "0.11.0"' in script
    assert '"crypto-manual-alert-v2": "2.0.0"' in script
    assert '("langgraph-cli", "langgraph-runtime-inmem", "pytest")' in script

    syntax = subprocess.run(
        ["bash", "-n", str(VERIFY_AGENT_IMAGE_SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr


def test_stop_script_scopes_cleanup_and_preserves_volumes_by_default(tmp_path: Path):
    script = STOP_SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert f'COMPOSE_PROJECT_NAME="{COMPOSE_PROJECT}"' in script
    assert '--project-name "$COMPOSE_PROJECT_NAME"' in script
    assert '--project-directory "$ROOT_DIR"' in script
    assert '--file "$ROOT_DIR/docker-compose.yml"' in script
    assert "--remove-orphans" in script

    default_result = _run_stop_script(tmp_path)
    assert default_result.returncode == 0, default_result.stderr
    default_args = (tmp_path / "docker-arguments").read_text(
        encoding="utf-8"
    ).splitlines()
    assert default_args == [
        "compose",
        "--project-name",
        COMPOSE_PROJECT,
        "--project-directory",
        str(ROOT),
        "--file",
        str(ROOT / "docker-compose.yml"),
        "down",
        "--remove-orphans",
    ]

    volume_result = _run_stop_script(tmp_path, "--volumes")
    assert volume_result.returncode == 0, volume_result.stderr
    volume_args = (tmp_path / "docker-arguments").read_text(
        encoding="utf-8"
    ).splitlines()
    assert volume_args == [*default_args, "--volumes"]

    invalid_result = _run_stop_script(tmp_path, "--unexpected")
    assert invalid_result.returncode != 0


def test_compose_commands_use_product_helpers_and_no_custom_runtime():
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
    assert services["langgraph-api-readiness"]["command"] == [
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
    assert "command" not in services["langgraph-api"]

    compose_source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for forbidden in ("langgraph dev", "agent-server:", "8011", "8123:8123"):
        assert forbidden not in compose_source


def test_all_container_upstreams_use_the_official_api_service():
    services = _load_compose()["services"]
    upstream_consumers = {
        "langgraph-api",
        "langgraph-api-readiness",
        "command-worker",
        "frontend",
    }

    for service_name in upstream_consumers:
        assert services[service_name]["environment"]["AGENT_SERVER_URL"] == (
            "http://langgraph-api:8000"
        )
    assert services["frontend"]["environment"]["PRODUCT_API_BASE_URL"] == (
        "http://langgraph-api:8000/app"
    )
    assert services["frontend"]["ports"] == [
        "127.0.0.1:${FRONTEND_PORT:-3001}:3001"
    ]
    assert not any(
        name.startswith("NEXT_PUBLIC_")
        for name in services["frontend"]["environment"]
    )


def test_official_api_gets_product_state_auth_and_production_settings():
    services = _load_compose()["services"]
    api = services["langgraph-api"]
    environment = api["environment"]

    assert environment["APP_ENVIRONMENT"] == "production"
    assert environment["PRODUCT_DATABASE_URL"] == (
        "${COMPOSE_PRODUCT_DATABASE_URL:-postgresql+asyncpg://crypto_alert:"
        "crypto_alert_local@product-postgres:5432/crypto_alert_v2}"
    )
    assert environment["AGENT_SERVER_INTERNAL_JWT_AUDIENCE"] == (
        "crypto-alert-agent-server"
    )
    assert environment["INTERNAL_JWT_PUBLIC_KEY_FILE"] == (
        "/run/internal-jwt-public/public.pem"
    )
    assert environment["INTERNAL_JWT_MAX_TTL_SECONDS"] == "60"
    assert "INTERNAL_JWT_PRIVATE_KEY_FILE" not in environment
    assert "INTERNAL_JWT_AUDIENCE" not in environment
    assert _structured_volumes(api) == {
        "/run/internal-jwt-public": {
            "type": "volume",
            "source": "internal-jwt-public",
            "target": "/run/internal-jwt-public",
            "read_only": True,
        }
    }


def test_compose_accepts_complete_percent_encoded_database_uris():
    product_uri = (
        "postgresql+asyncpg://app:p%40ss%3Aword%2F%3F%23@"
        "product-postgres:5432/crypto%20alert"
    )
    agent_uri = (
        "postgres://agent:p%40ss%3Aword%2F%3F%23@"
        "agent-postgres:5432/lang%20graph?sslmode=disable"
    )
    services = _render_scrubbed_compose(
        {
            "COMPOSE_PRODUCT_DATABASE_URL": product_uri,
            "COMPOSE_AGENT_POSTGRES_URI": agent_uri,
        }
    )["services"]

    for service_name in (
        "migrate",
        "development-bootstrap",
        "langgraph-api",
        "command-worker",
    ):
        assert services[service_name]["environment"]["PRODUCT_DATABASE_URL"] == (
            product_uri
        )
    assert services["langgraph-api"]["environment"]["POSTGRES_URI"] == agent_uri


def test_authenticated_readiness_targets_official_api_and_gates_worker():
    services = _load_compose()["services"]
    readiness = services["langgraph-api-readiness"]
    readiness_environment = readiness["environment"]

    assert readiness["restart"] == "on-failure:12"
    assert readiness_environment["AGENT_SERVER_URL"] == "http://langgraph-api:8000"
    assert services["command-worker"]["depends_on"][
        "langgraph-api-readiness"
    ] == {"condition": "service_completed_successfully"}
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
        if service_name != "langgraph-api-readiness":
            assert not any(
                name.startswith("AGENT_HEALTHCHECK_")
                for name in service.get("environment", {})
            )


def test_compose_dependencies_gate_both_databases_auth_and_readiness_in_order():
    services = _load_compose()["services"]
    expected_dependencies = {
        "migrate": {"product-postgres": "service_healthy"},
        "development-bootstrap": {"migrate": "service_completed_successfully"},
        "langgraph-api": {
            "agent-postgres": "service_healthy",
            "langgraph-redis": "service_healthy",
            "migrate": "service_completed_successfully",
            "internal-jwt-keys": "service_completed_successfully",
            "development-bootstrap": "service_completed_successfully",
        },
        "langgraph-api-readiness": {
            "internal-jwt-keys": "service_completed_successfully",
            "langgraph-api": "service_healthy",
        },
        "command-worker": {
            "migrate": "service_completed_successfully",
            "internal-jwt-keys": "service_completed_successfully",
            "development-bootstrap": "service_completed_successfully",
            "langgraph-api-readiness": "service_completed_successfully",
        },
        "frontend": {
            "langgraph-api": "service_healthy",
            "langgraph-api-readiness": "service_completed_successfully",
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


def test_compose_secret_consumers_and_jwt_mounts_follow_least_privilege():
    services = _load_compose()["services"]

    env_file_services = {
        name for name, service in services.items() if "env_file" in service
    }
    assert env_file_services == {"langgraph-api", "command-worker"}
    for service_name in env_file_services:
        assert services[service_name]["env_file"] == [
            {"path": "backend/.env", "required": False}
        ]

    expected_mounts = {
        "langgraph-api": {"/run/internal-jwt-public": "internal-jwt-public"},
        "langgraph-api-readiness": {
            "/run/internal-jwt-private": "internal-jwt-private"
        },
        "command-worker": {
            "/run/internal-jwt-private": "internal-jwt-private",
            "/run/internal-jwt-public": "internal-jwt-public",
        },
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
        "langgraph-api-readiness",
        "command-worker",
        "frontend",
    }


def test_compose_separates_bootstrap_from_production_services():
    services = _load_compose()["services"]

    for service_name in (
        "langgraph-api",
        "langgraph-api-readiness",
        "command-worker",
    ):
        assert services[service_name]["environment"]["APP_ENVIRONMENT"] == (
            "production"
        )

    for service_name in ("development-bootstrap", "frontend"):
        environment = services[service_name]["environment"]
        assert environment["APP_ENVIRONMENT"] == "development"
        assert environment["DEVELOPMENT_BOOTSTRAP_ENABLED"] == "true"
        assert environment["DEVELOPMENT_BOOTSTRAP_PROFILE"] == "local-proof"

    assert services["langgraph-api"]["environment"]["MARKET_DATA_HTTP_PROXY"] == (
        "${MARKET_DATA_HTTP_PROXY:-}"
    )
    for service_name in V2_SERVICES - {"langgraph-api"}:
        assert "MARKET_DATA_HTTP_PROXY" not in services[service_name].get(
            "environment", {}
        )


def test_container_build_context_and_compose_avoid_secret_or_host_mounts():
    dockerignore_patterns = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    agent_dockerignore_patterns = {
        line.strip()
        for line in (ROOT / "backend" / ".dockerignore")
        .read_text(encoding="utf-8")
        .splitlines()
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
    assert {
        "**/.env*",
        ".venv/",
        ".langgraph_api/",
        ".pytest_cache/",
        ".coverage",
        "tests/",
        "**/*.pem",
        "**/*.key",
        "**/secrets/",
        "**/credentials/",
    } <= agent_dockerignore_patterns

    agent_ignore = GitIgnoreSpec.from_lines(agent_dockerignore_patterns)
    for nested_environment_file in (
        ".env",
        ".env.example",
        "src/crypto_alert_v2/providers/.env.local",
        "alembic/versions/private/.env.production",
    ):
        assert agent_ignore.match_file(nested_environment_file)

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
        "durable-cancel-flow.spec.ts",
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
