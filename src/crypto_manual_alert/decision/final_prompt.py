from __future__ import annotations

from typing import Any

from crypto_manual_alert.domain import DataPoint, MarketSnapshot
from crypto_manual_alert.research_pipeline import ResearchAudit


def build_legacy_final_prompt_packet(
    *,
    skill_runtime: Any,
    snapshot: MarketSnapshot,
    skill_context: Any | None,
    research_audit: ResearchAudit | None,
) -> dict[str, Any]:
    """Build the current legacy final prompt with final-safe research views."""

    prompt_snapshot = _final_prompt_snapshot(snapshot)
    prompt_packet = skill_runtime.build_prompt_packet(prompt_snapshot, context=skill_context)
    if research_audit:
        prompt_packet["research"] = research_audit.to_prompt_dict()
    return prompt_packet


def _final_prompt_snapshot(snapshot: MarketSnapshot) -> MarketSnapshot:
    points = {}
    for name, point in snapshot.points.items():
        if name.startswith("web_"):
            points[name] = DataPoint(
                name=point.name,
                value=_redacted_search_point_value(str(name), point.value),
                timestamp_ms=point.timestamp_ms,
                source=point.source,
                status=point.status,
            )
        else:
            points[name] = point
    return MarketSnapshot(
        symbol=snapshot.symbol,
        fetched_at=snapshot.fetched_at,
        points=points,
        unavailable=list(snapshot.unavailable),
    )


def _redacted_search_point_value(point_name: str, value: Any) -> Any:
    if not isinstance(value, list):
        return value
    redacted = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            redacted.append(
                {
                    key: item.get(key)
                    for key in ("title", "url", "source")
                    if key in item
                }
                | {"snippet_ref": f"market_snapshot.points.{point_name}[{index}].snippet_redacted"}
            )
        else:
            redacted.append(
                {
                    "source": "search-derived",
                    "snippet_ref": f"market_snapshot.points.{point_name}[{index}].snippet_redacted",
                }
            )
    return redacted
