"""Request and run context package exports."""

from typing import Any

__all__ = [
    "DecisionRequest",
    "DecisionRunContext",
    "SideEffectPolicy",
    "build_manual_decision_request",
    "record_orchestration_artifacts",
]

_EXPORT_MODULES = {
    "DecisionRequest": "crypto_manual_alert.context.request",
    "DecisionRunContext": "crypto_manual_alert.context.run_context",
    "SideEffectPolicy": "crypto_manual_alert.context.run_context",
    "build_manual_decision_request": "crypto_manual_alert.context.request",
    "record_orchestration_artifacts": "crypto_manual_alert.context.artifacts",
}


def __getattr__(name: str) -> Any:
    import importlib

    if name not in _EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(_EXPORT_MODULES[name])
    return getattr(module, name)
