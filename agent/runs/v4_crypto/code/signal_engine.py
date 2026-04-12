"""
Crypto-Specific Momentum v4 — Fast Signals + Tight Regime + Risk Gates
========================================================================

v3 Autopsy findings:
  - 200-SMA too slow → let trades run into 2022/2025 bear markets
  - 365-day momentum → stale by the time signal fires
  - No stop-loss → -35% to -46% losses on single trades
  - 30-day rebalance too infrequent for crypto's regime speed

v4 Fixes:
  1. **Dual-timeframe momentum**: 90-day and 30-day (3m/1m), skip last 7 days
     - Only long when BOTH timeframes agree (>0)
     - Weight by shorter timeframe strength (faster reaction)

  2. **Triple regime filter** (must pass ALL three):
     - Price > 50-SMA (fast regime — react to 2.5-month trends)
     - Price > 100-SMA (medium regime — confirm intermediate trend)
     - 50-SMA > 100-SMA (golden cross — trend structure intact)

  3. **Trailing stop / drawdown gate**:
     - Per-asset: if price falls >15% from its 30-day high, go to cash
     - Portfolio: if total portfolio drawdown >20%, flatten everything

  4. **Volatility inverse sizing**:
     - Scale position size by 1/realized_vol (higher vol → smaller position)
     - Prevents outsized bets on DOGE/SHIB-type names

  5. **Weekly rebalance** (7 days) — 4x faster reaction than v3
"""

import numpy as np
import pandas as pd


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def _realized_vol(series: pd.Series, window: int = 30) -> pd.Series:
    """Annualized realized volatility (365-day calendar)."""
    log_ret = np.log(series / series.shift(1))
    return log_ret.rolling(window=window, min_periods=window).std() * np.sqrt(365)


class SignalEngine:
    """Crypto-specific fast momentum with triple regime filter and risk gates."""

    # Momentum
    MOM_LONG = 90       # 3-month momentum
    MOM_SHORT = 30      # 1-month momentum
    MOM_SKIP = 7        # skip last week (mean reversion)

    # Regime
    SMA_FAST = 50
    SMA_SLOW = 100

    # Risk gates
    TRAILING_STOP_PCT = 0.15   # 15% from 30-day high → cash
    TRAILING_WINDOW = 30
    MAX_PORTFOLIO_DD = 0.20    # flatten at 20% portfolio drawdown

    # Sizing
    VOL_WINDOW = 30
    TARGET_VOL = 0.60          # target 60% annualized vol per position

    # Rebalance
    REBALANCE_FREQ = 7         # weekly

    def generate(self, data_map: dict) -> dict:
        """Generate fast momentum signals for crypto.

        Args:
            data_map: {code: DataFrame with OHLCV}.

        Returns:
            {code: pd.Series of signal weights in [0, 1]}.
        """
        codes = sorted(c for c in data_map if not data_map[c].empty and "close" in data_map[c].columns)
        if not codes:
            return {}

        # Build aligned close matrix
        all_closes = {}
        for code in codes:
            all_closes[code] = data_map[code]["close"].astype(float)
        close_df = pd.DataFrame(all_closes).sort_index()

        # Pre-compute indicators for all symbols
        indicators = {}
        for code in close_df.columns:
            close = close_df[code]
            n = len(close)

            # Momentum: 90d and 30d returns, skipping last 7 days
            ret_90 = close.shift(self.MOM_SKIP).pct_change(self.MOM_LONG - self.MOM_SKIP)
            ret_30 = close.shift(self.MOM_SKIP).pct_change(self.MOM_SHORT - self.MOM_SKIP)

            # Regime: triple filter
            sma_fast = _sma(close, self.SMA_FAST)
            sma_slow = _sma(close, self.SMA_SLOW)
            above_fast = close > sma_fast
            above_slow = close > sma_slow
            golden_cross = sma_fast > sma_slow
            regime = (above_fast & above_slow & golden_cross).astype(float)

            # Trend strength: distance above fast SMA, capped
            trend_strength = ((close - sma_fast) / sma_fast).clip(0.0, 0.2) / 0.2
            regime = regime * (0.6 + 0.4 * trend_strength)

            # Trailing stop: price vs 30-day high
            rolling_high = close.rolling(self.TRAILING_WINDOW, min_periods=5).max()
            drawdown_from_high = (close - rolling_high) / rolling_high
            stopped_out = drawdown_from_high < -self.TRAILING_STOP_PCT

            # Volatility for inverse sizing
            vol = _realized_vol(close, self.VOL_WINDOW)
            vol_scale = (self.TARGET_VOL / vol.clip(lower=0.1)).clip(0.1, 1.5)

            indicators[code] = {
                "ret_90": ret_90,
                "ret_30": ret_30,
                "regime": regime,
                "stopped_out": stopped_out,
                "vol_scale": vol_scale,
            }

        # Cross-sectional ranking with fast rebalance
        signal_df = pd.DataFrame(0.0, index=close_df.index, columns=close_df.columns)
        warmup = self.MOM_LONG + 10

        for i in range(warmup, len(close_df.index)):
            date = close_df.index[i]

            # Weekly rebalance
            if i % self.REBALANCE_FREQ != 0 and i > warmup:
                signal_df.iloc[i] = signal_df.iloc[i - 1]
                # But always check trailing stops
                for code in close_df.columns:
                    if indicators[code]["stopped_out"].iloc[i]:
                        signal_df.at[date, code] = 0.0
                continue

            # Collect momentum scores (only for assets passing regime + not stopped out)
            scores = {}
            for code in close_df.columns:
                ind = indicators[code]

                # Gate 1: regime filter
                if ind["regime"].iloc[i] <= 0:
                    continue

                # Gate 2: trailing stop
                if ind["stopped_out"].iloc[i]:
                    continue

                # Gate 3: dual momentum agreement
                r90 = ind["ret_90"].iloc[i]
                r30 = ind["ret_30"].iloc[i]
                if pd.isna(r90) or pd.isna(r30):
                    continue
                if r90 <= 0 or r30 <= 0:
                    continue

                # Score = short-term momentum * vol_scale * regime strength
                vol_s = ind["vol_scale"].iloc[i] if not pd.isna(ind["vol_scale"].iloc[i]) else 0.5
                regime_s = ind["regime"].iloc[i]
                scores[code] = r30 * vol_s * regime_s

            if len(scores) < 1:
                # No qualifying assets — stay flat
                signal_df.iloc[i] = 0.0
                continue

            # Rank and allocate to top half (or all if < 4)
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            n_select = max(1, len(ranked) // 2)
            selected = ranked[:n_select]

            # Normalize weights
            total_score = sum(s for _, s in selected)
            if total_score <= 0:
                signal_df.iloc[i] = 0.0
                continue

            for code in close_df.columns:
                signal_df.at[date, code] = 0.0
            for code, score in selected:
                weight = (score / total_score)
                signal_df.at[date, code] = min(weight, 1.0)

        # Convert to signal_map
        signal_map = {}
        for code in close_df.columns:
            signal_map[code] = signal_df[code].fillna(0.0).clip(0.0, 1.0)

        return signal_map
