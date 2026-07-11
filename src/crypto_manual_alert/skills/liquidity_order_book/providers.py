from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Mapping
import hashlib
import json
import math
import time
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class OrderBookRequest:
    symbol: str
    trace_id: str
    task_id: str


@dataclass(frozen=True)
class OrderBookFactRefs:
    mark_ref: str
    index_ref: str
    order_book_ref: str

    def to_fact_refs(self) -> dict[str, str]:
        return {
            "mark": self.mark_ref,
            "index": self.index_ref,
            "order_book": self.order_book_ref,
        }


class OrderBookProvider(Protocol):
    def fetch(self, request: OrderBookRequest) -> OrderBookFactRefs:
        """Return exchange-native fact refs without exposing raw order book payloads."""


@dataclass(frozen=True)
class FixtureOrderBookProvider:
    exchange: str = "fixture"

    def fetch(self, request: OrderBookRequest) -> OrderBookFactRefs:
        prefix = f"exchange:{self.exchange}:{request.symbol}:{request.trace_id}"
        return OrderBookFactRefs(
            mark_ref=f"{prefix}:mark",
            index_ref=f"{prefix}:index",
            order_book_ref=f"{prefix}:order_book",
        )


@dataclass(frozen=True)
class OkxPublicOrderBookProvider:
    base_url: str = "https://www.okx.com"
    timeout_seconds: int = 8
    order_book_depth: int = 20
    max_age_seconds: int = 60
    clock_ms: Callable[[], int] = lambda: int(time.time() * 1000)
    http_get: Callable[[str, dict[str, str]], Mapping[str, Any]] | None = None

    def fetch(self, request: OrderBookRequest) -> OrderBookFactRefs:
        mark_payload = self._get(
            "/api/v5/public/mark-price",
            {"instType": "SWAP", "instId": request.symbol},
        )
        index_payload = self._get(
            "/api/v5/market/index-tickers",
            {"instId": _index_instrument_id(request.symbol)},
        )
        book_payload = self._get(
            "/api/v5/market/books",
            {"instId": request.symbol, "sz": str(self.order_book_depth)},
        )
        mark_row = _first_row(mark_payload)
        index_row = _first_row(index_payload)
        book_row = _first_row(book_payload)
        now_ms = int(self.clock_ms())
        _ensure_fresh("mark", mark_row, now_ms=now_ms, max_age_seconds=self.max_age_seconds)
        _ensure_fresh("index", index_row, now_ms=now_ms, max_age_seconds=self.max_age_seconds)
        _ensure_fresh("order_book", book_row, now_ms=now_ms, max_age_seconds=self.max_age_seconds)
        if not _is_finite_number(mark_row.get("markPx")):
            raise RuntimeError("OKX mark price missing")
        if not _is_finite_number(index_row.get("idxPx")):
            raise RuntimeError("OKX index price missing")
        if not book_row.get("asks") or not book_row.get("bids"):
            raise RuntimeError("OKX order book depth missing")

        prefix = f"exchange:okx_public:{request.symbol}:{request.trace_id}"
        return OrderBookFactRefs(
            mark_ref=f"{prefix}:mark:{_stable_hash(_ref_payload(request, mark_row, 'mark'))}",
            index_ref=f"{prefix}:index:{_stable_hash(_ref_payload(request, index_row, 'index'))}",
            order_book_ref=f"{prefix}:order_book:{_stable_hash(_book_ref_payload(request, book_row))}",
        )

    def _get(self, path: str, params: dict[str, str]) -> Mapping[str, Any]:
        if self.http_get is not None:
            payload = self.http_get(path, params)
        else:
            with httpx.Client(base_url=self.base_url.rstrip("/"), timeout=self.timeout_seconds) as client:
                response = client.get(path, params=params)
                response.raise_for_status()
                payload = response.json()
        if not isinstance(payload, Mapping):
            raise RuntimeError("OKX response payload must be an object")
        if str(payload.get("code")) != "0":
            raise RuntimeError(f"OKX returned code={payload.get('code')}")
        return payload


def _first_row(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], Mapping):
        raise RuntimeError("OKX response data is empty")
    return rows[0]


def _ref_payload(request: OrderBookRequest, row: Mapping[str, Any], fact_type: str) -> dict[str, Any]:
    value_key = "markPx" if fact_type == "mark" else "idxPx"
    return {
        "exchange": "okx_public",
        "symbol": request.symbol,
        "task_id": request.task_id,
        "fact_type": fact_type,
        "value": str(row.get(value_key) or ""),
        "ts": str(row.get("ts") or ""),
    }


def _book_ref_payload(request: OrderBookRequest, row: Mapping[str, Any]) -> dict[str, Any]:
    asks = row.get("asks") if isinstance(row.get("asks"), list) else []
    bids = row.get("bids") if isinstance(row.get("bids"), list) else []
    return {
        "exchange": "okx_public",
        "symbol": request.symbol,
        "task_id": request.task_id,
        "fact_type": "order_book",
        "ask_depth": len(asks),
        "bid_depth": len(bids),
        "ts": str(row.get("ts") or ""),
    }


def _ensure_fresh(name: str, row: Mapping[str, Any], *, now_ms: int, max_age_seconds: int) -> None:
    ts = _int_or_none(row.get("ts"))
    if ts is None:
        raise RuntimeError(f"OKX {name} timestamp missing")
    max_age_ms = max(0, int(max_age_seconds)) * 1000
    if now_ms - ts > max_age_ms:
        raise RuntimeError(f"OKX {name} data is stale")


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _is_finite_number(value: Any) -> bool:
    try:
        return value not in {None, ""} and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _index_instrument_id(symbol: str) -> str:
    normalized = symbol.strip()
    if normalized.upper().endswith("-SWAP"):
        return normalized[:-5]
    return normalized


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
