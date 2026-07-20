import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "v2" / "run_local_supply_chain_gate.sh"
SECRET_SENTINEL = "local-supply-chain-secret-sentinel"
RAW_ERROR_SENTINEL = "raw-tool-error-must-not-be-published"


def _write_executable(path: Path, source: str) -> None:
    path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def _write_fake_tools(fake_bin: Path, repository: Path) -> None:
    _write_executable(
        fake_bin / "uv",
        f"""
        #!/bin/bash
        set -euo pipefail
        bin_dir="$(cd -- "${{BASH_SOURCE[0]%/*}}" && pwd -P)"
        printf 'uv %s\n' "$*" >>"$bin_dir/calls.log"
        [[ -z "${{UV_INDEX_URL:-}}" ]]
        [[ -z "${{UV_EXTRA_INDEX_URL:-}}" ]]
        [[ -z "${{NPM_TOKEN:-}}" ]]
        case "${{1:-}}" in
          --version)
            printf 'uv 0.11.28 (fake)\n'
            ;;
          audit)
            [[ "${{UV_DEFAULT_INDEX:-}}" == "https://pypi.org/simple" ]]
            [[ "${{UV_NO_CONFIG:-}}" == "1" ]]
            mode="$(cat "$bin_dir/uv-mode")"
            if [[ "$mode" == "invalid_audit" ]]; then
              printf '%s\n' '{RAW_ERROR_SENTINEL}' >&2
              printf 'not-json\n'
              exit 17
            fi
            audited=3
            adverse_count=0
            adverse='[]'
            exit_code=0
            if [[ "$mode" == "zero_audit" ]]; then
              audited=0
            elif [[ "$mode" == "adverse" ]]; then
              adverse_count=1
              adverse='[{{"name":"archived-package","status":"archived","reason":null}}]'
              exit_code=1
            fi
            printf '{{"schema":{{"version":"preview"}},"summary":{{"audited_packages":%s,"vulnerabilities":0,"adverse_statuses":%s}},"vulnerabilities":[],"adverse_statuses":%s}}\n' \
              "$audited" "$adverse_count" "$adverse"
            exit "$exit_code"
            ;;
          export)
            mode="$(cat "$bin_dir/uv-mode")"
            if [[ "$mode" == "zero_sbom" ]]; then
              printf '%s\n' '{{"bomFormat":"CycloneDX","specVersion":"1.5","metadata":{{"component":{{"type":"application","name":"fixture"}}}},"components":[],"dependencies":[]}}'
            else
              printf '%s\n' '{{"bomFormat":"CycloneDX","specVersion":"1.5","metadata":{{"component":{{"type":"application","name":"fixture"}}}},"components":[{{"name":"a"}},{{"name":"b"}},{{"name":"c"}}],"dependencies":[{{"ref":"root"}},{{"ref":"a"}},{{"ref":"b"}},{{"ref":"c"}}]}}'
            fi
            ;;
          *)
            exit 98
            ;;
        esac
        """,
    )

    npm_source = r"""
        #!/bin/bash
        set -euo pipefail
        bin_dir="$(cd -- "${BASH_SOURCE[0]%/*}" && pwd -P)"
        printf 'npm %s\n' "$*" >>"$bin_dir/calls.log"
        [[ -z "${NPM_TOKEN:-}" ]]
        [[ -z "${NODE_AUTH_TOKEN:-}" ]]
        case "${1:-}" in
          --version)
            printf '11.12.1-fake\n'
            ;;
          audit)
            [[ "${npm_config_registry:-}" == "https://registry.npmjs.org/" ]]
            [[ "${npm_config_ignore_scripts:-}" == "true" ]]
            [[ -f "${NPM_CONFIG_USERCONFIG:-missing}" ]]
            [[ -f "${NPM_CONFIG_GLOBALCONFIG:-missing}" ]]
            mode="$(cat "$bin_dir/npm-mode")"
            if [[ "$mode" == "invalid_audit" ]]; then
              printf '%s\n' '__RAW_ERROR_SENTINEL__' >&2
              printf '<html>network failure</html>\n'
              exit 19
            fi
            dependencies=4
            vulnerability_total=0
            vulnerabilities='{}'
            exit_code=0
            if [[ "$mode" == "zero_audit" ]]; then
              dependencies=0
            elif [[ "$mode" == "vulnerability" ]]; then
              vulnerability_total=1
              vulnerabilities='{"affected-package":{"name":"affected-package","severity":"high","isDirect":false,"via":[],"effects":[],"range":"*","nodes":[],"fixAvailable":false}}'
              exit_code=1
            fi
            printf '{"auditReportVersion":2,"vulnerabilities":%s,"metadata":{"vulnerabilities":{"info":0,"low":0,"moderate":0,"high":%s,"critical":0,"total":%s},"dependencies":{"prod":2,"dev":2,"optional":0,"peer":0,"peerOptional":0,"total":%s}}}\n' \
              "$vulnerabilities" "$vulnerability_total" "$vulnerability_total" "$dependencies"
            exit "$exit_code"
            ;;
          sbom)
            mode="$(cat "$bin_dir/npm-mode")"
            if [[ "$mode" == "zero_sbom" ]]; then
              printf '%s\n' '{"bomFormat":"CycloneDX","specVersion":"1.6","metadata":{"component":{"type":"application","name":"fixture"}},"components":[],"dependencies":[]}'
              exit 0
            fi
            if [[ "$mode" == "mutate_source" ]]; then
              printf '\nchanged during scan\n' >>__MUTATE_PATH__
            fi
            printf '%s\n' '{"bomFormat":"CycloneDX","specVersion":"1.6","metadata":{"component":{"type":"application","name":"fixture"}},"components":[{"name":"one"},{"name":"two"},{"name":"three"},{"name":"four"}],"dependencies":[{"ref":"root"},{"ref":"one"},{"ref":"two"},{"ref":"three"},{"ref":"four"}]}'
            ;;
          *)
            exit 97
            ;;
        esac
    """
    npm_source = npm_source.replace("__RAW_ERROR_SENTINEL__", RAW_ERROR_SENTINEL)
    npm_source = npm_source.replace(
        "__MUTATE_PATH__",
        shlex.quote(str(repository / "backend" / "src" / "app.py")),
    )
    _write_executable(fake_bin / "npm", npm_source)
    _write_executable(
        fake_bin / "node",
        """
        #!/bin/bash
        set -euo pipefail
        printf 'node %s\n' "$*" >>"${BASH_SOURCE[0]%/*}/calls.log"
        [[ -z "${NPM_TOKEN:-}" ]]
        printf 'v26.0.0-fake\n'
        """,
    )
    (fake_bin / "uv-mode").write_text("success\n", encoding="utf-8")
    (fake_bin / "npm-mode").write_text("success\n", encoding="utf-8")


