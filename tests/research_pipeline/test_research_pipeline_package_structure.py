from __future__ import annotations

import importlib
import sys

from crypto_manual_alert.research_pipeline import (
    CORE_MARKET_POINTS,
    FixtureSearchAdapter,
    ResearchAudit,
    ResearchPlan,
    ResearchQuery,
    SearchResult,
    build_leader_synthesizer,
    build_research_planner,
    build_search_adapter,
    candle_max_age_seconds,
    execute_research,
    needs_research_fallback,
    synthesize_search_evidence,
)
from crypto_manual_alert.research_pipeline.evidence import (
    CORE_MARKET_POINTS as CoreMarketPointsFromEvidence,
    candle_max_age_seconds as candle_max_age_seconds_from_evidence,
    needs_research_fallback as needs_research_fallback_from_evidence,
    synthesize_search_evidence as synthesize_search_evidence_from_evidence,
)
from crypto_manual_alert.research_pipeline.executor import execute_research as execute_research_from_executor
from crypto_manual_alert.research_pipeline.factory import (
    build_leader_synthesizer as build_leader_synthesizer_from_factory,
    build_research_planner as build_research_planner_from_factory,
    build_search_adapter as build_search_adapter_from_factory,
)
from crypto_manual_alert.research_pipeline.models import (
    ResearchAudit as ResearchAuditFromModels,
    ResearchPlan as ResearchPlanFromModels,
    ResearchQuery as ResearchQueryFromModels,
    SearchResult as SearchResultFromModels,
)
from crypto_manual_alert.research_pipeline.protocols import (
    LeaderResearchSynthesizer as LeaderResearchSynthesizerFromProtocols,
    ResearchPlanner as ResearchPlannerFromProtocols,
    SearchAdapter as SearchAdapterFromProtocols,
)
from crypto_manual_alert.research_pipeline import LeaderResearchSynthesizer, ResearchPlanner, SearchAdapter


def test_research_pipeline_package_import_does_not_eagerly_import_implementation_modules():
    implementation_modules = [
        "crypto_manual_alert.research_pipeline.core",
        "crypto_manual_alert.research_pipeline.evidence",
        "crypto_manual_alert.research_pipeline.executor",
        "crypto_manual_alert.research_pipeline.factory",
        "crypto_manual_alert.research_pipeline.models",
        "crypto_manual_alert.research_pipeline.protocols",
        "crypto_manual_alert.research_pipeline.search_adapters",
    ]
    previous_modules = {name: sys.modules.pop(name, None) for name in implementation_modules}
    sys.modules.pop("crypto_manual_alert.research_pipeline", None)
    try:
        importlib.import_module("crypto_manual_alert.research_pipeline")

        for name in implementation_modules:
            assert name not in sys.modules
    finally:
        sys.modules.pop("crypto_manual_alert.research_pipeline", None)
        for name, module in previous_modules.items():
            if module is not None:
                sys.modules[name] = module


def test_research_pipeline_package_exports_canonical_objects():
    assert ResearchQueryFromModels is ResearchQuery
    assert ResearchPlanFromModels is ResearchPlan
    assert SearchResultFromModels is SearchResult
    assert ResearchAuditFromModels is ResearchAudit
    assert ResearchPlannerFromProtocols is ResearchPlanner
    assert SearchAdapterFromProtocols is SearchAdapter
    assert LeaderResearchSynthesizerFromProtocols is LeaderResearchSynthesizer
    assert FixtureSearchAdapter.__name__ == "FixtureSearchAdapter"
    assert execute_research.__name__ == "execute_research"
    assert needs_research_fallback.__name__ == "needs_research_fallback"
    assert synthesize_search_evidence.__name__ == "synthesize_search_evidence"
    assert CoreMarketPointsFromEvidence is CORE_MARKET_POINTS
    assert set(CORE_MARKET_POINTS) >= {"last", "mark", "index", "order_book"}


def test_research_pipeline_splits_evidence_executor_and_factory_boundaries():
    assert CoreMarketPointsFromEvidence is CORE_MARKET_POINTS
    assert needs_research_fallback_from_evidence is needs_research_fallback
    assert synthesize_search_evidence_from_evidence is synthesize_search_evidence
    assert candle_max_age_seconds_from_evidence is candle_max_age_seconds
    assert execute_research_from_executor is execute_research
    assert build_research_planner_from_factory is build_research_planner
    assert build_search_adapter_from_factory is build_search_adapter
    assert build_leader_synthesizer_from_factory is build_leader_synthesizer


def test_research_pipeline_search_adapters_have_canonical_module():
    search_adapters = __import__(
        "crypto_manual_alert.research_pipeline.search_adapters",
        fromlist=["FixtureSearchAdapter"],
    )
    FixtureSearchAdapterFromSearchAdapters = search_adapters.FixtureSearchAdapter

    assert FixtureSearchAdapterFromSearchAdapters is FixtureSearchAdapter

    init_source = __import__("pathlib").Path("src/crypto_manual_alert/research_pipeline/__init__.py").read_text(
        encoding="utf-8"
    )
    factory_source = __import__("pathlib").Path("src/crypto_manual_alert/research_pipeline/factory.py").read_text(
        encoding="utf-8"
    )
    core_source = __import__("pathlib").Path("src/crypto_manual_alert/research_pipeline/core.py").read_text(
        encoding="utf-8"
    )

    for name in (
        "DisabledSearchAdapter",
        "FixtureSearchAdapter",
        "DuckDuckGoHtmlSearchAdapter",
        "ResponsesWebSearchAdapter",
    ):
        assert f'"{name}": "crypto_manual_alert.research_pipeline.search_adapters"' in init_source

    assert "from crypto_manual_alert.research_pipeline.search_adapters import" in factory_source
    assert "class DisabledSearchAdapter" not in core_source
    assert "class FixtureSearchAdapter" not in core_source
    assert "class DuckDuckGoHtmlSearchAdapter" not in core_source
    assert "class ResponsesWebSearchAdapter" not in core_source
    assert "class _DuckDuckGoParser" not in core_source


def test_research_pipeline_leader_synthesizers_have_canonical_module():
    leader_synthesizers = __import__(
        "crypto_manual_alert.research_pipeline.leader_synthesizers",
        fromlist=["StaticLeaderResearchSynthesizer"],
    )
    StaticLeaderResearchSynthesizerFromModule = leader_synthesizers.StaticLeaderResearchSynthesizer

    from crypto_manual_alert.research_pipeline import StaticLeaderResearchSynthesizer

    assert StaticLeaderResearchSynthesizerFromModule is StaticLeaderResearchSynthesizer

    init_source = __import__("pathlib").Path("src/crypto_manual_alert/research_pipeline/__init__.py").read_text(
        encoding="utf-8"
    )
    factory_source = __import__("pathlib").Path("src/crypto_manual_alert/research_pipeline/factory.py").read_text(
        encoding="utf-8"
    )
    core_source = __import__("pathlib").Path("src/crypto_manual_alert/research_pipeline/core.py").read_text(
        encoding="utf-8"
    )

    for name in (
        "StaticLeaderResearchSynthesizer",
        "OpenAICompatibleLeaderResearchSynthesizer",
        "FallbackLeaderResearchSynthesizer",
    ):
        assert f'"{name}": "crypto_manual_alert.research_pipeline.leader_synthesizers"' in init_source
        assert f"class {name}" not in core_source

    assert "from crypto_manual_alert.research_pipeline.leader_synthesizers import" in factory_source
