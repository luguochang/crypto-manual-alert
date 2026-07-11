from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


DEFAULT_API_BASE = "http://127.0.0.1:8010"

TRADE_ACTIONS = {
    "open long",
    "hold long",
    "trigger long",
    "flip short to long",
    "open short",
    "hold short",
    "trigger short",
    "flip long to short",
}


class RealOutcomeEvidenceError(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check an already running API for at least one real, exchange-native, matured, "
            "scorable outcome sample. This proves outcome evidence exists; it is not "
            "prod-actionable alert proof."
        )
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--evaluation-target", default=None)
    parser.add_argument("--symbol", default=None)
    parser.add_argument(
        "--collected-after",
        default=None,
        help=(
            "Only count matched outcomes whose window.collected_at is at or after this "
            "timezone-aware ISO timestamp. This prevents stale sidecar samples from "
            "satisfying a fresh hosted collection proof."
        ),
    )
    parser.add_argument("--min-count", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    try:
        result = run_smoke(
            api_base=args.api_base,
            evaluation_target=args.evaluation_target,
            symbol=args.symbol,
            collected_after=args.collected_after,
            min_count=args.min_count,
            timeout=args.timeout,
        )
    except RealOutcomeEvidenceError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "smoke_profile": "real_outcome_evidence",
                    "api": _normalize_base(args.api_base),
                    "symbol": args.symbol,
                    "collected_after": args.collected_after,
                    "error": str(exc),
                    "real_exchange_native_matured_outcome_proven": False,
                    "prod_actionable_alert_proven": False,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def run_smoke(
    *,
    api_base: str,
    timeout: float,
    evaluation_target: str | None = None,
    symbol: str | None = None,
    collected_after: str | None = None,
    min_count: int = 1,
) -> dict[str, Any]:
    if min_count < 1:
        raise RealOutcomeEvidenceError("min_count_must_be_positive")

    api = _normalize_base(api_base)
    normalized_symbol = _normalize_optional_symbol(symbol)
    collected_after_dt = _parse_required_datetime(collected_after, label="collected_after") if collected_after else None
    path = "/api/eval/outcomes"
    if evaluation_target:
        path = f"{path}?{urlencode({'evaluation_target': evaluation_target})}"

    payload = _get_json(_join(api, path), timeout=timeout, label="eval outcomes")
    data = _require_envelope_ok(payload, "eval outcomes")
    items = data.get("items")
    if not isinstance(items, list):
        raise RealOutcomeEvidenceError("eval_outcomes_items_missing")

    matched = [
        _public_match_summary(item)
        for item in items
        if _is_real_scored_outcome(
            item,
            symbol=normalized_symbol,
            collected_after=collected_after_dt,
        )
    ]
    if len(matched) < min_count:
        raise RealOutcomeEvidenceError(
            "no_real_exchange_native_matured_outcome: "
            "expected at least "
            f"{min_count}, matched {len(matched)} of {len(items)} outcomes"
        )

    return {
        "ok": True,
        "smoke_profile": "real_outcome_evidence",
        "api": api,
        "evaluation_target": evaluation_target,
        "symbol": normalized_symbol,
        "collected_after": collected_after_dt.isoformat() if collected_after_dt is not None else None,
        "total_count": len(items),
        "matched_count": len(matched),
        "matched": matched,
        "real_exchange_native_matured_outcome_proven": True,
        "prod_actionable_alert_proven": False,
    }


def _is_real_scored_outcome(
    item: Any,
    *,
    symbol: str | None = None,
    collected_after: datetime | None = None,
) -> bool:
    if not isinstance(item, dict):
        return False
    window = item.get("window")
    if not isinstance(window, dict):
        return False
    if symbol is not None and (
        _normalize_optional_symbol(item.get("symbol")) != symbol
        or _normalize_optional_symbol(window.get("symbol")) != symbol
    ):
        return False
    if collected_after is not None:
        collected_at = _parse_optional_datetime(window.get("collected_at"))
        if collected_at is None or collected_at < collected_after:
            return False
    if window.get("source_type") != "exchange_native":
        return False
    if window.get("matured") is not True:
        return False
    if item.get("can_score") is not True:
        return False
    if window.get("can_score_execution_outcome") is not True:
        return False
    if item.get("unscored_reason") not in (None, ""):
        return False
    if window.get("unscored_reason") not in (None, ""):
        return False
    action = str(item.get("action") or "").strip().lower()
    if action not in TRADE_ACTIONS:
        return False
    for key in ("entry_price", "stop_price", "target_1"):
        if item.get(key) is None:
            return False
    for key in ("open_price", "high_price", "low_price", "close_price"):
        if window.get(key) is None:
            return False
    return True


def _public_match_summary(item: dict[str, Any]) -> dict[str, Any]:
    window = item["window"]
    return {
        "decision_ref": item.get("decision_ref"),
        "evaluation_target": item.get("evaluation_target"),
        "symbol": item.get("symbol"),
        "window_name": window.get("name"),
        "action": item.get("action"),
        "collected_at": window.get("collected_at"),
        "window_end": window.get("window_end"),
        "close_price": window.get("close_price"),
    }


def _normalize_optional_symbol(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def _parse_required_datetime(value: str, *, label: str) -> datetime:
    parsed = _parse_optional_datetime(value)
    if parsed is None:
        raise RealOutcomeEvidenceError(f"{label}_must_be_timezone_aware_iso_datetime")
    return parsed


def _parse_optional_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _normalize_base(value: str) -> str:
    return value.rstrip("/")


def _join(base: str, path: str) -> str:
    return urljoin(f"{base}/", path.lstrip("/"))


def _get_json(url: str, *, timeout: float, label: str) -> dict[str, Any]:
    request = Request(url, headers={"accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RealOutcomeEvidenceError(f"{label} returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RealOutcomeEvidenceError(f"{label} request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise RealOutcomeEvidenceError(f"{label} returned non-object JSON")
    return payload


def _require_envelope_ok(payload: dict[str, Any], label: str) -> dict[str, Any]:
    if payload.get("ok") is not True:
        raise RealOutcomeEvidenceError(f"{label} returned ok=false")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RealOutcomeEvidenceError(f"{label} data is missing or not an object")
    return data


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
