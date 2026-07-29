from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import json
import socket


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools/v2/run_real_deep_research_e2e.sh"
SUPERVISOR = ROOT / "tools/v2/aegra_restart_supervisor.py"
COMPOSE_SUPERVISOR = ROOT / "tools/v2/aegra_compose_restart_supervisor.py"
WINDOWS_SERVE = ROOT / "tools/v2/aegra_windows_serve.py"
PROFILE = ROOT / "tools/v2/profiles/real-deep-research.env"
PLAYWRIGHT_FLOW = ROOT / "frontend/tests/e2e-product/real-deep-research-flow.spec.ts"
PLAYWRIGHT_CONFIG = ROOT / "frontend/playwright.config.ts"


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


def _run_runner(*args: str, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_bash_executable(), RUNNER.relative_to(ROOT).as_posix(), *args],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _runner_text() -> str:
    return RUNNER.read_text()


def _clean_environment() -> dict[str, str]:
    return {
        "HOME": os.environ.get("HOME", ""),
        "PATH": os.environ["PATH"],
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    }


def test_profile_contains_only_non_secret_literal_defaults() -> None:
    text = PROFILE.read_text()
    assignments = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
        assert match is not None, f"invalid profile line {line_number}"
        assignments.append(match.groups())

    assert assignments
    names = {name for name, _value in assignments}
    assert {
        "APP_ENVIRONMENT",
        "SEARCH_PROVIDER",
        "DEEP_RESEARCH_HARNESS_MODE",
        "REAL_DEEP_RESEARCH_AGENT_PORT",
        "REAL_DEEP_RESEARCH_WORKER_PORT",
        "REAL_DEEP_RESEARCH_FRONTEND_PORT",
        "DEVELOPMENT_BOOTSTRAP_ENABLED",
        "DEVELOPMENT_BOOTSTRAP_PROFILE",
        "DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID",
    } <= names
    forbidden_name = re.compile(
        r"SECRET|TOKEN|PASSWORD|CREDENTIAL|API_KEY|PRIVATE_KEY|LICENSE",
        re.IGNORECASE,
    )
    forbidden_value = re.compile(
        r"(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+|postgres(?:ql)?://[^/\s]+@)",
        re.IGNORECASE,
    )
    for name, value in assignments:
        assert forbidden_name.search(name) is None
        assert forbidden_value.search(value) is None
        assert "$(" not in value
        assert "${" not in value
        assert "`" not in value


def test_runner_has_no_dotenv_or_process_environment_scraping() -> None:
    text = _runner_text()
    # Only reject shell source/dot commands at the beginning of a line. The
    # runner embeds small Python validators whose variables may be named
    # `source`, but those do not inspect dotenv files.
    assert re.search(
        r"(?m)^(?:source|\.)[ \t]+(?![=])[^\n]*\.env(?:[ \t\"']|$)",
        text,
    ) is None
    assert "/proc/" not in text
    assert "ps e" not in text
    assert "printenv" not in text
    assert "set -x" not in text
    assert "env |" not in text


def test_runner_has_secret_safe_provider_presence_preflight() -> None:
    text = _runner_text()

    assert "validate_provider_presence" in text
    assert "from crypto_alert_v2.config import get_settings" in text
    assert "settings.openai_api_key is not None" in text
    assert "settings.tavily_api_key is not None" in text
    assert "provider-preflight.json" in text
    assert "Required real Provider environment variable is not configured" in text
    assert '"OPENAI_API_KEY": {"required": True' in text
    assert '"TAVILY_API_KEY": {' in text
    assert text.index("validate_provider_presence\n") < text.index("docker run --detach")
    assert "${OPENAI_API_KEY}" not in text
    assert "${TAVILY_API_KEY}" not in text


