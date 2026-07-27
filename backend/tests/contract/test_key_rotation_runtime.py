from __future__ import annotations

from pathlib import Path
import json
import os
import stat
import subprocess

import pytest

from crypto_alert_v2 import atomic_io
from crypto_alert_v2.notifications import rotate_credentials as rotation_cli


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "v2" / "key_rotation_drill.sh"


def _bash_executable() -> str:
    if os.name != "nt":
        return "bash"
    bash = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git/bin/bash.exe"
    assert bash.is_file(), "Git Bash is required for Windows shell contracts"
    return str(bash)


def _bash_command(*arguments: str) -> list[str]:
    if os.name != "nt":
        return [str(SCRIPT), *arguments]
    return [_bash_executable(), SCRIPT.as_posix(), *arguments]


def _git_mode() -> str:
    result = subprocess.run(
        ["git", "ls-files", "-s", "--", SCRIPT.relative_to(ROOT).as_posix()],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.split()[0]


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _bash_command(*arguments),
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )


def test_key_rotation_drill_is_executable_and_has_valid_bash_syntax() -> None:
    assert _git_mode() == "100755"
    syntax = subprocess.run(
        [_bash_executable(), "-n", SCRIPT.as_posix()],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr


def test_key_rotation_drill_fails_before_tools_without_external_output() -> None:
    result = _run()

    assert result.returncode == 64
    assert result.stdout == ""
    assert "--output-root must be an absolute existing directory" in result.stderr


def test_key_rotation_drill_refuses_to_misclassify_hosted_acceptance(
    tmp_path: Path,
) -> None:
    output = tmp_path / "rotation-output"
    output.mkdir()

    result = _run(
        "--profile",
        "hosted-production",
        "--output-root",
        str(output),
    )

    assert result.returncode == 78
    assert result.stdout == ""
    assert "hosted key rotation acceptance is not implemented" in result.stderr
    assert list(output.iterdir()) == []


def test_key_rotation_drill_keeps_secret_material_out_of_report_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in source
    assert "umask 077" in source
    assert "export APP_ENVIRONMENT=test" in source
    assert "export CRYPTO_ALERT_DISABLE_DOTENV=1" in source
    assert "trap cleanup EXIT" in source
    assert "kill -KILL" in source
    assert "taskkill.exe /PID" in source
    assert "MSYS_NO_PATHCONV=1" in source
    assert "kill_status=$?" in source
    assert "Get-Process -Id" in source
    assert "Get-CimInstance Win32_Process" in source
    assert "Start-Process" in source
    assert "ROTATION_PID_FILE" in source
    assert "ROTATION_LAUNCH_REPORT" in source
    assert "[char]10" in source
    assert "Windows rotation launcher failed" in source
    assert "force_kill_rotation" in source
    assert "rotation process exited before resumable boundary" in source
    assert ".error_type // empty" in source
    assert 'current_stage="resume_rotation"' in source
    assert 'current_stage="start_interrupted_rotation"' in source
    assert 'current_stage="observe_partial_commit"' in source
    assert '"probe_stage"' in source
    assert '"error_type"' in source
    assert "delivery probe produced no bounded report" in source
    assert "ROTATION_DELIVERY_REPORT" in source
    assert "delivery probe wrapper failed during overlap" in source
    assert "return 0" in source
    assert "process_status=$?" in source
    assert "key-rotation-failure.json" in source
    assert "probe_error_type" in source
    assert "failure_evidence_enabled=true" in source
    assert "NOTIFICATION_CREDENTIAL_DECRYPT_KEYS" in source
    assert "old_version_rows_remaining" in source
    assert "retired_old_token_rejected" in source
    assert "local-key-rotation-rehearsal" in source
    assert "hosted_secret_manager_rotation" in source
    assert "release_attestation" in source
    assert "set -x" not in source
    assert "OPENAI_API_KEY" not in source
    assert "LANGSMITH_API_KEY" not in source
    assert "LANGFUSE_SECRET_KEY" not in source
    assert "TAVILY_API_KEY" not in source
    assert "docker volume" not in source


def test_rotation_cli_emits_only_bounded_operational_fields() -> None:
    source = (
        ROOT
        / "backend"
        / "src"
        / "crypto_alert_v2"
        / "notifications"
        / "rotate_credentials.py"
    ).read_text(encoding="utf-8")

    for field in (
        "active_key_version",
        "batches",
        "scanned_rows",
        "rewrapped_rows",
        "remaining_old_version_rows",
    ):
        assert field in source
    for forbidden in (
        "credential_ciphertext",
        "get_secret_value",
        "destination_id",
        "tenant_id",
        "workspace_id",
        "owner_user_id",
    ):
        assert forbidden not in source


def test_rotation_uses_returning_for_cas_and_treats_conflicts_as_recoverable() -> None:
    source = (
        ROOT / "backend" / "src" / "crypto_alert_v2" / "notifications" / "rotation.py"
    ).read_text(encoding="utf-8")

    assert ".returning(NotificationDestination.id)" in source
    assert "scalar_one_or_none()" in source
    assert "result.rowcount" not in source
    assert "skip_locked=True" in source
    assert "batch.rewrapped_rows == 0" in source


def test_rotation_cli_publishes_reports_with_durable_atomic_replace() -> None:
    source = (
        ROOT
        / "backend"
        / "src"
        / "crypto_alert_v2"
        / "notifications"
        / "rotate_credentials.py"
    ).read_text(encoding="utf-8")

    assert "atomic_write_text" in source
    assert 'path.with_name(f".{path.name}.tmp")' not in source


def test_key_rotation_drill_declares_real_dependencies_and_does_not_put_keys_in_argv() -> (
    None
):
    source = SCRIPT.read_text(encoding="utf-8")

    for command_name in ("tr", "grep", "mv"):
        assert command_name in source
    assert "required backend executable is unavailable" in source
    assert ".venv/Scripts/python.exe" in source
    assert ".venv/Scripts/alembic.exe" in source
    assert "ROTATION_OLD_KEY" in source
    assert "jq -cn --arg key" not in source
    assert "$(cat " not in source
    assert "seq " not in source
    assert (
        'summary_tmp="$(mktemp "$output_root/.key-rotation-summary.XXXXXX")"' in source
    )
    assert 'mv -f "$summary_tmp" "$summary_path"' in source


def test_rotation_cli_atomically_replaces_an_existing_private_report(
    tmp_path: Path,
) -> None:
    output = tmp_path / "rotation.json"
    output.write_text("stale\n", encoding="utf-8")

    rotation_cli._write_report(output, {"status": "passed", "rewrapped_rows": 2})

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "rewrapped_rows": 2,
        "status": "passed",
    }
    if os.name != "nt":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert list(tmp_path.glob(".rotation.json.*.tmp")) == []


def test_rotation_cli_preserves_the_previous_report_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "rotation.json"
    output.write_text("stale\n", encoding="utf-8")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("replace unavailable")

    monkeypatch.setattr(atomic_io.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace unavailable"):
        rotation_cli._write_report(output, {"status": "passed"})

    assert output.read_text(encoding="utf-8") == "stale\n"
    assert list(tmp_path.glob(".rotation.json.*.tmp")) == []
