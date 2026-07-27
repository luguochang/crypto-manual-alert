from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "v2" / "probe_aegra_ha.sh"
CLIENT = ROOT / "tools" / "v2" / "aegra_durability_probe.py"
AVAILABILITY = ROOT / "tools" / "v2" / "aegra_ha_availability.py"
OVERLAY = ROOT / "deploy" / "docker-compose.task8-ha.yml"
HAPROXY_CONFIG = ROOT / "deploy" / "task8-ha-haproxy.cfg"
HAPROXY_IMAGE = (
    "public.ecr.aws/docker/library/haproxy:3.0-alpine@sha256:"
    "dee54db8b27cd6c21519ea4f0ba0604f3742e8e7369bc16fb5b69133dec3f47f"
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
        assert match is not None, "Git Bash is required for HA probe contracts"
        return str(match)
    match = shutil.which("bash")
    assert match is not None, "bash is required for HA probe contracts"
    return match


def _bash_path(path: Path) -> str:
    absolute = path.resolve()
    if os.name != "nt":
        return str(absolute)
    rendered = absolute.as_posix()
    return f"/{rendered[0].lower()}{rendered[2:]}"


def test_ha_overlay_removes_secret_file_and_host_port() -> None:
    overlay = OVERLAY.read_text(encoding="utf-8")

    assert "env_file: !reset []" in overlay
    assert "ports: !reset []" in overlay
    assert "backend/.env" not in overlay
    assert set(re.findall(r"^  ([a-z0-9-]+):$", overlay, re.MULTILINE)) == {
        "langgraph-api",
        "command-worker",
        "ha-gateway",
    }
    assert f"image: {HAPROXY_IMAGE}" in overlay
    assert "pull_policy: never" in overlay
    assert "source: ./deploy/task8-ha-haproxy.cfg" in overlay
    assert "http://127.0.0.1:8080/health" in overlay
    assert "no-new-privileges:true" in overlay
    assert 'AEGRA_REPLICA_A: "${COMPOSE_PROJECT_NAME}-langgraph-api-1"' in overlay
    assert 'AEGRA_REPLICA_B: "${COMPOSE_PROJECT_NAME}-langgraph-api-2"' in overlay


def test_ha_gateway_uses_docker_dns_active_checks_and_redispatch() -> None:
    source = HAPROXY_CONFIG.read_text(encoding="utf-8")

    assert 'server replica-a "${AEGRA_REPLICA_A}":8000' in source
    assert 'server replica-b "${AEGRA_REPLICA_B}":8000' in source
    assert "server-template" not in source
    assert "nameserver docker_dns 127.0.0.11:53" in source
    assert "check resolvers docker" in source
    assert "resolve-opts allow-dup-ip" not in source
    assert "http-check send meth GET uri /health" in source
    assert "http-check expect status 200" in source
    assert "option redispatch" in source
    assert "timeout connect 1s" in source
    assert "acl health_path path -i /health" in source
    assert "use_backend aegra_health if health_path" in source
    assert (
        "retry-on conn-failure empty-response response-timeout 502 503 504" in source
    )
    assert "init-addr libc,none" in source
    health_backend = source.split("\nbackend aegra_health\n", 1)[1].split(
        "\nbackend aegra_pool\n", 1
    )[0]
    graph_backend = source.split("\nbackend aegra_pool\n", 1)[1]
    assert "retry-on" in health_backend
    assert "retry-on" not in graph_backend


def test_ha_runner_uses_two_owned_replicas_and_sequential_rollout() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "COMPOSE_DISABLE_ENV_FILE=1" in source
    assert 'HA_COMPOSE_FILE="$ROOT_DIR/deploy/docker-compose.task8-ha.yml"' in source
    assert "--scale langgraph-api=2" in source
    assert re.search(
        r'up --detach --wait --wait-timeout 180 \\\n'
        r'  --scale langgraph-api=2 ha-gateway',
        source,
    )
    assert 'Expected exactly two running Aegra replicas' in source
    assert 'docker stop --time 10 "$container_a"' in source
    assert 'docker start "$container_a"' in source
    assert 'docker stop --time 10 "$container_b"' in source
    assert 'docker start "$container_b"' in source
    assert "health-checked-haproxy" in source
    assert HAPROXY_IMAGE in source
    assert 'docker pull "$GATEWAY_IMAGE"' in source
    assert "--env AEGRA_REPLICA_A=localhost" in source
    assert "--env AEGRA_REPLICA_B=localhost" in source
    assert 'run_client "$url_gateway" ha-prepare' in source
    assert 'run_client "$url_gateway" ha-resume' in source
    assert '--target "$url_gateway"' in source
    assert "gateway-config-sha256.txt" in source
    assert "gateway-runtime.json" in source
    assert "stable-compose-replica-dns" in source
    assert "haproxy.log" in source
    assert "EVIDENCE_FINALIZED=0" in source
    assert 'if [[ "$EVIDENCE_FINALIZED" != "1" ]]' in source
    assert "EVIDENCE_FINALIZED=1" in source
    assert "runtime-versions.json aegra-ha.log haproxy.log evidence-manifest.json" in source
    assert source.index('(root / "evidence-manifest.json").write_text') < source.index(
        ">artifact-sha256.txt"
    )
    assert "host_ports" in source
    assert "availability.json" in source
    assert "observe-initial-b.json" in source
    assert "observe-after-a-stop.json" in source
    assert "observe-after-b-stop.json" in source
    assert "QA-only interrupt fixture" in source
    assert "not production ingress" in source
    assert "backend/.env" not in source
    assert "docker compose restart" not in source
    assert "docker kill" not in source
    assert "curl" not in source


def test_ha_runner_is_valid_bash() -> None:
    completed = subprocess.run(
        [_bash_executable(), "-n", _bash_path(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_ha_client_uses_official_sdk_and_bounded_health_sampling() -> None:
    source = CLIENT.read_text(encoding="utf-8")
    ast.parse(source)

    for phase in (
        "ha-prepare",
        "ha-observe",
        "ha-resume",
        "ha-final",
    ):
        assert f'"{phase}"' in source
    assert "get_client(" in source
    assert "AgentServerRunner(" in source
    assert "await runner.get_interrupts(handle)" in source
    assert "await runner.resume(" in source
    assert 'item.interrupt_id: {"action": "approve"}' in source
    assert "EventSource" not in source
    assert "text/event-stream" not in source


def test_ha_availability_probe_only_samples_health() -> None:
    source = AVAILABILITY.read_text(encoding="utf-8")
    ast.parse(source)

    assert 'target.rstrip("/") + "/health"' in source
    assert "max_keepalive_connections=0" in source
    assert 'headers={"connection": "close"}' in source
    assert "if failures:" in source
    assert "HA service discovery had" in source
    for forbidden in ("threads", "runs", "checkpoint", "text/event-stream"):
        assert forbidden not in source
