from __future__ import annotations

from fastapi import HTTPException, Request

from .schemas import failure


def require_diagnostic_routes_enabled(request: Request) -> None:
    config = getattr(request.app.state, "config", None)
    diagnostic = getattr(config, "diagnostic", None)
    if bool(getattr(diagnostic, "routes_enabled", False)):
        return
    raise HTTPException(
        status_code=403,
        detail=failure(
            code="diagnostic_routes_disabled",
            message="diagnostic routes are disabled for this environment",
        ),
    )
