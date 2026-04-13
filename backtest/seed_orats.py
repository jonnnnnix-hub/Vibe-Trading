#!/usr/bin/env python3
"""
Seed ORATS historical data for backtest.
Downloads cores (IV surface) and dailies (stock-level) for 90 tickers + SPY.
"""

import os
import csv
import time
import json
import urllib.request
import urllib.parse
from io import StringIO

API_KEY = "9e8c6cb2-a56e-41ba-8993-6bea2c095c8f"

TICKERS = [
    "AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSM","AVGO","ORCL","CRM",
    "ADBE","INTC","AMD","QCOM","TXN","INTU","ISRG","NOW","AMAT","MU",
    "LRCX","KLAC","MRVL","SNPS","UNH","JNJ","LLY","ABBV","MRK","PFE",
    "TMO","ABT","DHR","BMY","AMGN","GILD","VRTX","REGN","MDT","JPM",
    "BAC","WFC","GS","MS","BLK","SCHW","AXP","C","USB","PNC",
    "TFC","PG","KO","PEP","COST","WMT","HD","MCD","NKE","SBUX",
    "TGT","LOW","TJX","CMG","CAT","DE","HON","UNP","UPS","GE",
    "RTX","LMT","BA","MMM","XOM","CVX","COP","SLB","EOG","MPC",
    "NEE","DUK","SO","AMT","PLD","CCI","V","MA","SPY"
]

# Quarterly date chunks covering 2025-01-02 to 2026-04-11
DATE_CHUNKS = [
    ("2025-01-02", "2025-03-31"),
    ("2025-04-01", "2025-06-30"),
    ("2025-07-01", "2025-09-30"),
    ("2025-10-01", "2025-12-31"),
    ("2026-01-01", "2026-04-11"),
]

CORES_FIELDS = "ticker,tradeDate,orIvXern20d,orIvXern50d,orHv20d,orHv50d,orHv100d,slope,slopeInf,deriv,derivInf,iv30d,iv60d,iv90d,divYield"

CORES_DIR = "/home/user/workspace/Vibe-Trading/backtest/data/orats_cores"
DAILIES_DIR = "/home/user/workspace/Vibe-Trading/backtest/data/orats_dailies"

SKIP_THRESHOLD = 500  # bytes


def fetch_orats(url, retries=3):
    """Fetch URL and return parsed JSON data list."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "seed_orats/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                parsed = json.loads(raw)
                return parsed.get("data", [])
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Retry {attempt+1}/{retries} after error: {e}")
                time.sleep(1.0)
            else:
                raise
    return []


def rows_to_csv_lines(rows):
    """Convert list-of-dicts to list of CSV strings (with header)."""
    if not rows:
        return []
    output = StringIO()
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def download_ticker(ticker):
    """Download cores and dailies for a single ticker. Returns (cores_rows, dailies_rows)."""
    all_cores = []
    all_dailies = []

    for (date_from, date_to) in DATE_CHUNKS:
        # --- Cores ---
        cores_url = (
            f"https://api.orats.io/datav2/hist/cores?"
            f"token={API_KEY}&ticker={ticker}"
            f"&tradeDateFrom={date_from}&tradeDateTo={date_to}"
            f"&fields={urllib.parse.quote(CORES_FIELDS)}"
        )
        try:
            chunk = fetch_orats(cores_url)
            all_cores.extend(chunk)
            print(f"    cores {date_from}~{date_to}: {len(chunk)} rows")
        except Exception as e:
            print(f"    cores {date_from}~{date_to}: ERROR {e}")

        time.sleep(0.3)

        # --- Dailies ---
        dailies_url = (
            f"https://api.orats.io/datav2/hist/dailies?"
            f"token={API_KEY}&ticker={ticker}"
            f"&tradeDateFrom={date_from}&tradeDateTo={date_to}"
        )
        try:
            chunk = fetch_orats(dailies_url)
            all_dailies.extend(chunk)
            print(f"    dailies {date_from}~{date_to}: {len(chunk)} rows")
        except Exception as e:
            print(f"    dailies {date_from}~{date_to}: ERROR {e}")

        time.sleep(0.3)

    return all_cores, all_dailies


def save_csv(rows, filepath):
    """Write list-of-dicts to CSV file."""
    if not rows:
        # Write empty file so we know it was attempted
        with open(filepath, "w") as f:
            f.write("")
        return 0

    fieldnames = list(rows[0].keys())
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main():
    succeeded = 0
    failed = 0
    total_cores_rows = 0
    total_dailies_rows = 0
    skipped = 0

    print(f"Starting ORATS data seed for {len(TICKERS)} tickers...")
    print(f"Date range: 2025-01-02 to 2026-04-11 ({len(DATE_CHUNKS)} quarterly chunks)\n")

    for idx, ticker in enumerate(TICKERS, 1):
        cores_path = os.path.join(CORES_DIR, f"{ticker}.csv")
        dailies_path = os.path.join(DAILIES_DIR, f"{ticker}.csv")

        # Skip if both files already exist and are large enough
        cores_exists = os.path.exists(cores_path) and os.path.getsize(cores_path) > SKIP_THRESHOLD
        dailies_exists = os.path.exists(dailies_path) and os.path.getsize(dailies_path) > SKIP_THRESHOLD

        if cores_exists and dailies_exists:
            print(f"[{idx:3d}/{len(TICKERS)}] {ticker}: SKIPPED (already downloaded)")
            skipped += 1
            continue

        print(f"[{idx:3d}/{len(TICKERS)}] {ticker}: downloading...")

        try:
            cores_rows, dailies_rows = download_ticker(ticker)

            c_count = save_csv(cores_rows, cores_path)
            d_count = save_csv(dailies_rows, dailies_path)

            total_cores_rows += c_count
            total_dailies_rows += d_count
            succeeded += 1
            print(f"  => cores: {c_count} rows, dailies: {d_count} rows\n")

        except Exception as e:
            print(f"  => FAILED: {e}\n")
            failed += 1

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Tickers:    {len(TICKERS)} total")
    print(f"  Succeeded:  {succeeded}")
    print(f"  Skipped:    {skipped}")
    print(f"  Failed:     {failed}")
    print(f"  Cores rows:   {total_cores_rows:,}")
    print(f"  Dailies rows: {total_dailies_rows:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
