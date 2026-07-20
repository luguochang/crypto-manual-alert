import json
import os
from pathlib import Path
import stat
import subprocess
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "v2" / "rehearse_product_database_backup.sh"
SECRET_URL = "postgresql+asyncpg://backup-user:do-not-print@db.invalid/product"


def _write_executable(path: Path, source: str) -> None:
    path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def fake_gate_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "bin"
    state_dir = tmp_path / "state"
    temp_dir = tmp_path / "tmp"
    fake_bin.mkdir()
    state_dir.mkdir()
    temp_dir.mkdir()
    call_log = tmp_path / "calls.log"

    _write_executable(
        fake_bin / "psql",
        r"""
        #!/usr/bin/env bash
        set -euo pipefail
        printf 'psql %s host=%s port=%s user=%s database=%s\n' \
          "$*" "$PGHOST" "$PGPORT" "$PGUSER" "$PGDATABASE" >>"$FAKE_CALL_LOG"
        if [[ "$*" == *"--command"* ]]; then
          printf 'SELECT_COUNTS\n'
          exit 0
        fi
        cat >/dev/null || true
        counter_file="$FAKE_STATE_DIR/source-count-calls"
        count=0
        if [[ -f "$counter_file" ]]; then
          count="$(cat "$counter_file")"
        fi
        count=$((count + 1))
        printf '%s\n' "$count" >"$counter_file"
        printf 'public\talembic_version\t1\n'
        if [[ "${FAKE_SOURCE_CHANGED:-0}" == "1" && "$count" -ge 2 ]]; then
          printf 'public\ttasks\t4\n'
        else
          printf 'public\ttasks\t3\n'
        fi
        """,
    )
    _write_executable(
        fake_bin / "pg_dump",
        r"""
        #!/usr/bin/env bash
        set -euo pipefail
        printf 'pg_dump %s\n' "$*" >>"$FAKE_CALL_LOG"
        output=""
        for argument in "$@"; do
          case "$argument" in
            --file=*) output="${argument#--file=}" ;;
          esac
        done
        [[ -n "$output" ]]
        printf 'fake-custom-format-archive\n' >"$output"
        """,
    )
    _write_executable(
        fake_bin / "pg_restore",
        r"""
        #!/usr/bin/env bash
        set -euo pipefail
        printf 'pg_restore %s\n' "$*" >>"$FAKE_CALL_LOG"
        [[ "${1:-}" == "--list" ]]
        """,
    )
    _write_executable(
        fake_bin / "docker",
        r"""
        #!/usr/bin/env bash
        set -euo pipefail
        printf 'docker %s\n' "$*" >>"$FAKE_CALL_LOG"
        operation="${1:-}"
        shift || true
        case "$operation" in
          run)
            printf 'fake-container-id\n'
            ;;
          cp | rm)
            ;;
          exec)
            if [[ "${1:-}" == "--interactive" ]]; then
              shift
            fi
            shift
            command_name="${1:-}"
            shift || true
            case "$command_name" in
              pg_isready | createdb)
                ;;
              pg_restore)
                if [[ "${FAKE_RESTORE_FAIL:-0}" == "1" ]]; then
                  exit 9
                fi
                ;;
              psql)
                if [[ "$*" == *"pg_catalog.pg_constraint"* ]]; then
                  printf '0\n'
                elif [[ "$*" == *"pg_catalog.pg_class"* ]]; then
                  printf 'SELECT_COUNTS\n'
                else
                  cat >/dev/null || true
                  printf 'public\talembic_version\t1\n'
                  printf 'public\ttasks\t3\n'
                fi
                ;;
              *)
                printf 'unexpected fake docker exec command: %s\n' "$command_name" >&2
                exit 97
                ;;
            esac
            ;;
          *)
            printf 'unexpected fake docker operation: %s\n' "$operation" >&2
            exit 98
            ;;
        esac
        """,
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
            "PRODUCT_DATABASE_URL": SECRET_URL,
            "FAKE_CALL_LOG": str(call_log),
            "FAKE_STATE_DIR": str(state_dir),
            "TMPDIR": str(temp_dir),
        }
    )
    for name in (
        "BACKUP_REHEARSAL_POSTGRES_IMAGE",
        "BACKUP_REHEARSAL_REPORT_PATH",
        "FAKE_RESTORE_FAIL",
        "FAKE_SOURCE_CHANGED",
    ):
        environment.pop(name, None)
    return environment, call_log


