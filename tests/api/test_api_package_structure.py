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
    previous_parent_attrs = {
        prefix: _get_parent_attr(prefix)
        for prefix in prefixes
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
        for prefix, previous_attr in previous_parent_attrs.items():
            _restore_parent_attr(prefix, previous_attr)


def _get_parent_attr(module_name: str) -> tuple[object, str, object, bool] | None:
    parent_name, _, attr_name = module_name.rpartition(".")
    parent = sys.modules.get(parent_name)
    if parent is None:
        return None
    if hasattr(parent, attr_name):
        return parent, attr_name, getattr(parent, attr_name), True
    return parent, attr_name, None, False


def _restore_parent_attr(module_name: str, previous_attr: tuple[object, str, object, bool] | None) -> None:
    if previous_attr is None:
        return
    parent, attr_name, value, existed = previous_attr
    if existed:
        setattr(parent, attr_name, value)
    elif hasattr(parent, attr_name):
        delattr(parent, attr_name)


def test_api_package_import_does_not_construct_application_graph():
    with _without_modules(
        "crypto_manual_alert.api",
        "crypto_manual_alert.workflow",
        "crypto_manual_alert.storage",
        "crypto_manual_alert.eval",
    ):
        api = importlib.import_module("crypto_manual_alert.api")

        assert "crypto_manual_alert.api.app" not in sys.modules
        assert not any(name.startswith("crypto_manual_alert.workflow.") for name in sys.modules)
        assert not any(name.startswith("crypto_manual_alert.storage.") for name in sys.modules)
        assert not any(name.startswith("crypto_manual_alert.eval.") for name in sys.modules)

        app_module = importlib.import_module("crypto_manual_alert.api.app")
        assert api.create_app is app_module.create_app
