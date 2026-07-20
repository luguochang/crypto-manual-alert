from datetime import UTC, datetime
import json
from typing import Any

import pytest

from crypto_alert_v2.agents import deep_research
from crypto_alert_v2.domain.deep_research import (
    DeepResearchArtifact,
    DeepResearchReport,
    DeepResearchSearchCoverage,
    commit_deep_research_artifact,
    materialize_deep_research_artifact,
)
from crypto_alert_v2.providers.search import SearchEvidenceUnavailable, WebEvidence


NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
COMPLETE_SEARCH_COVERAGE = DeepResearchSearchCoverage(
    status="complete",
    attempted_queries=1,
    successful_queries=1,
)


def _report(*, source_indexes: list[int]) -> DeepResearchReport:
    return DeepResearchReport.model_validate(
        {
            "executive_summary": "BTC 的事件风险仍需谨慎评估。",
            "sections": [
                {
                    "title": "事件风险",
                    "summary": "公开来源显示短期事件窗口较密集。",
                    "findings": [
                        {
                            "claim": "本周存在需要纳入决策的宏观事件。",
                            "source_indexes": source_indexes,
                        }
                    ],
                }
            ],
            "risk_notes": ["事件结果可能快速改变当前判断。"],
            "evidence_gaps": [],
        }
    )


def _evidence(
    *,
    query: str = "BTC macro events",
    url: str = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    content_hash: str = "a" * 64,
) -> WebEvidence:
    return WebEvidence(
        query=query,
        final_url=url,
        fetched_at=NOW,
        content_hash=content_hash,
        title="Federal Reserve calendar",
        source="test_search",
        excerpt="The calendar lists the next scheduled policy meeting.",
        evidence_relation="supports",
    )


class _OutcomeSearch:
    def __init__(self, outcomes: dict[str, list[WebEvidence] | Exception]) -> None:
        self._outcomes = outcomes
        self.calls: list[str] = []

    def search(self, query: str, config: Any = None) -> list[WebEvidence]:
        del config
        self.calls.append(query)
        outcome = self._outcomes[query]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_materialized_report_is_a_reviewable_draft_with_an_immutable_source_catalog() -> (
    None
):
    artifact = materialize_deep_research_artifact(
        report=_report(source_indexes=[1]),
        evidence=(_evidence(),),
        harness_mode="deepagents",
        search_coverage=COMPLETE_SEARCH_COVERAGE,
        model_audits=(),
    )

    assert artifact.artifact_type == "deep_research_report"
    assert artifact.status == "draft"
    assert artifact.harness_mode == "deepagents"
    assert artifact.sources[0].index == 1
    assert artifact.sources[0].evidence.final_url == _evidence().final_url


@pytest.mark.asyncio
async def test_verified_source_ledger_preserves_partial_multi_query_evidence() -> None:
    first_failure = SearchEvidenceUnavailable(
        "Authorization: Bearer must-never-enter-the-tool-result",
        provider="builtin_web_search",
        retryable=True,
        error_type="APITimeoutError",
        attempt=3,
    )
    final_failure = SearchEvidenceUnavailable(
        "raw upstream payload must stay private",
        provider="builtin_web_search",
        retryable=True,
        error_type="UnverifiedServerToolCall",
        attempt=2,
    )
    evidence = _evidence(
        query="BTC market structure",
        url="https://www.cmegroup.com/markets/cryptocurrencies/bitcoin.html",
        content_hash="b" * 64,
    )
    search = _OutcomeSearch(
        {
            "BTC macro": first_failure,
            "BTC market structure": [evidence],
            "BTC regulation": final_failure,
        }
    )
    ledger = deep_research._VerifiedSourceLedger(search)

    catalog = json.loads(
        await ledger.collect(
            ["BTC macro", "BTC market structure", "BTC regulation"],
            config=None,
        )
    )

    assert set(search.calls) == {
        "BTC macro",
        "BTC market structure",
        "BTC regulation",
    }
    assert len(search.calls) == 3
    assert ledger.evidence == (evidence,)
    assert catalog["sources"] == [
        {
            "index": 1,
            "title": evidence.title,
            "excerpt": evidence.excerpt,
            "published_at": None,
        }
    ]
    assert catalog["coverage"] == {
        "status": "partial",
        "attempted_queries": 3,
        "successful_queries": 1,
        "failed_query_indexes": [1, 3],
    }
    assert ledger.coverage.failed_queries[0].model_dump() == {
        "query_index": 1,
        "provider": "builtin_web_search",
        "error_kind": "timeout",
        "retryable": True,
        "attempt": 3,
    }
    assert ledger.coverage.failed_queries[1].error_kind == (
        "unverified_server_tool_call"
    )
    serialized = json.dumps(catalog)
    assert "must-never-enter" not in serialized
    assert "raw upstream payload" not in serialized
    assert "builtin_web_search" not in serialized
    assert "APITimeoutError" not in serialized


@pytest.mark.asyncio
async def test_verified_source_ledger_all_failures_raise_the_first_typed_error() -> (
    None
):
    first_failure = SearchEvidenceUnavailable(
        "first provider failure",
        provider="builtin_web_search",
        retryable=True,
        error_type="APITimeoutError",
        attempt=3,
    )
    second_failure = SearchEvidenceUnavailable(
        "second provider failure",
        provider="builtin_web_search",
        retryable=True,
        error_type="UnverifiedServerToolCall",
        attempt=2,
    )
    search = _OutcomeSearch(
        {
            "BTC macro": first_failure,
            "BTC regulation": second_failure,
            "BTC market structure": [],
        }
    )
    ledger = deep_research._VerifiedSourceLedger(search)

    with pytest.raises(SearchEvidenceUnavailable) as captured:
        await ledger.collect(
            ["BTC macro", "BTC regulation", "BTC market structure"],
            config=None,
        )

    assert captured.value is first_failure
    assert len(search.calls) == 3
    assert ledger.evidence == ()
    with pytest.raises(RuntimeError, match="has not completed"):
        _ = ledger.coverage


