from __future__ import annotations

import json
from pathlib import Path
import stat
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "v2" / "run_slo_probe.py"


def _measurements() -> dict[str, object]:
    values = {
        "api_agent_availability_rate": 1.0,
        "request_confirmation_p95_ms": 1_000,
        "first_visible_stage_event_p95_ms": 3_000,
        "market_analysis_p95_ms": 150_000,
        "market_analysis_max_ms": 180_000,
        "reconnect_success_rate": 0.98,
        "duplicate_product_event_rate": 0.0009,
        "structured_output_success_rate": 0.97,
        "allowed_evidence_reference_completeness_rate": 1.0,
        "checkpoint_recovery_success_rate": 0.95,
        "cross_tenant_leak_count": 0,
        "secret_leak_count": 0,
    }
    return {
        "schema_version": "2026-07-18.slo-measurements.v1",
        "profile": "local-rehearsal",
        "release_tier": "internal_alpha",
        "measurement_source": "synthetic-contract",
        "window": {
            "started_at": "2026-07-18T00:00:00Z",
            "finished_at": "2026-07-18T01:00:00Z",
        },
        "measurements": {
            name: {
                "value": value,
                "sample_count": 100,
                "query_id": f"contract:{name}",
            }
            for name, value in values.items()
        },
    }


def _run(
    measurements: Path,
    output: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--release-tier",
            "internal_alpha",
            "--measurements",
            str(measurements),
            "--output",
            str(output),
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_synthetic_source_candidate_covers_every_internal_alpha_slo(
    tmp_path: Path,
) -> None:
    measurements = tmp_path / "measurements.json"
    output = tmp_path / "slo.json"
    _write(measurements, _measurements())

    result = _run(measurements, output)

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["proof_level"] == "synthetic-source-candidate-slo-contract"
    assert len(report["metrics"]) == 12
    assert all(
        metric["passed"]
        for metric in report["metrics"].values()
        if metric["threshold"] is not None
    )
    assert report["metrics"]["duplicate_product_event_rate"]["comparator"] == (
        "max_exclusive"
    )
    assert report["metrics"]["api_agent_availability_rate"]["threshold"] is None
    assert report["metrics"]["api_agent_availability_rate"]["passed"] is None
    assert "secret_scan" not in report
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_slo_contract_fails_when_any_threshold_is_missed(tmp_path: Path) -> None:
    payload = _measurements()
    payload["measurements"]["reconnect_success_rate"]["value"] = 0.979  # type: ignore[index]
    measurements = tmp_path / "failed-measurements.json"
    output = tmp_path / "failed-slo.json"
    _write(measurements, payload)

    result = _run(measurements, output)

    assert result.returncode == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["metrics"]["reconnect_success_rate"]["passed"] is False
    assert report["metrics"]["request_confirmation_p95_ms"]["passed"] is True


def test_slo_contract_rejects_missing_zero_sample_and_non_finite_metrics(
    tmp_path: Path,
) -> None:
    cases = []
    missing = _measurements()
    missing["measurements"].pop("secret_leak_count")  # type: ignore[union-attr]
    cases.append(missing)
    zero_sample = _measurements()
    zero_sample["measurements"]["market_analysis_p95_ms"]["sample_count"] = 0  # type: ignore[index]
    cases.append(zero_sample)
    non_finite = _measurements()
    non_finite["measurements"]["market_analysis_p95_ms"]["value"] = float("nan")  # type: ignore[index]
    cases.append(non_finite)

    for index, payload in enumerate(cases):
        measurements = tmp_path / f"invalid-{index}.json"
        output = tmp_path / f"invalid-{index}-output.json"
        _write(measurements, payload)
        result = _run(measurements, output)
        assert result.returncode == 1
        assert not output.exists()
        error = json.loads(result.stderr)
        assert error["error_type"] == "ValueError"


def test_slo_contract_refuses_hosted_claim_without_hosted_provenance(
    tmp_path: Path,
) -> None:
    measurements = tmp_path / "measurements.json"
    output = tmp_path / "hosted-slo.json"
    _write(measurements, _measurements())

    result = _run(
        measurements,
        output,
        "--profile",
        "hosted-production",
    )

    assert result.returncode == 78
    assert not output.exists()
    error = json.loads(result.stderr)
    assert error["status"] == "failed"
    assert error["error_type"] == "RuntimeError"


def test_slo_contract_rejects_unbound_local_observed_values(tmp_path: Path) -> None:
    payload = _measurements()
    payload["measurement_source"] = "local-observed"
    measurements = tmp_path / "unbound-local-observed.json"
    output = tmp_path / "unbound-local-observed-report.json"
    _write(measurements, payload)

    result = _run(measurements, output)

    assert result.returncode == 1
    assert not output.exists()
    error = json.loads(result.stderr)
    assert error["status"] == "failed"
    assert error["error_type"] == "ValueError"
