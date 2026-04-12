"""
HK Equities v4b — HSI-Gated Defensive Momentum
=================================================

Applies the same regime-gate architecture that turned crypto from -48%
to +152% (v4b), adapted for Hong Kong equities:

  BTC gate (crypto)  →  HSI gate (HK)
  -----------------------------------------
  BTC > 50-SMA       →  Tracker Fund (2800.HK) > 50-SMA
  All crypto flat     →  All HK stocks flat when HSI is weak

Why HSI gate works for HK:
  - HK stocks are ~80% correlated to the Hang Seng Index
  - The 2022 HK bear saw HSI drop from 23K to 14.6K (-36%)
  - The 2023-2025 recovery was uneven — HSI above/below 50-SMA
    provided a cleaner entry/exit signal than per-stock 200-SMA

Additional v4b features ported from crypto:
  - Faster 20/50 SMA cross per stock (was 200-SMA in v3)
  - 12% trailing stop from 20-day high
  - Max 7 positions (HK has 15 names, more liquid than crypto)
  - Inverse-vol sizing (20% annualized vol target, higher than crypto's 15%)
  - Weekly rebalance with intra-week stop enforcement
  - Dual 60/30-day momentum with 5-day skip
  - 5% absolute momentum gate

The HSI proxy is included in the data via 2800.HK (Tracker Fund of HK).
The signal engine detects it by ticker and uses it as the master switch
without trading it.
"""

import numpy as np
import pandas as pd


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def _realized_vol(series: pd.Series, window: int = 20) -> pd.Series:
    log_ret = np.log(series / series.shift(1))
    return log_ret.rolling(window=window, min_periods=window).std() * np.sqrt(252)


class SignalEngine:
    """HK equities with HSI-gated regime filter."""

    # Momentum
    MOM_LONG = 60        # 2-month
    MOM_SHORT = 30       # 1-month
    MOM_SKIP = 5         # skip last week
    ABS_MOM_THRESHOLD = 0.05  # 5% min 30d return

    # Regime
    SMA_FAST = 20
    SMA_SLOW = 50
    HSI_GATE_SMA = 50    # HSI must be above its 50-SMA

    # Risk
    TRAILING_STOP_PCT = 0.12
    TRAILING_WINDOW = 20
    MAX_POSITIONS = 7
    TARGET_VOL = 0.20    # slightly higher than crypto (HK less volatile)

    # Rebalance
    REBALANCE_FREQ = 5   # weekly (5 trading days)

    # HSI proxy ticker
    HSI_PROXY = "2800.HK"

    def generate(self, data_map: dict) -> dict:
        codes = sorted(c for c in data_map
                       if not data_map[c].empty and "close" in data_map[c].columns)
        if not codes:
            return {}

        all_closes = {c: data_map[c]["close"].astype(float) for c in codes}
        close_df = pd.DataFrame(all_closes).sort_index()

        # ── HSI master regime ──
        hsi_col = None
        for c in close_df.columns:
            if self.HSI_PROXY.upper() in c.upper() or "2800" in c:
                hsi_col = c
                break

        if hsi_col is not None:
            hsi_sma = _sma(close_df[hsi_col], self.HSI_GATE_SMA)
            hsi_regime = (close_df[hsi_col] > hsi_sma).astype(float)
        else:
            # Fallback: no gate (shouldn't happen if config includes 2800.HK)
            hsi_regime = pd.Series(1.0, index=close_df.index)

        # Tradeable codes: everything except the HSI proxy
        trade_codes = [c for c in close_df.columns if c != hsi_col]

        # ── Per-asset indicators ──
        indicators = {}
        for code in trade_codes:
            close = close_df[code]

            # Momentum
            ret_long = close.shift(self.MOM_SKIP).pct_change(self.MOM_LONG - self.MOM_SKIP)
            ret_short = close.shift(self.MOM_SKIP).pct_change(self.MOM_SHORT - self.MOM_SKIP)

            # Per-stock regime: 20/50 SMA
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

            # Volatility
            vol = _realized_vol(close, 20)
            vol_scale = (self.TARGET_VOL / vol.clip(lower=0.10)).clip(0.05, 1.0)

            indicators[code] = {
                "ret_long": ret_long,
                "ret_short": ret_short,
                "regime": regime,
                "stopped": stopped,
                "vol_scale": vol_scale,
            }

        # ── Signal generation ──
        signal_df = pd.DataFrame(0.0, index=close_df.index, columns=close_df.columns)
        warmup = self.MOM_LONG + self.SMA_SLOW + 5

        for i in range(warmup, len(close_df.index)):
            date = close_df.index[i]

            # Weekly rebalance (but always enforce stops + HSI gate)
            if i % self.REBALANCE_FREQ != 0 and i > warmup:
                signal_df.iloc[i] = signal_df.iloc[i - 1]
                # Enforce stops
                for code in trade_codes:
                    if indicators[code]["stopped"].iloc[i]:
                        signal_df.at[date, code] = 0.0
                # HSI kill switch
                if hsi_regime.iloc[i] <= 0:
                    signal_df.iloc[i] = 0.0
                continue

            # HSI gate: if HSI below 50-SMA, everything flat
            if hsi_regime.iloc[i] <= 0:
                signal_df.iloc[i] = 0.0
                continue

            # Score qualifying stocks
            scores = {}
            for code in trade_codes:
                ind = indicators[code]

                # Per-stock regime
                if ind["regime"].iloc[i] <= 0:
                    continue
                if ind["stopped"].iloc[i]:
                    continue

                rl = ind["ret_long"].iloc[i]
                rs = ind["ret_short"].iloc[i]
                if pd.isna(rl) or pd.isna(rs):
                    continue

                # Dual momentum: both positive
                if rl <= 0 or rs <= 0:
                    continue

                # Absolute momentum gate
                if rs < self.ABS_MOM_THRESHOLD:
                    continue

                vol_s = ind["vol_scale"].iloc[i] if not pd.isna(ind["vol_scale"].iloc[i]) else 0.3
                scores[code] = rs * vol_s

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

        # Always zero-signal the HSI proxy (don't trade the index)
        if hsi_col and hsi_col in signal_df.columns:
            signal_df[hsi_col] = 0.0

        signal_map = {}
        for code in close_df.columns:
            signal_map[code] = signal_df[code].fillna(0.0).clip(0.0, 1.0)

        return signal_map
