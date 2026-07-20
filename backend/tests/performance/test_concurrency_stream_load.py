from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import stat
import subprocess
import sys
import threading


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "v2" / "run_load_probe.py"


class _HealthHandler(BaseHTTPRequestHandler):
    response_status = 200

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/app/api/v2/health":
            self.send_error(404)
            return
        payload = json.dumps({"status": "ok", "version": "2.0.0"}).encode()
        self.send_response(self.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *args: object) -> None:
        del args


@contextmanager
def _server(*, status: int = 200) -> Iterator[str]:
    handler = type("HealthHandler", (_HealthHandler,), {"response_status": status})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _run(
    output: Path, base_url: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--base-url",
            base_url,
            "--release-tier",
            "internal_alpha",
            "--output",
            str(output),
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )


def test_local_load_probe_records_bounded_real_loopback_measurements(
    tmp_path: Path,
) -> None:
    output = tmp_path / "load.json"
    with _server() as base_url:
        result = _run(
            output,
            base_url,
            "--requests",
            "20",
            "--concurrency",
            "4",
        )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["proof_level"] == "local-http-load-preflight"
    assert report["load"]["request_count"] == 20
    assert report["load"]["success_count"] == 20
    assert report["load"]["failure_count"] == 0
    assert report["load"]["latency_ms"]["p95"] > 0
    assert report["slo_claims"] == []
    assert "market_analysis_p95" in report["does_not_prove"]
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_local_load_probe_fails_on_non_healthy_responses(tmp_path: Path) -> None:
    output = tmp_path / "load-failed.json"
    with _server(status=503) as base_url:
        result = _run(
            output,
            base_url,
            "--requests",
            "4",
            "--concurrency",
            "2",
        )

    assert result.returncode == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["load"]["success_count"] == 0
    assert report["load"]["failure_count"] == 4
    assert report["load"]["outcomes"] == {"unexpected_status": 4}


def test_load_probe_refuses_hosted_claim_without_hosted_gate(tmp_path: Path) -> None:
    output = tmp_path / "hosted.json"
    result = _run(
        output,
        "https://example.com",
        "--profile",
        "hosted-production",
    )

    assert result.returncode == 78
    assert not output.exists()
    error = json.loads(result.stderr)
    assert error["status"] == "failed"
    assert error["error_type"] == "RuntimeError"


def test_load_probe_rejects_credentials_and_unbounded_concurrency(
    tmp_path: Path,
) -> None:
    credential_output = tmp_path / "credential.json"
    credentials = _run(
        credential_output,
        "http://user:secret@127.0.0.1:8123",
    )
    assert credentials.returncode == 1
    assert "secret" not in credentials.stderr
    assert not credential_output.exists()

    concurrency_output = tmp_path / "concurrency.json"
    concurrency = _run(
        concurrency_output,
        "http://127.0.0.1:8123",
        "--requests",
        "2",
        "--concurrency",
        "3",
    )
    assert concurrency.returncode == 1
    assert not concurrency_output.exists()
