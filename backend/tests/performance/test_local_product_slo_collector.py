from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from crypto_alert_v2.evaluation.product_slo_observation import (
    FORMAL_SLO_METRIC_NAMES,
    EVENTS_QUERY,
    PROJECTIONS_QUERY,
    RUNS_QUERY,
    CollectedProductData,
    EventRecord,
    ProjectionIntegrityRecord,
    RunRecord,
    build_local_observation_report,
    nearest_rank_percentile,
)


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "v2" / "collect_local_product_slo.py"


def _collected_data() -> CollectedProductData:
    started_at = datetime(2026, 7, 18, 0, tzinfo=UTC)
    run_id = "00000000-0000-0000-0000-000000000101"
    task_id = "00000000-0000-0000-0000-000000000201"
    return CollectedProductData(
        observed_at=started_at + timedelta(minutes=5),
        snapshot_sha256="b" * 64,
        migration_revision="0018_progressive_events",
        runs=(
            RunRecord(
                run_id=run_id,
                task_id=task_id,
                task_created_at=started_at,
                run_created_at=started_at + timedelta(milliseconds=20),
                started_at=started_at + timedelta(milliseconds=50),
                finished_at=started_at + timedelta(seconds=2),
                status="succeeded",
                failure_code=None,
            ),
        ),
        events=(
            EventRecord(
                run_id=run_id,
                event_type="market.snapshot.committed",
                payload_hash="c" * 64,
                created_at=started_at + timedelta(milliseconds=300),
            ),
            EventRecord(
                run_id=run_id,
                event_type="research.evidence.committed",
                payload_hash="d" * 64,
                created_at=started_at + timedelta(milliseconds=500),
            ),
            EventRecord(
                run_id=run_id,
                event_type="agent.output.committed",
                payload_hash="e" * 64,
                created_at=started_at + timedelta(milliseconds=900),
            ),
            EventRecord(
                run_id=run_id,
                event_type="artifact.committed",
                payload_hash="f" * 64,
                created_at=started_at + timedelta(seconds=1),
            ),
            EventRecord(
                run_id=run_id,
                event_type="run.terminal",
                payload_hash="1" * 64,
                created_at=started_at + timedelta(seconds=2),
            ),
        ),
        projection_integrity=(
            ProjectionIntegrityRecord(
                run_id=run_id,
                artifact_version_count=1,
                decision_count=1,
                web_evidence_count=1,
            ),
        ),
    )


def test_nearest_rank_percentile_is_deterministic() -> None:
    assert nearest_rank_percentile([1.0], 0.95) == 1.0
    assert nearest_rank_percentile([5.0, 1.0, 4.0, 2.0, 3.0], 0.8) == 4.0
    with pytest.raises(ValueError, match="at least one"):
        nearest_rank_percentile([], 0.95)


def test_reviewed_queries_are_actor_scoped_and_payload_free() -> None:
    for query in (RUNS_QUERY, EVENTS_QUERY, PROJECTIONS_QUERY):
        assert "CAST(:tenant_id AS uuid)" in query
        assert "CAST(:workspace_id AS uuid)" in query
    assert "de.payload," not in EVENTS_QUERY
    assert "source_url" not in PROJECTIONS_QUERY
    assert ".content" not in PROJECTIONS_QUERY
    assert "d.decision" not in PROJECTIONS_QUERY
    assert "d.risk_verdict" not in PROJECTIONS_QUERY


def test_product_database_report_cannot_claim_formal_slo_acceptance() -> None:
    window_start = datetime(2026, 7, 18, 0, tzinfo=UTC)
    report = build_local_observation_report(
        _collected_data(),
        window_started_at=window_start,
        window_finished_at=window_start + timedelta(hours=1),
        scope_label="unit-test-scope",
        environment="test",
        traffic_class="synthetic",
        source_identity="dirty-working-tree",
        database_source_label="unit-test-postgres",
    )

    assert report["schema_version"] == ("2026-07-18.local-product-slo-observation.v1")
    assert report["proof_level"] == "local-product-database-observation"
    assert report["formal_slo_coverage"] == {
        "measured": 0,
        "required": 12,
        "production_acceptance": False,
    }
    assert set(report["metrics"]) == set(FORMAL_SLO_METRIC_NAMES)
    assert {metric["measurement_status"] for metric in report["metrics"].values()} <= {
        "proxy",
        "unavailable",
    }
    assert report["metrics"]["market_analysis_p95_ms"]["value"] == 850.0
    assert report["metrics"]["market_analysis_max_ms"]["value"] == 1_950.0
    assert report["metrics"]["duplicate_product_event_rate"]["value"] == 0.0
    assert (
        report["metrics"]["allowed_evidence_reference_completeness_rate"][
            "measurement_status"
        ]
        == "unavailable"
    )
    assert (
        report["diagnostics"]["successful_projection_chain_integrity_rate"]["value"]
        == 1.0
    )
    assert (
        report["diagnostics"]["run_started_to_first_persisted_stage_event_p95_ms"][
            "value"
        ]
        == 250.0
    )
    assert report["provenance"]["payload_columns_read"] is False
    encoded = json.dumps(report, sort_keys=True)
    assert '"passed"' not in encoded
    assert "database_url" not in encoded
    assert "tenant_id" not in encoded
    assert "workspace_id" not in encoded


def test_collector_cli_requires_database_url_only_from_environment(
    tmp_path: Path,
) -> None:
    output = tmp_path / "observation.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--started-at",
            "2026-07-18T00:00:00Z",
            "--finished-at",
            "2026-07-18T01:00:00Z",
            "--tenant-id",
            "00000000-0000-0000-0000-000000000001",
            "--workspace-id",
            "00000000-0000-0000-0000-000000000002",
            "--scope-label",
            "credential-redaction-test",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "PRODUCT_DATABASE_URL": (
                "postgresql+asyncpg://collector:never-print-this@127.0.0.1:1/db"
            ),
        },
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "never-print-this" not in result.stdout
    assert "never-print-this" not in result.stderr
    assert not output.exists()


def test_atomic_report_writer_uses_owner_only_permissions(tmp_path: Path) -> None:
    from crypto_alert_v2.evaluation.product_slo_observation import write_report

    output = tmp_path / "observation.json"
    write_report(output, {"proof_level": "local-product-database-observation"})

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
