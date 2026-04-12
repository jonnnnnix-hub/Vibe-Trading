"""
Universal Relative Momentum + Trend Continuation Engine (v3)
=============================================================

Same 12-1 month momentum + 200-SMA regime filter from v3-US, adapted for
any asset class by auto-scaling lookback windows to the trading calendar:

  - Equities (US/HK): 252 trading days/year  → 252-bar momentum, 21-bar skip
  - Crypto (24/7):     365 calendar days/year → 365-bar momentum, 30-bar skip

Cross-sectional ranking is performed within each asset class — crypto
assets compete against other crypto, equities against equities. This
avoids regime-mismatch where crypto's higher volatility would dominate.
"""

import numpy as np
import pandas as pd


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def _classify(code: str) -> str:
    """Classify symbol into asset class by naming convention."""
    c = code.strip().upper()
    if c.endswith("-USDT") or "/USDT" in c:
        return "crypto"
    if c.endswith(".HK"):
        return "hk_equity"
    return "us_equity"


# Lookback parameters per asset class
_PARAMS = {
    "us_equity": {"momentum": 252, "skip": 21, "sma": 200, "rebal": 21},
    "hk_equity": {"momentum": 252, "skip": 21, "sma": 200, "rebal": 21},
    "crypto":    {"momentum": 365, "skip": 30, "sma": 200, "rebal": 30},
}


class SignalEngine:
    """Cross-sectional momentum with regime filter — universal across asset classes."""

    def generate(self, data_map: dict) -> dict:
        """Compute momentum signals, ranking within each asset class.

        Args:
            data_map: {code: DataFrame with OHLCV}.

        Returns:
            {code: pd.Series of signal weights in [0, 1]}.
        """
        # Group codes by asset class
        groups: dict[str, list[str]] = {}
        for code in data_map:
            cls = _classify(code)
            groups.setdefault(cls, []).append(code)

        # Generate signals per asset class, then merge
        signal_map = {}
        for asset_class, codes in groups.items():
            params = _PARAMS.get(asset_class, _PARAMS["us_equity"])
            sub_map = self._generate_group(data_map, codes, params)
            signal_map.update(sub_map)

        return signal_map

    def _generate_group(
        self,
        data_map: dict,
        codes: list[str],
        params: dict,
    ) -> dict:
        """Generate signals for one asset-class group."""
        momentum_window = params["momentum"]
        skip_window = params["skip"]
        regime_sma = params["sma"]
        rebalance_freq = params["rebal"]

        all_closes = {}
        for code in codes:
            df = data_map.get(code)
            if df is None or df.empty or "close" not in df.columns:
                continue
            all_closes[code] = df["close"].astype(float)

        if not all_closes:
            return {}

        close_df = pd.DataFrame(all_closes).sort_index()

        # 12-1 month momentum
        ret_long = close_df.pct_change(momentum_window)
        ret_short = close_df.pct_change(skip_window)
        momentum = ret_long - ret_short

        # Regime filter: per-asset SMA
        above_sma = pd.DataFrame(0.0, index=close_df.index, columns=close_df.columns)
        for code in close_df.columns:
            sma = _sma(close_df[code], regime_sma)
            is_above = (close_df[code] > sma).astype(float)
            dist = ((close_df[code] - sma) / sma).clip(0.0, 0.3) / 0.3
            above_sma[code] = is_above * (0.5 + 0.5 * dist)

        # Cross-sectional ranking
        signal_df = pd.DataFrame(0.0, index=close_df.index, columns=close_df.columns)
        start_idx = momentum_window + 5

        for i in range(start_idx, len(close_df.index)):
            date = close_df.index[i]

            # Only rebalance periodically
            if i % rebalance_freq != 0 and i > start_idx:
                signal_df.iloc[i] = signal_df.iloc[i - 1]
                continue

            mom_today = momentum.iloc[i].dropna()
            if len(mom_today) < 2:
                if i > 0:
                    signal_df.iloc[i] = signal_df.iloc[i - 1]
                continue

            # Top half by momentum gets signal
            median_mom = mom_today.median()
            for code in mom_today.index:
                if mom_today[code] >= median_mom and mom_today[code] > 0:
                    rank_pct = mom_today.rank(pct=True)[code]
                    regime = above_sma.iloc[i].get(code, 0.0)
                    signal_df.at[date, code] = rank_pct * regime
                else:
                    signal_df.at[date, code] = 0.0

        signal_map = {}
        for code in close_df.columns:
            signal_map[code] = signal_df[code].fillna(0.0).clip(0.0, 1.0)

        return signal_map