@dataclass(frozen=True)
class GateFixture:
    repository: Path
    script: Path
    fake_bin: Path
    output_parent: Path

    @property
    def call_log(self) -> Path:
        return self.fake_bin / "calls.log"

    def set_modes(self, *, uv: str = "success", npm: str = "success") -> None:
        (self.fake_bin / "uv-mode").write_text(f"{uv}\n", encoding="utf-8")
        (self.fake_bin / "npm-mode").write_text(f"{npm}\n", encoding="utf-8")


@pytest.fixture
def gate_fixture(tmp_path: Path) -> GateFixture:
    repository = tmp_path / "repository"
    fake_bin = tmp_path / "fake-bin"
    output_parent = tmp_path / "evidence"
    for directory in (
        repository / "tools" / "v2",
        repository / "backend" / "src",
        repository / "backend" / "tests" / "contract",
        repository / "frontend" / "src",
        fake_bin,
        output_parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    shutil.copy2(SCRIPT, repository / "tools" / "v2" / SCRIPT.name)
    (repository / "backend" / "src" / "app.py").write_text(
        "APPLICATION = 'fixture'\n", encoding="utf-8"
    )
    (repository / "backend" / "tests" / "contract" / "test_fixture.py").write_text(
        "def test_fixture():\n    assert True\n", encoding="utf-8"
    )
    (repository / "backend" / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (repository / "backend" / "uv.lock").write_text(
        'version = 1\nrevision = 3\nrequires-python = ">=3.12"\n', encoding="utf-8"
    )
    (repository / "frontend" / "src" / "app.ts").write_text(
        "export const app = 'fixture';\n", encoding="utf-8"
    )
    (repository / "frontend" / "package.json").write_text(
        json.dumps({"name": "fixture", "version": "1.0.0", "private": True}) + "\n",
        encoding="utf-8",
    )
    (repository / "frontend" / "package-lock.json").write_text(
        json.dumps(
            {
                "name": "fixture",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {
                    "": {"name": "fixture", "version": "1.0.0"},
                    "node_modules/one": {"version": "1.0.0"},
                    "node_modules/two": {"version": "1.0.0"},
                    "node_modules/three": {"version": "1.0.0"},
                    "node_modules/four": {"version": "1.0.0"},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (repository / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repository / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    git_environment = os.environ.copy()
    git_environment.update(
        {
            "GIT_AUTHOR_NAME": "Contract Test",
            "GIT_AUTHOR_EMAIL": "contract@example.invalid",
            "GIT_COMMITTER_NAME": "Contract Test",
            "GIT_COMMITTER_EMAIL": "contract@example.invalid",
        }
    )
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"],
        cwd=repository,
        env=git_environment,
        check=True,
    )
    _write_fake_tools(fake_bin, repository)
    return GateFixture(
        repository=repository,
        script=repository / "tools" / "v2" / SCRIPT.name,
        fake_bin=fake_bin,
        output_parent=output_parent,
    )


def _run_gate(
    fixture: GateFixture,
    *,
    output_dir: Path | None = None,
    path: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    if output_dir is None:
        output_dir = fixture.output_parent / "run"
        output_dir.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": path or f"{fixture.fake_bin}{os.pathsep}{environment['PATH']}",
            "SUPPLY_CHAIN_OUTPUT_DIR": str(output_dir),
            "NPM_TOKEN": SECRET_SENTINEL,
            "NODE_AUTH_TOKEN": SECRET_SENTINEL,
            "UV_INDEX_URL": f"https://user:{SECRET_SENTINEL}@packages.invalid/simple",
            "UV_EXTRA_INDEX_URL": f"https://user:{SECRET_SENTINEL}@extra.invalid/simple",
        }
    )
    result = subprocess.run(
        ["/bin/bash", str(fixture.script)],
        cwd=fixture.repository,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return result, output_dir


def _load_summary(output_dir: Path) -> dict[str, object]:
    return json.loads(
        (output_dir / "supply-chain-summary.json").read_text(encoding="utf-8")
    )


def _all_evidence_text(output_dir: Path) -> str:
    return "".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(output_dir.iterdir())
        if path.is_file()
    )


def test_script_has_valid_syntax_and_fail_closed_static_contract() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    source = SCRIPT.read_text(encoding="utf-8")

    assert result.returncode == 0, result.stderr
    assert "set -euo pipefail" in source
    assert "umask 077" in source
    assert "backend/uv.lock" in source
    assert "frontend/package-lock.json" in source
    assert "source-manifest-after.sha256" in source
    assert "lockfile_changed_during_scan" in source
    assert "--locked" in source
    assert "--package-lock-only" in source
    assert "env -i" in source
    assert "https://pypi.org/simple" in source
    assert "https://registry.npmjs.org/" in source
    assert "skipped_scans" in source
    assert "container_image_sbom" in source
    assert "artifact_signature" in source
    assert "release_attestation" in source
    assert "production_release" in source
    assert ".env" not in source
    assert "--no-dev" not in source
    assert "--omit" not in source
    assert "--ignore " not in source
    assert "--force" not in source
    assert "curl " not in source
    assert "wget " not in source
    assert "npx " not in source
    assert "set -x" not in source


def test_success_runs_all_scans_and_binds_redacted_artifacts(
    gate_fixture: GateFixture,
) -> None:
    result, output_dir = _run_gate(gate_fixture)

    assert result.returncode == 0, result.stderr
    expected_names = {
        "source-manifest.sha256",
        "python-audit.json",
        "frontend-audit.json",
        "python.cdx.json",
        "frontend.cdx.json",
        "supply-chain-summary.json",
    }
    assert {path.name for path in output_dir.iterdir()} == expected_names
    summary = _load_summary(output_dir)
    assert json.loads(result.stdout) == summary
    assert summary["status"] == "passed"
    assert summary["proof_level"] == "local-working-tree-supply-chain"
    assert summary["scan_count"] == 4
    assert summary["attempted_scans"] == 4
    assert summary["completed_scans"] == 4
    assert summary["skipped_scans"] == 0
    assert summary["network_checks_completed"] == 2
    assert summary["scans"]["python_audit"]["audited_packages"] == 3
    assert summary["scans"]["frontend_audit"]["audited_dependencies"] == 4
    assert summary["source"]["git_dirty"] is False
    assert summary["source"]["file_count"] > 0
    assert summary["source"]["identity_rechecked"] is True
    assert summary["source"]["stable_during_scan"] is True
    assert summary["does_not_prove"] == [
        "committed_source_candidate",
        "hosted_dependency_audit",
        "container_image_sbom",
        "artifact_signature",
        "release_attestation",
        "production_release",
    ]

    for name in expected_names:
        assert stat.S_IMODE((output_dir / name).stat().st_mode) == 0o600
    for name, expected_digest in summary["artifact_sha256"].items():
        assert (
            expected_digest
            == hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
        )
    assert (
        summary["source"]["manifest_sha256"]
        == summary["artifact_sha256"]["source-manifest.sha256"]
    )
    assert (
        summary["locks"]["backend"]["sha256"]
        == hashlib.sha256(
            (gate_fixture.repository / "backend" / "uv.lock").read_bytes()
        ).hexdigest()
    )
    assert (
        summary["locks"]["frontend"]["sha256"]
        == hashlib.sha256(
            (gate_fixture.repository / "frontend" / "package-lock.json").read_bytes()
        ).hexdigest()
    )

    combined = result.stdout + result.stderr + _all_evidence_text(output_dir)
    if gate_fixture.call_log.exists():
        combined += gate_fixture.call_log.read_text(encoding="utf-8")
    assert SECRET_SENTINEL not in combined
    calls = gate_fixture.call_log.read_text(encoding="utf-8")
    assert "uv audit" in calls
    assert "uv export" in calls
    assert "npm audit" in calls
    assert "npm sbom" in calls


def test_missing_tool_fails_before_scans_with_machine_readable_summary(
    gate_fixture: GateFixture, tmp_path: Path
) -> None:
    hermetic_bin = tmp_path / "hermetic-bin"
    hermetic_bin.mkdir()
    commands = (
        "cat",
        "chmod",
        "cmp",
        "cp",
        "date",
        "env",
        "git",
        "jq",
        "mkdir",
        "mv",
        "node",
        "npm",
        "rm",
        "rmdir",
        "shasum",
        "sort",
    )
    for command in commands:
        source = gate_fixture.fake_bin / command
        executable = source if source.exists() else Path(shutil.which(command) or "")
        assert executable.is_file(), command
        (hermetic_bin / command).symlink_to(executable)

    result, output_dir = _run_gate(gate_fixture, path=str(hermetic_bin))

    assert result.returncode != 0
    summary = _load_summary(output_dir)
    assert summary["status"] == "failed"
    assert summary["failure_reason"] == "required_tool_missing"
    assert summary["missing_tool"] == "uv"
    assert summary["attempted_scans"] == 0
    assert summary["skipped_scans"] == 4
    assert not gate_fixture.call_log.exists()
    assert SECRET_SENTINEL not in result.stdout + result.stderr + _all_evidence_text(
        output_dir
    )


@pytest.mark.parametrize(
    (
        "uv_mode",
        "npm_mode",
        "expected_python_adverse",
        "expected_frontend_vulnerabilities",
    ),
    [
        ("adverse", "success", 1, 0),
        ("success", "vulnerability", 0, 1),
    ],
)
def test_dependency_findings_exit_two_and_preserve_complete_evidence(
    gate_fixture: GateFixture,
    uv_mode: str,
    npm_mode: str,
    expected_python_adverse: int,
    expected_frontend_vulnerabilities: int,
) -> None:
    gate_fixture.set_modes(uv=uv_mode, npm=npm_mode)

    result, output_dir = _run_gate(gate_fixture)

    assert result.returncode == 2
    summary = _load_summary(output_dir)
    assert summary["status"] == "failed"
    assert summary["failure_reason"] == "dependency_findings_detected"
    assert summary["attempted_scans"] == 4
    assert summary["completed_scans"] == 4
    assert summary["skipped_scans"] == 0
    assert (
        summary["scans"]["python_audit"]["adverse_statuses"] == expected_python_adverse
    )
    assert (
        summary["scans"]["frontend_audit"]["vulnerabilities"]
        == expected_frontend_vulnerabilities
    )
    assert (output_dir / "python-audit.json").is_file()
    assert (output_dir / "frontend-audit.json").is_file()
    assert (output_dir / "python.cdx.json").is_file()
    assert (output_dir / "frontend.cdx.json").is_file()


def test_invalid_audit_output_fails_closed_without_raw_error_leakage(
    gate_fixture: GateFixture,
) -> None:
    gate_fixture.set_modes(uv="invalid_audit")

    result, output_dir = _run_gate(gate_fixture)

    assert result.returncode != 0
    summary = _load_summary(output_dir)
    assert summary["failure_reason"] == "python_audit_invalid_json_or_schema"
    assert summary["attempted_scans"] == 1
    assert summary["completed_scans"] == 0
    assert summary["skipped_scans"] == 3
    assert summary["source"]["identity_rechecked"] is True
    assert summary["source"]["stable_during_scan"] is True
    assert not (output_dir / "python-audit.json").exists()
    combined = result.stdout + result.stderr + _all_evidence_text(output_dir)
    assert RAW_ERROR_SENTINEL not in combined
    assert SECRET_SENTINEL not in combined


@pytest.mark.parametrize(
    ("uv_mode", "npm_mode", "expected_reason"),
    [
        ("zero_audit", "success", "python_audit_zero_packages"),
        ("success", "zero_audit", "frontend_audit_zero_dependencies"),
        ("zero_sbom", "success", "python_sbom_zero_inventory"),
        ("success", "zero_sbom", "frontend_sbom_zero_inventory"),
    ],
)
def test_zero_scan_or_inventory_is_rejected(
    gate_fixture: GateFixture,
    uv_mode: str,
    npm_mode: str,
    expected_reason: str,
) -> None:
    gate_fixture.set_modes(uv=uv_mode, npm=npm_mode)

    result, output_dir = _run_gate(gate_fixture)

    assert result.returncode != 0
    summary = _load_summary(output_dir)
    assert summary["status"] == "failed"
    assert summary["failure_reason"] == expected_reason


def test_source_change_during_scans_is_rejected(gate_fixture: GateFixture) -> None:
    gate_fixture.set_modes(npm="mutate_source")

    result, output_dir = _run_gate(gate_fixture)

    assert result.returncode != 0
    summary = _load_summary(output_dir)
    assert summary["failure_reason"] == "source_changed_during_scan"
    assert summary["attempted_scans"] == 4
    assert summary["completed_scans"] == 4
    assert summary["skipped_scans"] == 0
    assert summary["source"]["identity_rechecked"] is True
    assert summary["source"]["stable_during_scan"] is False


def test_nonempty_output_directory_is_rejected_without_modification(
    gate_fixture: GateFixture,
) -> None:
    output_dir = gate_fixture.output_parent / "nonempty"
    output_dir.mkdir()
    marker = output_dir / "keep.txt"
    marker.write_text("keep\n", encoding="utf-8")

    result, _ = _run_gate(gate_fixture, output_dir=output_dir)

    assert result.returncode == 64
    assert (
        json.loads(result.stdout)["failure_reason"] == "output_directory_must_be_empty"
    )
    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert {path.name for path in output_dir.iterdir()} == {"keep.txt"}


def test_output_directory_inside_repository_is_rejected(
    gate_fixture: GateFixture,
) -> None:
    output_dir = gate_fixture.repository / "local-evidence"
    output_dir.mkdir()

    result, _ = _run_gate(gate_fixture, output_dir=output_dir)

    assert result.returncode == 64
    assert (
        json.loads(result.stdout)["failure_reason"]
        == "output_directory_must_be_outside_repository"
    )
    assert list(output_dir.iterdir()) == []
