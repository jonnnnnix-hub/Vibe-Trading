"""
Multi-Factor Momentum + Mean Reversion Signal Engine
=====================================================

Combines three alpha signals into a composite long/short score:

1. **Dual SMA Crossover** (trend-following)
   - Long when SMA(20) > SMA(50), short when SMA(20) < SMA(50)
   - Weight: 0.4

2. **RSI Mean Reversion** (counter-trend)
   - Long when RSI(14) < 30 (oversold), short when RSI(14) > 70 (overbought)
   - Neutral between 30-70
   - Weight: 0.3

3. **MACD Histogram** (momentum confirmation)
   - Long when MACD histogram > 0 and rising, short when < 0 and falling
   - Weight: 0.3

Position sizing: composite score in [-1, +1] per symbol.
"""

import numpy as np
import pandas as pd


def _sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=window, min_periods=window).mean()


def _ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


def _macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, signal line, and histogram."""
    fast_ema = _ema(series, fast)
    slow_ema = _ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


class SignalEngine:
    """Multi-factor signal engine for US equity backtest."""

    # Signal weights
    W_SMA = 0.40
    W_RSI = 0.30
    W_MACD = 0.30

    # Parameters
    SMA_FAST = 20
    SMA_SLOW = 50
    RSI_PERIOD = 14
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70

    def generate(self, data_map: dict) -> dict:
        """Generate composite signal for each symbol.

        Args:
            data_map: {code: DataFrame with OHLCV columns}.

        Returns:
            {code: pd.Series of signal weights in [-1, 1]}.
        """
        signal_map = {}
        for code, df in data_map.items():
            if df.empty or "close" not in df.columns:
                continue
            close = df["close"].astype(float)
            if len(close) < self.SMA_SLOW + 5:
                # Not enough data for indicators
                signal_map[code] = pd.Series(0.0, index=df.index)
                continue

            # --- Signal 1: Dual SMA crossover ---
            sma_fast = _sma(close, self.SMA_FAST)
            sma_slow = _sma(close, self.SMA_SLOW)
            # Continuous signal: normalized distance between SMAs
            sma_spread = (sma_fast - sma_slow) / sma_slow
            # Clip to [-1, 1] with a scaling factor
            sma_signal = (sma_spread * 20).clip(-1.0, 1.0)

            # --- Signal 2: RSI mean reversion ---
            rsi = _rsi(close, self.RSI_PERIOD)
            rsi_signal = pd.Series(0.0, index=df.index)
            # Oversold → long (scale: 0 to +1 as RSI goes from 30 to 0)
            oversold_mask = rsi < self.RSI_OVERSOLD
            rsi_signal[oversold_mask] = (self.RSI_OVERSOLD - rsi[oversold_mask]) / self.RSI_OVERSOLD
            # Overbought → short (scale: 0 to -1 as RSI goes from 70 to 100)
            overbought_mask = rsi > self.RSI_OVERBOUGHT
            rsi_signal[overbought_mask] = -(rsi[overbought_mask] - self.RSI_OVERBOUGHT) / (100 - self.RSI_OVERBOUGHT)

            # --- Signal 3: MACD histogram momentum ---
            _, _, histogram = _macd(close)
            hist_diff = histogram.diff()  # rising or falling histogram
            # Normalize: histogram direction + magnitude
            hist_std = histogram.rolling(50, min_periods=20).std().replace(0, np.nan)
            macd_signal = (histogram / hist_std).clip(-1.0, 1.0).fillna(0.0)
            # Boost when histogram and its direction agree
            direction_agreement = np.sign(histogram) * np.sign(hist_diff)
            macd_signal = macd_signal * (0.7 + 0.3 * direction_agreement.clip(0, 1))

            # --- Composite signal ---
            composite = (
                self.W_SMA * sma_signal.fillna(0.0)
                + self.W_RSI * rsi_signal.fillna(0.0)
                + self.W_MACD * macd_signal.fillna(0.0)
            )

            # Apply a threshold: only trade when conviction is high enough
            composite[composite.abs() < 0.05] = 0.0

            signal_map[code] = composite

        return signal_map