def test_runner_uses_profile_and_required_current_source_commands() -> None:
    text = _runner_text()
    assert "--profile" in text
    assert "--check-profile" in text
    assert "profiles/real-deep-research.env" in text
    assert "node_modules/@playwright/test/cli.js test" in text
    assert "--project=fixture-desktop" in text
    assert "--project=fixture-pixel-7" in text
    assert "uv run --frozen --no-dev --extra aegra" in text
    assert "python -m uvicorn" in text
    assert "aegra_api.main:app" in text
    assert "aegra serve" not in text
    assert "AEGRA_WINDOWS_SERVE" in text
    windows_serve = WINDOWS_SERVE.read_text(encoding="utf-8")
    assert "loop=asyncio.SelectorEventLoop" in windows_serve
    assert "uvicorn.Server(config).run()" in windows_serve
    assert 'wait_for_http "$AGENT_SERVER_URL/health"' in text
    assert "--redis-broker" in text
    assert "ENABLE_REDIS_BROKER=0" in text
    assert "export REDIS_BROKER_ENABLED=true" in text
    assert "export REDIS_BROKER_ENABLED=false" in text
    assert "redis://127.0.0.1:$REDIS_PORT/0" in text
    assert "redis:7-alpine@sha256:" in text
    assert 'docker rm --force --volumes "$REDIS_CONTAINER"' in text
    assert "redis-broker-receipt.json" in text
    assert "redis-broker-cleanup.json" in text
    assert "aegra_restart_supervisor.py" in text
    assert "REAL_DEEP_RESEARCH_AEGRA_RESTART=1" in text
    assert 'EVIDENCE_NATIVE_DIR="$(cygpath -w "$EVIDENCE_DIR")"' in text
    assert 'PYTHON_RUNNER="python.exe"' in text
    assert "REAL_DEEP_RESEARCH_PROXYCHAINS_CONFIG" in text
    assert "python -m crypto_alert_v2.workers" in text
    assert "npm run build" in text
    assert "npm run start" in text
    assert "alembic upgrade head" in text
    assert 'DATABASE_MODE="docker-postgres-temporary"' in text
    assert "$POSTGRES_IMAGE" in text
    assert "postgres:16-alpine@sha256:" in text
    assert 'docker rm --force --volumes "$DATABASE_CONTAINER"' in text
    assert 'createdb "$DATABASE_NAME"' in text
    assert 'dropdb --if-exists --force "$DATABASE_NAME"' in text
    assert 'run_psql -X -qAt' in text
    assert '"$PYTHON_RUNNER" - "$port"' in text
    assert "lsof" not in text

    flow = PLAYWRIGHT_FLOW.read_text(encoding="utf-8")
    assert "const restartErrorWindow = beginErrorWindow(observer)" in flow
    assert "await closeExpectedAegraRestartWindow(" in flow
    assert "aegra-restart-browser-outage-window" in flow
    assert "net::ERR_INCOMPLETE_CHUNKED_ENCODING" in flow
    assert "502 GET /api/product/api/v2/tasks/" in flow
    assert "502 POST /api/agent/threads/${runtime.thread_id.toLowerCase()}/history" in flow
    assert "502 POST /api/agent/threads/" in flow
    assert "errors.pageErrors).toEqual([])" in flow
    assert "errors.productResponseErrors).toEqual([])" in flow
    assert "end.consoleErrors - start.consoleErrors" in flow
    assert "const realDeepResearchAdmissionTimeoutMs = 480_000" in flow


def test_runner_enforces_evidence_junit_projects_cleanup_and_manifest() -> None:
    text = _runner_text()
    for marker in (
        "PLAYWRIGHT_EVIDENCE_DIR",
        "PLAYWRIGHT_BROWSER_CHANNEL=chromium",
        "junit.xml",
        "results.json",
        "html/index.html",
        "test-results",
        "fixture-desktop",
        "fixture-pixel-7",
        "skipped testcase is forbidden",
        "database-evidence.json",
        "terminal-state-receipt.json",
        "review-policy-before.json",
        "review-policy-required.json",
        "review-policy-restored.json",
        "artifact-sha256.txt",
        "evidence-manifest.json",
        "manifest_self_hash_excluded",
        "trap cleanup EXIT",
        "stop_all_owned_processes",
        "aegra-restart-validation.json",
        "validate_aegra_restart_receipts",
        "target_unavailable_observed",
        "target_recovered_observed",
        "active Product worker recovery is not proved",
        "active Aegra worker lease/reaper recovery is not proved",
        "preflight stopped before runtime because a required host tool was unavailable",
        "preflight stopped before runtime because required real Provider",
        "failure manifest fallback omitted artifact hashes because jq or a SHA-256 tool was unavailable",
    ):
        assert marker in text
    assert "Port 3110 is reserved" in text
    assert 'kill -TERM -- "-$pid"' in text
    assert 'getattr(os, "setsid", lambda: None)' in text
    assert "shutil.which(command[0])" in text
    assert "subprocess.Popen(command" in text
    assert "subprocess.CREATE_NEW_PROCESS_GROUP" in text
    assert "child.wait()" in text
    assert 'process_line="$(ps -W -p "$pid"' in text
    assert 'taskkill //PID "$native_pid" //T //F' in text
    assert 'taskkill //PID "$pid"' not in text
    assert "pkill" not in text
    assert "killall" not in text
    assert "sha256_command=(sha256sum)" in text
    assert "sha256_command=(shasum -a 256)" in text
    assert 'digest_output="$("${sha256_command[@]}" "$path")"' in text
    assert "sha256sum or shasum" in text


