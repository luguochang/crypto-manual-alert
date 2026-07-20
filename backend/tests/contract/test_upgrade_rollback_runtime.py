from pathlib import Path
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "v2" / "upgrade_rollback_drill.sh"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *arguments],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )


def test_upgrade_rollback_drill_is_executable_and_has_valid_bash() -> None:
    assert stat.S_IMODE(SCRIPT.stat().st_mode) == 0o755
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
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
        'run_alembic "upgrade head"',
        'run_alembic "downgrade $BASELINE_REVISION"',
        "forked_from_checkpoint_id",
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
