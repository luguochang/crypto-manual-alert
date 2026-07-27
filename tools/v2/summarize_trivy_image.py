from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any


BLOCKING_SEVERITIES = frozenset({"CRITICAL", "HIGH"})


class SummaryError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize(report: dict[str, Any], *, expected_image_id: str) -> dict[str, Any]:
    if report.get("SchemaVersion") != 2:
        raise SummaryError("unsupported_trivy_schema")
    if report.get("ArtifactType") != "container_image":
        raise SummaryError("not_a_container_image_report")
    if report.get("ArtifactName") != expected_image_id:
        raise SummaryError("image_identity_mismatch")

    vulnerabilities = [
        vulnerability
        for result in report.get("Results") or []
        for vulnerability in (result.get("Vulnerabilities") or [])
    ]
    severity_counts = Counter(
        str(vulnerability.get("Severity") or "UNKNOWN").upper()
        for vulnerability in vulnerabilities
    )
    blocking = [
        vulnerability
        for vulnerability in vulnerabilities
        if str(vulnerability.get("Severity") or "UNKNOWN").upper()
        in BLOCKING_SEVERITIES
    ]
    blocking_cves = sorted(
        {
            str(vulnerability.get("VulnerabilityID"))
            for vulnerability in blocking
            if vulnerability.get("VulnerabilityID")
        }
    )
    fixable = sum(bool(vulnerability.get("FixedVersion")) for vulnerability in vulnerabilities)
    return {
        "schema_version": "1.0",
        "status": "failed" if blocking else "passed",
        "proof_level": "local-exact-container-image-trivy-cve-audit",
        "image_id": expected_image_id,
        "trivy": {
            "schema_version": report["SchemaVersion"],
            "result_targets": len(report.get("Results") or []),
        },
        "policy": {
            "maximum_critical": 0,
            "maximum_high": 0,
            "fail_closed": True,
        },
        "vulnerabilities": {
            "total": len(vulnerabilities),
            "by_severity": dict(sorted(severity_counts.items())),
            "fixable": fixable,
            "unfixed": len(vulnerabilities) - fixable,
            "blocking_occurrences": len(blocking),
            "blocking_unique_cves": blocking_cves,
        },
        "does_not_prove": [
            "registry_published_image_digest",
            "protected_signing_identity",
            "transparency_log_inclusion",
            "signed_oci_attestation",
            "production_release",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-image-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    report = json.loads(arguments.report.read_text(encoding="utf-8"))
    summary = summarize(report, expected_image_id=arguments.expected_image_id)
    summary["trivy"]["report_sha256"] = _sha256(arguments.report)
    arguments.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
