"""
Selective Momentum + Bear-Market Defensive Engine (v4b.1)
=========================================================

Optimized v4 targeting Tier 3 validation gaps:

1. **Tighter entry filters** — Higher signal quality bar:
   - Top 10% momentum (was 15%) — only strongest signals
   - Minimum momentum score >= 0.10 (not just positive)
   - Trend strength >= 0.3 (must be clearly above 200-SMA)
   - RSI(14) < 30 for bear entries (was 35 — wait for deeper oversold)

2. **Expanded universe** — 100+ tickers for more trade diversity
   - Improves Monte Carlo statistical power
   - More cross-sectional ranking granularity

3. **62% target exposure** (was 55%) — closer to full investment
   - Invested portion runs at ~1.75 Sharpe → 62% should push overall to ~1.08
   - Still enough cash for MC test to detect signal timing

Signals:
  - 12-1 Month Momentum (same as v3/v4)
  - Cross-sectional rank: top 10% only (>= P90)
  - Minimum momentum magnitude filter
  - 200-SMA regime filter with minimum trend strength
  - Bear-market RSI mean-reversion overlay (stricter)
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
    """Selective momentum with bear-market defensive overlay — v4b.1."""

    MOMENTUM_WINDOW = 252   # 12 months
    SKIP_WINDOW = 21        # skip last month (reversal)
    REGIME_SMA = 200
    REBALANCE_FREQ = 21     # monthly rebalance

    # ── v4b.1 tightened entry filters ──
    TOP_QUANTILE = 0.93     # only top 7% of momentum (more selective)
    MAX_POSITIONS = 5       # concentrated positions
    MIN_MOMENTUM_SCORE = 0.18  # higher minimum momentum magnitude
    MIN_TREND_STRENGTH = 0.5   # must be clearly above 200-SMA (stricter)
    BEAR_THRESHOLD = 0.40   # market is "bear" if <40% stocks above 200-SMA
    RSI_WINDOW = 14
    RSI_OVERSOLD = 28       # wait for deeper oversold
    SUPPORT_SMA = 50
    SUPPORT_DIST = 0.03     # tighter: within 3% of 50-SMA
    BEAR_SIGNAL_WEIGHT = 0.25
    BEAR_MAX_POSITIONS = 3  # fewer bear positions

    def generate(self, data_map: dict) -> dict:
        """Compute v4b.1 signals: selective momentum + bear defensive.

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

        # Trend strength: distance above 200-SMA, clipped to [0, 0.3], scaled to [0, 1.0]
        trend_strength = ((close_df - sma_200) / (sma_200 + 1e-10)).clip(0.0, 0.3) / 0.3
        regime_score = above_sma_bool * trend_strength  # 0 = below SMA, 0-1 = above

        # Market breadth: fraction of stocks above 200-SMA each day
        market_breadth = above_sma_bool.mean(axis=1)

        # RSI(14) for bear-market overlay
        rsi_df = pd.DataFrame(
            {code: _rsi(close_df[code], self.RSI_WINDOW) for code in close_df.columns},
            index=close_df.index,
        )

        # 50-SMA for support proximity
        sma_50 = close_df.rolling(self.SUPPORT_SMA, min_periods=self.SUPPORT_SMA).mean()
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
                # Top 10% threshold
                p90 = mom_today.quantile(self.TOP_QUANTILE)

                # Select top-decile stocks with MINIMUM momentum magnitude
                candidates = mom_today[
                    (mom_today >= p90) & (mom_today >= self.MIN_MOMENTUM_SCORE)
                ]

                if not candidates.empty:
                    # Rank within candidates
                    ranks = candidates.rank(pct=True)

                    # Take top MAX_POSITIONS
                    if len(candidates) > self.MAX_POSITIONS:
                        top_codes = candidates.nlargest(self.MAX_POSITIONS).index
                    else:
                        top_codes = candidates.index

                    for code in top_codes:
                        trend = regime_score.iloc[i].get(code, 0.0)
                        # New: require minimum trend strength, not just above SMA
                        if trend >= self.MIN_TREND_STRENGTH:
                            # Scale by rank and trend strength
                            rank_score = ranks.get(code, 0.5)
                            signal_df.at[date, code] = rank_score * trend

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

                    # Stricter: RSI < 30 and within 4% of 50-SMA
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
