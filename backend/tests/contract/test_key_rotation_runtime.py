from __future__ import annotations

from pathlib import Path
import json
import stat
import subprocess

import pytest

from crypto_alert_v2.notifications import rotate_credentials as rotation_cli


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "v2" / "key_rotation_drill.sh"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *arguments],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )


def test_key_rotation_drill_is_executable_and_has_valid_bash_syntax() -> None:
    assert stat.S_IMODE(SCRIPT.stat().st_mode) == 0o755
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr


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
    assert "trap cleanup EXIT" in source
    assert "kill -KILL" in source
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

    assert "tempfile.mkstemp" in source
    assert "os.fchmod" in source
    assert "os.fsync(stream.fileno())" in source
    assert "os.replace(temporary, path)" in source
    assert 'path.with_name(f".{path.name}.tmp")' not in source


def test_key_rotation_drill_declares_real_dependencies_and_does_not_put_keys_in_argv() -> (
    None
):
    source = SCRIPT.read_text(encoding="utf-8")

    for command_name in ("tr", "grep", "mv"):
        assert command_name in source
    assert "required backend executable is unavailable" in source
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

    monkeypatch.setattr(rotation_cli.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace unavailable"):
        rotation_cli._write_report(output, {"status": "passed"})

    assert output.read_text(encoding="utf-8") == "stale\n"
    assert list(tmp_path.glob(".rotation.json.*.tmp")) == []
