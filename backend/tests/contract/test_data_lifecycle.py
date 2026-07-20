from __future__ import annotations

from pathlib import Path
import inspect

import pytest
from pydantic import ValidationError
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from crypto_alert_v2.api.schemas import (
    DataDeletionSubmission,
    DataLifecyclePolicyUpdate,
)
from crypto_alert_v2.api.app import create_app
from crypto_alert_v2.lifecycle.service import (
    LifecycleError,
    compute_manifest_hash,
    validate_manifest_hash,
)
from crypto_alert_v2.persistence.base import Base, PRODUCT_SCHEMA
from crypto_alert_v2.persistence.models import (
    DATA_LIFECYCLE_DELETION_STATUSES,
    DATA_LIFECYCLE_EXPORT_STATUSES,
    DataDeletionJob,
    DataExportJob,
    DataLifecyclePolicy,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = BACKEND_ROOT / "alembic" / "versions" / "0022_data_lifecycle.py"


def _unique_sets(model: type[object]) -> set[frozenset[str]]:
    return {
        frozenset(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints  # type: ignore[attr-defined]
        if isinstance(constraint, UniqueConstraint)
    }


def test_lifecycle_models_are_scoped_and_have_explicit_status_constraints() -> None:
    assert {table.name for table in Base.metadata.sorted_tables if table.name.startswith("data_")} == {
        "data_lifecycle_policies",
        "data_export_jobs",
        "data_deletion_jobs",
    }
    for model in (DataLifecyclePolicy, DataExportJob, DataDeletionJob):
        assert model.__table__.schema == PRODUCT_SCHEMA
        assert {"tenant_id", "workspace_id", "owner_user_id"} <= set(model.__table__.c.keys())
        assert frozenset({"tenant_id", "workspace_id", "owner_user_id"}) in _unique_sets(model) or (
            model is not DataLifecyclePolicy
        )
    assert frozenset(
        {"tenant_id", "workspace_id", "owner_user_id", "idempotency_key"}
    ) in _unique_sets(DataExportJob)
    assert frozenset(
        {"tenant_id", "workspace_id", "owner_user_id", "idempotency_key"}
    ) in _unique_sets(DataDeletionJob)
    assert isinstance(DataExportJob.__table__.c.manifest.type, JSONB)
    assert isinstance(DataExportJob.__table__.c.bundle.type, JSONB)
    assert isinstance(DataDeletionJob.__table__.c.system_status.type, JSONB)
    assert set(DATA_LIFECYCLE_EXPORT_STATUSES) == {"queued", "running", "succeeded", "failed"}
    assert set(DATA_LIFECYCLE_DELETION_STATUSES) == {
        "queued", "running", "pending_external", "succeeded", "blocked_legal_hold", "failed"
    }


def test_policy_defaults_and_strict_deletion_confirmation() -> None:
    defaults = DataLifecyclePolicy.__table__.c
    assert str(defaults.product_retention_days.server_default.arg) == "365"
    assert str(defaults.artifact_retention_days.server_default.arg) == "365"
    assert str(defaults.task_retention_days.server_default.arg) == "365"
    assert str(defaults.run_retention_days.server_default.arg) == "365"
    assert str(defaults.decision_retention_days.server_default.arg) == "365"
    assert str(defaults.usage_retention_days.server_default.arg) == "365"
    assert str(defaults.completed_checkpoint_retention_days.server_default.arg) == "30"
    assert str(defaults.technical_projection_retention_days.server_default.arg) == "30"
    assert str(defaults.log_retention_days.server_default.arg) == "30"
    assert str(defaults.backup_retention_days.server_default.arg) == "35"
    assert str(defaults.retain_raw_prompt.server_default.arg) == "false"
    assert str(defaults.retain_raw_response.server_default.arg) == "false"
    assert DataDeletionSubmission(confirmation="DELETE MY DATA").scope == "user_data"
    with pytest.raises(ValidationError):
        DataDeletionSubmission(confirmation="delete my data")
    with pytest.raises(ValidationError):
        DataDeletionSubmission(confirmation="DELETE MY DATA", extra_field="x")
    with pytest.raises(ValidationError):
        DataLifecyclePolicyUpdate(legal_hold_active=True)
    with pytest.raises(ValidationError):
        DataLifecyclePolicyUpdate(legal_hold_active=False, legal_hold_reason="reason")


def test_manifest_hash_is_self_validating_and_detects_tampering() -> None:
    bundle = {"bundle_version": 1, "records": {"tasks": [{"id": "task-1"}]}}
    manifest = {
        "manifest_version": 1,
        "export_id": "export-1",
        "scope": "user_data",
        "bundle_sha256": __import__("hashlib").sha256(
            __import__("json").dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "tables": {"tasks": {"row_count": 1, "records_sha256": "a" * 64}},
    }
    manifest_hash = compute_manifest_hash(manifest)
    validate_manifest_hash(manifest, manifest_hash, bundle=bundle)
    tampered = {**manifest, "scope": "other_data"}
    with pytest.raises(LifecycleError, match="manifest hash"):
        validate_manifest_hash(tampered, manifest_hash, bundle=bundle)


def test_migration_is_reversible_and_worker_uses_the_unified_runtime_boundary() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0022_data_lifecycle"' in source
    assert 'down_revision = "0021_scheduled_monitors"' in source
    for table in ("data_lifecycle_policies", "data_export_jobs", "data_deletion_jobs"):
        assert f'"{table}"' in source
        assert f'op.drop_table("{table}"' in source
    from crypto_alert_v2.lifecycle.worker import LifecycleWorker
    from crypto_alert_v2.workers.runtime import WorkerRuntime

    assert inspect.iscoroutinefunction(LifecycleWorker.dispatch_once)
    assert inspect.iscoroutinefunction(LifecycleWorker.release_owned_leases)
    assert "workers" in inspect.signature(WorkerRuntime).parameters


def test_product_api_exposes_typed_lifecycle_routes() -> None:
    app = create_app(service=object(), mode="local")
    routes = {
        (route.path, method)
        for route in app.routes
        if route.path.startswith("/api/v2/data-lifecycle")
        for method in getattr(route, "methods", set())
    }
    assert ("/api/v2/data-lifecycle/policy", "GET") in routes
    assert ("/api/v2/data-lifecycle/policy", "PUT") in routes
    assert ("/api/v2/data-lifecycle/exports", "POST") in routes
    assert ("/api/v2/data-lifecycle/exports/{export_id}", "GET") in routes
    assert ("/api/v2/data-lifecycle/exports/{export_id}/manifest", "GET") in routes
    assert ("/api/v2/data-lifecycle/exports/{export_id}/bundle", "GET") in routes
    assert ("/api/v2/data-lifecycle/deletions", "POST") in routes
    assert ("/api/v2/data-lifecycle/deletions/{deletion_id}", "GET") in routes
