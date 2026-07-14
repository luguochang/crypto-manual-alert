from collections.abc import Mapping

from pydantic import TypeAdapter

from crypto_alert_v2.domain.models import (
    OPENING_ACTIONS,
    Action,
    EvidenceVerdict,
    MarketSnapshot,
    ResearchBundle,
)


REQUIRED_MARKET_FIELDS = ("ticker", "mark_price", "index_price", "order_book", "candles")
REQUIRED_MACRO_FIELDS = ("vix", "real_yield_10y", "dxy", "macro_event_scan")
OPTIONAL_MARKET_FIELDS = ("funding_rate", "open_interest")
OPTIONAL_EVIDENCE_CAP = 0.70

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
    if action in OPENING_ACTIONS:
        missing_required.extend(_missing_market_fields(snapshot))
        missing_required.extend(_missing_macro_fields(research))

    missing_optional = _missing_optional_fields(snapshot)
    sufficient = not missing_required
    confidence_cap = 0.0 if not sufficient else (OPTIONAL_EVIDENCE_CAP if missing_optional else 1.0)
    warnings = [f"evidence.optional_missing:{field}" for field in missing_optional]

    return EvidenceVerdict(
        sufficient=sufficient,
        confidence_cap=confidence_cap,
        missing_required=missing_required,
        missing_optional=missing_optional,
        warnings=warnings,
    )


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

    return [field for field in REQUIRED_MACRO_FIELDS if getattr(research, field) is None]


def _missing_optional_fields(snapshot: MarketSnapshot | None) -> list[str]:
    if snapshot is None:
        return []
    return [field for field in OPTIONAL_MARKET_FIELDS if getattr(snapshot, field) is None]
