from collections.abc import Mapping

from pydantic import TypeAdapter

from crypto_alert_v2.domain.models import (
    OPENING_ACTIONS,
    Action,
    EvidenceVerdict,
    MarketSnapshot,
    ResearchBundle,
)


REQUIRED_MARKET_FIELDS = (
    "ticker",
    "mark_price",
    "index_price",
    "order_book",
    "candles",
)
REQUIRED_MACRO_FIELDS = ("vix", "real_yield_10y", "dxy", "macro_event_scan")
OPTIONAL_MARKET_FIELDS = ("funding_rate", "open_interest")
DATA_AVAILABILITY_ORDER = (
    "exchange_native_market_data",
    *REQUIRED_MARKET_FIELDS,
    *OPTIONAL_MARKET_FIELDS,
    *REQUIRED_MACRO_FIELDS,
    "verified_web_evidence",
)
OPTIONAL_EVIDENCE_CAP = 0.70
WEB_SEARCH_CONTEXT_CAP = 0.50

_ACTION_ADAPTER = TypeAdapter(Action)


def check_evidence_sufficiency(
    market_snapshot: MarketSnapshot | Mapping[str, object] | None,
    research_bundle: ResearchBundle | Mapping[str, object] | None,
    main_action: Action | str,
) -> EvidenceVerdict:
    """Apply the deterministic live-evidence gate to validated provider output."""
    action = _ACTION_ADAPTER.validate_python(main_action)
    snapshot = _validate_snapshot(market_snapshot)
    research = _validate_research(research_bundle)

    missing_required: list[str] = []
    web_search_market = (
        snapshot is not None and snapshot.source_level == "web_search_verified"
    )
    if web_search_market and action != "no_trade":
        missing_required.append("exchange_native_market_data")
    if action in OPENING_ACTIONS:
        missing_required.extend(_missing_market_fields(snapshot))
        missing_required.extend(_missing_macro_fields(research))

    missing_optional = _missing_optional_fields(snapshot)
    sufficient = not missing_required
    confidence_cap = (
        0.0
        if not sufficient
        else min(
            OPTIONAL_EVIDENCE_CAP if missing_optional else 1.0,
            WEB_SEARCH_CONTEXT_CAP if web_search_market else 1.0,
        )
    )
    warnings = [f"evidence.optional_missing:{field}" for field in missing_optional]
    if web_search_market:
        warnings.append("evidence.market_source:web_search_verified")

    return EvidenceVerdict(
        sufficient=sufficient,
        confidence_cap=confidence_cap,
        missing_required=missing_required,
        missing_optional=missing_optional,
        warnings=warnings,
    )


def derive_unavailable_data(
    market_snapshot: MarketSnapshot | Mapping[str, object] | None,
    research_bundle: ResearchBundle | Mapping[str, object] | None,
    *,
    verified_web_evidence_count: int,
) -> list[str]:
    """Derive stable availability codes exclusively from validated provider data."""
    snapshot = _validate_snapshot(market_snapshot)
    research = _validate_research(research_bundle)

    missing = {
        *_missing_market_fields(snapshot),
        *_missing_macro_fields(research),
    }
    if snapshot is None:
        missing.update(OPTIONAL_MARKET_FIELDS)
    else:
        missing.update(_missing_optional_fields(snapshot))
        if snapshot.source_level == "web_search_verified":
            missing.add("exchange_native_market_data")
    if verified_web_evidence_count <= 0:
        missing.add("verified_web_evidence")

    return [field for field in DATA_AVAILABILITY_ORDER if field in missing]


def _validate_snapshot(
    value: MarketSnapshot | Mapping[str, object] | None,
) -> MarketSnapshot | None:
    if value is None or isinstance(value, MarketSnapshot):
        return value
    return MarketSnapshot.model_validate(value)


def _validate_research(
    value: ResearchBundle | Mapping[str, object] | None,
) -> ResearchBundle | None:
    if value is None or isinstance(value, ResearchBundle):
        return value
    return ResearchBundle.model_validate(value)


def _missing_market_fields(snapshot: MarketSnapshot | None) -> list[str]:
    if snapshot is None:
        return list(REQUIRED_MARKET_FIELDS)

    missing: list[str] = []
    if snapshot.ticker is None:
        missing.append("ticker")
    if snapshot.mark_price is None:
        missing.append("mark_price")
    if snapshot.index_price is None:
        missing.append("index_price")
    if (
        snapshot.order_book is None
        or not snapshot.order_book.bids
        or not snapshot.order_book.asks
    ):
        missing.append("order_book")
    if not snapshot.candles:
        missing.append("candles")
    return missing


def _missing_macro_fields(research: ResearchBundle | None) -> list[str]:
    if research is None:
        return list(REQUIRED_MACRO_FIELDS)

    return [
        field for field in REQUIRED_MACRO_FIELDS if getattr(research, field) is None
    ]


def _missing_optional_fields(snapshot: MarketSnapshot | None) -> list[str]:
    if snapshot is None:
        return []
    return [
        field for field in OPTIONAL_MARKET_FIELDS if getattr(snapshot, field) is None
    ]
