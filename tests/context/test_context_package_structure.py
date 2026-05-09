from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def _without_modules(*prefixes: str) -> Iterator[None]:
    previous = {
        name: module
        for name, module in sys.modules.items()
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)
    }
    for name in previous:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes):
                sys.modules.pop(name, None)
        sys.modules.update(previous)


def test_context_package_import_does_not_eagerly_import_runtime_context_modules():
    with _without_modules("crypto_manual_alert.context", "crypto_manual_alert.decision"):
        context = importlib.import_module("crypto_manual_alert.context")

        assert "crypto_manual_alert.context.artifacts" not in sys.modules
        assert "crypto_manual_alert.context.run_context" not in sys.modules
        assert "crypto_manual_alert.decision.frozen_input" not in sys.modules

        run_context = importlib.import_module("crypto_manual_alert.context.run_context")
        request = importlib.import_module("crypto_manual_alert.context.request")
        artifacts = importlib.import_module("crypto_manual_alert.context.artifacts")

        assert context.DecisionRequest is request.DecisionRequest
        assert context.DecisionRunContext is run_context.DecisionRunContext
        assert context.SideEffectPolicy is run_context.SideEffectPolicy
        assert context.build_manual_decision_request is request.build_manual_decision_request
        assert context.record_orchestration_artifacts is artifacts.record_orchestration_artifacts
