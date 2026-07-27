from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations

from crypto_alert_v2.api.schemas import UsageGovernanceView
from crypto_alert_v2.persistence.models import Run, UsageReconciliation
from crypto_alert_v2.persistence.usage_governance import (
    run_usage_facts,
    usage_period_start,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load_revision() -> Any:
    path = BACKEND_ROOT / "alembic" / "versions" / "0028_usage_governance.py"
    spec = importlib.util.spec_from_file_location("usage_governance", path)
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


def test_usage_governance_revision_is_append_only_and_extends_entitlements() -> None:
    revision = _load_revision()
    sql = _render("upgrade")

    assert revision.revision == "0028_usage_governance"
    assert revision.down_revision == "0027_improvement_review_runtime"
    assert "ADD COLUMN allowed_task_types JSONB" in sql
    assert "ADD COLUMN monthly_model_token_limit BIGINT" in sql
    assert "ADD COLUMN storage_byte_limit BIGINT" in sql
    assert "CREATE TABLE app.usage_reconciliations (" in sql
    assert "BEFORE UPDATE OR DELETE ON app.usage_reconciliations" in sql
    assert "usage_reconciliations is append-only" in sql


def test_terminal_run_produces_stable_measured_usage_facts() -> None:
    started = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
    run = Run(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        owner_user_id=uuid4(),
        thread_id=uuid4(),
        task_id=uuid4(),
        attempt=1,
        status="succeeded",
        input_payload={},
        output_payload={
            "terminal_status": "succeeded",
            "web_evidence": [
                {"query": "BTC ETF", "final_url": "https://example.com/1"},
                {"query": "BTC ETF", "final_url": "https://example.com/2"},
                {"query": "BTC liquidity", "final_url": "https://example.com/3"},
            ],
            "artifact": {
                "provenance": {
                    "model_audits": [
                        {"total_tokens": 120},
                        {"total_tokens": 80},
                    ]
                }
            },
        },
        started_at=started,
        finished_at=started + timedelta(milliseconds=1250),
        terminal_output_hash="a" * 64,
    )

    facts = {fact.unit: fact for fact in run_usage_facts(run)}

    assert facts["model_token"].quantity == 200
    assert facts["search_request"].quantity == 2
    assert facts["runtime_millisecond"].quantity == 1250
    assert facts["storage_byte"].quantity > 0
    assert all(fact.resource_id == str(run.id) for fact in facts.values())
    assert all(fact.source_receipt_hash == "a" * 64 for fact in facts.values())


def test_usage_schema_requires_complete_totals_and_month_boundary() -> None:
    period = usage_period_start(datetime(2026, 7, 23, 10, 11, tzinfo=UTC))
    totals = {
        "agent_admission": 1,
        "trigger": 2,
        "model_token": 3,
        "search_request": 4,
        "runtime_millisecond": 5,
        "storage_byte": 6,
    }
    parsed = UsageGovernanceView.model_validate(
        {
            "period_start": period,
            "entitlement": {
                "allowed_task_types": ["market_analysis"],
                "active_monitor_limit": 1,
                "min_interval_seconds": 300,
                "max_concurrent_tasks": 2,
                "max_retention_days": 365,
                "limits": totals,
                "valid_from": period,
                "valid_until": None,
            },
            "totals": totals,
            "latest_reconciliation": None,
        }
    )

    assert parsed.period_start == datetime(2026, 7, 1, tzinfo=UTC)
    assert "updated_at" not in UsageReconciliation.__table__.c
