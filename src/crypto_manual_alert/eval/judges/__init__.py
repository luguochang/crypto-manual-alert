from __future__ import annotations

from typing import Any

__all__ = ["FixtureLLMJudge", "OpenAICompatibleLLMJudge", "OPENING_ACTIONS", "RuleJudge", "build_side_effect_score"]

_EXPORT_MODULES = {
    "FixtureLLMJudge": "crypto_manual_alert.eval.judges.fixture_llm",
    "OpenAICompatibleLLMJudge": "crypto_manual_alert.eval.judges.llm",
    "OPENING_ACTIONS": "crypto_manual_alert.eval.judges.rules",
    "RuleJudge": "crypto_manual_alert.eval.judges.rules",
    "build_side_effect_score": "crypto_manual_alert.eval.judges.side_effects",
}


def __getattr__(name: str) -> Any:
    import importlib

    if name not in _EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(_EXPORT_MODULES[name])
    return getattr(module, name)
