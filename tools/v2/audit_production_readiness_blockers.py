from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any

from crypto_alert_v2.atomic_io import atomic_write_text


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "2026-07-22.production-readiness-blockers.v1"
PROOF_LEVEL = "local-production-readiness-blocker-audit"
PLAN_PATH = PurePosixPath("docs/v2/14-v2-final-implementation-plan.md")

CRITICAL_REPOSITORY_ARTIFACTS = (
    ".github/workflows/ci.yml",
    "docs/v2/normative-baseline.json",
    "docs/v2/requirements-registry.yaml",
    "deploy/docker-compose.production.yml",
    "deploy/env.production.example",
    "deploy/alerts.yaml",
    "deploy/attestation-policy.yaml",
    "docs/v2/runbooks/production.md",
    "frontend/tests/e2e/hosted-production.spec.ts",
    "frontend/tests/e2e/hosted-security.spec.ts",
    "artifacts/v2-final/requirements-evidence.json",
    "artifacts/v2-final/final-review-attestation.json",
    "artifacts/v2-final/final-review-attestation.sigstore.json",
    "artifacts/v2-final/versions.json",
)

EXTERNAL_BLOCKERS = (
    {
        "id": "hosted_oidc_https_actor_matrix",
        "owner_input": "production_hosting_domain_oidc_and_test_identities",
        "evidence_paths": ("artifacts/v2-final/hosted-playwright",),
    },
    {
        "id": "hosted_aegra_rollout_failover",
        "owner_input": "production_ingress_instances_and_rollout_controller",
        "evidence_paths": (
            "artifacts/v2-final/deployment/preflight.json",
            "artifacts/v2-final/deployment/exit-drill.json",
        ),
    },
    {
        "id": "external_opentelemetry_backend",
        "owner_input": "free_self_hosted_otel_endpoint_and_query_access",
        "evidence_paths": ("artifacts/v2-final/observability",),
    },
    {
        "id": "production_alerts",
        "owner_input": "monitoring_backend_and_alert_routing",
        "evidence_paths": (
            "artifacts/v2-final/alerts/hosted-red.json",
            "artifacts/v2-final/alerts/hosted-green.json",
        ),
    },
    {
        "id": "production_database_pitr_dr",
        "owner_input": "managed_database_backup_and_disaster_recovery_targets",
        "evidence_paths": (
            "artifacts/v2-final/migrations",
            "artifacts/v2-final/deployment/upgrade-rollback",
        ),
    },
    {
        "id": "hosted_load_slo_security",
        "owner_input": "hosted_load_monitoring_and_security_observation_window",
        "evidence_paths": (
            "artifacts/v2-final/load/hosted-results.json",
            "artifacts/v2-final/slo/hosted-results.json",
            "artifacts/v2-final/security",
        ),
    },
    {
        "id": "registry_protected_signing_attestation",
        "owner_input": "registry_kms_or_keyless_signing_identity",
        "evidence_paths": (
            "artifacts/v2-final/deployment/candidate-digest.txt",
            "artifacts/v2-final/deployment/baseline-attestation.sigstore.json",
        ),
    },
    {
        "id": "external_lifecycle_deletion_receipts",
        "owner_input": "external_storage_trace_log_and_backup_deletion_adapters",
        "evidence_paths": (
            "artifacts/v2-final/pre-deletion-inventory.json",
            "artifacts/v2-final/post-deletion-survivor-scan.json",
        ),
    },
    {
        "id": "immutable_release_candidate",
        "owner_input": "protected_release_environment_and_source_candidate",
        "evidence_paths": (
            "artifacts/v2-final/deployment/source-sha.txt",
            "artifacts/v2-final/requirements-evidence.json",
        ),
    },
    {
        "id": "ordered_independent_review",
        "owner_input": "independent_spec_quality_custodian_and_release_reviewers",
        "evidence_paths": (
            "artifacts/v2-final/final-review-attestation.json",
            "artifacts/v2-final/final-review-attestation.sigstore.json",
        ),
    },
)

SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{12,}", re.IGNORECASE),
    re.compile(r"postgres(?:ql)?(?:\+asyncpg)?://[^:]+:[^@]+@", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])(?:sk|tvly)-[A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY", re.IGNORECASE),
)


class AuditError(RuntimeError):
    pass


def _secret_findings(payload: str) -> int:
    return sum(len(pattern.findall(payload)) for pattern in SECRET_PATTERNS)


def _safe_relative_path(value: str) -> str:
    normalized = PurePosixPath(value.strip().rstrip("/"))
    if normalized.is_absolute() or ".." in normalized.parts or not normalized.parts:
        raise AuditError("declared artifact path is unsafe")
    return normalized.as_posix()


def extract_create_paths(plan: str) -> list[str]:
    paths = re.findall(r"(?m)^- Create: `([^`]+)`\s*$", plan)
    return sorted({_safe_relative_path(path) for path in paths})


def extract_final_artifact_paths(plan: str) -> list[str]:
    paths = re.findall(r"artifacts/v2-final/[A-Za-z0-9._/-]+", plan)
    return sorted({_safe_relative_path(path) for path in paths})


