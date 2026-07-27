from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "v2" / "summarize_trivy_image.py"
SPEC = importlib.util.spec_from_file_location("summarize_trivy_image", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _report(vulnerabilities: list[dict[str, object]]) -> dict[str, object]:
    return {
        "SchemaVersion": 2,
        "ArtifactName": "sha256:image",
        "ArtifactType": "container_image",
        "Results": [{"Target": "debian", "Vulnerabilities": vulnerabilities}],
    }


def test_trivy_summary_fails_closed_on_high_or_critical() -> None:
    summary = MODULE.summarize(
        _report(
            [
                {"VulnerabilityID": "CVE-critical", "Severity": "CRITICAL"},
                {"VulnerabilityID": "CVE-high", "Severity": "HIGH"},
                {
                    "VulnerabilityID": "CVE-medium",
                    "Severity": "MEDIUM",
                    "FixedVersion": "2",
                },
            ]
        ),
        expected_image_id="sha256:image",
    )

    assert summary["status"] == "failed"
    assert summary["vulnerabilities"]["blocking_occurrences"] == 2
    assert summary["vulnerabilities"]["fixable"] == 1
    assert summary["policy"] == {
        "maximum_critical": 0,
        "maximum_high": 0,
        "fail_closed": True,
    }


def test_trivy_summary_passes_when_no_blocking_severity_exists() -> None:
    summary = MODULE.summarize(
        _report([{"VulnerabilityID": "CVE-low", "Severity": "LOW"}]),
        expected_image_id="sha256:image",
    )

    assert summary["status"] == "passed"
    assert summary["vulnerabilities"]["by_severity"] == {"LOW": 1}


def test_trivy_summary_rejects_report_for_another_image() -> None:
    with pytest.raises(MODULE.SummaryError, match="image_identity_mismatch"):
        MODULE.summarize(_report([]), expected_image_id="sha256:other")
