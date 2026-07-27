from pathlib import Path
import os
import subprocess


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "v2" / "upgrade_rollback_drill.sh"


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


def test_upgrade_rollback_drill_is_executable_and_has_valid_bash() -> None:
    assert _git_mode() == "100755"
    result = subprocess.run(
        [_bash_executable(), "-n", SCRIPT.as_posix()],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_upgrade_rollback_drill_rejects_missing_output_root() -> None:
    result = _run()

    assert result.returncode == 64
    assert result.stdout == ""
    assert "--output-root must be an absolute existing directory" in result.stderr


def test_upgrade_rollback_drill_refuses_hosted_claims(tmp_path: Path) -> None:
    result = _run(
        "--profile",
        "hosted-production",
        "--output-root",
        str(tmp_path),
    )

    assert result.returncode == 78
    assert result.stdout == ""
    assert "hosted upgrade/rollback acceptance is not implemented" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_upgrade_rollback_drill_has_explicit_migration_and_evidence_boundaries() -> (
    None
):
    source = SCRIPT.read_text(encoding="utf-8")

    for required in (
        "0015_observability_delivery",
        "0017_domain_events",
        "0018_progressive_events",
        "0019_ddgs_provenance",
        "0020_entitlements_usage",
        "0021_scheduled_monitors",
        "0022_data_lifecycle",
        'run_alembic "upgrade head"',
        'run_alembic "downgrade $BASELINE_REVISION"',
        "forked_from_checkpoint_id",
        "final_feature_tables",
        ".venv/Scripts/alembic.exe",
        'proof_level: "local-migration-upgrade-rollback-rehearsal"',
        "does_not_prove",
        "chmod 600",
        'mktemp "$output_root/.upgrade-rollback-summary.XXXXXX"',
    ):
        assert required in source
    for forbidden in (
        "OPENAI_API_KEY",
        "LANGSMITH_API_KEY",
        "LANGFUSE_SECRET_KEY",
        "set -x",
    ):
        assert forbidden not in source
