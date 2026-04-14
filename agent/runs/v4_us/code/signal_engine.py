"""
Selective Momentum + Bear-Market Defensive Engine (v4)
======================================================

Builds on v3's 12-1 month momentum but with two key changes targeting
Tier 3 validation:

1. **Exposure cap (~55%)** — Only select top-quartile momentum stocks
   (not top-half) to concentrate alpha on high-conviction picks.  This
   lowers exposure fraction, giving the MC return-randomization test
   more statistical power to distinguish signal timing from random.

2. **Bear-market defensive signal** — When the broad market is in a
   downturn (fewer than 40% of stocks above 200-SMA), activate a
   short-term mean-reversion overlay: buy stocks with RSI(14) < 35
   that are within 5% of their 50-SMA (oversold near support).
   This generates trades in bear windows where v3 had zero activity.

3. **Stricter regime filter** — Momentum entries require price > 200-SMA
   AND the stock must be in the top 25% of cross-sectional momentum
   (was top 50% in v3).

Signals:
  - 12-1 Month Momentum (same as v3)
  - Cross-sectional rank: top quartile only (>= P75)
  - 200-SMA regime filter with trend-strength scaling
  - Bear-market RSI mean-reversion overlay
  - Monthly rebalance (21 trading days)
"""

import numpy as np
import pandas as pd


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def _rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Compute RSI using exponential moving average of gains/losses."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(span=window, min_periods=window).mean()
    avg_loss = loss.ewm(span=window, min_periods=window).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    return 100.0 - (100.0 / (1.0 + rs))


class SignalEngine:
    """Selective momentum with bear-market defensive overlay."""

    MOMENTUM_WINDOW = 252   # 12 months
    SKIP_WINDOW = 21        # skip last month (reversal)
    REGIME_SMA = 200
    REBALANCE_FREQ = 21     # monthly rebalance

    # ── v4 new parameters ──
    TOP_QUANTILE = 0.85     # only top 15% of momentum (was median in v3)
    MAX_POSITIONS = 8       # tight cap for concentration + lower exposure
    BEAR_THRESHOLD = 0.50   # market is "bear" if <50% stocks above 200-SMA (tightened from 0.40)
    RSI_WINDOW = 14
    RSI_OVERSOLD = 35       # RSI threshold for bear-market entries
    SUPPORT_SMA = 50        # near-support reference
    SUPPORT_DIST = 0.05     # within 5% of 50-SMA to qualify
    BEAR_SIGNAL_WEIGHT = 0.25  # smaller position size for defensive trades
    BEAR_MAX_POSITIONS = 5  # cap bear-market defensive positions

    def generate(self, data_map: dict) -> dict:
        """Compute v4 signals: selective momentum + bear defensive.

        Args:
            data_map: {code: DataFrame with OHLCV}.

        Returns:
            {code: pd.Series of signal weights in [0, 1]}.
        """
        codes = sorted(data_map.keys())
        if not codes:
            return {}

        # Align close prices
        all_closes = {}
        for code in codes:
            df = data_map[code]
            if df.empty or "close" not in df.columns:
                continue
            all_closes[code] = df["close"].astype(float)

        if not all_closes:
            return {}

        close_df = pd.DataFrame(all_closes).sort_index()

        # ── Pre-compute indicators ──

        # 12-1 month momentum
        ret_12m = close_df.pct_change(self.MOMENTUM_WINDOW)
        ret_1m = close_df.pct_change(self.SKIP_WINDOW)
        momentum = ret_12m - ret_1m

        # Per-stock 200-SMA regime
        sma_200 = close_df.rolling(self.REGIME_SMA, min_periods=self.REGIME_SMA).mean()
        above_sma_bool = (close_df > sma_200).astype(float)

        # Trend strength: distance above 200-SMA, clipped to [0, 0.3], scaled to [0.5, 1.0]
        trend_strength = ((close_df - sma_200) / (sma_200 + 1e-10)).clip(0.0, 0.3) / 0.3
        regime_score = above_sma_bool * (0.5 + 0.5 * trend_strength)

        # Market breadth: fraction of stocks above 200-SMA each day
        market_breadth = above_sma_bool.mean(axis=1)

        # RSI(14) for bear-market overlay
        rsi_df = pd.DataFrame(
            {code: _rsi(close_df[code], self.RSI_WINDOW) for code in close_df.columns},
            index=close_df.index,
        )

        # 50-SMA for support proximity
        sma_50 = close_df.rolling(self.SUPPORT_SMA, min_periods=self.SUPPORT_SMA).mean()
        # Distance from 50-SMA: abs((close - sma50) / sma50)
        dist_from_support = ((close_df - sma_50) / (sma_50 + 1e-10)).abs()

        # ── Generate signals ──
        signal_df = pd.DataFrame(0.0, index=close_df.index, columns=close_df.columns)

        start_bar = self.MOMENTUM_WINDOW + 5
        for i in range(start_bar, len(close_df.index)):
            date = close_df.index[i]

            # Only rebalance monthly
            if i % self.REBALANCE_FREQ != 0 and i > start_bar:
                signal_df.iloc[i] = signal_df.iloc[i - 1]
                continue

            breadth = market_breadth.iloc[i]
            is_bear_market = breadth < self.BEAR_THRESHOLD

            # ── MOMENTUM SIGNAL (bull/neutral market) ──
            mom_today = momentum.iloc[i].dropna()
            if len(mom_today) >= 4:
                # Top quartile threshold
                p75 = mom_today.quantile(self.TOP_QUANTILE)

                # Select top-quartile stocks with positive momentum
                candidates = mom_today[(mom_today >= p75) & (mom_today > 0)]

                if not candidates.empty:
                    # Rank within candidates
                    ranks = candidates.rank(pct=True)

                    # Take top MAX_POSITIONS
                    if len(candidates) > self.MAX_POSITIONS:
                        top_codes = candidates.nlargest(self.MAX_POSITIONS).index
                    else:
                        top_codes = candidates.index

                    for code in top_codes:
                        regime = regime_score.iloc[i].get(code, 0.0)
                        if regime > 0:
                            # Scale by rank and regime strength
                            rank_score = ranks.get(code, 0.5)
                            signal_df.at[date, code] = rank_score * regime

            # ── BEAR-MARKET DEFENSIVE SIGNAL ──
            if is_bear_market:
                rsi_today = rsi_df.iloc[i].dropna()
                dist_today = dist_from_support.iloc[i].dropna()

                # Collect bear candidates, rank by oversold severity
                bear_candidates = []
                for code in close_df.columns:
                    # Skip if already has momentum signal
                    if signal_df.at[date, code] > 0:
                        continue

                    rsi_val = rsi_today.get(code, 50.0)
                    dist_val = dist_today.get(code, 1.0)

                    # Oversold near support: RSI < 35 and within 5% of 50-SMA
                    if rsi_val < self.RSI_OVERSOLD and dist_val < self.SUPPORT_DIST:
                        oversold_score = (self.RSI_OVERSOLD - rsi_val) / self.RSI_OVERSOLD
                        bear_candidates.append((code, oversold_score))

                # Take only top BEAR_MAX_POSITIONS by oversold severity
                bear_candidates.sort(key=lambda x: x[1], reverse=True)
                for code, score in bear_candidates[:self.BEAR_MAX_POSITIONS]:
                    signal_df.at[date, code] = self.BEAR_SIGNAL_WEIGHT * score

        # Convert to signal_map
        signal_map = {}
        for code in close_df.columns:
            sig = signal_df[code].fillna(0.0).clip(0.0, 1.0)
            signal_map[code] = sig

        return signal_map
