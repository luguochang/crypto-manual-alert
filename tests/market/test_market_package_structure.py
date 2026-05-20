from __future__ import annotations

import sys

import crypto_manual_alert.market.providers as canonical_market_providers


def test_market_package_import_does_not_eagerly_import_provider_module():
    previous_providers = sys.modules.pop("crypto_manual_alert.market.providers", None)
    sys.modules.pop("crypto_manual_alert.market", None)
    try:
        __import__("crypto_manual_alert.market")

        assert "crypto_manual_alert.market.providers" not in sys.modules
    finally:
        sys.modules.pop("crypto_manual_alert.market", None)
        if previous_providers is not None:
            sys.modules["crypto_manual_alert.market.providers"] = previous_providers


def test_market_package_exports_canonical_provider_objects():
    assert canonical_market_providers.MarketDataProvider
    assert canonical_market_providers.FixtureMarketDataProvider
    assert canonical_market_providers.OkxPublicMarketDataProvider
