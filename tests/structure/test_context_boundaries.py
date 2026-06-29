from __future__ import annotations

import ast
from pathlib import Path


CONTEXT_PACKAGE = Path("src/crypto_manual_alert/context")


def test_context_layer_does_not_import_decision_layer():
    offenders: list[tuple[str, int, str]] = []
    for path in CONTEXT_PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("crypto_manual_alert.decision"):
                offenders.append((path.as_posix(), node.lineno, node.module or ""))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("crypto_manual_alert.decision"):
                        offenders.append((path.as_posix(), node.lineno, alias.name))

    assert offenders == []
