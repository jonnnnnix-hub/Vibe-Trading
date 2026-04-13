#!/usr/bin/env python3
"""Seed historical OHLCV data from Polygon.io for the 90-stock Syntax-AI universe.

Downloads daily bars for each ticker from 2024-10-01 (warmup) through 2026-04-12,
saves as individual CSV files in backtest/data/ohlcv/.
Also downloads SPY for macro context.
"""

import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

POLYGON_KEY = os.environ.get("POLYGON_API_KEY", "7I9WEdac15PSd13EEYHk4_9fxerCQVWn")

# Full 90-stock universe + SPY for macro
UNIVERSE = [
    # Technology (24)
    "AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSM","AVGO","ORCL","CRM",
    "ADBE","INTC","AMD","QCOM","TXN","INTU","ISRG","NOW","AMAT","MU",
    "LRCX","KLAC","MRVL","SNPS",
    # Healthcare (15)
    "UNH","JNJ","LLY","ABBV","MRK","PFE","TMO","ABT","DHR","BMY",
    "AMGN","GILD","VRTX","REGN","MDT",
    # Financials (12)
    "JPM","BAC","WFC","GS","MS","BLK","SCHW","AXP","C","USB","PNC","TFC",
    # Consumer (13)
    "PG","KO","PEP","COST","WMT","HD","MCD","NKE","SBUX","TGT","LOW","TJX","CMG",
    # Industrials (10)
    "CAT","DE","HON","UNP","UPS","GE","RTX","LMT","BA","MMM",
    # Energy (7)
    "XOM","CVX","COP","SLB","EOG","PXD","MPC",
    # Utilities (3)
    "NEE","DUK","SO",
    # REITs (3)
    "AMT","PLD","CCI",
    # Diversified (3)
    "BRK.B","V","MA",
    # Macro (for regime)
    "SPY",
]

# Date range: 3 months warmup before Jan 2025 for indicator computation
START_DATE = "2024-10-01"
END_DATE = "2026-04-12"

DATA_DIR = Path(__file__).resolve().parent / "data" / "ohlcv"


def fetch_polygon_bars(ticker: str, start: str, end: str) -> list:
    """Fetch daily OHLCV bars from Polygon.io."""
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
        f"{start}/{end}?adjusted=true&sort=asc&limit=50000&apiKey={POLYGON_KEY}"
    )
    req = Request(url, headers={"User-Agent": "VibeTradingBacktest/1.0"})
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") in ("OK", "DELAYED") and data.get("results"):
            return data["results"]
        return []
    except (HTTPError, URLError, json.JSONDecodeError) as e:
        print(f"  ERROR fetching {ticker}: {e}")
        return []


def bars_to_csv(bars: list, filepath: Path, ticker: str):
    """Write Polygon bars to CSV with standard columns."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "open", "high", "low", "close", "volume", "vwap", "transactions"])
        for bar in bars:
            ts = bar.get("t", 0)
            dt = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""
            writer.writerow([
                dt,
                bar.get("o", ""),
                bar.get("h", ""),
                bar.get("l", ""),
                bar.get("c", ""),
                int(bar.get("v", 0)),
                bar.get("vw", ""),
                bar.get("n", ""),
            ])


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    total = len(UNIVERSE)
    success = 0
    failed = []

    print(f"Seeding OHLCV data for {total} tickers: {START_DATE} → {END_DATE}")
    print(f"Output: {DATA_DIR}\n")

    for i, ticker in enumerate(UNIVERSE, 1):
        filepath = DATA_DIR / f"{ticker.replace('.','_')}.csv"

        # Skip if already downloaded
        if filepath.exists() and filepath.stat().st_size > 500:
            print(f"[{i}/{total}] {ticker:8s} — already exists, skipping")
            success += 1
            continue

        print(f"[{i}/{total}] {ticker:8s} — fetching...", end=" ", flush=True)
        bars = fetch_polygon_bars(ticker, START_DATE, END_DATE)

        if bars:
            bars_to_csv(bars, filepath, ticker)
            print(f"✓ {len(bars)} bars")
            success += 1
        else:
            print("✗ no data")
            failed.append(ticker)

        # Rate limit: Polygon free tier = 5 calls/min
        # With paid tier, can go faster. Be conservative.
        if i % 5 == 0:
            time.sleep(1.0)

    print(f"\n{'='*50}")
    print(f"Done: {success}/{total} tickers downloaded")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    print(f"Data directory: {DATA_DIR}")


if __name__ == "__main__":
    main()
