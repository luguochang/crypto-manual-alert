from __future__ import annotations

from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from crypto_alert_v2.persistence.models import DomainEvent
from crypto_alert_v2.domain.deep_research import (
    DeepResearchReport,
    DeepResearchSearchCoverage,
    commit_deep_research_artifact,
    materialize_deep_research_artifact,
)
from crypto_alert_v2.domain.models import MarketSnapshot
from crypto_alert_v2.providers.search import WebEvidence
from crypto_alert_v2.projections.domain_events import (
    domain_event_specs,
    progressive_event_specs,
)
from tests.fixtures.golden_cases import (
    NOW,
    complete_market_snapshot,
    valid_market_analysis,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _committed_output() -> dict[str, object]:
    artifact = {
        "status": "committed",
        "analysis": {"main_action": "no_trade"},
        "evidence_verdict": {"sufficient": True},
        "risk_verdict": {"allowed": True},
    }
    return {
        "terminal_status": "succeeded",
        "market_snapshot": {"symbol": "BTC-USDT-SWAP"},
        "web_evidence": [{"content_hash": "a" * 64}],
        "artifact": artifact,
        "errors": [],
    }


def _research_draft() -> dict[str, object]:
    evidence = WebEvidence(
        query="BTC adoption",
        final_url="https://example.com/verified-btc-source",
        fetched_at=NOW,
        content_hash="d" * 64,
        title="Verified BTC source",
        source="test_search",
        excerpt="A verified source excerpt.",
        evidence_relation="supports",
    )
    report = DeepResearchReport.model_validate(
        {
            "executive_summary": "Verified evidence supports a measured conclusion.",
            "sections": [
                {
                    "title": "Adoption",
                    "summary": "The source catalog supports the finding.",
                    "findings": [
                        {
                            "claim": "Institutional adoption remains active.",
                            "source_indexes": [1],
                        }
                    ],
                }
            ],
        }
    )
    return materialize_deep_research_artifact(
        report=report,
        evidence=(evidence,),
        harness_mode="deepagents",
        search_coverage=DeepResearchSearchCoverage(
            status="complete",
            attempted_queries=1,
            successful_queries=1,
        ),
        model_audits=(),
    ).model_dump(mode="json")


def test_domain_event_table_has_scoped_ordered_idempotent_contract() -> None:
    table = DomainEvent.__table__

    assert {
        "id",
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "thread_id",
        "task_id",
        "run_id",
        "official_run_id",
        "checkpoint_id",
        "event_type",
        "schema_version",
        "payload_ref",
        "payload_hash",
        "payload",
        "source_event_key",
        "source_event_id",
        "sequence",
        "created_at",
    } <= set(table.c.keys())
    unique_sets = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("run_id", "source_event_key") in unique_sets
    assert ("run_id", "event_type") not in unique_sets
    assert ("thread_id", "sequence") in unique_sets
    run_scope = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_domain_events_run_scope"
    )
    assert tuple(run_scope.columns.keys()) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "thread_id",
        "task_id",
        "run_id",
    )
    check_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_domain_events_type" in check_names
    assert "ck_domain_events_sequence" in check_names


def test_committed_notification_run_produces_exact_normative_event_order() -> None:
    specs = domain_event_specs(
        _committed_output(),
        notification_payload={"channel": "bark", "type": "analysis_completed"},
    )

    assert [spec.event_type for spec in specs] == [
        "market.snapshot.committed",
        "research.evidence.committed",
        "agent.output.committed",
        "evidence.verdict.committed",
        "risk.verdict.committed",
        "artifact.committed",
        "notification.planned",
        "run.terminal",
    ]
    assert len({spec.payload_hash for spec in specs}) == len(specs)
    assert all(len(spec.payload_hash) == 64 for spec in specs)
    assert all(spec.schema_version == "1.0" for spec in specs)
    assert all(spec.payload for spec in specs)