def test_restart_supervisor_and_browser_handshake_are_explicit() -> None:
    supervisor = SUPERVISOR.read_text(encoding="utf-8")
    flow = PLAYWRIGHT_FLOW.read_text(encoding="utf-8")
    config = PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")
    ast.parse(supervisor)

    assert "subprocess.Popen(args.command" in supervisor
    assert "shell=True" not in supervisor
    assert "Aegra URL did not become unavailable" in supervisor
    assert "Aegra URL did not recover" in supervisor
    assert "aegra-restart-request-" in supervisor
    assert "aegra-restart-receipt-" in supervisor
    assert "aegra-restart-complete-" in supervisor

    assert 'process.env.REAL_DEEP_RESEARCH_AEGRA_RESTART === "1"' in flow
    assert "await requestAegraRestart(firstReview, testInfo)" in flow
    assert '"review-round-1-after-aegra-restart"' in flow
    assert "expect(receipt.request).toEqual(request)" in flow
    assert '"REAL_DEEP_RESEARCH_AEGRA_RESTART"' in config


def test_compose_restart_supervisor_is_scoped_and_does_not_implement_runtime() -> None:
    supervisor = COMPOSE_SUPERVISOR.read_text(encoding="utf-8")
    ast.parse(supervisor)

    assert '["docker", *arguments]' in supervisor
    assert '"stop", "--time", "0", args.container' in supervisor
    assert '"start", args.container' in supervisor
    assert 'labels.get("com.docker.compose.project")' in supervisor
    assert 'labels.get("com.docker.compose.service")' in supervisor
    assert '"restart_operation": "docker-stop-start"' in supervisor
    assert "shell=True" not in supervisor
    for forbidden in (
        "checkpoint",
        "stream_mode",
        "astream",
        "state.fork",
        "update_state",
    ):
        assert forbidden not in supervisor.lower()


def test_restart_supervisor_restarts_owned_http_child(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    working = tmp_path / "working"
    working.mkdir()
    with socket.socket() as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        port = probe_socket.getsockname()[1]
    command = [
        sys.executable,
        "tools/v2/aegra_restart_supervisor.py",
        "--working-directory",
        str(working),
        "--evidence-dir",
        str(evidence),
        "--health-url",
        f"http://127.0.0.1:{port}/",
        "--startup-timeout",
        "10",
        "--project",
        "fixture-desktop",
        "--",
        sys.executable,
        "-m",
        "http.server",
        str(port),
        "--bind",
        "127.0.0.1",
    ]
    supervisor = subprocess.Popen(command, cwd=ROOT)
    try:
        request = {
            "schema_version": "1.0",
            "project": "fixture-desktop",
            "requested_at": "2026-07-21T00:00:00Z",
            "task_id": "00000000-0000-4000-8000-000000000001",
            "product_run_id": "00000000-0000-4000-8000-000000000002",
            "assistant_id": "00000000-0000-4000-8000-000000000003",
            "thread_id": "00000000-0000-4000-8000-000000000004",
            "run_id": "00000000-0000-4000-8000-000000000005",
            "pause_id": "00000000-0000-4000-8000-000000000006",
            "pause_version": 1,
            "interrupt_ids": ["interrupt-1"],
            "review_iteration": 1,
        }
        request_path = evidence / "aegra-restart-request-fixture-desktop.json"
        complete_path = evidence / "aegra-restart-complete-fixture-desktop.json"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not complete_path.exists():
            if supervisor.poll() is not None:
                raise AssertionError(f"supervisor exited with {supervisor.returncode}")
            if not request_path.exists():
                request_path.write_text(json.dumps(request) + "\n", encoding="utf-8")
            time.sleep(0.1)
        assert complete_path.exists(), "supervisor did not write a completion receipt"
        receipt = json.loads(
            (evidence / "aegra-restart-receipt-fixture-desktop.json").read_text(
                encoding="utf-8"
            )
        )
        assert receipt["request"] == request
        assert receipt["generation_before"]["pid"] != receipt["generation_after"]["pid"]
        assert receipt["target_unavailable_observed"] is True
        assert receipt["target_recovered_observed"] is True
    finally:
        supervisor.terminate()
        try:
            supervisor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            supervisor.kill()
            supervisor.wait(timeout=5)
        if os.name == "nt":
            for process in subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Select-Object -ExpandProperty ProcessId"],
                text=True,
            ).splitlines():
                if not process.strip().isdigit():
                    continue
                candidate = int(process.strip())
                try:
                    details = subprocess.check_output(
                        [
                            "powershell",
                            "-NoProfile",
                            "-Command",
                            f"(Get-CimInstance Win32_Process -Filter 'ProcessId={candidate}').CommandLine",
                        ],
                        text=True,
                        stderr=subprocess.DEVNULL,
                    )
                except subprocess.CalledProcessError:
                    continue
                if f"http.server {port}" in details:
                    subprocess.run(
                        ["taskkill", "/PID", str(candidate), "/T", "/F"],
                        check=False,
                        capture_output=True,
                    )


