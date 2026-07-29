from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "v2" / "audit_production_readiness_blockers.py"
SPEC = importlib.util.spec_from_file_location("production_readiness_blockers", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    plan_path = repository / "docs" / "v2" / "14-v2-final-implementation-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan = "\n".join(
        (
            "- Create: `.github/workflows/ci.yml`",
            "- Create: `artifacts/v2-final/versions.json`",
            "Publish `artifacts/v2-final/load/hosted-results.json`.",
        )
    )
    plan_path.write_text(plan + "\n", encoding="utf-8")
    workflow = repository / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: fixture\n", encoding="utf-8")
    return repository, plan


def test_plan_parsers_return_unique_safe_paths() -> None:
    plan = "\n".join(
        (
            "- Create: `backend/a.py`",
            "- Create: `backend/a.py`",
            "- Create: `artifacts/v2-final/result.json`",
            "Use `artifacts/v2-final/result.json` and ",
            "`artifacts/v2-final/logs/`.",
        )
    )

    assert MODULE.extract_create_paths(plan) == [
        "artifacts/v2-final/result.json",
        "backend/a.py",
    ]
    assert MODULE.extract_final_artifact_paths(plan) == [
        "artifacts/v2-final/logs",
        "artifacts/v2-final/result.json",
    ]
    with pytest.raises(MODULE.AuditError, match="unsafe"):
        MODULE._safe_relative_path("../outside")


def test_secret_scan_rejects_keys_without_matching_task_paths() -> None:
    assert MODULE._secret_findings("task-14-production-gate") == 0
    assert MODULE._secret_findings("sk-" + "a" * 20) == 1


def test_report_never_treats_presence_as_production_proof(tmp_path: Path) -> None:
    repository, plan = _repository(tmp_path)

    report = MODULE.build_report(
        repository,
        plan=plan,
        git_head="a" * 40,
        git_dirty=True,
    )

    assert report["status"] == "blocked"
    assert report["verdict"] == {"v2": "PARTIAL", "production_ready": False}
    assert report["plan_create_path_audit"]["declared"] == 2
    assert report["plan_create_path_audit"]["present_unverified"] == 1
    assert report["final_artifact_path_audit"]["declared"] == 2
    assert report["critical_repository_artifacts"]["present_unverified"] == 1
    assert len(report["external_authority_blockers"]) == 10
    assert all(
        blocker["status"] == "requires_external_authority"
        for blocker in report["external_authority_blockers"]
    )
    assert report["policy"] == {
        "dotenv_files_read": False,
        "environment_values_read": False,
        "artifact_presence_treated_as_production_proof": False,
        "mock_fixture_skip_or_local_results_accepted_as_production": False,
    }
    assert report["secret_scan"] == {"findings": 0}


def test_external_blockers_require_free_observability_without_notifications(
    tmp_path: Path,
) -> None:
    repository, plan = _repository(tmp_path)

    report = MODULE.build_report(
        repository,
        plan=plan,
        git_head="a" * 40,
        git_dirty=False,
    )

    blockers = {
        blocker["id"]: blocker
        for blocker in report["external_authority_blockers"]
    }
    assert "external_opentelemetry_backend" in blockers
    assert "production_alerts" in blockers
    assert "external_langsmith_langfuse" not in blockers
    assert "production_alerts_and_notification_receipts" not in blockers
    owner_inputs = " ".join(report["required_owner_inputs"])
    assert "langsmith" not in owner_inputs
    assert "langfuse" not in owner_inputs
    assert "notification_provider" not in owner_inputs


def test_cli_writes_external_report_and_exits_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repository, _plan = _repository(tmp_path)
    output = tmp_path / "production-readiness-blockers.json"
    monkeypatch.setattr(MODULE, "_git_identity", lambda _root: ("b" * 40, True))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--repository-root",
            str(repository),
            "--output",
            str(output),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        MODULE.main()

    assert exc_info.value.code == 78
    summary = json.loads(capsys.readouterr().out)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert summary == {
        "schema_version": MODULE.SCHEMA_VERSION,
        "status": "blocked",
        "proof_level": MODULE.PROOF_LEVEL,
        "blocked_reason_count": len(report["blocked_reasons"]),
        "external_blocker_count": 10,
        "output_written": True,
    }
    assert report["source"] == {"git_head": "b" * 40, "git_dirty": True}
    assert report["secret_scan"]["findings"] == 0
    assert not (repository / output.name).exists()


def test_source_has_no_environment_value_access_or_production_pass_path() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "os.environ" not in source
    assert "getenv(" not in source
    assert '"status": "passed"' not in source
    assert '"production_ready": True' not in source
    assert "raise SystemExit(78)" in source
    assert "artifact_presence_treated_as_production_proof" in source
    assert "mock_fixture_skip_or_local_results_accepted_as_production" in source
