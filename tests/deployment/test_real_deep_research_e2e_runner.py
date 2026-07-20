from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools/v2/run_real_deep_research_e2e.sh"
PROFILE = ROOT / "tools/v2/profiles/real-deep-research.env"


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


def test_runner_uses_profile_and_required_current_source_commands() -> None:
    text = _runner_text()
    assert "--profile" in text
    assert "--check-profile" in text
    assert "profiles/real-deep-research.env" in text
    assert "npm run test:e2e:real-deep-research" in text
    assert "uv run --frozen langgraph dev" in text
    assert "--no-reload" in text
    assert "python -m crypto_alert_v2.workers" in text
    assert "npm run build" in text
    assert "npm run start" in text
    assert "alembic upgrade head" in text
    assert 'createdb "$DATABASE_NAME"' in text
    assert 'dropdb --if-exists --force "$DATABASE_NAME"' in text


def test_runner_enforces_evidence_junit_projects_cleanup_and_manifest() -> None:
    text = _runner_text()
    for marker in (
        "PLAYWRIGHT_EVIDENCE_DIR",
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
    ):
        assert marker in text
    assert "Port 3110 is reserved" in text
    assert 'kill -TERM -- "-$pid"' in text
    assert "pkill" not in text
    assert "killall" not in text


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
    completed = subprocess.run(
        [str(RUNNER), "--check-profile", "--profile", str(PROFILE)],
        cwd=ROOT,
        env=_clean_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Profile contract is valid" in completed.stdout


def test_runner_rejects_missing_relative_and_nonempty_evidence(tmp_path: Path) -> None:
    environment = _clean_environment()
    missing = subprocess.run(
        [str(RUNNER)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 64
    assert "--evidence-dir" in missing.stderr

    relative = subprocess.run(
        [str(RUNNER), "--evidence-dir", "relative-evidence"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert relative.returncode == 64
    assert "absolute path" in relative.stderr

    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "existing.txt").write_text("existing evidence\n")
    occupied = subprocess.run(
        [str(RUNNER), "--evidence-dir", str(nonempty)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert occupied.returncode == 64
    assert "absent or empty" in occupied.stderr


def test_runner_is_executable_bash_and_parses() -> None:
    assert os.access(RUNNER, os.X_OK)
    completed = subprocess.run(
        ["bash", "-n", str(RUNNER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