def _path_state(repository_root: Path, relative: str) -> str:
    candidate = repository_root.joinpath(*PurePosixPath(relative).parts)
    if candidate.is_symlink():
        return "unsafe_symlink"
    if candidate.is_file():
        return "present_unverified_file"
    if candidate.is_dir():
        return "present_unverified_directory"
    return "missing"


def _inventory(repository_root: Path, paths: list[str]) -> dict[str, Any]:
    entries = [
        {"path": path, "state": _path_state(repository_root, path)}
        for path in paths
    ]
    existing = sum(entry["state"].startswith("present_unverified") for entry in entries)
    unsafe = sum(entry["state"] == "unsafe_symlink" for entry in entries)
    return {
        "declared": len(entries),
        "present_unverified": existing,
        "missing": len(entries) - existing - unsafe,
        "unsafe_symlink": unsafe,
        "entries": entries,
    }


def _git_identity(repository_root: Path) -> tuple[str, bool]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if head.returncode != 0 or status.returncode != 0:
        raise AuditError("git source identity is unavailable")
    value = head.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise AuditError("git HEAD is invalid")
    return value, bool(status.stdout.strip())


def build_report(
    repository_root: Path,
    *,
    plan: str,
    git_head: str,
    git_dirty: bool,
) -> dict[str, Any]:
    critical = _inventory(repository_root, list(CRITICAL_REPOSITORY_ARTIFACTS))
    create_paths = _inventory(repository_root, extract_create_paths(plan))
    final_paths = _inventory(repository_root, extract_final_artifact_paths(plan))
    external = []
    for blocker in EXTERNAL_BLOCKERS:
        evidence = _inventory(repository_root, list(blocker["evidence_paths"]))
        external.append(
            {
                "id": blocker["id"],
                "status": "requires_external_authority",
                "owner_input": blocker["owner_input"],
                "evidence": evidence,
            }
        )

    reasons = ["external_authority_evidence_unverified"]
    if git_dirty:
        reasons.append("working_tree_not_immutable")
    if critical["missing"] or critical["unsafe_symlink"]:
        reasons.append("critical_repository_artifacts_missing_or_unsafe")
    if final_paths["missing"] or final_paths["unsafe_symlink"]:
        reasons.append("final_release_artifacts_missing_or_unsafe")

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "blocked",
        "proof_level": PROOF_LEVEL,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "verdict": {"v2": "PARTIAL", "production_ready": False},
        "source": {"git_head": git_head, "git_dirty": git_dirty},
        "blocked_reasons": reasons,
        "critical_repository_artifacts": critical,
        "plan_create_path_audit": create_paths,
        "final_artifact_path_audit": final_paths,
        "external_authority_blockers": external,
        "required_owner_inputs": sorted(
            blocker["owner_input"] for blocker in EXTERNAL_BLOCKERS
        ),
        "policy": {
            "dotenv_files_read": False,
            "environment_values_read": False,
            "artifact_presence_treated_as_production_proof": False,
            "mock_fixture_skip_or_local_results_accepted_as_production": False,
        },
        "does_not_prove": [
            "production_readiness",
            "hosted_identity_or_https",
            "hosted_observability_or_alerts",
            "production_data_resilience",
            "protected_supply_chain_identity",
            "independent_release_review",
        ],
    }
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    findings = _secret_findings(encoded)
    if findings:
        raise AuditError("blocker report contains a secret-like value")
    report["secret_scan"] = {"findings": 0}
    return report


def _validated_repository_root(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_dir() or resolved.is_symlink():
        raise AuditError("repository root must be a real directory")
    return resolved


def _validated_output(path: Path, repository_root: Path) -> Path:
    if not path.is_absolute():
        raise AuditError("output path must be absolute")
    resolved = path.resolve()
    if resolved.is_relative_to(repository_root):
        raise AuditError("output path must be outside the repository")
    if resolved.exists() or resolved.is_symlink():
        raise AuditError("output path must not already exist")
    if not resolved.parent.is_dir() or resolved.parent.is_symlink():
        raise AuditError("output parent must be a real directory")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Emit secret-safe machine-readable production blocker evidence"
    )
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        repository_root = _validated_repository_root(args.repository_root)
        output = _validated_output(args.output, repository_root)
        plan_path = repository_root.joinpath(*PLAN_PATH.parts)
        if not plan_path.is_file() or plan_path.is_symlink():
            raise AuditError("final implementation plan is unavailable")
        plan = plan_path.read_text(encoding="utf-8")
        git_head, git_dirty = _git_identity(repository_root)
        report = build_report(
            repository_root,
            plan=plan,
            git_head=git_head,
            git_dirty=git_dirty,
        )
        atomic_write_text(
            output,
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            mode=0o600,
        )
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "blocked",
                    "proof_level": PROOF_LEVEL,
                    "blocked_reason_count": len(report["blocked_reasons"]),
                    "external_blocker_count": len(
                        report["external_authority_blockers"]
                    ),
                    "output_written": True,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        raise SystemExit(78)
    except SystemExit:
        raise
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "error",
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
