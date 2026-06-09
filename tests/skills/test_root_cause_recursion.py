from __future__ import annotations

from crypto_manual_alert.skills.facade import SkillTaskContext
from crypto_manual_alert.skills.root_cause import RootCauseSearchSkill
from crypto_manual_alert.skills.realtime_search.providers import SearchProviderRequest
from crypto_manual_alert.skills.root_cause.providers import RealtimeBackedRootCauseProvider, RootCauseSearchRequest


class RecordingRootCauseProvider:
    def __init__(self) -> None:
        self.requests: list[RootCauseSearchRequest] = []

    def expand(self, request: RootCauseSearchRequest) -> list[dict[str, str]]:
        self.requests.append(request)
        if request.depth == 1:
            return [
                {
                    "factor_type": "macro_event",
                    "title": "ETF flow surprise",
                    "query": "ETF flow surprise drivers",
                    "url": "https://example.test/root",
                    "snippet_ref": "root_cause.depth1[0].snippet_redacted",
                },
                {
                    "factor_type": "liquidity",
                    "title": "order book imbalance",
                    "query": "order book imbalance drivers",
                    "url": "https://example.test/ignored-by-branch-limit",
                    "snippet_ref": "root_cause.depth1[1].snippet_redacted",
                },
            ]
        return [
            {
                "factor_type": "flow",
                "title": f"child factor for {request.query}",
                "query": "should not be expanded past max depth",
                "url": "https://example.test/child",
                "snippet_ref": "root_cause.depth2[0].snippet_redacted",
            }
        ]


def test_root_cause_skill_recursively_expands_provider_with_depth_and_branch_limits():
    provider = RecordingRootCauseProvider()
    context = SkillTaskContext(
        skill_name="root_cause_search",
        task_id="skill:root_cause",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-root",
        query="why did ETH move",
        input_view={},
        max_depth=2,
        timeout_seconds=20,
    )

    public = RootCauseSearchSkill(provider=provider, max_branch_count=1).run(context).to_public_dict()

    assert provider.requests == [
        RootCauseSearchRequest(
            symbol="ETH-USDT-SWAP",
            query="why did ETH move",
            trace_id="trace-root",
            task_id="skill:root_cause",
            depth=1,
            max_branch_count=1,
        ),
        RootCauseSearchRequest(
            symbol="ETH-USDT-SWAP",
            query="ETF flow surprise drivers",
            trace_id="trace-root",
            task_id="skill:root_cause",
            depth=2,
            max_branch_count=1,
        ),
    ]
    assert public["evidence_candidates"] == [
        {
            "title": "depth 1 macro_event: ETF flow surprise",
            "url": "https://example.test/root",
            "snippet_ref": "root_cause.depth1[0].snippet_redacted",
            "source_type": "search_derived",
        },
        {
            "title": "depth 2 flow: child factor for ETF flow surprise drivers",
            "url": "https://example.test/child",
            "snippet_ref": "root_cause.depth2[0].snippet_redacted",
            "source_type": "search_derived",
        },
    ]


class ExpandingRootCauseProvider:
    def __init__(self) -> None:
        self.requests: list[RootCauseSearchRequest] = []

    def expand(self, request: RootCauseSearchRequest) -> list[dict[str, str]]:
        self.requests.append(request)
        return [
            {
                "factor_type": "flow",
                "title": f"factor depth {request.depth}",
                "query": f"next factor depth {request.depth + 1}",
                "url": f"https://example.test/depth/{request.depth}",
                "snippet_ref": f"root_cause.depth{request.depth}[0].snippet_redacted",
            }
        ]


def test_root_cause_skill_stops_recursive_expansion_when_budget_is_exhausted():
    provider = ExpandingRootCauseProvider()
    context = SkillTaskContext(
        skill_name="root_cause_search",
        task_id="skill:root_cause",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-root-budget",
        query="why did ETH move",
        input_view={},
        max_depth=5,
        timeout_seconds=20,
    )

    public = RootCauseSearchSkill(
        provider=provider,
        max_branch_count=1,
        max_expansion_calls=2,
        clock=lambda: 100.0,
    ).run(context).to_public_dict()

    assert [request.depth for request in provider.requests] == [1, 2]
    assert [request.remaining_budget for request in provider.requests] == [2, 1]
    assert len(public["evidence_candidates"]) == 2


def test_root_cause_skill_stops_recursive_expansion_when_deadline_is_expired():
    provider = ExpandingRootCauseProvider()
    clock_values = iter([100.0, 100.0, 102.0])
    context = SkillTaskContext(
        skill_name="root_cause_search",
        task_id="skill:root_cause",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-root-deadline",
        query="why did ETH move",
        input_view={},
        max_depth=5,
        timeout_seconds=1,
    )

    public = RootCauseSearchSkill(
        provider=provider,
        max_branch_count=1,
        max_expansion_calls=5,
        clock=lambda: next(clock_values),
    ).run(context).to_public_dict()

    assert [request.depth for request in provider.requests] == [1]
    assert provider.requests[0].deadline_at == 101.0
    assert len(public["evidence_candidates"]) == 1


class RecordingSearchProvider:
    def __init__(self) -> None:
        self.requests: list[SearchProviderRequest] = []

    def search(self, request: SearchProviderRequest) -> list[dict[str, str]]:
        self.requests.append(request)
        return [
            {
                "title": "ETF flow surprise",
                "url": "https://example.test/etf",
                "snippet_ref": "search.root_cause[0].snippet_redacted",
            }
        ]


def test_realtime_backed_root_cause_provider_expands_factors_from_search_results():
    search_provider = RecordingSearchProvider()
    provider = RealtimeBackedRootCauseProvider(search_provider=search_provider, factor_type="flow")
    request = RootCauseSearchRequest(
        symbol="ETH-USDT-SWAP",
        query="why did ETH move",
        trace_id="trace-root",
        task_id="skill:root_cause",
        depth=1,
        max_branch_count=2,
    )

    factors = provider.expand(request)

    assert search_provider.requests == [
        SearchProviderRequest(
            symbol="ETH-USDT-SWAP",
            query="why did ETH move",
            trace_id="trace-root",
            task_id="skill:root_cause",
            max_results=2,
        )
    ]
    assert factors == [
        {
            "factor_type": "flow",
            "title": "ETF flow surprise",
            "query": "ETF flow surprise",
            "url": "https://example.test/etf",
            "snippet_ref": "search.root_cause[0].snippet_redacted",
        }
    ]