def test_database_export_is_an_explicit_secret_safe_allowlist() -> None:
    text = _runner_text()
    match = re.search(
        r"<<'DATABASE_EVIDENCE_SQL'.*?\n(.*?)\nDATABASE_EVIDENCE_SQL",
        text,
        re.DOTALL,
    )
    assert match is not None
    sql = match.group(1)
    for required in (
        "request_payload_hash",
        "payload_hash",
        "terminal_output_hash",
        "resume_of_run_id",
        "member_set_hash",
        "content_sha256",
        "source_url_sha256",
        "event_type_counts",
        "decisions",
    ):
        assert required in sql
    assert re.search(r"task\.request_payload(?!_hash)", sql) is None
    assert "run.input_payload" not in sql
    assert "run.output_payload" not in sql
    assert re.search(r"command\.payload(?!_hash)", sql) is None
    # `decision.decision_version` is an allowlisted lineage field. Reject the
    # raw decision payload reference itself, including common SQL delimiters.
    assert re.search(r"\bdecision\.decision\s*(?:[,)]|$)", sql, re.MULTILINE) is None
    assert "evidence_verdict" not in sql
    assert "risk_verdict" not in sql
    assert "failure_message" not in sql
    assert "query_text" not in sql
    assert "authorization" not in sql.lower()


def test_runner_executable_profile_contract() -> None:
    completed = _run_runner(
        "--check-profile",
        "--profile",
        PROFILE.relative_to(ROOT).as_posix(),
        environment=_clean_environment(),
    )
    assert completed.returncode == 0, completed.stderr
    assert "Profile contract is valid" in completed.stdout


def test_runner_fails_before_runtime_when_provider_is_absent(tmp_path: Path) -> None:
    evidence = tmp_path / "provider-preflight"
    environment = _clean_environment()
    environment["TMPDIR"] = _bash_path(tmp_path)
    environment["CRYPTO_ALERT_DISABLE_DOTENV"] = "1"
    completed = _run_runner(
        "--evidence-dir",
        _bash_path(evidence),
        environment=environment,
    )

    assert completed.returncode == 78
    assert "OPENAI_API_KEY" in completed.stderr
    receipt = json.loads((evidence / "provider-preflight.json").read_text())
    assert receipt == {
        "schema_version": "1.0",
        "valid": False,
        "search_provider": "builtin_web_search",
        "variables": {
            "OPENAI_API_KEY": {"required": True, "present": False},
            "TAVILY_API_KEY": {"required": False, "present": False},
        },
    }
    manifest = json.loads((evidence / "evidence-manifest.json").read_text())
    assert manifest["provider_preflight"] == {
        key: value for key, value in receipt.items() if key != "schema_version"
    }
    assert manifest["result"] == "failed"
    assert manifest["topology"]["agent_port"] is None
    assert manifest["topology"]["worker_health_port"] is None
    assert manifest["topology"]["frontend_port"] is None
    assert manifest["hash_policy"]["algorithm"] == "sha256"
    assert manifest["artifacts"]
    assert all(artifact["sha256"] for artifact in manifest["artifacts"])
    assert (evidence / "run-status.json").is_file()
    assert not (evidence / "migration-head.json").exists()


def test_runner_reports_e2e_failure_before_missing_restart_receipts() -> None:
    text = _runner_text()

    e2e_failure = 'die 70 "Real Deep Research Playwright profile failed with status $e2e_status"'
    restart_failure = "die 70 'Aegra restart receipt validation failed'"
    assert text.index(e2e_failure) < text.index(restart_failure)


def test_runner_rejects_missing_relative_and_nonempty_evidence(tmp_path: Path) -> None:
    environment = _clean_environment()
    missing = _run_runner(environment=environment)
    assert missing.returncode == 64
    assert "--evidence-dir" in missing.stderr

    relative = _run_runner(
        "--evidence-dir",
        "relative-evidence",
        environment=environment,
    )
    assert relative.returncode == 64
    assert "absolute path" in relative.stderr

    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "existing.txt").write_text("existing evidence\n")
    occupied = _run_runner(
        "--evidence-dir",
        _bash_path(nonempty),
        environment=environment,
    )
    assert occupied.returncode == 64
    assert "absent or empty" in occupied.stderr


def test_runner_is_executable_bash_and_parses() -> None:
    assert os.access(RUNNER, os.X_OK)
    completed = subprocess.run(
        [_bash_executable(), "-n", RUNNER.relative_to(ROOT).as_posix()],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_runner_embedded_python_heredocs_parse() -> None:
    scripts = re.findall(r"<<'PY'\n(.*?)\nPY", _runner_text(), re.DOTALL)
    assert scripts
    for script in scripts:
        ast.parse(script)