def _run(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def test_backup_restore_rehearsal_script_has_valid_bash_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_backup_restore_rehearsal_is_secret_safe_and_non_destructive() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in source
    assert "umask 077" in source
    assert "trap cleanup EXIT" in source
    assert "unset PRODUCT_DATABASE_URL" in source
    assert "urlsplit(source)" in source
    assert 'values["PGPASSWORD"]' in source
    assert 'PGDATABASE="$source_conninfo"' not in source
    assert "--network none" in source
    assert "--tmpfs /var/lib/postgresql/data" in source
    assert "--exit-on-error" in source
    assert "source_counts_stable" in source
    assert "restored_counts_match" in source
    assert "production_rto_rpo" in source
    assert "@sha256:" in source
    assert ".env" not in source
    assert "set -x" not in source
    assert "docker volume" not in source
    assert "--publish" not in source
    assert " -p " not in source
    assert 'pg_restore "$source_conninfo"' not in source
    assert 'pg_dump "$source_conninfo"' not in source


def test_missing_database_url_fails_before_any_external_command(
    fake_gate_environment: tuple[dict[str, str], Path],
) -> None:
    environment, call_log = fake_gate_environment
    environment.pop("PRODUCT_DATABASE_URL")

    result = _run(environment)

    assert result.returncode == 64
    assert result.stdout == ""
    assert "PRODUCT_DATABASE_URL must be set" in result.stderr
    assert not call_log.exists()


def test_rehearsal_restores_into_ephemeral_container_and_emits_redacted_report(
    tmp_path: Path,
    fake_gate_environment: tuple[dict[str, str], Path],
) -> None:
    environment, call_log = fake_gate_environment
    report_path = tmp_path / "backup-restore-proof.json"
    environment["BACKUP_REHEARSAL_REPORT_PATH"] = str(report_path)

    result = _run(environment)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report == json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["proof_level"] == "local-backup-restore-rehearsal"
    assert report["table_count"] == 2
    assert report["row_count"] == 4
    assert report["source_counts_stable"] is True
    assert report["restored_counts_match"] is True
    assert report["unvalidated_constraints"] == 0
    assert report["does_not_prove"] == [
        "hosted_backup_policy",
        "point_in_time_recovery",
        "cross_region_restore",
        "production_rto_rpo",
    ]
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600

    calls = call_log.read_text(encoding="utf-8")
    combined_output = result.stdout + result.stderr + calls
    assert SECRET_URL not in combined_output
    assert "do-not-print" not in combined_output
    assert "docker run --detach --rm" in calls
    assert "--network none" in calls
    assert "--publish" not in calls
    assert "docker exec" in calls
    assert "pg_restore --exit-on-error" in calls
    assert "docker rm --force" in calls
    assert "host=db.invalid port=5432 user=backup-user database=product" in calls


def test_source_change_fails_closed_before_restore(
    fake_gate_environment: tuple[dict[str, str], Path],
) -> None:
    environment, call_log = fake_gate_environment
    environment["FAKE_SOURCE_CHANGED"] = "1"

    result = _run(environment)

    assert result.returncode != 0
    assert result.stdout == ""
    assert "source table counts changed during the dump" in result.stderr
    calls = call_log.read_text(encoding="utf-8")
    assert "docker run" not in calls
    assert SECRET_URL not in result.stderr + calls


def test_restore_failure_is_nonzero_and_removes_ephemeral_container(
    fake_gate_environment: tuple[dict[str, str], Path],
) -> None:
    environment, call_log = fake_gate_environment
    environment["FAKE_RESTORE_FAIL"] = "1"

    result = _run(environment)

    assert result.returncode != 0
    assert result.stdout == ""
    assert "pg_restore failed in the isolated database" in result.stderr
    calls = call_log.read_text(encoding="utf-8")
    assert "docker run --detach --rm" in calls
    assert "docker rm --force" in calls
    assert SECRET_URL not in result.stderr + calls


def test_unpinned_restore_image_is_rejected_without_docker_access(
    fake_gate_environment: tuple[dict[str, str], Path],
) -> None:
    environment, call_log = fake_gate_environment
    environment["BACKUP_REHEARSAL_POSTGRES_IMAGE"] = "postgres:16-alpine"

    result = _run(environment)

    assert result.returncode != 0
    assert "must be the pinned PostgreSQL 16 Alpine digest" in result.stderr
    assert not call_log.exists()
    assert SECRET_URL not in result.stderr
