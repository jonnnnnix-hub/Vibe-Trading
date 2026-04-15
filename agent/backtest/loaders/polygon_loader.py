"""Polygon.io-backed loader for US/HK equity OHLCV data."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import pandas as pd

from backtest.loaders.base import validate_date_range
from backtest.loaders.registry import register

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]

_INTERVAL_MAP = {
    "1D": "day",
    "1H": "hour",
    "4H": "hour",
    "15m": "minute",
    "30m": "minute",
    "5m": "minute",
    "1m": "minute",
}


def _to_polygon_ticker(code: str) -> str:
    """Convert project symbols into Polygon ticker format.

    Args:
        code: Project symbol (e.g. AAPL.US, 700.HK).

    Returns:
        Polygon ticker string.
    """
    upper = code.strip().upper()
    if upper.endswith(".US"):
        return upper[:-3]
    if upper.endswith(".HK"):
        return upper  # Polygon uses same HK format
    return upper


def _to_polygon_interval(interval: str) -> str:
    """Map backtest interval to Polygon timespan."""
    normalized = str(interval or "1D").strip()
    return _INTERVAL_MAP.get(normalized, "day")


@register
class DataLoader:
    """Fetch equity bars from Polygon.io."""

    name = "polygon"
    markets = {"us_equity", "hk_equity"}
    requires_auth = True

    def __init__(self) -> None:
        self.api_key = os.environ.get("POLYGON_API_KEY", "")
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Check if Polygon API key is configured."""
        if self._available is None:
            self._available = bool(self.api_key)
        return self._available

    def fetch(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        fields: Optional[List[str]] = None,
        interval: str = "1D",
    ) -> Dict[str, pd.DataFrame]:
        """Fetch OHLCV history from Polygon.io.

        Args:
            codes: Project symbols.
            start_date: Start date YYYY-MM-DD.
            end_date: End date YYYY-MM-DD.
            fields: Ignored.
            interval: Bar interval.

        Returns:
            {symbol: DataFrame} mapping.
        """
        del fields
        if not codes or not self.is_available():
            return {}
        validate_date_range(start_date, end_date)

        try:
            import requests
        except ImportError:
            return {}

        timespan = _to_polygon_interval(interval)
        multiplier = 1 if timespan != "hour" else "4"
        if timespan == "hour":
            timespan = "hour"

        results: Dict[str, pd.DataFrame] = {}

        for code in codes:
            ticker = _to_polygon_ticker(code)
            url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{start_date}/{end_date}"
            params = {
                "adjusted": "true",
                "sort": "asc",
                "limit": 50000,
                "apiKey": self.api_key,
            }
            try:
                resp = requests.get(url, params=params, timeout=30)
                data = resp.json()
                if data.get("status") != "OK" or not data.get("results"):
                    continue

                rows = data["results"]
                df = pd.DataFrame(rows)
                df["t"] = pd.to_datetime(df["t"], unit="ms")
                df = df.rename(columns={
                    "o": "open", "h": "high", "l": "low",
                    "c": "close", "v": "volume", "t": "trade_date",
                })
                df = df[_OHLCV_COLUMNS + ["trade_date"]]
                df.index = pd.DatetimeIndex(df["trade_date"])
                df.index.name = "trade_date"
                df = df.drop(columns=["trade_date"])
                df = df.apply(pd.to_numeric, errors="coerce")
                df = df.sort_index()
                df = df.dropna(subset=["open", "high", "low", "close"])
                df["volume"] = df["volume"].fillna(0.0)

                if not df.empty:
                    results[code] = df
            except Exception:
                continue

        return results