@pytest.mark.asyncio
async def test_empty_result_cannot_replace_a_later_real_provider_failure() -> None:
    provider_failure = SearchEvidenceUnavailable(
        "provider failure",
        provider="builtin_web_search",
        retryable=True,
        error_type="InternalServerError",
        attempt=2,
    )
    ledger = deep_research._VerifiedSourceLedger(
        _OutcomeSearch(
            {
                "BTC macro": [],
                "BTC regulation": provider_failure,
            }
        )
    )

    with pytest.raises(SearchEvidenceUnavailable) as captured:
        await ledger.collect(["BTC macro", "BTC regulation"], config=None)

    assert captured.value is provider_failure


@pytest.mark.asyncio
async def test_search_failure_coordinates_use_server_allowlists() -> None:
    canary = "sk-secret-canary"
    failure = SearchEvidenceUnavailable(
        "private provider payload",
        provider=canary,
        retryable=True,
        error_type=canary,
        attempt=2,
    )
    evidence = _evidence()
    ledger = deep_research._VerifiedSourceLedger(
        _OutcomeSearch(
            {
                "BTC unsafe metadata": failure,
                "BTC verified": [evidence],
            }
        )
    )

    tool_result = await ledger.collect(
        ["BTC unsafe metadata", "BTC verified"],
        config=None,
    )

    assert canary not in tool_result
    assert ledger.coverage.failed_queries[0].provider == "search"
    assert ledger.coverage.failed_queries[0].error_kind == "provider_error"


@pytest.mark.asyncio
async def test_verified_sources_are_round_robin_bounded_and_cached_per_run() -> None:
    def result_set(query: str, group: str) -> list[WebEvidence]:
        return [
            _evidence(
                query=query,
                url=f"https://example.com/{group}-{index}",
                content_hash=(f"{group}{index}" * 64)[:64],
            )
            for index in range(8)
        ]

    macro = result_set("BTC macro", "macro")
    regulation = result_set("BTC regulation", "regulation")
    structure = result_set("BTC market structure", "structure")
    search = _OutcomeSearch(
        {
            "BTC macro": macro,
            "BTC regulation": regulation,
            "BTC market structure": structure,
        }
    )
    ledger = deep_research._VerifiedSourceLedger(search)

    first_result = await ledger.collect(
        ["BTC macro", "BTC regulation", "BTC market structure"],
        config=None,
    )
    replay_result = await ledger.collect(["a replay must not search"], config=None)

    assert replay_result == first_result
    assert search.calls == ["BTC macro", "BTC regulation", "BTC market structure"]
    assert len(ledger.evidence) == 8
    assert ledger.evidence[:6] == (
        macro[0],
        regulation[0],
        structure[0],
        macro[1],
        regulation[1],
        structure[1],
    )
    artifact = materialize_deep_research_artifact(
        report=_report(source_indexes=[1]),
        evidence=ledger.evidence,
        harness_mode="deepagents",
        search_coverage=ledger.coverage,
        model_audits=(),
    )
    assert len(artifact.sources) == 8


@pytest.mark.asyncio
async def test_unexpected_search_failure_propagates_without_query_fallback() -> None:
    unexpected = RuntimeError("programming failure")
    search = _OutcomeSearch(
        {
            "BTC invalid": unexpected,
            "BTC should not run": [_evidence()],
        }
    )
    ledger = deep_research._VerifiedSourceLedger(search)

    with pytest.raises(RuntimeError) as captured:
        await ledger.collect(
            ["BTC invalid", "BTC should not run"],
            config=None,
        )

    assert captured.value is unexpected
    assert search.calls == ["BTC invalid"]


def test_commit_promotes_the_same_validated_draft_without_mutating_content() -> None:
    draft = materialize_deep_research_artifact(
        report=_report(source_indexes=[1]),
        evidence=(_evidence(),),
        harness_mode="deepagents",
        search_coverage=COMPLETE_SEARCH_COVERAGE,
        model_audits=(),
    )

    committed = commit_deep_research_artifact(draft)

    assert draft.status == "draft"
    assert committed.status == "committed"
    assert committed.report == draft.report
    assert committed.sources == draft.sources
    assert committed.search_coverage == draft.search_coverage
    assert committed.harness_mode == draft.harness_mode
    assert committed.model_audits == draft.model_audits

    with pytest.raises(ValueError, match="draft"):
        commit_deep_research_artifact(committed)


def test_research_artifact_rejects_an_unsupported_status() -> None:
    draft = materialize_deep_research_artifact(
        report=_report(source_indexes=[1]),
        evidence=(_evidence(),),
        harness_mode="deepagents",
        search_coverage=COMPLETE_SEARCH_COVERAGE,
        model_audits=(),
    )

    with pytest.raises(ValueError, match="status"):
        DeepResearchArtifact.model_validate(
            {**draft.model_dump(mode="json"), "status": "streaming"}
        )


def test_materialized_report_rejects_an_index_outside_its_source_catalog() -> None:
    with pytest.raises(ValueError, match="unknown evidence source index"):
        materialize_deep_research_artifact(
            report=_report(source_indexes=[2]),
            evidence=(_evidence(),),
            harness_mode="deepagents",
            search_coverage=COMPLETE_SEARCH_COVERAGE,
            model_audits=(),
        )
