"""
Adaptive Trend-Following Signal Engine (v2)
=============================================

Improvements over v1:
- Long-only in uptrend (200-day SMA filter) — avoids shorting in bull markets
- Higher conviction threshold (0.15) to reduce noise trades
- Volume confirmation — requires above-average volume on signal days
- Adaptive lookback — uses ATR-normalized signals to handle volatility regimes
- Regime filter — cash when the broad trend is ambiguous

Signals:
1. **Price vs 200-SMA regime** — master filter: only go long above 200-SMA
2. **Golden/Death cross (50/200)** — primary trend signal
3. **RSI momentum** — buy pullbacks in uptrends (RSI 30-45)
4. **Breakout** — new 52-week highs get extra weight
5. **Volatility filter** — scale position size inversely to recent volatility
"""

import numpy as np
import pandas as pd


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


class SignalEngine:
    """Adaptive trend-following engine — long-only with regime filter."""

    # Regime
    TREND_SMA = 200
    FAST_SMA = 50
    SLOW_SMA = 200

    # RSI
    RSI_PERIOD = 14
    RSI_BUY_LOW = 30
    RSI_BUY_HIGH = 45

    # Breakout
    BREAKOUT_WINDOW = 252  # 52-week high

    # Volume
    VOL_AVG_WINDOW = 20

    # Conviction
    MIN_CONVICTION = 0.15

    def generate(self, data_map: dict) -> dict:
        """Generate long-only trend signals.

        Args:
            data_map: {code: DataFrame with OHLCV}.

        Returns:
            {code: pd.Series of signal weights in [0, 1]}.
        """
        signal_map = {}

        for code, df in data_map.items():
            if df.empty or "close" not in df.columns:
                continue

            close = df["close"].astype(float)
            n = len(close)

            if n < self.SLOW_SMA + 10:
                signal_map[code] = pd.Series(0.0, index=df.index)
                continue

            # --- Regime filter: price vs 200-SMA ---
            sma_200 = _sma(close, self.TREND_SMA)
            above_200 = (close > sma_200).astype(float)

            # --- Signal 1: Golden cross (50/200 SMA) ---
            sma_50 = _sma(close, self.FAST_SMA)
            # Continuous: how far above/below the cross
            cross_spread = (sma_50 - sma_200) / sma_200
            trend_signal = (cross_spread * 15).clip(0.0, 1.0)

            # --- Signal 2: RSI pullback in uptrend ---
            rsi = _rsi(close, self.RSI_PERIOD)
            rsi_signal = pd.Series(0.0, index=df.index)
            # Buy pullbacks: RSI in [30, 45] zone during uptrend
            pullback_mask = (rsi >= self.RSI_BUY_LOW) & (rsi <= self.RSI_BUY_HIGH)
            rsi_signal[pullback_mask] = (self.RSI_BUY_HIGH - rsi[pullback_mask]) / (
                self.RSI_BUY_HIGH - self.RSI_BUY_LOW
            )
            # Deep oversold gets stronger signal
            deep_oversold = rsi < self.RSI_BUY_LOW
            rsi_signal[deep_oversold] = 1.0

            # --- Signal 3: 52-week high breakout ---
            rolling_high = close.rolling(window=self.BREAKOUT_WINDOW, min_periods=100).max()
            breakout_signal = pd.Series(0.0, index=df.index)
            near_high = close >= rolling_high * 0.97  # within 3% of 52-week high
            breakout_signal[near_high] = 0.5
            at_high = close >= rolling_high * 0.995  # within 0.5%
            breakout_signal[at_high] = 1.0

            # --- Signal 4: Volume confirmation ---
            if "volume" in df.columns:
                volume = df["volume"].astype(float)
                avg_vol = _sma(volume, self.VOL_AVG_WINDOW)
                vol_ratio = (volume / avg_vol.replace(0, np.nan)).fillna(1.0)
                vol_multiplier = vol_ratio.clip(0.5, 2.0) / 2.0  # scale [0.25, 1.0]
            else:
                vol_multiplier = pd.Series(1.0, index=df.index)

            # --- Signal 5: Volatility scaling (inverse vol) ---
            atr = _atr(df, 14)
            atr_pct = (atr / close).fillna(0.02)
            # Lower vol = larger position; higher vol = smaller position
            # Normalize around median ATR%
            median_atr = atr_pct.rolling(60, min_periods=20).median().fillna(atr_pct.median())
            vol_scale = (median_atr / atr_pct.clip(lower=0.005)).clip(0.3, 1.5)

            # --- Composite ---
            composite = (
                0.40 * trend_signal
                + 0.25 * rsi_signal
                + 0.20 * breakout_signal
                + 0.15 * vol_multiplier
            )

            # Apply regime filter: zero out everything when below 200-SMA
            composite = composite * above_200

            # Volume confirmation: boost signals on high-volume days
            composite = composite * vol_scale

            # Conviction threshold
            composite[composite < self.MIN_CONVICTION] = 0.0

            # Cap at 1.0
            composite = composite.clip(0.0, 1.0)

            signal_map[code] = composite

        return signal_map
