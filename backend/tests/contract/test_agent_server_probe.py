import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
from threading import Thread


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROBE_SCRIPT = BACKEND_DIR.parent / "tools" / "v2" / "probe_agent_server.sh"


def _probe_command() -> list[str]:
    if os.name != "nt":
        return [str(PROBE_SCRIPT)]
    bash = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git/bin/bash.exe"
    assert bash.is_file(), "Git Bash is required for Windows shell contracts"
    return [str(bash), PROBE_SCRIPT.as_posix()]


class _QuietOkHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def test_probe_rejects_a_port_owned_by_an_existing_server() -> None:
    existing = ThreadingHTTPServer(("127.0.0.1", 0), _QuietOkHandler)
    port = int(existing.server_address[1])
    serving = Thread(target=existing.serve_forever, daemon=True)
    serving.start()
    env = os.environ | {"AGENT_SERVER_LOCAL_TOKEN": "test-local-agent-token"}
    try:
        env["LANGGRAPH_PROBE_PORT"] = str(port)

        result = subprocess.run(
            _probe_command(),
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        assert result.returncode != 0
        assert serving.is_alive()
    finally:
        existing.shutdown()
        existing.server_close()
        serving.join(timeout=10)


def test_probe_declares_401_403_and_200_resource_auth_contract() -> None:
    source = PROBE_SCRIPT.read_text(encoding="utf-8")

    assert 'if [[ "$UNAUTHENTICATED_STATUS" != "401" ]]' in source
    assert 'if [[ "$FORBIDDEN_STATUS" != "403" ]]' in source
    assert 'if [[ "$ALLOWED_STATUS" == "200" ]]' in source
    assert "401/403/200 resource auth verified" in source


def test_probe_protocol_extension_is_explicit_and_uses_the_official_node_probe() -> (
    None
):
    source = PROBE_SCRIPT.read_text(encoding="utf-8")

    assert '"${TASK8_PROTOCOL_V2_PROBE:-0}" == "1"' in source
    assert 'NODE_PROBE="$ROOT_DIR/tools/v2/probe_protocol_v2.mjs"' in source
    assert '"langgraph.multi-interrupt.json"' in source
    assert "export CRYPTO_ALERT_DISABLE_DOTENV=1" in source
    assert (
        'PROTOCOL_TOKEN="$(issue_token \'["analysis:read","analysis:write"]\')"'
        in source
    )
    assert 'READ_ONLY_CREATE_STATUS="$(curl --silent \\' in source
    assert 'TASK8_AGENT_URL="$BASE_URL"' in source
    assert 'TASK8_AGENT_TOKEN="$PROTOCOL_TOKEN"' in source
    assert (
        'TASK8_SINGLE_GRAPH_ID="${TASK8_PROTOCOL_SINGLE_GRAPH_ID:-crypto_analysis}"'
        in source
    )
    assert (
        'TASK8_BATCH_GRAPH_ID="${TASK8_PROTOCOL_BATCH_GRAPH_ID:-multi_interrupt_fixture}"'
        in source
    )
    assert "TASK8_EXPECTED_BATCH_INTERRUPTS=2" in source
    assert "TASK8_EXPECTED_PROTOCOL_VERSION" in source
    assert 'node "$NODE_PROBE"' in source
