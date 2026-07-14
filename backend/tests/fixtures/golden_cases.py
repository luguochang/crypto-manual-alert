from copy import deepcopy
from datetime import datetime, timezone


NOW = datetime(2026, 7, 13, 4, 0, tzinfo=timezone.utc)

SUPPORTED_SYMBOLS = (
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP",
    "SOL-USDT-SWAP",
)

OPENING_ACTIONS = (
    "open_long",
    "open_short",
    "trigger_long",
    "trigger_short",
    "flip_long_to_short",
    "flip_short_to_long",
)


def complete_market_snapshot(symbol: str = "BTC-USDT-SWAP") -> dict:
    return deepcopy(
        {
            "symbol": symbol,
            "fetched_at": NOW,
            "source_level": "exchange_native",
            "ticker": {
                "last": "65000.25",
                "bid": "65000.00",
                "ask": "65000.50",
                "volume_24h": "1250.5",
            },
            "mark_price": "65001.00",
            "index_price": "64999.75",
            "funding_rate": "0.0001",
            "open_interest": "125000.5",
            "order_book": {
                "bids": [["65000.00", "1.25"]],
                "asks": [["65000.50", "1.10"]],
            },
            "candles": [
                {
                    "timestamp": NOW,
                    "open": "64900",
                    "high": "65100",
                    "low": "64850",
                    "close": "65000.25",
                    "volume": "100.5",
                }
            ],
        }
    )


def complete_research_bundle() -> dict:
    return deepcopy(
        {
            "vix": "15.25",
            "real_yield_10y": "1.82",
            "dxy": "98.40",
            # An empty result is still evidence that the event scan ran.
            "macro_event_scan": [],
            "findings": [
                {
                    "title": "Fed calendar checked",
                    "summary": "No FOMC decision falls inside the analysis horizon.",
                    "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                    "fetched_at": NOW,
                }
            ],
            "source_conflicts": [],
            "evidence_gaps": [],
        }
    )


def valid_market_analysis(**overrides: object) -> dict:
    analysis = {
        "regime": "risk_on",
        "factor_scores": {
            "market_structure": 1,
            "macro": 0,
            "derivatives": 1,
        },
        "total_score": 2,
        "main_action": "open_long",
        "instrument": "BTC-USDT-SWAP",
        "horizon": "4h",
        "reference_price": "65000.25",
        "entry_trigger": "65100",
        "stop_price": "64500",
        "target_1": "66000",
        "target_2": "67000",
        "probability": 0.65,
        "position_size_class": "light",
        "max_leverage": 2,
        "risk_pct": 0.10,
        "root_cause_chain": ["Price reclaimed resistance", "Liquidity supports continuation"],
        "why_not_opposite": "The bearish invalidation has not triggered.",
        "invalidation": "Close below 64500.",
        "manual_execution_required": True,
        "expires_in_seconds": 90,
    }
    analysis.update(overrides)
    return deepcopy(analysis)
