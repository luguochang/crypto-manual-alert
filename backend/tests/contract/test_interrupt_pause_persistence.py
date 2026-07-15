from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from crypto_alert_v2.persistence.base import PRODUCT_SCHEMA
from crypto_alert_v2.persistence.models import (
    INTERRUPT_PAUSE_STATUSES,
    InterruptPause,
    InterruptProjection,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load_revision() -> Any:
    path = BACKEND_ROOT / "alembic" / "versions" / "0007_interrupt_pauses.py"
    spec = importlib.util.spec_from_file_location("product_interrupt_pauses", path)
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _render_revision_sql(method_name: str) -> str:
    revision = _load_revision()
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    getattr(revision, method_name)()
    return output.getvalue()


def _unique_column_sets(table: Any) -> set[frozenset[str]]:
    return {
        frozenset(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_interrupt_pause_model_enforces_aggregate_identity_and_scope() -> None:
    table = InterruptPause.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert table.schema == PRODUCT_SCHEMA
    assert {
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "run_id",
        "pause_version",
        "root_thread_id",
        "root_checkpoint_ns",
        "root_checkpoint_id",
        "root_checkpoint_map",
        "member_set_hash",
        "status",
        "expires_at",
        "resume_run_id",
        "accepted_payload_hash",
        "created_at",
        "updated_at",
    } <= set(table.c.keys())
    assert table.c.resume_run_id.nullable is True
    assert table.c.accepted_payload_hash.nullable is True
    assert INTERRUPT_PAUSE_STATUSES == (
        "pending",
        "responding",
        "resolved",
        "expired",
        "resume_failed",
        "cancelled",
    )

    unique_columns = _unique_column_sets(table)
    assert frozenset({"run_id", "pause_version"}) in unique_columns
    assert frozenset(
        {"run_id", "root_checkpoint_ns", "root_checkpoint_id"}
    ) in unique_columns
    assert frozenset({"resume_run_id"}) in unique_columns

    run_scope = constraints["fk_interrupt_pauses_run_scope"]
    assert isinstance(run_scope, ForeignKeyConstraint)
    assert tuple(column.name for column in run_scope.columns) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "run_id",
    )
    assert tuple(element.target_fullname for element in run_scope.elements) == (
        "app.runs.tenant_id",
        "app.runs.workspace_id",
        "app.runs.owner_user_id",
        "app.runs.task_id",
        "app.runs.id",
    )

    resume_scope = constraints["fk_interrupt_pauses_resume_scope"]
    assert isinstance(resume_scope, ForeignKeyConstraint)
    assert tuple(column.name for column in resume_scope.columns) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "resume_run_id",
    )
    assert tuple(element.target_fullname for element in resume_scope.elements) == (
        "app.runs.tenant_id",
        "app.runs.workspace_id",
        "app.runs.owner_user_id",
        "app.runs.task_id",
        "app.runs.id",
    )

    status = constraints["ck_interrupt_pauses_status"]
    assert isinstance(status, CheckConstraint)
    status_sql = str(status.sqltext)
    assert {
        value for value in INTERRUPT_PAUSE_STATUSES if f"'{value}'" in status_sql
    } == set(INTERRUPT_PAUSE_STATUSES)


def test_interrupt_pause_membership_is_unique_scope_safe_and_bidirectional() -> None:
    table = InterruptProjection.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert table.c.pause_id.nullable is False
    assert frozenset({"pause_id", "official_interrupt_id"}) in _unique_column_sets(table)

    pause_scope = constraints["fk_interrupt_inbox_pause_scope"]
    assert isinstance(pause_scope, ForeignKeyConstraint)
    assert tuple(column.name for column in pause_scope.columns) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "run_id",
        "pause_id",
    )
    assert tuple(element.target_fullname for element in pause_scope.elements) == (
        "app.interrupt_pauses.tenant_id",
        "app.interrupt_pauses.workspace_id",
        "app.interrupt_pauses.owner_user_id",
        "app.interrupt_pauses.task_id",
        "app.interrupt_pauses.run_id",
        "app.interrupt_pauses.id",
    )
    assert pause_scope.ondelete == "CASCADE"

    assert InterruptPause.projections.property.back_populates == "pause"
    assert InterruptPause.projections.property.uselist is True
    assert InterruptProjection.pause.property.back_populates == "projections"
    assert InterruptProjection.pause.property.uselist is False


