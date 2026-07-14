import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import Request, urlopen


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROBE_SCRIPT = BACKEND_DIR.parent / "tools" / "v2" / "probe_agent_server.sh"


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_until_ready(port: int, process: subprocess.Popen[str]) -> None:
    for _ in range(90):
        if process.poll() is not None:
            raise AssertionError("pre-existing Agent Server exited before readiness")
        try:
            request = Request(
                f"http://127.0.0.1:{port}/ok",
                headers={"Authorization": "Bearer test-local-agent-token"},
            )
            with urlopen(request, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("pre-existing Agent Server did not become ready")


def test_probe_rejects_a_port_owned_by_an_existing_server() -> None:
    port = _free_port()
    env = os.environ | {"AGENT_SERVER_LOCAL_TOKEN": "test-local-agent-token"}
    existing = subprocess.Popen(
        [
            "uv",
            "run",
            "langgraph",
            "dev",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-browser",
        ],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        _wait_until_ready(port, existing)
        env["LANGGRAPH_PROBE_PORT"] = str(port)

        result = subprocess.run(
            [str(PROBE_SCRIPT)],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        assert result.returncode != 0
        assert existing.poll() is None
    finally:
        existing.terminate()
        try:
            existing.wait(timeout=10)
        except subprocess.TimeoutExpired:
            existing.kill()
            existing.wait(timeout=10)


def test_probe_exercises_401_403_and_200_resource_auth() -> None:
    port = _free_port()
    env = os.environ | {
        "AGENT_SERVER_LOCAL_TOKEN": "probe-only-local-token",
        "LANGGRAPH_PROBE_PORT": str(port),
        "LANGGRAPH_PROBE_HOST": "127.0.0.1",
    }

    result = subprocess.run(
        [str(PROBE_SCRIPT)],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "401/403/200 resource auth verified" in result.stdout
