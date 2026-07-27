from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations

from crypto_alert_v2.persistence.models import ImprovementReview


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load_revision() -> Any:
    path = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "0027_improvement_review_runtime.py"
    )
    spec = importlib.util.spec_from_file_location("improvement_review_runtime", path)
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


def test_review_runtime_revision_persists_official_interrupt_identity() -> None:
    revision = _load_revision()
    upgrade_sql = _render("upgrade")

    assert revision.revision == "0027_improvement_review_runtime"
    assert revision.down_revision == "0026_improvement_governance"
    for column in (
        "official_assistant_id",
        "official_thread_id",
        "official_run_id",
        "official_interrupt_id",
        "interrupt_payload",
        "checkpoint",
    ):
        assert f"ADD COLUMN {column}" in upgrade_sql
    assert "uq_improvement_reviews_actor_idempotency" in upgrade_sql
    assert "uq_improvement_reviews_official_thread" in upgrade_sql


def test_review_model_can_retain_a_pending_runtime_recovery_boundary() -> None:
    table = ImprovementReview.__table__

    assert table.c.task_id.nullable is True
    assert table.c.idempotency_key.nullable is False
    assert table.c.official_thread_id.nullable is True
    assert table.c.checkpoint.nullable is True
    assert table.c.interrupt_payload.nullable is True
