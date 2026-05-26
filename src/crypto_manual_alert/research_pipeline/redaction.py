from __future__ import annotations

from typing import Any


def redact_snippets_for_prompt(value: Any, *, path: str) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if "snippet" in key_text.lower():
                redacted[key_text] = f"{path}.{key_text}.redacted"
            else:
                redacted[key_text] = redact_snippets_for_prompt(item, path=f"{path}.{key_text}")
        return redacted
    if isinstance(value, list):
        return [redact_snippets_for_prompt(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    return value