def test_progressive_updates_map_only_canonical_paid_stage_payloads() -> None:
    analysis = valid_market_analysis()
    updates = {
        "collect_market_snapshot": {
            "market_snapshot": complete_market_snapshot(),
            "lifecycle": "market_collected",
        },
        "research_events": {
            "web_evidence": [
                {
                    "query": "BTC macro risk",
                    "final_url": "https://www.federalreserve.gov/monetarypolicy.htm",
                    "redirect_chain": [],
                    "http_status": 200,
                    "fetched_at": "2026-07-18T00:00:00Z",
                    "published_at": None,
                    "content_hash": "a" * 64,
                    "parser_version": "provider-citation-v1",
                    "title": "Federal Reserve policy",
                    "author": None,
                    "source": "openai_builtin_web_search",
                    "excerpt": "Policy remained restrictive.",
                    "evidence_relation": "supports",
                }
            ],
            "lifecycle": "research_collected",
        },
        "analyze_market": {
            "analysis": analysis,
            "lifecycle": "analysis_completed",
        },
        "validate_evidence": {
            "evidence_verdict": {
                "sufficient": True,
                "confidence_cap": 1.0,
                "missing_required": [],
                "missing_optional": [],
                "warnings": [],
            },
            "lifecycle": "evidence_validated",
        },
        "apply_risk_policy": {
            "risk_verdict": {
                "allowed": True,
                "blocked_reasons": [],
                "warnings": [],
                "confidence_cap": 1.0,
            },
            "lifecycle": "risk_validated",
        },
        "untrusted_node": {"request": {"api_key": "must-not-persist"}},
    }

    specs = progressive_event_specs(updates)

    assert [spec.event_type for spec in specs] == [
        "market.snapshot.committed",
        "research.evidence.committed",
        "agent.output.committed",
        "evidence.verdict.committed",
        "risk.verdict.committed",
    ]
    assert all("api_key" not in str(spec.payload) for spec in specs)


def test_research_draft_never_emits_artifact_committed_before_approval() -> None:
    draft = _research_draft()

    progressive = progressive_event_specs(
        {"run_deep_research": {"deep_research_artifact": draft}}
    )
    blocked = domain_event_specs(
        {
            "terminal_status": "blocked",
            "web_evidence": [],
            "deep_research_artifact": draft,
            "errors": [],
        },
        notification_payload=None,
    )
    committed = commit_deep_research_artifact(
        materialize_deep_research_artifact(
            report=DeepResearchReport.model_validate(draft["report"]),
            evidence=tuple(
                WebEvidence.model_validate(source["evidence"])
                for source in draft["sources"]
            ),
            harness_mode="deepagents",
            search_coverage=DeepResearchSearchCoverage.model_validate(
                draft["search_coverage"]
            ),
            model_audits=(),
        )
    )
    succeeded = domain_event_specs(
        {
            "terminal_status": "succeeded",
            "web_evidence": [],
            "deep_research_artifact": committed.model_dump(mode="json"),
            "errors": [],
        },
        notification_payload=None,
    )

    assert "artifact.committed" not in {spec.event_type for spec in progressive}
    assert "artifact.committed" not in {spec.event_type for spec in blocked}
    assert [spec.event_type for spec in succeeded].count("artifact.committed") == 1


def test_progressive_and_terminal_payloads_share_one_null_normalization() -> None:
    raw_market = complete_market_snapshot()
    raw_market["ticker"] = {"last": "65000.25"}
    progressive = progressive_event_specs(
        {
            "collect_market_snapshot": {
                "market_snapshot": raw_market,
                "lifecycle": "market_collected",
            }
        }
    )
    terminal_market = MarketSnapshot.model_validate(raw_market).model_dump(
        mode="json",
        exclude_none=True,
    )
    terminal = domain_event_specs(
        {
            "terminal_status": "failed",
            "market_snapshot": terminal_market,
            "errors": [{"code": "research_unavailable"}],
        },
        notification_payload=None,
    )

    assert progressive[0].payload == terminal_market
    assert progressive[0].payload_hash == terminal[0].payload_hash


def test_failed_run_emits_only_payloads_that_were_actually_committed() -> None:
    specs = domain_event_specs(
        {
            "terminal_status": "failed",
            "market_snapshot": {"symbol": "BTC-USDT-SWAP"},
            "web_evidence": [],
            "errors": [{"code": "research_unavailable"}],
        },
        notification_payload=None,
    )

    assert [spec.event_type for spec in specs] == [
        "market.snapshot.committed",
        "run.terminal",
    ]


def test_progressive_domain_event_migration_extends_the_terminal_ledger() -> None:
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "0018_progressive_events.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "0018_progressive_events"' in source
    assert 'down_revision = "0017_domain_events"' in source
    assert '"official_stream_last_event_id"' in source
    assert '"next_domain_event_sequence"' in source
    assert '"source_event_key"' in source
    assert '"payload"' in source
    assert "uq_domain_events_run_source_key" in source
    assert "fk_domain_events_run_scope" in source
