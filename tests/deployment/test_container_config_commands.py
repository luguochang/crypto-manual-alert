from __future__ import annotations

import copy
import os
import re
import shutil
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
    "integration-secret-files",
    "development-bootstrap",
    "langgraph-api",
    "langgraph-api-readiness",
    "command-worker",
    "frontend",
}
BACKEND_IMAGE_SERVICES = {
    "migrate",
    "internal-jwt-keys",
    "integration-secret-files",
    "development-bootstrap",
    "langgraph-api",
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


def _bash_executable() -> str:
    if os.name == "nt":
        candidates = (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Git"
            / "bin"
            / "bash.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Git"
            / "usr"
            / "bin"
            / "bash.exe",
        )
        match = next((candidate for candidate in candidates if candidate.is_file()), None)
        assert match is not None, "Git Bash is required for deployment script tests"
        return str(match)
    match = shutil.which("bash")
    assert match is not None, "bash is required for deployment script tests"
    return match


def _bash_path(path: Path) -> str:
    absolute = path.resolve()
    if os.name != "nt":
        return str(absolute)
    rendered = absolute.as_posix()
    return f"/{rendered[0].lower()}{rendered[2:]}"


def _bash_stub_path(bin_dir: Path) -> str:
    if os.name == "nt":
        return f"{_bash_path(bin_dir)}:/usr/bin:/bin"
    return f"{bin_dir}:{os.environ['PATH']}"


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


def _compose_command() -> list[str]:
    docker = shutil.which("docker")
    if os.name == "nt" and docker:
        standalone = Path(docker).with_name("docker-compose.exe")
        if standalone.is_file():
            return [str(standalone)]
    return ["docker", "compose"]


def _render_scrubbed_compose(extra_env: dict[str, str]) -> dict:
    compose = copy.deepcopy(_load_compose())
    for service in compose["services"].values():
        service.pop("env_file", None)
    result = subprocess.run(
        [
            *_compose_command(),
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
            "HOME": os.environ.get("HOME", str(Path.home())),
            "PATH": os.environ["PATH"],
            "NOTIFICATION_CREDENTIAL_KEY": "test-notification-placeholder",
            "NOTIFICATION_CREDENTIAL_DECRYPT_KEYS": "{}",
            "INTERNAL_JWT_PUBLIC_KEYS": "{}",
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
        [_bash_executable(), _bash_path(STOP_SCRIPT), *arguments],
        cwd=ROOT,
        env=os.environ
        | {
            "PATH": _bash_stub_path(bin_dir),
            "DOCKER_CAPTURE": _bash_path(capture),
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
        "if [[ \"${FAIL_COMPOSE_UP:-0}\" == 1 ]]; then\n"
        "  for argument in \"$@\"; do\n"
        "    if [[ \"$argument\" == up ]]; then exit 42; fi\n"
        "  done\n"
        "fi\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return subprocess.run(
        [_bash_executable(), _bash_path(START_SCRIPT)],
        cwd=ROOT,
        env=os.environ
        | {
            "PATH": _bash_stub_path(bin_dir),
            "DOCKER_CAPTURE": _bash_path(tmp_path / "docker-arguments"),
            "COMPOSE_PROJECT_NAME": "foreign-project",
            "FAIL_COMPOSE_UP": "1" if fail_compose_up else "0",
            "NOTIFICATION_CREDENTIAL_KEY": "test-notification-placeholder",
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
    assert "uv sync --frozen --no-dev --extra aegra --no-install-project" in dockerfile
    assert "COPY backend ./" in dockerfile
    assert "uv sync --frozen --no-dev --extra aegra" in dockerfile
    assert "ARG PIP_VERSION=26.1.2" in dockerfile
    assert "ARG LIBLZMA_VERSION=5.8.1-1+deb13u1" in dockerfile
    assert '"pip==${PIP_VERSION}"' in dockerfile
    assert '"liblzma5=${LIBLZMA_VERSION}"' in dockerfile
    assert dockerfile.index("COPY backend/pyproject.toml backend/uv.lock ./") < (
        dockerfile.index("COPY backend ./")
    )
    assert "langgraph-runtime-inmem" not in dockerfile
    assert "langgraph dev" not in dockerfile
    assert "8011" not in dockerfile
    assert "uvicorn" not in dockerfile


def test_production_dependency_closure_selects_aegra_and_excludes_dev_runtime():
    pyproject = tomllib.loads(
        (ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    )
    production_names = _dependency_names(pyproject["project"]["dependencies"])
    aegra_names = _dependency_names(pyproject["project"]["optional-dependencies"]["aegra"])
    dev_dependencies = pyproject["dependency-groups"]["dev"]

    assert "langgraph-cli" not in production_names
    assert "langgraph-api" not in production_names
    assert aegra_names == {"aegra-api", "aegra-cli"}
    assert "langgraph-cli[inmem]==0.4.31" in dev_dependencies
    assert "langgraph-api==0.11.1" in dev_dependencies
    assert pyproject["tool"]["uv"]["conflicts"] == [
        [{"extra": "aegra"}, {"group": "dev"}]
    ]

    exported = subprocess.run(
        [
            "uv",
            "export",
            "--project",
            "backend",
            "--frozen",
            "--no-dev",
            "--extra",
            "aegra",
            "--no-emit-project",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.lower()
    assert "aegra-api==0.9.24" in exported
    assert "aegra-cli==0.9.24" in exported
    assert "langgraph-cli==" not in exported
    assert "langgraph-api==" not in exported
    assert "langgraph-runtime-inmem==" not in exported


def test_frontend_dockerfile_builds_locked_next_runtime_without_public_upstreams():
    dockerfile = (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")

    assert (
        "FROM public.ecr.aws/docker/library/node:22@sha256:"
        "175215a1f306ed5df592434b99cc2019f70624373fe49cb659240a618a846aed"
    ) in dockerfile
    assert dockerfile.count(
        "FROM public.ecr.aws/docker/library/node:22@sha256:"
    ) == 3
    assert "NODE_BASE_IMAGE" not in dockerfile
    assert "COPY frontend/package.json frontend/package-lock.json ./" in dockerfile
    assert "RUN npm ci" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert "ENV NODE_ENV=production" in dockerfile
    assert "NEXT_TELEMETRY_DISABLED=1" in dockerfile
    assert "COPY --from=builder /app/frontend/.next ./.next" in dockerfile
    assert "COPY --from=builder /app/frontend/public ./public" in dockerfile
    assert "EXPOSE 3001" in dockerfile
    assert (
        'CMD ["npm", "exec", "next", "--", "start", "--hostname", '
        '"0.0.0.0", "--port", "3001"]'
    ) in dockerfile
    assert "NEXT_PUBLIC_" not in dockerfile


def test_compose_declares_the_aegra_durable_v2_topology():
    compose = _load_compose()
    services = compose["services"]

    assert compose["name"] == COMPOSE_PROJECT
    assert set(services) == V2_SERVICES
    assert services["langgraph-api"]["image"] == "crypto-manual-alert-v2-backend:local"
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
    assert api["environment"]["DATABASE_URL"] == (
        "${COMPOSE_AGENT_DATABASE_URL:-postgresql://langgraph:langgraph_local@"
        "agent-postgres:5432/langgraph?sslmode=disable}"
    )
    assert api["environment"]["REDIS_BROKER_ENABLED"] == "true"
    assert api["environment"]["REDIS_URL"] == "redis://langgraph-redis:6379/0"
    assert api["environment"]["WORKER_COUNT"] == "${AEGRA_WORKER_COUNT:-1}"
    assert api["environment"]["N_JOBS_PER_WORKER"] == "${AEGRA_JOBS_PER_WORKER:-2}"
    assert api["environment"]["LEASE_DURATION_SECONDS"] == (
        "${AEGRA_LEASE_DURATION_SECONDS:-30}"
    )
    assert api["environment"]["HEARTBEAT_INTERVAL_SECONDS"] == (
        "${AEGRA_HEARTBEAT_INTERVAL_SECONDS:-10}"
    )
    assert api["environment"]["REAPER_INTERVAL_SECONDS"] == (
        "${AEGRA_REAPER_INTERVAL_SECONDS:-15}"
    )
    assert api["environment"]["STUCK_PENDING_THRESHOLD_SECONDS"] == (
        "${AEGRA_STUCK_PENDING_THRESHOLD_SECONDS:-120}"
    )
    assert api["environment"]["AEGRA_CONFIG"] == "${AEGRA_CONFIG_BASENAME:-aegra.json}"
    assert api["command"] == [
        "aegra",
        "serve",
        "--config",
        "${AEGRA_CONFIG_BASENAME:-aegra.json}",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
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
        env=os.environ
        | {
            "COMPOSE_DISABLE_ENV_FILE": "1",
            "NOTIFICATION_CREDENTIAL_KEY": "test-notification-placeholder",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_aegra_runtime_uses_the_locked_extra_and_canonical_config():
    config = load_json((ROOT / "backend" / "aegra.json").read_text())
    langgraph = load_json((ROOT / "backend" / "langgraph.json").read_text())
    assert config == {
        "graphs": {
            **langgraph["graphs"],
            "candidate_review": (
                "./src/crypto_alert_v2/evaluation/review_graph.py:graph_factory"
            ),
        },
        "auth": langgraph["auth"],
        "http": langgraph["http"],
    }
    assert "env" not in config
    assert not (ROOT / "deploy" / "agent-server-image.lock").exists()
    lock = (ROOT / "backend" / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "aegra-api"' in lock
    assert 'name = "aegra-cli"' in lock


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


def test_start_script_builds_locked_aegra_image_and_scoped_stack(
    tmp_path: Path,
):
    script = START_SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert (
        'AEGRA_CONFIG_FILE="${AEGRA_CONFIG_FILE:-${LANGGRAPH_CONFIG_FILE:-$BACKEND_DIR/aegra.json}}"'
        in script
    )
    assert 'AEGRA_CONFIG_BASENAME="$(basename "$AEGRA_CONFIG_FILE")"' in script
    assert '"$BACKEND_DIR/aegra.task8-qa.json"' in script
    assert "--wait" in script
    assert '--wait-timeout "$START_WAIT_TIMEOUT_SECONDS"' in script
    assert "START_WAIT_TIMEOUT_SECONDS=180" in script
    assert "--allow-multi-interrupt-fixture" in script
    assert '"$AGENT_IMAGE_VERIFIER" "$AGENT_LOCAL_IMAGE"' in script
    assert "cleanup_failed_start" in script
    assert '"$STOP_SCRIPT" || true' in script
    for forbidden in (
        "LANGGRAPH_CLOUD_LICENSE_KEY",
        "agent-server-image.lock",
        "langgraph build",
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
        [_bash_executable(), "-n", _bash_path(START_SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    result = _run_start_script(tmp_path)
    assert result.returncode == 0, result.stderr
    docker_calls = [
        line.split("\t")
        for line in (tmp_path / "docker-arguments")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("docker\t")
    ]
    assert docker_calls[0] == [
        "docker",
        "compose",
        "--project-name",
        COMPOSE_PROJECT,
        "--project-directory",
        _bash_path(ROOT),
        "--file",
        _bash_path(ROOT / "docker-compose.yml"),
        "build",
        "migrate",
        "frontend",
    ]
    assert docker_calls[1] == [
        "docker",
        "image",
        "inspect",
        "crypto-manual-alert-v2-backend:local",
    ]
    assert docker_calls[2][0:3] == ["docker", "run", "--rm"]
    assert "crypto-manual-alert-v2-backend:local" in docker_calls[2]
    assert docker_calls[2][-2] == "-c"
    assert docker_calls[3] == [
        "docker",
        "compose",
        "--project-name",
        COMPOSE_PROJECT,
        "--project-directory",
        _bash_path(ROOT),
        "--file",
        _bash_path(ROOT / "docker-compose.yml"),
        "up",
        "--detach",
        "--wait",
        "--wait-timeout",
        "180",
        "--remove-orphans",
    ]


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
        _bash_path(ROOT),
        "--file",
        _bash_path(ROOT / "docker-compose.yml"),
        "down",
        "--remove-orphans",
    ]


def test_agent_image_verifier_binds_aegra_config_and_dependencies():
    script = VERIFY_AGENT_IMAGE_SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert 'docker image inspect "$agent_image"' in script
    assert "--network none" in script
    assert "--read-only" in script
    assert '"aegra-api": "0.9.24"' in script
    assert '"aegra-cli": "0.9.24"' in script
    assert '"langgraph": "1.2.9"' in script
    assert '"langgraph-sdk": "0.4.2"' in script
    assert 'root = Path("/app/backend")' in script
    assert 'else "aegra.json"' in script
    assert "TASK8_ALLOW_MULTI_INTERRUPT_FIXTURE" in script
    assert "--allow-multi-interrupt-fixture" in script
    assert '"crypto-manual-alert-v2": "2.0.0"' in script
    for distribution in (
        '"langgraph-api"',
        '"langgraph-cli"',
        '"langgraph-runtime-inmem"',
        '"pytest"',
    ):
        assert distribution in script

    syntax = subprocess.run(
        [_bash_executable(), "-n", _bash_path(VERIFY_AGENT_IMAGE_SCRIPT)],
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
        _bash_path(ROOT),
        "--file",
        _bash_path(ROOT / "docker-compose.yml"),
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
        "--cursor-key-directory",
        "/run/product-inbox-cursor-key",
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
        "crypto_alert_v2.workers",
        "--worker-id",
        "compose-worker",
    ]
    assert services["langgraph-api"]["command"][:2] == ["aegra", "serve"]

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
    assert services["frontend"]["environment"]["PRODUCT_API_TIMEOUT_MS"] == "8000"
    assert services["frontend"]["ports"] == [
        "127.0.0.1:${FRONTEND_PORT:-3001}:3001"
    ]
    assert not any(
        name.startswith("NEXT_PUBLIC_")
        for name in services["frontend"]["environment"]
    )


def test_aegra_api_gets_product_state_auth_and_production_settings():
    services = _load_compose()["services"]
    api = services["langgraph-api"]
    environment = api["environment"]

    assert environment["APP_ENVIRONMENT"] == "production"
    assert environment["ENV_MODE"] == "PRODUCTION"
    assert environment["RUN_MIGRATIONS_ON_STARTUP"] == "true"
    assert environment["REDIS_BROKER_ENABLED"] == "true"
    assert "LANGGRAPH_CLOUD_LICENSE_KEY" not in environment
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
    assert environment["INTERNAL_JWT_PUBLIC_KEYS"] == "${INTERNAL_JWT_PUBLIC_KEYS:-{}}"
    assert environment["INTEGRATION_SECRET_STORE"] == "file"
    assert environment["INTEGRATION_SECRET_FILE_DIR"] == "/run/integration-secrets"
    assert "NOTIFICATION_CREDENTIAL_KEY" not in environment
    assert "NOTIFICATION_CREDENTIAL_DECRYPT_KEYS" not in environment
    assert environment["PRODUCT_INBOX_CURSOR_KEY_FILE"] == (
        "/run/product-inbox-cursor-key/key"
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
        },
        "/run/product-inbox-cursor-key": {
            "type": "volume",
            "source": "product-inbox-cursor-key",
            "target": "/run/product-inbox-cursor-key",
            "read_only": True,
        },
        "/run/integration-secrets": {
            "type": "volume",
            "source": "integration-secret-files",
            "target": "/run/integration-secrets",
            "read_only": True,
        },
    }


def test_compose_passes_key_rotation_state_to_product_api_and_worker():
    services = _load_compose()["services"]

    # Aegra hosts the custom Product API HTTP app through the config boundary.
    assert "product-api" not in services
    expected = {
        "INTERNAL_JWT_PUBLIC_KEYS": "${INTERNAL_JWT_PUBLIC_KEYS:-{}}",
        "INTEGRATION_SECRET_STORE": "file",
        "INTEGRATION_SECRET_FILE_DIR": "/run/integration-secrets",
    }
    for service_name in ("langgraph-api", "command-worker"):
        environment = services[service_name]["environment"]
        for variable, value in expected.items():
            assert environment[variable] == value


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
            "COMPOSE_AGENT_DATABASE_URL": agent_uri,
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
    assert services["langgraph-api"]["environment"]["DATABASE_URL"] == agent_uri


def test_authenticated_readiness_targets_official_api_and_gates_worker():
    services = _load_compose()["services"]
    readiness = services["langgraph-api-readiness"]
    readiness_environment = readiness["environment"]

    assert readiness["restart"] == "unless-stopped"
    assert readiness_environment["AGENT_SERVER_URL"] == "http://langgraph-api:8000"
    assert readiness_environment["SEARCH_PROVIDER"] == "builtin_web_search"
    assert readiness_environment["AGENT_HEALTHCHECK_EXPECTED_SEARCH_PROVIDER"] == (
        "${SEARCH_PROVIDER:-builtin_web_search}"
    )
    assert readiness_environment["AGENT_READINESS_HOST"] == "0.0.0.0"
    assert readiness_environment["AGENT_READINESS_PORT"] == "9091"
    assert services["langgraph-api"]["environment"]["AGENT_READINESS_URL"] == (
        "http://langgraph-api-readiness:9091/readyz"
    )
    assert services["command-worker"]["depends_on"][
        "langgraph-api-readiness"
    ] == {"condition": "service_healthy"}
    readiness_healthcheck = readiness["healthcheck"]["test"]
    assert readiness_healthcheck[:3] == ["CMD", "python", "-c"]
    assert "http://127.0.0.1:9091/readyz" in readiness_healthcheck[-1]
    worker_environment = services["command-worker"]["environment"]
    assert worker_environment["WORKER_READINESS_FAILURE_THRESHOLD"] == "3"
    assert worker_environment["WORKER_READINESS_STALE_AFTER_SECONDS"] == "30"
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
        "AGENT_HEALTHCHECK_EXPECTED_SEARCH_PROVIDER": (
            "${SEARCH_PROVIDER:-builtin_web_search}"
        ),
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
            "integration-secret-files": "service_completed_successfully",
            "development-bootstrap": "service_completed_successfully",
        },
        "langgraph-api-readiness": {
            "internal-jwt-keys": "service_completed_successfully",
            "langgraph-api": "service_healthy",
        },
        "command-worker": {
            "migrate": "service_completed_successfully",
            "internal-jwt-keys": "service_completed_successfully",
            "integration-secret-files": "service_completed_successfully",
            "development-bootstrap": "service_completed_successfully",
            "langgraph-api-readiness": "service_healthy",
        },
        "frontend": {
            "langgraph-api": "service_healthy",
            "langgraph-api-readiness": "service_healthy",
            "command-worker": "service_healthy",
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
        "langgraph-api": {
            "/run/internal-jwt-public": "internal-jwt-public",
            "/run/product-inbox-cursor-key": "product-inbox-cursor-key",
            "/run/integration-secrets": "integration-secret-files",
        },
        "langgraph-api-readiness": {
            "/run/internal-jwt-private": "internal-jwt-private"
        },
        "command-worker": {
            "/run/internal-jwt-private": "internal-jwt-private",
            "/run/internal-jwt-public": "internal-jwt-public",
            "/run/integration-secrets": "integration-secret-files",
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
        assert environment["DEVELOPMENT_BOOTSTRAP_SUBJECT"] == "dev-user"
        assert environment["DEVELOPMENT_BOOTSTRAP_IDENTITY_ISSUER"] == (
            "crypto-alert-v2-compose"
        )
        assert environment["DEVELOPMENT_BOOTSTRAP_CONTEXT_ID"] == (
            "99999999-9999-4999-8999-999999999999"
        )

    frontend_environment = services["frontend"]["environment"]
    assert frontend_environment["INTERNAL_JWT_PRIVATE_KEY_FILE"] == (
        "/run/internal-jwt-private/private.pem"
    )

    assert services["langgraph-api"]["environment"]["MARKET_DATA_HTTP_PROXY"] == (
        "${MARKET_DATA_HTTP_PROXY:-}"
    )
    assert services["langgraph-api"]["environment"]["SEARCH_PROVIDER"] == (
        "${SEARCH_PROVIDER:-builtin_web_search}"
    )
    assert services["langgraph-api"]["environment"]["SEARCH_HTTP_PROXY"] == (
        "${SEARCH_HTTP_PROXY:-}"
    )
    for service_name in V2_SERVICES - {
        "langgraph-api",
        "langgraph-api-readiness",
        "command-worker",
    }:
        environment = services[service_name].get("environment", {})
        assert "MARKET_DATA_HTTP_PROXY" not in environment
        assert "SEARCH_PROVIDER" not in environment
        assert "SEARCH_HTTP_PROXY" not in environment
    readiness_environment = services["langgraph-api-readiness"]["environment"]
    assert readiness_environment["SEARCH_PROVIDER"] == "builtin_web_search"
    assert readiness_environment["AGENT_HEALTHCHECK_EXPECTED_SEARCH_PROVIDER"] == (
        "${SEARCH_PROVIDER:-builtin_web_search}"
    )
    assert "MARKET_DATA_HTTP_PROXY" not in readiness_environment
    assert "SEARCH_HTTP_PROXY" not in readiness_environment


def test_backend_environment_example_documents_v2_provider_egress_safely():
    example = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")

    for assignment in (
        "SEARCH_PROVIDER=builtin_web_search",
        "MARKET_DATA_HTTP_PROXY=",
        "SEARCH_HTTP_PROXY=",
        "OPENAI_API_KEY=",
        "AEGRA_CONFIG=aegra.json",
        "REDIS_BROKER_ENABLED=true",
        "WORKER_COUNT=1",
        "DEVELOPMENT_BOOTSTRAP_IDENTITY_ISSUER=crypto-alert-v2-local-proof",
        "DEVELOPMENT_BOOTSTRAP_CONTEXT_ID=99999999-9999-4999-8999-999999999999",
    ):
        assert assignment in example
    assert "sk-" not in example
    assert "LANGGRAPH_CLOUD_LICENSE_KEY" not in example


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

    assert 'testDir: "./tests"' in config
    assert '"**/e2e/hosted-production.spec.ts"' in config
    assert '"**/e2e/hosted-security.spec.ts"' in config
    required_specs = {
        "durable-cancel-flow.spec.ts",
        "hitl-review-flow.spec.ts",
        "official-stream-main-flow.spec.ts",
        "real-inbox-flow.spec.ts",
        "real-product-flow.spec.ts",
        "runs-product.spec.ts",
        "work-product.spec.ts",
    }
    assert required_specs <= {path.name for path in suite_directory.glob("*.spec.ts")}
    package = load_json((ROOT / "frontend" / "package.json").read_text())
    real_inbox_gate = package["scripts"]["test:e2e:real-inbox"]
    assert "REAL_PRODUCT_E2E=1" in real_inbox_gate
    assert "PLAYWRIGHT_EXTERNAL_SERVER=1" in real_inbox_gate
    assert "real-inbox-flow.spec.ts" in real_inbox_gate
    assert "forbidOnly: true" in config
    assert 'mode: "on"' in config
    assert "screenshots: false" in config
    assert "snapshots: true" in config
    assert "sources: true" in config
    assert ': "retain-on-failure"' in config
    assert 'screenshot: "only-on-failure"' in config
    assert 'video: "retain-on-failure"' in config
    assert "forbiddenBrowserRequests" in official_flow
    assert "isPublicHttpsUrl" in official_flow
    assert 'url.protocol !== "https:"' in official_flow
    assert '"localhost"' in official_flow
    assert "first === 10 || first === 127" in official_flow
