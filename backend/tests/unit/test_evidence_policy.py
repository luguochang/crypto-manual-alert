from copy import deepcopy
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parents[1]))

from crypto_alert_v2.domain.evidence_policy import (
    check_evidence_sufficiency,
    derive_unavailable_data,
)
from tests.fixtures.golden_cases import (
    OPENING_ACTIONS,
    complete_market_snapshot,
    complete_research_bundle,
)


REQUIRED_MARKET = ("ticker", "mark_price", "index_price", "order_book", "candles")
REQUIRED_MACRO = ("vix", "real_yield_10y", "dxy", "macro_event_scan")


def test_complete_opening_evidence_is_sufficient() -> None:
    verdict = check_evidence_sufficiency(
        market_snapshot=complete_market_snapshot(),
        research_bundle=complete_research_bundle(),
        main_action="open_long",
    )

    assert verdict.sufficient is True
    assert verdict.missing_required == []
    assert verdict.missing_optional == []
    assert verdict.confidence_cap == 1


def test_complete_typed_sources_derive_no_unavailable_data() -> None:
    assert (
        derive_unavailable_data(
            market_snapshot=complete_market_snapshot(),
            research_bundle=complete_research_bundle(),
            verified_web_evidence_count=1,
        )
        == []
    )


def test_unavailable_data_is_derived_from_typed_sources_in_stable_order() -> None:
    snapshot = complete_market_snapshot()
    snapshot["funding_rate"] = None
    research = complete_research_bundle()
    research["vix"] = None
    research["dxy"] = None

    assert derive_unavailable_data(
        market_snapshot=snapshot,
        research_bundle=research,
        verified_web_evidence_count=2,
    ) == ["funding_rate", "vix", "dxy"]


def test_missing_verified_web_evidence_is_a_typed_capability_gap() -> None:
    assert derive_unavailable_data(
        market_snapshot=complete_market_snapshot(),
        research_bundle=complete_research_bundle(),
        verified_web_evidence_count=0,
    ) == ["verified_web_evidence"]


@pytest.mark.parametrize("missing", REQUIRED_MARKET)
def test_opening_action_requires_each_exchange_field(missing: str) -> None:
    snapshot = complete_market_snapshot()
    snapshot[missing] = None if missing != "candles" else []

    verdict = check_evidence_sufficiency(
        market_snapshot=snapshot,
        research_bundle=complete_research_bundle(),
        main_action="open_long",
    )

    assert verdict.sufficient is False
    assert verdict.missing_required == [missing]
    assert verdict.confidence_cap == 0


@pytest.mark.parametrize("missing", REQUIRED_MACRO)
def test_opening_action_requires_each_macro_field(missing: str) -> None:
    research = complete_research_bundle()
    research[missing] = None

    verdict = check_evidence_sufficiency(
        market_snapshot=complete_market_snapshot(),
        research_bundle=research,
        main_action="open_long",
    )

    assert verdict.sufficient is False
    assert verdict.missing_required == [missing]
    assert verdict.confidence_cap == 0


@pytest.mark.parametrize("action", OPENING_ACTIONS)
def test_all_open_trigger_and_flip_actions_use_the_hard_gate(action: str) -> None:
    snapshot = complete_market_snapshot()
    snapshot["order_book"] = None
    research = complete_research_bundle()
    research["dxy"] = None

    verdict = check_evidence_sufficiency(snapshot, research, action)

    assert verdict.sufficient is False
    assert verdict.missing_required == ["order_book", "dxy"]
    assert verdict.confidence_cap == 0


@pytest.mark.parametrize(
    "action",
    ("hold_long", "hold_short", "close_long", "close_short", "no_trade"),
)
def test_non_opening_actions_do_not_invent_hard_evidence_requirements(
    action: str,
) -> None:
    verdict = check_evidence_sufficiency(None, None, action)

    assert verdict.sufficient is True
    assert verdict.missing_required == []


