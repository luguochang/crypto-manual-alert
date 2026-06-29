#!/usr/bin/env python3
import argparse
import json
import ssl
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

BASE = "https://www.okx.com"


def get(path):
    url = BASE + path
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 crypto-macro-decision/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except (ssl.SSLCertVerificationError, urllib.error.URLError) as e:
        reason = getattr(e, "reason", e)
        if not isinstance(reason, ssl.SSLCertVerificationError) and "CERTIFICATE_VERIFY_FAILED" not in str(e):
            raise
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            data = json.loads(r.read().decode("utf-8"))
            if isinstance(data, dict):
                data["_warning"] = "SSL certificate verification failed locally; retried with unverified context."
            return data


def safe(path):
    try:
        return get(path)
    except Exception as e:
        return {"error": str(e), "path": path}


def index_id(inst):
    if inst.endswith("-SWAP"):
        return inst[:-5]
    return inst


def main():
    p = argparse.ArgumentParser(description="Fetch OKX crypto futures snapshot.")
    p.add_argument("instruments", nargs="*", default=["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"])
    p.add_argument("--no-candles", action="store_true", help="Skip 1H and 4H candles.")
    p.add_argument("--no-books", action="store_true", help="Skip top order book.")
    args = p.parse_args()

    out = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_quality_note": "Default snapshot includes last/mark/index, funding, OI, 1H/4H candles, and order book. OI change, liquidation, long/short, taker/CVD, and basis require external sources unless separately fetched.",
        "instruments": {},
    }

    for inst in args.instruments:
        item = {}
        item["ticker"] = safe(f"/api/v5/market/ticker?instId={inst}")
        item["funding"] = safe(f"/api/v5/public/funding-rate?instId={inst}")
        item["open_interest"] = safe(f"/api/v5/public/open-interest?instId={inst}")
        item["mark_price"] = safe(f"/api/v5/public/mark-price?instType=SWAP&instId={inst}")
        item["index_ticker"] = safe(f"/api/v5/market/index-tickers?instId={index_id(inst)}")
        item["open_interest_change_note"] = "current OI only; use historical snapshots or aggregator data for 1h/4h/24h OI change"
        if not args.no_books:
            item["books"] = safe(f"/api/v5/market/books?instId={inst}&sz=10")
        if not args.no_candles:
            item["candles_1h"] = safe(f"/api/v5/market/candles?instId={inst}&bar=1H&limit=48")
            item["candles_4h"] = safe(f"/api/v5/market/candles?instId={inst}&bar=4H&limit=30")
        out["instruments"][inst] = item

    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
