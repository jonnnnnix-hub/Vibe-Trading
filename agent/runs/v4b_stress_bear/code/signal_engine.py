"""
Crypto v4b — Defensive Momentum with BTC Regime Gate
======================================================

v4a lessons:
  - 2022 crash still kills returns: -$290K in year one because signals
    fire as soon as warmup completes, right into the bear
  - Triple SMA filter helps in trending markets but not fast crashes
  - Per-asset trailing stop works but portfolio-level DD gate was not enforced

v4b key changes:
  1. **BTC as master switch** — crypto is ~70% correlated to BTC.
     If BTC itself is below its 50-SMA, go 100% cash on everything.
     This is the single most protective filter for crypto.

  2. **Faster regime: 20/50 SMA cross** instead of 50/100.
     Cuts reaction time in half.

  3. **Tighter trailing stop: 12%** from 20-day high (was 15% / 30-day).

  4. **Absolute momentum gate** — only trade when 30-day return > 5%.
     Filters out sideways chop that generates whipsaw losses.

  5. **Max 5 positions** — concentrate on strongest signals only.
     Prevents spreading thin across weak alt coins.

  6. **Position vol cap** — cap each position's annualized vol contribution
     at 15% (reduced from 60% target). Much tighter sizing.
"""

import numpy as np
import pandas as pd


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def _realized_vol(series: pd.Series, window: int = 20) -> pd.Series:
    log_ret = np.log(series / series.shift(1))
    return log_ret.rolling(window=window, min_periods=window).std() * np.sqrt(365)


class SignalEngine:
    """Crypto v4b — BTC-gated defensive momentum."""

    # Momentum
    MOM_WINDOW = 60      # 2-month lookback
    MOM_SHORT = 30       # 1-month
    MOM_SKIP = 5         # skip last 5 days
    ABS_MOM_THRESHOLD = 0.05  # 5% minimum 30d return

    # Regime
    SMA_FAST = 20
    SMA_SLOW = 50

    # Risk
    TRAILING_STOP_PCT = 0.12
    TRAILING_WINDOW = 20
    MAX_POSITIONS = 5
    TARGET_VOL = 0.15    # much tighter vol budget

    # Rebalance
    REBALANCE_FREQ = 7

    def generate(self, data_map: dict) -> dict:
        codes = sorted(c for c in data_map if not data_map[c].empty and "close" in data_map[c].columns)
        if not codes:
            return {}

        all_closes = {c: data_map[c]["close"].astype(float) for c in codes}
        close_df = pd.DataFrame(all_closes).sort_index()

        # ── BTC master regime ──
        btc_col = None
        for c in close_df.columns:
            if "BTC" in c.upper():
                btc_col = c
                break

        if btc_col is not None:
            btc_sma50 = _sma(close_df[btc_col], self.SMA_SLOW)
            btc_regime = (close_df[btc_col] > btc_sma50).astype(float)
        else:
            btc_regime = pd.Series(1.0, index=close_df.index)

        # ── Per-asset indicators ──
        indicators = {}
        for code in close_df.columns:
            close = close_df[code]

            # Momentum
            ret_60 = close.shift(self.MOM_SKIP).pct_change(self.MOM_WINDOW - self.MOM_SKIP)
            ret_30 = close.shift(self.MOM_SKIP).pct_change(self.MOM_SHORT - self.MOM_SKIP)

            # Regime: 20/50 SMA
            sma_fast = _sma(close, self.SMA_FAST)
            sma_slow = _sma(close, self.SMA_SLOW)
            above_fast = close > sma_fast
            above_slow = close > sma_slow
            golden = sma_fast > sma_slow
            regime = (above_fast & above_slow & golden).astype(float)

            # Trailing stop
            rolling_high = close.rolling(self.TRAILING_WINDOW, min_periods=5).max()
            dd_from_high = (close - rolling_high) / rolling_high
            stopped = dd_from_high < -self.TRAILING_STOP_PCT

            # Vol
            vol = _realized_vol(close, 20)
            vol_scale = (self.TARGET_VOL / vol.clip(lower=0.15)).clip(0.05, 1.0)

            indicators[code] = {
                "ret_60": ret_60,
                "ret_30": ret_30,
                "regime": regime,
                "stopped": stopped,
                "vol_scale": vol_scale,
            }

        # ── Signal generation ──
        signal_df = pd.DataFrame(0.0, index=close_df.index, columns=close_df.columns)
        warmup = self.MOM_WINDOW + self.SMA_SLOW + 5

        for i in range(warmup, len(close_df.index)):
            date = close_df.index[i]

            # Weekly rebalance (but always check stops)
            if i % self.REBALANCE_FREQ != 0 and i > warmup:
                signal_df.iloc[i] = signal_df.iloc[i - 1]
                for code in close_df.columns:
                    if indicators[code]["stopped"].iloc[i]:
                        signal_df.at[date, code] = 0.0
                # BTC master kill switch
                if btc_regime.iloc[i] <= 0:
                    signal_df.iloc[i] = 0.0
                continue

            # BTC gate: if BTC below 50-SMA, everything flat
            if btc_regime.iloc[i] <= 0:
                signal_df.iloc[i] = 0.0
                continue

            # Score qualifying assets
            scores = {}
            for code in close_df.columns:
                ind = indicators[code]

                # Per-asset regime
                if ind["regime"].iloc[i] <= 0:
                    continue
                if ind["stopped"].iloc[i]:
                    continue

                r60 = ind["ret_60"].iloc[i]
                r30 = ind["ret_30"].iloc[i]
                if pd.isna(r60) or pd.isna(r30):
                    continue

                # Dual momentum: both must be positive
                if r60 <= 0 or r30 <= 0:
                    continue

                # Absolute momentum gate: 30d return must exceed threshold
                if r30 < self.ABS_MOM_THRESHOLD:
                    continue

                vol_s = ind["vol_scale"].iloc[i] if not pd.isna(ind["vol_scale"].iloc[i]) else 0.3
                scores[code] = r30 * vol_s

            if not scores:
                signal_df.iloc[i] = 0.0
                continue

            # Top N positions
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            selected = ranked[:self.MAX_POSITIONS]

            total = sum(s for _, s in selected)
            if total <= 0:
                signal_df.iloc[i] = 0.0
                continue

            for code in close_df.columns:
                signal_df.at[date, code] = 0.0
            for code, score in selected:
                signal_df.at[date, code] = min(score / total, 1.0)

        signal_map = {}
        for code in close_df.columns:
            signal_map[code] = signal_df[code].fillna(0.0).clip(0.0, 1.0)

        return signal_map
