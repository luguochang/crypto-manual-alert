from __future__ import annotations

import json
from numbers import Real
from datetime import datetime, timezone
from typing import Any

from .domain import ALLOWED_ACTIONS, DecisionPlan


class PlanParseError(ValueError):
    """Raised when the decision output cannot become a safe manual plan."""


REQUIRED_FIELDS = (
    "instrument",
    "main_action",
    "horizon",
    "manual_execution_required",
    "expires_in_seconds",
)

NUMERIC_FIELDS = {
    "reference_price",
    "entry_trigger",
    "stop_price",
    "target_1",
    "target_2",
    "probability",
    "max_leverage",
    "risk_pct",
    "expires_in_seconds",
}


def _extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanParseError(f"decision output must be strict JSON object without markdown fences or extra text: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlanParseError("decision output must be strict JSON object")
    return payload


def _validate_required_fields(payload: dict[str, Any]) -> None:
    for field in REQUIRED_FIELDS:
        value = payload.get(field)
        if field not in payload or value is None or value == "":
            raise PlanParseError(f"{field} is required")
    if payload.get("manual_execution_required") is not True:
        raise PlanParseError("manual_execution_required must be boolean true")


def _validate_action(payload: dict[str, Any]) -> None:
    action = payload.get("main_action")
    if action is not None and str(action) not in ALLOWED_ACTIONS:
        raise PlanParseError(f"invalid main_action: {action}")


def _validate_numeric_fields(payload: dict[str, Any]) -> None:
    for field in NUMERIC_FIELDS:
        value = payload.get(field)
        if field not in payload or value is None or value == "":
            continue
        if isinstance(value, bool):
            raise PlanParseError(f"invalid numeric field: {field}")
        if field in {"max_leverage", "expires_in_seconds"}:
            if not isinstance(value, int):
                raise PlanParseError(f"invalid numeric field: {field}")
            if field == "expires_in_seconds" and value <= 0:
                raise PlanParseError("expires_in_seconds must be positive")
            continue
        if not isinstance(value, Real):
            raise PlanParseError(f"invalid numeric field: {field}")
        if field == "probability" and not 0 <= float(value) <= 1:
            raise PlanParseError("probability must be within [0, 1]")


def parse_decision_plan(raw: str, generated_at: datetime | None = None) -> DecisionPlan:
    payload = _extract_json(raw)
    _validate_action(payload)
    _validate_numeric_fields(payload)
    _validate_required_fields(payload)
    try:
        plan = DecisionPlan.from_payload(payload, generated_at or datetime.now(timezone.utc))
    except (TypeError, ValueError) as exc:
        for field in NUMERIC_FIELDS:
            message = str(exc)
            if field in message or field in payload:
                raise PlanParseError(f"invalid numeric field: {field}") from exc
        raise PlanParseError(f"invalid decision payload: {exc}") from exc
    if not plan.instrument:
        raise PlanParseError("instrument is required")
    if not plan.manual_execution_required:
        raise PlanParseError("manual_execution_required must be true")
    return plan
