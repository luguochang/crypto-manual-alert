import ast
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRODUCT_PROBE = ROOT / "tools" / "v2" / "probe_product_api.sh"
AEGRA_PROBE = ROOT / "tools" / "v2" / "probe_aegra_durability.sh"
PYTHON_CLIENT = ROOT / "tools" / "v2" / "aegra_durability_probe.py"
REPLAY_PROBE = ROOT / "tools" / "v2" / "probe_aegra_replay.mjs"
PROTOCOL_PROBE = ROOT / "tools" / "v2" / "probe_protocol_v2.mjs"
QA_CONFIG = ROOT / "backend" / "aegra.task8-qa.json"
QA_COMPOSE = ROOT / "deploy" / "docker-compose.task8-qa.yml"
IMAGE_VERIFIER = ROOT / "tools" / "v2" / "verify_agent_image.sh"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def test_task8_shell_and_node_probes_parse() -> None:
    for script in (PRODUCT_PROBE, AEGRA_PROBE):
        result = subprocess.run(
            ["bash", "-n"],
            cwd=ROOT,
            input=_text(script).encode("utf-8"),
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    for script in (REPLAY_PROBE, PROTOCOL_PROBE):
        result = subprocess.run(
            ["node", "--check", str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    ast.parse(_text(PYTHON_CLIENT))


def test_product_probe_delegates_to_the_open_source_runtime_proof() -> None:
    script = _text(PRODUCT_PROBE)
    assert 'AEGRA_PROBE="$ROOT_DIR/tools/v2/probe_aegra_durability.sh"' in script
    assert '"$AEGRA_PROBE" --evidence-dir "$EVIDENCE_DIR"' in script
    assert "local Aegra durability slice passed" in script
    assert "does not claim hosted OIDC/HTTPS" in script
    for forbidden in (
        "LANGGRAPH_CLOUD_LICENSE_KEY",
        "LANGSMITH_API_KEY",
        "LICENSED_AGENT_SERVER",
        "licensed-persistent",
        "agent-server-image.lock",
        "langchain/langgraph-api",
    ):
        assert forbidden not in script


def test_product_probe_requires_a_retained_evidence_directory() -> None:
    script = _text(PRODUCT_PROBE)
    result = subprocess.run(
        ["bash", "-s", "--", "--help"],
        cwd=ROOT,
        input=script.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert "--evidence-dir PATH" in result.stdout.decode("utf-8")
    assert re.search(r"(?m)^EVIDENCE_DIR=(?:\"\")?\s*$", script)
    assert "Task 8 requires an explicit --evidence-dir" in script


def test_aegra_probe_uses_qa_config_without_loading_backend_env() -> None:
    script = _text(AEGRA_PROBE)
    overlay = _text(QA_COMPOSE)
    config = json.loads(_text(QA_CONFIG))

    assert "COMPOSE_DISABLE_ENV_FILE=1" in script
    assert "AEGRA_CONFIG_BASENAME=aegra.task8-qa.json" in script
    assert 'QA_COMPOSE_FILE="$ROOT_DIR/deploy/docker-compose.task8-qa.yml"' in script
    assert "env_file: !reset []" in overlay
    assert "backend/.env" not in script
    assert "source " not in script
    assert "printenv" not in script
    assert "set -x" not in script
    assert "command -v python3" in script
    assert '"$host_python"' in script
    assert "env" not in config
    assert "http" not in config
    assert config["graphs"] == {
        "crypto_analysis": "./src/crypto_alert_v2/graph/__init__.py:graph_factory",
        "candidate_review": (
            "./src/crypto_alert_v2/evaluation/review_graph.py:graph_factory"
        ),
        "single_interrupt_fixture": (
            "./src/crypto_alert_v2/testing/multi_interrupt_fixture.py:single_graph"
        ),
        "multi_interrupt_fixture": (
            "./src/crypto_alert_v2/testing/multi_interrupt_fixture.py:graph"
        ),
        "aegra_durability_fixture": (
            "./src/crypto_alert_v2/testing/aegra_durability_fixture.py:graph"
        ),
    }


def test_aegra_probe_uses_real_redis_worker_kill_and_reaper_evidence() -> None:
    script = _text(AEGRA_PROBE)
    ordered = (
        script.index('"${common_client[@]}" matrix'),
        script.index('node "$PROTOCOL_PROBE"'),
        script.index('"${common_client[@]}" prepare'),
        script.index('docker kill "$container_before"'),
        script.index('docker start "$container_before"'),
        script.index('"${common_client[@]}" verify'),
        script.index('node "$REPLAY_PROBE"'),
    )
    assert list(ordered) == sorted(ordered)
    assert "REDIS_BROKER_ENABLED" in _text(ROOT / "docker-compose.yml")
    assert "AEGRA_LEASE_DURATION_SECONDS" in script
    assert "AEGRA_HEARTBEAT_INTERVAL_SECONDS" in script
    assert "AEGRA_REAPER_INTERVAL_SECONDS" in script
    assert "Reaping crashed worker runs" in script
    assert "Re-enqueued recovered run" in script
    assert "target_unavailable" in script
    assert "target_recovered" in script
    assert "generation_before" in script
    assert "generation_after" in script


def test_aegra_probe_retains_hashed_secret_safe_evidence() -> None:
    script = _text(AEGRA_PROBE)
    for artifact in (
        "capability-matrix.json",
        "protocol-v2.log",
        "canonical-prepare.json",
        "canonical-verify.json",
        "prepare.json",
        "verify.json",
        "replay.json",
        "restart-receipt.json",
        "runtime-versions.json",
        "aegra.log",
        "artifact-sha256.txt",
        "evidence-manifest.json",
    ):
        assert artifact in script
    assert "sha256sum" in script
    assert "[REDACTED]" in script
    assert "dirty working-tree evidence is not an immutable release candidate" in script
    assert "QA-only graph fixture does not prove the real provider Product graph" in script
    assert "controlled post-provider state" in script
    assert "emitted no Protocol checkpoint envelope" in script
    assert "official Thread state checkpoint ID" in script
    assert "provisioned local Product memberships" in script
    assert "EVIDENCE_FINALIZED=0" in script
    assert 'if [[ "$EVIDENCE_FINALIZED" != "1" ]]' in script
    assert "EVIDENCE_FINALIZED=1" in script
    assert "runtime-versions.json aegra.log evidence-manifest.json" in script
    assert script.index('(root / "evidence-manifest.json").write_text') < script.index(
        ">artifact-sha256.txt"
    )
    cleanup = script[script.index("cleanup() {") : script.index("trap cleanup EXIT")]
    assert 'down --volumes --remove-orphans' in cleanup
    assert "rm -rf" not in cleanup
    assert "EVIDENCE_DIR" not in re.sub(r'aegra\.log', "", cleanup).split("down", 1)[1]


def test_python_probe_uses_official_sdk_and_refreshes_short_lived_auth() -> None:
    script = _text(PYTHON_CLIENT)
    assert "from langgraph_sdk import get_client" in script
    assert "AgentServerRunner" in script
    assert "RemoteRunHandle" in script
    assert "APIStatusError" in script
    assert "InternalTokenIssuer" in script
    assert "def _headers(" in script
    assert "client.runs.create(" in script
    assert "client.runs.get(" in script
    assert "client.threads.get_state(" in script
    assert "client.threads.get_history(" in script
    assert "prepared_count_after" in script
    assert "completion_count_after" in script
    assert "checkpoint_before_preserved" in script
    assert "canonical-prepare" in script
    assert "canonical-verify" in script
    assert 'graph_id="crypto_analysis"' in script
    assert 'command={"goto": "review_policy"}' in script
    assert '"checkpoint_preserved": True' in script
    assert '"interrupt_preserved": True' in script
    assert 'artifact.get("status") != "committed"' in script
    assert "cancel_runner.cancel(" in script
    assert "fork_runner.fork(" in script
    assert "issuer.issue_scoped(" in script
    assert '"provisioned_actor_matrix"' in script
    assert '"same_tenant_peer_status": same_tenant_peer_status' in script
    assert '"cross_tenant_status": cross_tenant_status' in script
    assert '"mismatched_context_status": mismatched_context_status' in script
    assert '"authority_metadata_overwritten": True' in script
    assert '"auth_forbidden_normalized_to_401": True' in script
    assert "if mismatched_context_status != 401:" in script
    assert '"membership_bootstrap": True' in script
    assert "requests." not in script
    assert "httpx." not in script.replace("httpx.Timeout", "")


def test_aegra_probe_bootstraps_provisioned_local_actor_matrix() -> None:
    script = _text(AEGRA_PROBE)
    assert "bootstrap_member()" in script
    assert "DEVELOPMENT_BOOTSTRAP_CONTEXT_ID" in script
    assert "task8-peer-user" in script
    assert "task8-cross-tenant-user" in script
    assert "AEGRA_PROBE_PEER_CONTEXT_ID" in script
    assert "AEGRA_PROBE_CROSS_CONTEXT_ID" in script
    assert (
        "provisioned local Product memberships do not prove hosted OIDC or a "
        "production tenant deployment"
    ) in script
    assert "unprovisioned cross-tenant identity" not in script


def test_replay_probe_delegates_sequence_and_identity_to_official_transport() -> None:
    script = _text(REPLAY_PROBE)
    assert re.search(
        r'frontendRequire\(\s*"@langchain/langgraph-sdk"\s*,?\s*\)',
        script,
    )
    assert "new ProtocolSseTransportAdapter(" in script
    assert "openEventStream(" in script
    assert "since," in script
    assert "left.seq !== right.seq" in script
    assert "left.event_id !== right.event_id" in script
    assert "left.method !== right.method" in script
    assert "fetch(" not in script
    assert "EventSource" not in script


def test_image_verifier_allows_only_the_explicit_qa_graphs() -> None:
    verifier = _text(IMAGE_VERIFIER)
    assert '"aegra.task8-qa.json"' in verifier
    assert 'expected_graphs["single_interrupt_fixture"]' in verifier
    assert 'expected_graphs["multi_interrupt_fixture"]' in verifier
    assert 'expected_graphs["aegra_durability_fixture"]' in verifier
    assert "TASK8_ALLOW_MULTI_INTERRUPT_FIXTURE" in verifier
    assert 'expected_http = None' in verifier
    assert 'else "aegra.json"' in verifier


def test_existing_protocol_probe_keeps_the_official_command_surface() -> None:
    script = _text(PROTOCOL_PROBE)
    assert 'frontendRequire("@langchain/langgraph-sdk")' in script
    assert "new ProtocolSseTransportAdapter(" in script
    assert "stream.run.start(" in script
    assert "input.respond(" in script
    assert "openEventStream(" in script
    assert "state.fork(" in script
    assert "since," in script
    assert re.search(
        r'seedModeEnvironment\(\s*"TASK8_SINGLE_SEED_MODE"\s*,\s*"canonical"',
        script,
    )
    assert re.search(
        r'booleanEnvironment\(\s*"TASK8_ALLOW_STATE_CHECKPOINT_FALLBACK"\s*,\s*false',
        script,
    )
    assert "allowStateCheckpointFallback" in script
    assert 'TASK8_ALLOW_STATE_CHECKPOINT_FALLBACK=1' in _text(AEGRA_PROBE)
    assert 'seedModeEnvironment("TASK8_BATCH_SEED_MODE"' in script
    assert "namespaceDepths" in script
    assert "nestedInterruptCount" in script
    assert "both root and nested interrupt namespaces" in script
    assert "batch_namespace_depths=" in script
    assert "batch_nested_interrupts=" in script
    assert "fetch(`${apiUrl}/threads/" not in script
