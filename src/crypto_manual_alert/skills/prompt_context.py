from __future__ import annotations

from crypto_manual_alert.skills.context_loader import SkillContext


def compact_prompt_context(context: SkillContext) -> dict[str, object]:
    return {
        "mode": "compact",
        "name": context.name,
        "sha256": context.sha256,
        "skill_md_excerpt": _compact_text(context.skill_md, 12000),
        "reference_excerpts": {name: _compact_text(text, 2500) for name, text in context.references.items()},
        "rules_reminder": [
            "manual-alert-only; never place orders",
            "one main_action only, from the canonical action enum",
            "separate known facts, inference, scenario, confidence cap, and invalidation",
            "use mark/index/order_book as exchange-native execution facts",
            "search-derived data can supplement context but cannot replace exchange-native execution facts",
            "include why_not_opposite, invalidation, unavailable_data, trigger/entry, stop, targets, probability, and next review time when available",
            "all user-facing explanatory text must be Simplified Chinese; keep JSON keys and action enum values canonical",
        ],
    }


def _compact_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head - 80
    return f"{text[:head]}\n\n...[compact excerpt; middle omitted for runtime cost]...\n\n{text[-tail:]}"
