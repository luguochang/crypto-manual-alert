__all__ = [
    "FixtureMarketDataProvider",
    "MarketDataProvider",
    "OkxPublicMarketDataProvider",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import providers

    return getattr(providers, name)