def test_missing_all_opening_evidence_is_reported_in_stable_exact_order() -> None:
    verdict = check_evidence_sufficiency(None, None, "flip_long_to_short")

    assert verdict.missing_required == [*REQUIRED_MARKET, *REQUIRED_MACRO]
    assert verdict.confidence_cap == 0


@pytest.mark.parametrize("missing", ("funding_rate", "open_interest"))
def test_missing_optional_derivatives_caps_confidence_at_point_seven(
    missing: str,
) -> None:
    snapshot = complete_market_snapshot()
    snapshot[missing] = None

    verdict = check_evidence_sufficiency(
        snapshot,
        complete_research_bundle(),
        "open_short",
    )

    assert verdict.sufficient is True
    assert verdict.missing_required == []
    assert verdict.missing_optional == [missing]
    assert verdict.confidence_cap == 0.70


def test_both_optional_derivatives_are_listed_without_compounding_cap() -> None:
    snapshot = complete_market_snapshot()
    snapshot["funding_rate"] = None
    snapshot["open_interest"] = None

    verdict = check_evidence_sufficiency(
        snapshot,
        complete_research_bundle(),
        "trigger_long",
    )

    assert verdict.missing_optional == ["funding_rate", "open_interest"]
    assert verdict.confidence_cap == 0.70


def test_required_and_optional_missing_are_kept_in_separate_lists() -> None:
    snapshot = complete_market_snapshot()
    snapshot["ticker"] = None
    snapshot["funding_rate"] = None

    verdict = check_evidence_sufficiency(
        snapshot,
        complete_research_bundle(),
        "open_long",
    )

    assert verdict.missing_required == ["ticker"]
    assert verdict.missing_optional == ["funding_rate"]
    assert verdict.confidence_cap == 0


def test_completed_empty_macro_event_scan_is_present_evidence() -> None:
    research = complete_research_bundle()
    assert research["macro_event_scan"] == []

    verdict = check_evidence_sufficiency(
        complete_market_snapshot(),
        research,
        "open_long",
    )

    assert verdict.sufficient is True


def test_malformed_provider_payload_raises_validation_instead_of_no_trade() -> None:
    with pytest.raises(ValidationError):
        check_evidence_sufficiency(
            market_snapshot={"provider_error": "timeout"},
            research_bundle=complete_research_bundle(),
            main_action="no_trade",
        )


def test_invalid_research_payload_raises_validation() -> None:
    research = deepcopy(complete_research_bundle())
    research["dxy"] = "not-a-number"

    with pytest.raises(ValidationError):
        check_evidence_sufficiency(
            complete_market_snapshot(),
            research,
            "open_long",
        )


def test_unknown_action_raises_validation() -> None:
    with pytest.raises(ValidationError):
        check_evidence_sufficiency(
            complete_market_snapshot(),
            complete_research_bundle(),
            "buy_now",
        )


@pytest.mark.parametrize(
    "action",
    (
        "open_long",
        "open_short",
        "hold_long",
        "hold_short",
        "close_long",
        "close_short",
        "flip_long_to_short",
        "flip_short_to_long",
        "trigger_long",
        "trigger_short",
    ),
)
def test_web_search_market_context_cannot_authorize_manual_execution(
    action: str,
) -> None:
    snapshot = complete_market_snapshot()
    snapshot["source_level"] = "web_search_verified"

    verdict = check_evidence_sufficiency(
        snapshot,
        complete_research_bundle(),
        action,
    )

    assert verdict.sufficient is False
    assert verdict.missing_required[0] == "exchange_native_market_data"
    assert verdict.confidence_cap == 0
    assert "evidence.market_source:web_search_verified" in verdict.warnings


def test_web_search_market_context_allows_only_bounded_no_trade_context() -> None:
    snapshot = complete_market_snapshot()
    snapshot["source_level"] = "web_search_verified"

    verdict = check_evidence_sufficiency(
        snapshot,
        complete_research_bundle(),
        "no_trade",
    )

    assert verdict.sufficient is True
    assert verdict.missing_required == []
    assert verdict.confidence_cap == 0.5
    assert verdict.warnings == ["evidence.market_source:web_search_verified"]
