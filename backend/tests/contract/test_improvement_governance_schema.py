from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations

from crypto_alert_v2.persistence.models import ImprovementReleaseEvent


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load_revision() -> Any:
    path = BACKEND_ROOT / "alembic" / "versions" / "0026_improvement_governance.py"
    spec = importlib.util.spec_from_file_location("improvement_governance", path)
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _render(method_name: str) -> str:
    revision = _load_revision()
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    getattr(revision, method_name)()
    return output.getvalue()


def test_improvement_governance_revision_builds_every_durable_stage() -> None:
    revision = _load_revision()
    upgrade_sql = _render("upgrade")

    assert revision.revision == "0026_improvement_governance"
    assert revision.down_revision == "0025_improvement_cases"
    for table in (
        "improvement_datasets",
        "improvement_dataset_members",
        "improvement_candidates",
        "improvement_experiments",
        "improvement_reviews",
        "improvement_shadow_runs",
        "improvement_release_events",
    ):
        assert f"CREATE TABLE app.{table} (" in upgrade_sql
    assert "BEFORE UPDATE OR DELETE ON app.improvement_release_events" in upgrade_sql
    assert "improvement_release_events are append-only" in upgrade_sql


def test_improvement_governance_downgrade_removes_dependents_first() -> None:
    downgrade_sql = _render("downgrade")
    tables = (
        "improvement_release_events",
        "improvement_shadow_runs",
        "improvement_reviews",
        "improvement_experiments",
        "improvement_dataset_members",
        "improvement_candidates",
        "improvement_datasets",
    )

    positions = [downgrade_sql.index(f"DROP TABLE app.{table}") for table in tables]
    assert positions == sorted(positions)


def test_release_event_orm_has_no_mutable_update_timestamp() -> None:
    assert "created_at" in ImprovementReleaseEvent.__table__.c
    assert "updated_at" not in ImprovementReleaseEvent.__table__.c
