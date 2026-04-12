"""
Relative Momentum + Trend Continuation Engine (v3)
====================================================

Core idea: rank stocks by 12-1 month momentum (skip last month to avoid
short-term reversal), go long top-half, cash bottom-half. Add a 200-SMA
regime filter to go fully to cash in bear markets.

This is a proven academic factor (Jegadeesh & Titman, 1993).

Signals:
1. **12-1 Month Momentum** — 252-day return minus last 21-day return
2. **Cross-sectional rank** — buy top N stocks (>= median momentum)
3. **200-SMA regime** — per-stock: only long if above 200-SMA
4. **Trend strength** — scale by distance above 200-SMA
5. **Rebalance monthly** — hold positions for ~21 trading days to reduce churn
"""

import numpy as np
import pandas as pd


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


class SignalEngine:
    """Cross-sectional momentum with regime filter."""

    MOMENTUM_WINDOW = 252   # 12 months
    SKIP_WINDOW = 21        # skip last month (reversal)
    REGIME_SMA = 200
    REBALANCE_FREQ = 21     # monthly rebalance

    def generate(self, data_map: dict) -> dict:
        """Compute momentum signals.

        Args:
            data_map: {code: DataFrame with OHLCV}.

        Returns:
            {code: pd.Series of signal weights in [0, 1]}.
        """
        # First, compute momentum scores for all stocks at each date
        codes = sorted(data_map.keys())
        if not codes:
            return {}

        # Get aligned close prices
        all_closes = {}
        for code in codes:
            df = data_map[code]
            if df.empty or "close" not in df.columns:
                continue
            all_closes[code] = df["close"].astype(float)

        if not all_closes:
            return {}

        close_df = pd.DataFrame(all_closes)
        close_df = close_df.sort_index()

        # 12-1 month momentum: return over [t-252, t-21]
        ret_12m = close_df.pct_change(self.MOMENTUM_WINDOW)
        ret_1m = close_df.pct_change(self.SKIP_WINDOW)
        momentum = ret_12m - ret_1m  # 12-1 momentum

        # Regime filter: per-stock 200-SMA
        above_sma = pd.DataFrame(index=close_df.index, columns=close_df.columns, data=0.0)
        for code in close_df.columns:
            sma_200 = _sma(close_df[code], self.REGIME_SMA)
            above_sma[code] = (close_df[code] > sma_200).astype(float)
            # Trend strength: how far above SMA (0-1 scale)
            dist = ((close_df[code] - sma_200) / sma_200).clip(0.0, 0.3) / 0.3
            above_sma[code] = above_sma[code] * (0.5 + 0.5 * dist)

        # Cross-sectional ranking at each date
        signal_df = pd.DataFrame(0.0, index=close_df.index, columns=close_df.columns)

        for i in range(self.MOMENTUM_WINDOW + 5, len(close_df.index)):
            date = close_df.index[i]

            # Only rebalance monthly
            if i % self.REBALANCE_FREQ != 0 and i > self.MOMENTUM_WINDOW + 5:
                signal_df.iloc[i] = signal_df.iloc[i - 1]
                continue

            mom_today = momentum.iloc[i].dropna()
            if len(mom_today) < 2:
                if i > 0:
                    signal_df.iloc[i] = signal_df.iloc[i - 1]
                continue

            # Rank stocks: top half gets signal
            median_mom = mom_today.median()
            for code in mom_today.index:
                if mom_today[code] >= median_mom and mom_today[code] > 0:
                    # Score based on rank position
                    rank_pct = (mom_today.rank(pct=True))[code]
                    raw_signal = rank_pct  # [0.5, 1.0] for top half

                    # Apply regime filter
                    regime = above_sma.iloc[i].get(code, 0.0)
                    signal_df.at[date, code] = raw_signal * regime
                else:
                    signal_df.at[date, code] = 0.0

        # Convert to signal_map format
        signal_map = {}
        for code in close_df.columns:
            sig = signal_df[code].fillna(0.0).clip(0.0, 1.0)
            signal_map[code] = sig

        return signal_map
