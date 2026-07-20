"""Product API package exports without importing the application eagerly.

Graph and worker modules share small API helpers, but importing those helpers must not
construct the Product FastAPI application or load Product settings as a package side
effect. The lazy export preserves the existing ``from crypto_alert_v2.api import app``
compatibility for actual API consumers.
"""

from typing import Any

__all__ = ["app", "create_app"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from crypto_alert_v2.api.app import app, create_app

        return {"app": app, "create_app": create_app}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
