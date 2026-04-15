"""Financial Modeling Prep (FMP) loader for US/HK equity OHLCV data."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import pandas as pd

from backtest.loaders.base import validate_date_range
from backtest.loaders.registry import register

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def _to_fmp_symbol(code: str) -> str:
    """Convert project symbols into FMP format.

    Args:
        code: Project symbol (e.g. AAPL.US, 700.HK).

    Returns:
        FMP ticker string.
    """
    upper = code.strip().upper()
    if upper.endswith(".US"):
        return upper[:-3]
    if upper.endswith(".HK"):
        return upper  # FMP uses same format
    return upper


@register
class DataLoader:
    """Fetch equity bars from Financial Modeling Prep API."""

    name = "fmp"
    markets = {"us_equity", "hk_equity"}
    requires_auth = True

    def __init__(self) -> None:
        self.api_key = os.environ.get("FMP_API_KEY", "")
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Check if FMP API key is configured."""
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
        """Fetch OHLCV history from FMP.

        Args:
            codes: Project symbols.
            start_date: Start date YYYY-MM-DD.
            end_date: End date YYYY-MM-DD.
            fields: Ignored.
            interval: Bar interval (1D supported).

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

        results: Dict[str, pd.DataFrame] = {}

        for code in codes:
            ticker = _to_fmp_symbol(code)
            url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{ticker}"
            params = {
                "from": start_date,
                "to": end_date,
                "apikey": self.api_key,
            }
            try:
                resp = requests.get(url, params=params, timeout=30)
                data = resp.json()
                historical = data.get("historical", [])
                if not historical:
                    continue

                df = pd.DataFrame(historical)
                df["date"] = pd.to_datetime(df["date"])
                df = df.rename(columns={
                    "open": "open", "high": "high", "low": "low",
                    "close": "close", "volume": "volume", "date": "trade_date",
                })
                df.index = pd.DatetimeIndex(df["trade_date"])
                df.index.name = "trade_date"
                df = df[_OHLCV_COLUMNS]
                df = df.apply(pd.to_numeric, errors="coerce")
                df = df.sort_index()
                df = df.dropna(subset=["open", "high", "low", "close"])
                df["volume"] = df["volume"].fillna(0.0)

                if not df.empty:
                    results[code] = df
            except Exception:
                continue

        return results