def test_interrupt_pause_tables_compile_with_postgresql_constraints() -> None:
    pause_sql = str(
        CreateTable(InterruptPause.__table__).compile(dialect=postgresql.dialect())
    )
    projection_sql = str(
        CreateTable(InterruptProjection.__table__).compile(dialect=postgresql.dialect())
    )

    assert "CONSTRAINT uq_interrupt_pauses_run_version UNIQUE (run_id, pause_version)" in pause_sql
    assert (
        "CONSTRAINT uq_interrupt_pauses_root_checkpoint UNIQUE "
        "(run_id, root_checkpoint_ns, root_checkpoint_id)"
    ) in pause_sql
    assert "CONSTRAINT uq_interrupt_pauses_resume_run UNIQUE (resume_run_id)" in pause_sql
    assert "CONSTRAINT fk_interrupt_pauses_run_scope FOREIGN KEY" in pause_sql
    assert "CONSTRAINT fk_interrupt_pauses_resume_scope FOREIGN KEY" in pause_sql
    assert (
        "CONSTRAINT uq_interrupt_inbox_pause_member UNIQUE "
        "(pause_id, official_interrupt_id)"
    ) in projection_sql
    assert "CONSTRAINT fk_interrupt_inbox_pause_scope FOREIGN KEY" in projection_sql


def test_interrupt_pause_revision_backfills_legacy_rows_and_preserves_compatibility() -> None:
    revision = _load_revision()
    assert revision.revision == "0007_interrupt_pauses"
    assert len(revision.revision) <= 32
    assert revision.down_revision == "0006_interrupt_projection"

    upgrade_sql = _render_revision_sql("upgrade")
    preflight_position = upgrade_sql.index("legacy interrupt pause migration blocked")
    create_table_position = upgrade_sql.index("CREATE TABLE app.interrupt_pauses (")
    assert preflight_position < create_table_position
    assert "active legacy respond command(s)" in upgrade_sql
    assert "multiple active legacy pauses" in upgrade_sql
    assert "namespace/checkpoint pairs" in upgrade_sql
    assert "non-root checkpoint namespace" in upgrade_sql
    assert "no official thread identity" in upgrade_sql
    assert "mixed member statuses" in upgrade_sql
    assert "Resolve or cancel the listed work before retrying" in upgrade_sql
    assert "revision 0007" in upgrade_sql
    assert "CREATE TABLE app.interrupt_pauses (" in upgrade_sql
    assert (
        "ALTER TABLE app.interrupt_inbox ADD COLUMN pause_id UUID;" in upgrade_sql
    )
    assert "INSERT INTO app.interrupt_pauses" in upgrade_sql
    assert "'{}'::jsonb AS root_checkpoint_map" in upgrade_sql
    assert "sha256(" in upgrade_sql
    assert "convert_to(" in upgrade_sql
    assert "row_number() OVER" in upgrade_sql
    assert "PARTITION BY run_id" in upgrade_sql
    assert "WHEN pause_version = pause_count THEN resume_run_id" in upgrade_sql
    assert (
        "CONSTRAINT ck_interrupt_pauses_status CHECK (status IN "
        "('pending', 'responding', 'resolved', 'expired', 'resume_failed', "
        "'cancelled'))"
    ) in upgrade_sql
    assert (
        "CREATE UNIQUE INDEX uq_interrupt_pauses_one_active_task ON "
        "app.interrupt_pauses (tenant_id, workspace_id, owner_user_id, task_id) "
        "WHERE status IN ('pending', 'responding');"
    ) in upgrade_sql
    assert "UPDATE app.interrupt_inbox AS inbox" in upgrade_sql
    assert "duplicate legacy interrupt membership was found" in upgrade_sql
    assert "ALTER TABLE app.interrupt_inbox ALTER COLUMN pause_id SET NOT NULL" in upgrade_sql
    assert (
        "ALTER TABLE app.interrupt_inbox ADD CONSTRAINT "
        "fk_interrupt_inbox_pause_scope FOREIGN KEY"
    ) in upgrade_sql
    assert (
        "ALTER TABLE app.interrupt_inbox ADD CONSTRAINT "
        "uq_interrupt_inbox_pause_member UNIQUE (pause_id, official_interrupt_id);"
    ) in upgrade_sql

    downgrade_sql = _render_revision_sql("downgrade")
    statements = (
        "ALTER TABLE app.interrupt_inbox DROP CONSTRAINT "
        "uq_interrupt_inbox_pause_member;",
        "ALTER TABLE app.interrupt_inbox DROP CONSTRAINT "
        "fk_interrupt_inbox_pause_scope;",
        "ALTER TABLE app.interrupt_inbox DROP COLUMN pause_id;",
        "DROP INDEX app.uq_interrupt_pauses_one_active_task;",
        "DROP INDEX app.ix_interrupt_pauses_scope_task_status;",
        "DROP INDEX app.ix_interrupt_pauses_scope_status_expiry;",
        "DROP TABLE app.interrupt_pauses;",
    )
    positions = [downgrade_sql.index(statement) for statement in statements]
    assert positions == sorted(positions)
