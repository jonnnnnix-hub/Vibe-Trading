#!/usr/bin/env python3
"""Options Backtesting Engine for Vibe-Trading.

Re-implements the three strategies from autobot.py and simulates OPTIONS trades
instead of equity trades over historical OHLCV data.

Strategies:
  1. Momentum Scanner   (v5)  — score >= 3/5 conditions
  2. Expert Committee   (v9)  — 5-expert vote >= 4/5 AGREE
  3. Aggressive Momentum (v10) — same committee + hard_stop=-5%, trailing=0.8%, min_hold=2d

Data sources:
  - OHLCV:       backtest/data/ohlcv/{TICKER}.csv
  - ORATS IV:    backtest/data/orats_cores/{TICKER}.csv  (optional)

Spec requirements:
  - Strike: next $5 increment above current close price
  - T: 20 trading days / 252 (matching max hold period)
  - σ: iv30d from ORATS (in percentage, divide by 100)
  - Position sizing: $10,000 notional per trade
  - Exit logic: mirrors autobot.py check_exits() exactly
  - IV updated daily for option repricing
"""

from __future__ import annotations

import logging
import math
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm  # type: ignore

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("backtest.engine")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
OHLCV_DIR = _HERE / "data" / "ohlcv"
ORATS_DIR = _HERE / "data" / "orats_cores"
RESULTS_DIR = _HERE / "results"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STARTING_CAPITAL = 100_000.0
NOTIONAL_PER_TRADE = 10_000.0    # $10,000 per trade as per spec
RISK_FREE_RATE = 0.05             # annualised, used in Black-Scholes
DEFAULT_IV = 0.30                 # fallback if no ORATS data (30%)
# ORATS iv30d is in percentage format (e.g. 25.5 means 25.5%) → divide by 100
BACKTEST_START = date(2025, 1, 2)
BACKTEST_END   = date(2026, 4, 11)
OPTION_T_YEARS = 20 / 252         # 20 trading days / 252, per spec

# Strategy configs — mirrors autobot.py AutoBot.configure()
# v2 ADJUSTMENTS (from backtest analysis):
#   A. max_hold 20→7d  (time exits were devastating: -$694K)
#   B. option_stop_pct 30%  (cap max loss on option premium)
#   C. trailing_activation 1.5→3.0%, trailing_distance 1.0→2.0%  (stop whipsaw)
#   D. delta_range (0.40, 0.50)  (slightly OTM preference)
#   E. iv_filter: skip entry when 5-day IV trend is declining
STRATEGY_CONFIGS = {
    "momentum_scanner": {
        "target_pct":          5.0,
        "trailing_activation": 3.0,
        "trailing_distance":   2.0,
        "hard_stop_pct":       None,        # underlying hard stop (disabled)
        "option_stop_pct":     60.0,        # max loss on option premium
        "max_hold_days":       10,           # sweet spot: 7-10d
        "min_hold_days":       1,
        "delta_min":           0.30,        # slightly OTM to ATM range
        "delta_max":           0.55,
        "iv_filter":           True,        # skip if 5d IV declining >5%
        "iv_decline_threshold": -5.0,       # only filter steep IV drops
    },
    "expert_committee": {
        "target_pct":          5.0,
        "trailing_activation": 3.0,
        "trailing_distance":   2.0,
        "hard_stop_pct":       None,
        "option_stop_pct":     60.0,
        "max_hold_days":       10,
        "min_hold_days":       1,
        "delta_min":           0.30,
        "delta_max":           0.55,
        "iv_filter":           True,
        "iv_decline_threshold": -5.0,
    },
    "aggressive_momentum": {
        "target_pct":          5.0,
        "trailing_activation": 3.0,
        "trailing_distance":   2.0,
        "hard_stop_pct":       5.0,
        "option_stop_pct":     60.0,
        "max_hold_days":       10,
        "min_hold_days":       2,
        "delta_min":           0.30,
        "delta_max":           0.55,
        "iv_filter":           True,
        "iv_decline_threshold": -5.0,
    },
}

# Default watchlist from autobot.py
WATCHLIST: List[str] = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "AMD", "NFLX", "CRM",
]


# ---------------------------------------------------------------------------
# All tickers discovered in the OHLCV directory
# ---------------------------------------------------------------------------
def discover_tickers() -> List[str]:
    """Return all tickers that have an OHLCV CSV file (excluding SPY)."""
    tickers = []
    for p in OHLCV_DIR.glob("*.csv"):
        stem = p.stem
        if stem == "SPY":
            continue
        # BRK_B → BRK.B for display but we keep BRK_B as file name key
        tickers.append(stem)
    return sorted(tickers)


def ticker_to_filename(ticker: str) -> str:
    """Map ticker symbol to OHLCV filename stem (BRK.B → BRK_B)."""
    return ticker.replace(".", "_")


# ============================================================================
# Data Loading
# ============================================================================

def load_ohlcv(ticker: str) -> Optional[pd.DataFrame]:
    """Load OHLCV CSV, normalise column names, parse dates, sort ascending."""
    filename = ticker_to_filename(ticker)
    path = OHLCV_DIR / f"{filename}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["date"])
        df = df.rename(columns={
            "date": "Date", "open": "Open", "high": "High",
            "low": "Low", "close": "Close", "volume": "Volume",
        })
        df = df.set_index("Date").sort_index()
        df = df[~df.index.duplicated(keep="first")]
        return df
    except Exception as exc:
        logger.warning("Failed to load OHLCV for %s: %s", ticker, exc)
        return None


def load_orats_iv(ticker: str) -> Optional[pd.DataFrame]:
    """Load ORATS IV data indexed by tradeDate.

    iv30d is stored as percentage (e.g. 25.5 for 25.5%).
    This function returns raw values; callers should divide by 100 for BS.
    Returns None if unavailable.
    """
    filename = ticker_to_filename(ticker)
    path = ORATS_DIR / f"{filename}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["tradeDate"])
        df = df.set_index("tradeDate").sort_index()
        df = df[~df.index.duplicated(keep="first")]
        return df
    except Exception as exc:
        logger.warning("Failed to load ORATS for %s: %s", ticker, exc)
        return None


# ============================================================================
# Technical Indicators  (exact mirror of autobot.py compute_indicators)
# ============================================================================

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all required technical indicators to an OHLCV DataFrame.

    Exact mirror of autobot.py compute_indicators().
    Adds: SMA_20, SMA_50, SMA_200, EMA_9, EMA_20, EMA_50,
          RSI_14, MACD_line, MACD_signal, MACD_histogram,
          BB_lower, BB_middle, BB_upper, BB_position,
          ADX_14, ATR_14, Volume_ratio, OBV, OBV_slope_10d,
          Momentum_5d, Momentum_10d, Momentum_20d,
          Pullback_depth, Dist_EMA20, Dist_SMA50
    """
    if df is None or df.empty or len(df) < 30:
        return df

    df = df.copy()
    close  = df["Close"]
    high   = df["High"]
    low    = df["Low"]
    volume = df["Volume"]

    # ── Moving Averages ──────────────────────────────────────────────────────
    df["SMA_20"]  = close.rolling(20).mean()
    df["SMA_50"]  = close.rolling(50).mean()
    df["SMA_200"] = close.rolling(200).mean()
    df["EMA_9"]   = close.ewm(span=9,  adjust=False).mean()
    df["EMA_20"]  = close.ewm(span=20, adjust=False).mean()
    df["EMA_50"]  = close.ewm(span=50, adjust=False).mean()

    # ── RSI ─────────────────────────────────────────────────────────────────
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI_14"] = 100 - (100 / (1 + rs))

    # ── MACD (12, 26, 9) ────────────────────────────────────────────────────
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD_line"]      = ema12 - ema26
    df["MACD_signal"]    = df["MACD_line"].ewm(span=9, adjust=False).mean()
    df["MACD_histogram"] = df["MACD_line"] - df["MACD_signal"]

    # ── Bollinger Bands (20, 2) ─────────────────────────────────────────────
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df["BB_middle"]   = bb_mid
    df["BB_upper"]    = bb_mid + 2 * bb_std
    df["BB_lower"]    = bb_mid - 2 * bb_std
    band_width        = df["BB_upper"] - df["BB_lower"]
    df["BB_position"] = np.where(
        band_width > 0,
        (close - df["BB_lower"]) / band_width,
        0.5,
    )

    # ── ADX (14) ─────────────────────────────────────────────────────────────
    tr1   = high - low
    tr2   = (high - close.shift(1)).abs()
    tr3   = (low  - close.shift(1)).abs()
    tr    = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = tr.ewm(com=13, adjust=False).mean()
    df["ATR_14"] = atr14

    plus_dm  = high.diff()
    minus_dm = -low.diff()
    plus_dm  = plus_dm.where((plus_dm > minus_dm)  & (plus_dm > 0),  0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    smooth_plus  = plus_dm.ewm(com=13, adjust=False).mean()
    smooth_minus = minus_dm.ewm(com=13, adjust=False).mean()

    di_plus  = 100 * smooth_plus  / atr14.replace(0, np.nan)
    di_minus = 100 * smooth_minus / atr14.replace(0, np.nan)
    dx       = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    df["ADX_14"] = dx.ewm(com=13, adjust=False).mean()

    # ── Volume Ratio ─────────────────────────────────────────────────────────
    vol_ma20       = volume.rolling(20).mean()
    df["Volume_ratio"] = volume / vol_ma20.replace(0, np.nan)

    # ── OBV ──────────────────────────────────────────────────────────────────
    direction         = np.sign(close.diff()).fillna(0)
    df["OBV"]         = (direction * volume).cumsum()
    df["OBV_slope_10d"] = df["OBV"].diff(10)

    # ── Momentum ─────────────────────────────────────────────────────────────
    df["Momentum_5d"]  = close.pct_change(5)  * 100
    df["Momentum_10d"] = close.pct_change(10) * 100
    df["Momentum_20d"] = close.pct_change(20) * 100

    # ── Pullback depth (% from 20-day rolling high) ───────────────────────────
    rolling_high      = close.rolling(20).max()
    df["Pullback_depth"] = ((close - rolling_high) / rolling_high) * 100

    # ── Distance from MAs ────────────────────────────────────────────────────
    df["Dist_EMA20"] = ((close - df["EMA_20"]) / df["EMA_20"]) * 100
    df["Dist_SMA50"] = ((close - df["SMA_50"]) / df["SMA_50"]) * 100

    return df


# ============================================================================
# Strategy Signal Functions  (exact mirrors of autobot.py)
# ============================================================================

def run_momentum_scanner(row: pd.Series) -> Dict[str, Any]:
    """v5 — score-based: BUY when >= 3 of 5 conditions pass.

    Conditions (exact from autobot.py run_momentum_scanner):
      1. RSI_14 between 40 and 70
      2. close > EMA_20
      3. MACD_histogram > 0
      4. Volume_ratio >= 1.0
      5. ADX_14 >= 18
    """
    conditions = {
        "rsi_in_range":  40 <= row.get("RSI_14", np.nan) <= 70,
        "above_ema20":   row["Close"] > row.get("EMA_20", np.inf),
        "macd_positive": row.get("MACD_histogram", np.nan) > 0,
        "volume_ok":     row.get("Volume_ratio", 0) >= 1.0,
        "adx_ok":        row.get("ADX_14", 0) >= 18,
    }
    score  = sum(1 for v in conditions.values() if v)
    signal = "BUY" if score >= 3 else "NO_SIGNAL"
    return {
        "signal":     signal,
        "score":      score,
        "confidence": score / 5.0,
        "conditions": {k: bool(v) for k, v in conditions.items()},
    }


# ── Expert committee helpers (exact mirrors of autobot.py) ──────────────────

def _trend_expert(row: pd.Series) -> Tuple[str, float]:
    """Trend expert: moving-average alignment + momentum.

    AGREE:    close > EMA_20 > SMA_50  AND  Momentum_5d > 0
    DISAGREE: close < SMA_50  OR  SMA_50 < SMA_200
    ABSTAIN:  otherwise
    """
    try:
        close  = row["Close"]
        ema20  = row.get("EMA_20", np.nan)
        sma50  = row.get("SMA_50", np.nan)
        sma200 = row.get("SMA_200", np.nan)
        mom5   = row.get("Momentum_5d", np.nan)
        adx    = row.get("ADX_14", np.nan)
        dist   = row.get("Dist_EMA20", np.nan)

        if any(pd.isna([close, ema20, sma50])):
            return ("ABSTAIN", 0.5)

        # DISAGREE conditions
        if close < sma50:
            return ("DISAGREE", 0.8)
        if not pd.isna(sma200) and sma50 < sma200:
            return ("DISAGREE", 0.8)

        # AGREE conditions
        if close > ema20 and ema20 > sma50 and (pd.isna(mom5) or mom5 > 0):
            conf = 0.5
            if not pd.isna(adx):
                conf += float(np.clip((adx - 20) / 40, 0, 1)) * 0.3
            if not pd.isna(dist):
                conf += float(np.clip(dist / 3.0, 0, 1)) * 0.2
            return ("AGREE", float(np.clip(conf, 0.5, 0.95)))

        return ("ABSTAIN", 0.5)
    except Exception:
        return ("ABSTAIN", 0.5)


def _momentum_expert(row: pd.Series) -> Tuple[str, float]:
    """Momentum expert: RSI + MACD + ADX health check.

    AGREE:    RSI 40-70  AND  MACD_histogram > 0  AND  ADX >= 20
    DISAGREE: RSI > 75, RSI < 30, ADX < 15, OR (MACD_histogram <= 0 AND RSI 40-70)
    ABSTAIN:  borderline RSI / ADX
    """
    try:
        rsi    = row.get("RSI_14", np.nan)
        macd_h = row.get("MACD_histogram", np.nan)
        adx    = row.get("ADX_14", np.nan)

        if any(pd.isna([rsi, macd_h, adx])):
            return ("ABSTAIN", 0.5)

        # DISAGREE
        if rsi > 75 or rsi < 30 or adx < 15:
            return ("DISAGREE", 0.8)
        if 40 <= rsi <= 70 and macd_h <= 0:
            return ("DISAGREE", 0.6)

        # AGREE
        if 40 <= rsi <= 70 and macd_h > 0 and adx >= 20:
            rsi_c  = float(np.clip(1.0 - abs(rsi - 60) / 20, 0.3, 1.0))
            macd_c = 0.8 if macd_h > 0 else 0.5
            adx_c  = float(np.clip((adx - 20) / 30, 0, 1)) * 0.3 + 0.5
            conf   = float(np.clip(rsi_c * 0.5 + macd_c * 0.25 + adx_c * 0.25, 0.45, 0.95))
            return ("AGREE", conf)

        # Borderline / ABSTAIN
        return ("ABSTAIN", 0.5)
    except Exception:
        return ("ABSTAIN", 0.5)


def _mean_reversion_expert(row: pd.Series) -> Tuple[str, float]:
    """Mean-reversion expert: Bollinger Band position + pullback depth.

    AGREE:    BB_position 0.2-0.7  AND  Pullback_depth -8% to -0.5%  AND  RSI >= 35
    DISAGREE: BB_position > 0.95, Pullback_depth < -12%, RSI < 35
    ABSTAIN:  otherwise
    """
    try:
        bb_pos   = row.get("BB_position", np.nan)
        pullback = row.get("Pullback_depth", np.nan)
        rsi      = row.get("RSI_14", np.nan)

        if any(pd.isna([bb_pos, pullback, rsi])):
            return ("ABSTAIN", 0.5)

        # DISAGREE
        if bb_pos > 0.95 or pullback < -12 or rsi < 35:
            return ("DISAGREE", 0.8)

        # AGREE
        if 0.2 <= bb_pos <= 0.7 and -8 <= pullback <= -0.5 and rsi >= 35:
            bb_c = float(np.clip(1.0 - abs(bb_pos - 0.4) / 0.3, 0, 1))
            pd_c = float(np.clip(1.0 - abs(pullback - (-3.0)) / 7.5, 0, 1))
            conf = float(np.clip(bb_c * 0.55 + pd_c * 0.45, 0.45, 0.92))
            return ("AGREE", conf)

        return ("ABSTAIN", 0.5)
    except Exception:
        return ("ABSTAIN", 0.5)


def _volume_expert(row: pd.Series) -> Tuple[str, float]:
    """Volume expert: volume ratio + OBV slope (accumulation signal).

    AGREE:    Volume_ratio > 1.2  AND  OBV_slope_10d >= 0
    DISAGREE: Volume_ratio < 0.5  OR  OBV_slope_10d < 0
    ABSTAIN:  medium volume (0.5-1.2)
    """
    try:
        vol_r  = row.get("Volume_ratio", np.nan)
        obv_sl = row.get("OBV_slope_10d", np.nan)

        if pd.isna(vol_r):
            return ("ABSTAIN", 0.5)

        # DISAGREE
        if vol_r < 0.5:
            return ("DISAGREE", 0.8)
        if not pd.isna(obv_sl) and obv_sl < 0:
            return ("DISAGREE", 0.7)

        # AGREE
        if vol_r > 1.2 and (pd.isna(obv_sl) or obv_sl >= 0):
            conf = float(np.clip((vol_r - 1.2) / (3.0 - 1.2), 0, 1)) * 0.4 + 0.5
            if not pd.isna(obv_sl) and obv_sl > 0:
                conf = min(conf + 0.05, 0.92)
            return ("AGREE", float(conf))

        return ("ABSTAIN", 0.5)
    except Exception:
        return ("ABSTAIN", 0.5)


def _macro_expert(spy_row: Optional[pd.Series]) -> Tuple[str, float]:
    """Macro expert: market regime gating via SPY trend.

    AGREE:    SPY > SMA_50 > SMA_200  (uptrend, green)
    DISAGREE: SPY < SMA_50 and SMA_50 < SMA_200  (downtrend, red)
    ABSTAIN:  mixed signals (yellow)
    """
    try:
        if spy_row is None or spy_row.empty:
            return ("ABSTAIN", 0.5)

        spy_close  = spy_row.get("Close", np.nan)
        spy_sma50  = spy_row.get("SMA_50", np.nan)
        spy_sma200 = spy_row.get("SMA_200", np.nan)

        if pd.isna(spy_close) or pd.isna(spy_sma50):
            return ("ABSTAIN", 0.5)

        # Green regime
        if spy_close > spy_sma50 and (pd.isna(spy_sma200) or spy_sma50 > spy_sma200):
            return ("AGREE", 0.9)

        # Red regime
        if spy_close < spy_sma50 and not pd.isna(spy_sma200) and spy_sma50 < spy_sma200:
            return ("DISAGREE", 0.9)

        # Yellow / pullback — still above SMA50
        if spy_close > spy_sma50:
            return ("AGREE", 0.7)

        return ("ABSTAIN", 0.5)
    except Exception:
        return ("ABSTAIN", 0.5)


def run_expert_committee(
    row: pd.Series,
    spy_row: Optional[pd.Series],
    threshold: int = 4,
) -> Dict[str, Any]:
    """v9 / v10 — 5-expert vote; BUY when >= threshold experts AGREE.

    Exact mirror of autobot.py run_expert_committee().
    """
    trend_vote,    trend_conf    = _trend_expert(row)
    momentum_vote, momentum_conf = _momentum_expert(row)
    mean_rev_vote, mean_rev_conf = _mean_reversion_expert(row)
    volume_vote,   volume_conf   = _volume_expert(row)
    macro_vote,    macro_conf    = _macro_expert(spy_row)

    votes = [trend_vote, momentum_vote, mean_rev_vote, volume_vote, macro_vote]
    confs = [trend_conf, momentum_conf, mean_rev_conf, volume_conf, macro_conf]

    agree_count = votes.count("AGREE")
    agree_confs = [c for v, c in zip(votes, confs) if v == "AGREE"]
    avg_conf    = float(np.mean(agree_confs)) if agree_confs else 0.0

    signal = "BUY" if agree_count >= threshold else "NO_SIGNAL"

    return {
        "signal":      signal,
        "agree_count": agree_count,
        "threshold":   threshold,
        "confidence":  round(avg_conf, 4),
        "avg_confidence": round(avg_conf, 4),
        "experts": {
            "trend":          {"vote": trend_vote,    "confidence": round(trend_conf, 4)},
            "momentum":       {"vote": momentum_vote, "confidence": round(momentum_conf, 4)},
            "mean_reversion": {"vote": mean_rev_vote, "confidence": round(mean_rev_conf, 4)},
            "volume":         {"vote": volume_vote,   "confidence": round(volume_conf, 4)},
            "macro":          {"vote": macro_vote,    "confidence": round(macro_conf, 4)},
        },
    }


# ============================================================================
# Black-Scholes Option Pricing
# ============================================================================

def black_scholes_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """European call price via Black-Scholes.

    C = S*N(d1) - K*e^(-rT)*N(d2)

    Args:
        S:     Underlying price
        K:     Strike price
        T:     Time to expiry in years
        r:     Risk-free rate (annualised)
        sigma: Implied volatility (annualised, as fraction, e.g. 0.25 for 25%)

    Returns:
        Call option price.  Returns intrinsic value if T <= 0.
    """
    if T <= 0:
        return max(0.0, S - K)
    if sigma <= 0 or sigma > 20:  # guard against bad IV
        sigma = DEFAULT_IV
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        return max(0.0, float(price))
    except Exception:
        return max(0.0, S - K)


def black_scholes_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Delta (dC/dS) for a European call via Black-Scholes."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    if sigma > 20:
        sigma = DEFAULT_IV
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        return float(norm.cdf(d1))
    except Exception:
        return 0.5


def select_strike(underlying_price: float) -> float:
    """Next $5 increment above current close price (spec: slightly OTM call).

    Per spec: strike = next $5 increment above current price (for calls).
    """
    return math.ceil(underlying_price / 5.0) * 5.0


def get_iv_for_date(
    orats_df: Optional[pd.DataFrame],
    trade_date: date,
    last_known: Optional[float] = None,
) -> float:
    """Look up iv30d from ORATS for the given date.

    iv30d is in percentage format (e.g. 25.5 for 25.5%), so we divide by 100.
    Falls back to most-recent prior date (forward-fill), then last_known, then DEFAULT_IV.
    """
    if orats_df is None or orats_df.empty:
        return last_known if last_known is not None else DEFAULT_IV

    ts = pd.Timestamp(trade_date)

    # Exact match
    if ts in orats_df.index:
        iv_raw = orats_df.loc[ts, "iv30d"]
        if not pd.isna(iv_raw) and iv_raw > 0:
            return float(iv_raw) / 100.0

    # Most recent prior date (forward-fill)
    prior = orats_df[orats_df.index <= ts]
    if not prior.empty:
        iv_raw = prior["iv30d"].iloc[-1]
        if not pd.isna(iv_raw) and iv_raw > 0:
            return float(iv_raw) / 100.0

    return last_known if last_known is not None else DEFAULT_IV


def get_iv_trend_5d(
    orats_df: Optional[pd.DataFrame],
    trade_date: date,
) -> Optional[float]:
    """Compute 5-day IV trend (change in iv30d over last 5 trading days).

    Returns positive if IV is rising, negative if falling, None if insufficient data.
    Used by the IV filter (adjustment E) to skip entries when IV is declining.
    """
    if orats_df is None or orats_df.empty:
        return None

    ts = pd.Timestamp(trade_date)
    prior = orats_df[orats_df.index <= ts]
    if len(prior) < 5:
        return None

    recent = prior.tail(5)
    iv_start = recent["iv30d"].iloc[0]
    iv_end   = recent["iv30d"].iloc[-1]

    if pd.isna(iv_start) or pd.isna(iv_end) or iv_start <= 0:
        return None

    # Return percentage change in IV over 5 days
    return float((iv_end - iv_start) / iv_start * 100)


# ============================================================================
# Position Tracking
# ============================================================================

class OptionPosition:
    """Tracks a single open options position."""

    __slots__ = (
        "symbol", "strategy", "entry_date", "underlying_entry",
        "strike", "entry_T", "iv_at_entry", "current_iv",
        "option_entry_price", "num_contracts", "cost_basis",
        "peak_underlying", "trailing_active",
        "days_held", "signal_confidence", "signal_details",
    )

    def __init__(
        self,
        symbol: str,
        strategy: str,
        entry_date: date,
        underlying_entry: float,
        strike: float,
        entry_T: float,
        iv_at_entry: float,
        option_entry_price: float,
        num_contracts: float,
        signal_confidence: float,
        signal_details: Dict[str, Any],
    ) -> None:
        self.symbol             = symbol
        self.strategy           = strategy
        self.entry_date         = entry_date
        self.underlying_entry   = underlying_entry
        self.strike             = strike
        self.entry_T            = entry_T
        self.iv_at_entry        = iv_at_entry
        self.current_iv         = iv_at_entry
        self.option_entry_price = option_entry_price
        self.num_contracts      = num_contracts
        self.cost_basis         = option_entry_price * num_contracts * 100
        self.peak_underlying    = underlying_entry
        self.trailing_active    = False
        self.days_held          = 0
        self.signal_confidence  = signal_confidence
        self.signal_details     = signal_details

    def remaining_T(self) -> float:
        """Remaining time to expiry in years (decreasing by trading day)."""
        return max(0.0, self.entry_T - self.days_held / 252.0)

    def reprice(self, current_underlying: float, updated_iv: Optional[float] = None) -> float:
        """Re-price the option using current underlying, remaining T, and updated IV."""
        iv = updated_iv if updated_iv is not None else self.current_iv
        T  = self.remaining_T()
        return black_scholes_call(current_underlying, self.strike, T, RISK_FREE_RATE, iv)


# ============================================================================
# Core Backtest Engine
# ============================================================================

class OptionsBacktestEngine:
    """Day-by-day options backtest engine.

    Usage::
        engine = OptionsBacktestEngine("expert_committee", watchlist=[...])
        results = engine.run()
    """

    def __init__(
        self,
        strategy_name: str,
        watchlist: Optional[List[str]] = None,
        starting_capital: float = STARTING_CAPITAL,
        notional_per_trade: float = NOTIONAL_PER_TRADE,
    ) -> None:
        if strategy_name not in STRATEGY_CONFIGS:
            raise ValueError(
                f"Unknown strategy '{strategy_name}'. "
                f"Choose from: {list(STRATEGY_CONFIGS)}"
            )
        self.strategy_name      = strategy_name
        self.cfg                = STRATEGY_CONFIGS[strategy_name]
        self.watchlist          = watchlist or WATCHLIST
        self.starting_capital   = starting_capital
        self.notional_per_trade = notional_per_trade

        # State
        self.portfolio_cash   = starting_capital
        self.open_positions: Dict[str, OptionPosition] = {}   # symbol -> pos
        self.closed_trades:  List[Dict[str, Any]] = []
        self.all_signals:    List[Dict[str, Any]] = []
        self.equity_curve:   List[Tuple[date, float]] = []
        self.daily_returns:  List[float] = []

        # Data caches
        self._ohlcv: Dict[str, Optional[pd.DataFrame]] = {}
        self._orats: Dict[str, Optional[pd.DataFrame]] = {}

    # ── Data helpers ─────────────────────────────────────────────────────────

    def _get_ohlcv(self, ticker: str) -> Optional[pd.DataFrame]:
        if ticker not in self._ohlcv:
            df = load_ohlcv(ticker)
            if df is not None:
                df = compute_indicators(df)
            self._ohlcv[ticker] = df
        return self._ohlcv[ticker]

    def _get_orats(self, ticker: str) -> Optional[pd.DataFrame]:
        if ticker not in self._orats:
            self._orats[ticker] = load_orats_iv(ticker)
        return self._orats[ticker]

    def _row_for_date(self, ticker: str, d: date) -> Optional[pd.Series]:
        """Return the OHLCV+indicator row for a given date (exact match)."""
        df = self._get_ohlcv(ticker)
        if df is None:
            return None
        ts = pd.Timestamp(d)
        if ts in df.index:
            return df.loc[ts]
        return None

    def _portfolio_value(self, current_date: date) -> float:
        """Total portfolio value = cash + sum of current option market values."""
        total = self.portfolio_cash
        for pos in self.open_positions.values():
            row = self._row_for_date(pos.symbol, current_date)
            underlying = float(row["Close"]) if row is not None else pos.underlying_entry
            opt_price  = pos.reprice(underlying)
            total += opt_price * pos.num_contracts * 100
        return total

    # ── Signal generation ────────────────────────────────────────────────────

    def _generate_signal(
        self,
        symbol: str,
        row: pd.Series,
        spy_row: Optional[pd.Series],
    ) -> Dict[str, Any]:
        """Generate signal for a single symbol on a given day."""
        if self.strategy_name == "momentum_scanner":
            return run_momentum_scanner(row)
        else:  # expert_committee or aggressive_momentum
            return run_expert_committee(row, spy_row, threshold=4)

    # ── Exit logic (mirrors autobot.py check_exits() exactly) ───────────────

    def _check_exit(
        self,
        pos: OptionPosition,
        current_underlying: float,
    ) -> Optional[str]:
        """Return exit reason string if position should be closed, else None.

        Priority order (v2 — updated from backtest analysis):
          0.   Min hold period gate
          0.25 Option premium stop (new — -30% on option value)
          0.5  Hard stop (on underlying % move)
          1-2  Trailing activation + trigger (on underlying % move)
          3.   Target profit (on underlying % move)
          4.   Time exit at max_hold_days (now 7d, was 20d)
        """
        cfg = self.cfg
        pnl_pct = ((current_underlying - pos.underlying_entry) / pos.underlying_entry) * 100

        # Step 0: Min hold period — skip all exits
        if pos.days_held < cfg["min_hold_days"]:
            return None

        # Step 0.25: Option premium stop (NEW in v2)
        # Caps max loss per trade based on option price, not underlying move
        option_stop = cfg.get("option_stop_pct")
        if option_stop is not None:
            current_opt_price = pos.reprice(current_underlying)
            opt_pnl_pct = ((current_opt_price - pos.option_entry_price) / pos.option_entry_price) * 100
            if opt_pnl_pct <= -abs(option_stop):
                return "option_stop"

        # Step 0.5: Hard stop (on underlying)
        if cfg["hard_stop_pct"] is not None:
            if pnl_pct <= -abs(cfg["hard_stop_pct"]):
                return "hard_stop"

        # Step 1: Update peak underlying
        if current_underlying > pos.peak_underlying:
            pos.peak_underlying = current_underlying

        # Step 2: Trailing activation (state transition)
        peak_pnl_pct = ((pos.peak_underlying - pos.underlying_entry) / pos.underlying_entry) * 100
        if not pos.trailing_active and peak_pnl_pct >= cfg["trailing_activation"]:
            pos.trailing_active = True

        # Step 3: Trailing stop trigger (on underlying)
        if pos.trailing_active:
            trail_level = pos.peak_underlying * (1 - cfg["trailing_distance"] / 100)
            if current_underlying <= trail_level:
                return "trailing_stop"

        # Step 4: Target profit (on underlying)
        if pnl_pct >= cfg["target_pct"]:
            return "target_profit"

        # Step 5: Time exit
        if pos.days_held >= cfg["max_hold_days"]:
            return "time_exit"

        return None

    # ── Trade entry ──────────────────────────────────────────────────────────

    def _enter_trade(
        self,
        symbol: str,
        entry_date: date,
        entry_close: float,
        signal_result: Dict[str, Any],
    ) -> Optional[OptionPosition]:
        """Size and open an option position per the spec (v2 with filters).

        Per spec + v2 adjustments:
          - Strike: next $5 increment above current close
          - T: 20 trading days / 252
          - σ: iv30d from ORATS / 100 (or DEFAULT_IV)
          - Position sizing: $10,000 notional
          - NEW (E): IV filter — skip if 5-day IV trend is declining
          - NEW (D): Delta filter — skip if delta outside 0.40-0.50 range
        """
        # IV from ORATS
        orats = self._get_orats(symbol)
        iv    = get_iv_for_date(orats, entry_date)

        # ── Adjustment E: IV trend filter ─────────────────────────────────────
        if self.cfg.get("iv_filter", False):
            iv_threshold = self.cfg.get("iv_decline_threshold", -3.0)
            iv_trend = get_iv_trend_5d(orats, entry_date)
            if iv_trend is not None and iv_trend < iv_threshold:
                return None  # Skip entry when IV is declining sharply

        # Strike selection: next $5 above close
        strike = select_strike(entry_close)

        # Fixed T per spec: 20 trading days / 252
        T = OPTION_T_YEARS

        # Black-Scholes entry price (per-share)
        raw_opt = black_scholes_call(entry_close, strike, T, RISK_FREE_RATE, iv)
        if raw_opt < 0.01:
            # Option is near-worthless (deep OTM or very low IV); skip
            return None

        # Delta
        delta = black_scholes_delta(entry_close, strike, T, RISK_FREE_RATE, iv)

        # ── Adjustment D: Delta filter — slightly OTM preference ─────────────
        delta_min = self.cfg.get("delta_min", 0.0)
        delta_max = self.cfg.get("delta_max", 1.0)
        if delta < delta_min or delta > delta_max:
            return None  # Skip if delta outside target range

        # Position sizing: $10,000 notional
        # Each contract = 100 shares
        # num_contracts = floor(10000 / (premium * 100))
        premium_per_contract = raw_opt * 100
        if premium_per_contract <= 0:
            return None
        num_contracts = max(1, int(self.notional_per_trade / premium_per_contract))
        cost_basis    = raw_opt * num_contracts * 100

        # Check cash availability
        if cost_basis > self.portfolio_cash:
            # Scale down to available cash
            num_contracts = max(0, int(self.portfolio_cash / premium_per_contract))
            if num_contracts == 0:
                return None
            cost_basis = raw_opt * num_contracts * 100

        # Deduct cash
        self.portfolio_cash -= cost_basis

        confidence = signal_result.get("confidence", 0.0)

        pos = OptionPosition(
            symbol=symbol,
            strategy=self.strategy_name,
            entry_date=entry_date,
            underlying_entry=entry_close,
            strike=strike,
            entry_T=T,
            iv_at_entry=iv,
            option_entry_price=raw_opt,
            num_contracts=num_contracts,
            signal_confidence=confidence,
            signal_details=signal_result,
        )
        return pos

    # ── Trade exit ───────────────────────────────────────────────────────────

    def _close_trade(
        self,
        pos: OptionPosition,
        exit_date: date,
        underlying_exit: float,
        exit_reason: str,
        exit_iv: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Close a position, book P&L, return trade record.

        P&L = (exit_option_price - entry_option_price) × num_contracts × 100
        """
        # Remaining T at exit
        T_exit = pos.remaining_T()

        # Re-price option at exit
        iv_used = exit_iv if exit_iv is not None else pos.current_iv
        exit_opt_price = pos.reprice(underlying_exit, updated_iv=iv_used)

        # P&L calculation per spec:
        # options_pnl = (exit_price - entry_price) × num_contracts × 100
        options_pnl = (exit_opt_price - pos.option_entry_price) * pos.num_contracts * 100
        pnl_pct     = (options_pnl / pos.cost_basis) * 100 if pos.cost_basis > 0 else 0.0

        # Return cash (sell proceeds)
        proceeds = exit_opt_price * pos.num_contracts * 100
        self.portfolio_cash += proceeds

        # Underlying % move
        underlying_pnl_pct = (
            (underlying_exit - pos.underlying_entry) / pos.underlying_entry * 100
        )

        trade_record = {
            "symbol":               pos.symbol,
            "strategy":             pos.strategy,
            "entry_date":           pos.entry_date.isoformat(),
            "exit_date":            exit_date.isoformat(),
            "days_held":            pos.days_held,
            # Option prices (per share)
            "entry_option_price":   round(pos.option_entry_price, 4),
            "exit_option_price":    round(exit_opt_price, 4),
            # Underlying prices
            "underlying_entry":     round(pos.underlying_entry, 4),
            "underlying_exit":      round(underlying_exit, 4),
            "underlying_pnl_pct":   round(underlying_pnl_pct, 4),
            # Options structure
            "strike":               pos.strike,
            "entry_T_years":        round(pos.entry_T, 6),
            "iv_at_entry":          round(pos.iv_at_entry, 4),
            "iv_at_exit":           round(iv_used, 4),
            "delta_at_entry":       round(
                black_scholes_delta(pos.underlying_entry, pos.strike, pos.entry_T, RISK_FREE_RATE, pos.iv_at_entry),
                4
            ),
            # P&L
            "num_contracts":        pos.num_contracts,
            "cost_basis":           round(pos.cost_basis, 2),
            "proceeds":             round(proceeds, 2),
            "pnl":                  round(options_pnl, 2),
            "pnl_pct":              round(pnl_pct, 4),
            # Signal info
            "exit_reason":          exit_reason,
            "signal_confidence":    round(pos.signal_confidence, 4),
            "avg_confidence":       round(pos.signal_details.get("avg_confidence", pos.signal_confidence), 4),
        }
        return trade_record

    # ── Main run loop ─────────────────────────────────────────────────────────

    def run(self) -> Dict[str, Any]:
        """Execute the full backtest.  Returns a results dict."""
        logger.info(
            "Starting backtest: strategy=%s, tickers=%d, period=%s to %s",
            self.strategy_name, len(self.watchlist),
            BACKTEST_START, BACKTEST_END,
        )

        # Pre-load SPY data
        spy_df = self._get_ohlcv("SPY")
        if spy_df is None:
            logger.error("No SPY data found — cannot run backtest")
            return self._empty_results()

        # Generate trading calendar from SPY data
        all_dates: List[date] = []
        for ts in spy_df.index:
            d = ts.date() if hasattr(ts, "date") else ts
            if BACKTEST_START <= d <= BACKTEST_END:
                all_dates.append(d)
        all_dates.sort()

        print(f'[DEBUG run()] all_dates={len(all_dates)}, spy_df_rows={len(spy_df) if spy_df is not None else None}, BS={BACKTEST_START}, BE={BACKTEST_END}')
        if not all_dates:
            logger.warning("No trading dates found in SPY data for the backtest period")
            return self._empty_results()

        # Pre-load all ticker data
        tickers_to_load = list(set(self.watchlist + ["SPY"]))
        logger.info("Pre-loading data for %d tickers...", len(tickers_to_load))
        for t in tickers_to_load:
            self._get_ohlcv(t)
            self._get_orats(t)

        # ── Day loop ──────────────────────────────────────────────────────────
        prev_equity = self.starting_capital

        for i, current_date in enumerate(all_dates):
            # Get SPY row for macro expert
            spy_row = self._row_for_date("SPY", current_date)

            # ── 1. Update open positions and check exits ──────────────────────
            symbols_to_close: List[Tuple[str, str, float, float]] = []
            # (symbol, reason, underlying_price, updated_iv)

            for symbol, pos in list(self.open_positions.items()):
                pos.days_held += 1

                row = self._row_for_date(symbol, current_date)
                if row is None:
                    continue

                underlying = float(row["Close"])

                # Update IV for repricing
                orats     = self._get_orats(symbol)
                updated_iv = get_iv_for_date(orats, current_date, last_known=pos.current_iv)
                pos.current_iv = updated_iv

                reason = self._check_exit(pos, underlying)
                if reason:
                    symbols_to_close.append((symbol, reason, underlying, updated_iv))

            for symbol, reason, underlying_exit, exit_iv in symbols_to_close:
                pos = self.open_positions.pop(symbol)
                trade_rec = self._close_trade(pos, current_date, underlying_exit, reason, exit_iv)
                self.closed_trades.append(trade_rec)

            # ── 2. Generate signals for today ────────────────────────────────
            # Signal on day N → entry at close of day N (use close as entry price per spec)
            pending_entries: List[Tuple[str, Dict[str, Any], float]] = []

            for symbol in self.watchlist:
                if symbol in self.open_positions:
                    continue  # already holding

                row = self._row_for_date(symbol, current_date)
                if row is None:
                    continue

                close_price   = float(row["Close"])
                signal_result = self._generate_signal(symbol, row, spy_row)

                signal_record = {
                    "date":           current_date.isoformat(),
                    "symbol":         symbol,
                    "strategy":       self.strategy_name,
                    "signal":         signal_result.get("signal", "NO_SIGNAL"),
                    "confidence":     signal_result.get("confidence", 0.0),
                    "avg_confidence": signal_result.get("avg_confidence", signal_result.get("confidence", 0.0)),
                    "close":          round(close_price, 4),
                    "details":        signal_result,
                }
                self.all_signals.append(signal_record)

                if signal_result.get("signal") == "BUY":
                    pending_entries.append((symbol, signal_result, close_price))

            # ── 3. Execute entries using today's close as entry price ─────────
            # (Spec uses close price for option pricing on entry day)
            for symbol, signal_result, close_price in pending_entries:
                if symbol in self.open_positions:
                    continue
                pos = self._enter_trade(symbol, current_date, close_price, signal_result)
                if pos is not None:
                    self.open_positions[symbol] = pos

            # ── 4. Record equity curve ────────────────────────────────────────
            equity = self._portfolio_value(current_date)
            self.equity_curve.append((current_date, round(equity, 2)))
            if prev_equity > 0:
                self.daily_returns.append((equity - prev_equity) / prev_equity)
            prev_equity = equity

        # ── Force-close any still-open positions at end of backtest ──────────
        last_date = all_dates[-1] if all_dates else BACKTEST_END
        for symbol, pos in list(self.open_positions.items()):
            row = self._row_for_date(symbol, last_date)
            underlying_exit = float(row["Close"]) if row is not None else pos.underlying_entry
            orats      = self._get_orats(symbol)
            exit_iv    = get_iv_for_date(orats, last_date, last_known=pos.current_iv)
            trade_rec  = self._close_trade(pos, last_date, underlying_exit, "end_of_backtest", exit_iv)
            self.closed_trades.append(trade_rec)
        self.open_positions.clear()

        return self._compile_results()

    # ── Results compilation ───────────────────────────────────────────────────

    def _compile_results(self) -> Dict[str, Any]:
        """Aggregate all trades and metrics into the results dict."""
        trades   = self.closed_trades
        n_trades = len(trades)

        if n_trades == 0:
            return self._empty_results()

        pnls      = [t["pnl"] for t in trades]
        wins      = [p for p in pnls if p > 0]
        losses    = [p for p in pnls if p <= 0]
        win_rate  = len(wins) / n_trades if n_trades else 0.0
        total_pnl = sum(pnls)

        avg_win  = float(np.mean(wins))  if wins   else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        avg_win_pct  = float(np.mean([t["pnl_pct"] for t in trades if t["pnl"] > 0]))  if wins   else 0.0
        avg_loss_pct = float(np.mean([t["pnl_pct"] for t in trades if t["pnl"] <= 0])) if losses else 0.0

        gross_profit  = sum(wins)
        gross_loss    = abs(sum(losses)) if losses else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else None

        max_drawdown = self._max_drawdown()
        sharpe       = self._sharpe()
        avg_hold     = float(np.mean([t["days_held"] for t in trades])) if trades else 0.0

        # Monthly P&L breakdown
        monthly_pnl = self._monthly_pnl()

        # Exit reason breakdown
        exit_reasons = {}
        for t in trades:
            r = t["exit_reason"]
            exit_reasons[r] = exit_reasons.get(r, 0) + 1

        # Confidence calibration (for Expert Committee)
        conf_calibration = self._confidence_calibration()

        # Total return %
        final_equity = self.portfolio_cash
        total_return_pct = (final_equity - self.starting_capital) / self.starting_capital * 100

        return {
            "strategy_name":       self.strategy_name,
            "backtest_start":      BACKTEST_START.isoformat(),
            "backtest_end":        BACKTEST_END.isoformat(),
            "starting_capital":    self.starting_capital,
            "final_equity":        round(final_equity, 2),
            "total_return_pct":    round(total_return_pct, 4),
            "total_signals":       len(self.all_signals),
            "buy_signals":         sum(1 for s in self.all_signals if s["signal"] == "BUY"),
            "total_trades":        n_trades,
            "winning_trades":      len(wins),
            "losing_trades":       len(losses),
            "win_rate":            round(win_rate, 4),
            "avg_win_pct":         round(avg_win_pct, 4),
            "avg_loss_pct":        round(avg_loss_pct, 4),
            "avg_win":             round(avg_win, 2),
            "avg_loss":            round(avg_loss, 2),
            "total_pnl":           round(total_pnl, 2),
            "gross_profit":        round(gross_profit, 2),
            "gross_loss":          round(gross_loss, 2),
            "profit_factor":       round(profit_factor, 4) if profit_factor is not None else None,
            "max_drawdown_pct":    round(max_drawdown, 4),
            "sharpe_ratio":        round(sharpe, 4),
            "avg_hold_days":       round(avg_hold, 2),
            "exit_reasons":        exit_reasons,
            "confidence_calibration": conf_calibration,
            "monthly_pnl":         monthly_pnl,
            "equity_curve":        [(d.isoformat(), v) for d, v in self.equity_curve],
            "trades":              trades,
        }

    def _empty_results(self) -> Dict[str, Any]:
        return {
            "strategy_name":       self.strategy_name,
            "backtest_start":      BACKTEST_START.isoformat(),
            "backtest_end":        BACKTEST_END.isoformat(),
            "starting_capital":    self.starting_capital,
            "final_equity":        self.starting_capital,
            "total_return_pct":    0.0,
            "total_signals":       0,
            "buy_signals":         0,
            "total_trades":        0,
            "winning_trades":      0,
            "losing_trades":       0,
            "win_rate":            0.0,
            "avg_win_pct":         0.0,
            "avg_loss_pct":        0.0,
            "avg_win":             0.0,
            "avg_loss":            0.0,
            "total_pnl":           0.0,
            "gross_profit":        0.0,
            "gross_loss":          0.0,
            "profit_factor":       None,
            "max_drawdown_pct":    0.0,
            "sharpe_ratio":        0.0,
            "avg_hold_days":       0.0,
            "exit_reasons":        {},
            "confidence_calibration": {},
            "monthly_pnl":         {},
            "equity_curve":        [],
            "trades":              [],
        }

    def _max_drawdown(self) -> float:
        """Maximum peak-to-trough drawdown as a percentage."""
        if not self.equity_curve:
            return 0.0
        values = np.array([v for _, v in self.equity_curve])
        peak   = np.maximum.accumulate(values)
        dd     = (peak - values) / np.where(peak > 0, peak, 1)
        return float(np.max(dd)) * 100

    def _sharpe(self, rf_daily: float = RISK_FREE_RATE / 252) -> float:
        """Annualised Sharpe ratio on daily option returns."""
        r = np.array(self.daily_returns)
        if len(r) < 2:
            return 0.0
        excess = r - rf_daily
        std    = np.std(excess, ddof=1)
        if std == 0:
            return 0.0
        return float(np.mean(excess) / std * math.sqrt(252))

    def _monthly_pnl(self) -> Dict[str, float]:
        """Monthly P&L breakdown from closed trades."""
        monthly: Dict[str, float] = {}
        for t in self.closed_trades:
            month = t["exit_date"][:7]  # YYYY-MM
            monthly[month] = monthly.get(month, 0.0) + t["pnl"]
        return {k: round(v, 2) for k, v in sorted(monthly.items())}

    def _confidence_calibration(self) -> Dict[str, Any]:
        """Compare avg_confidence of winning vs losing trades.

        Relevant for Expert Committee strategy.
        """
        if not self.closed_trades:
            return {}

        win_confs  = [t["avg_confidence"] for t in self.closed_trades if t["pnl"] > 0]
        loss_confs = [t["avg_confidence"] for t in self.closed_trades if t["pnl"] <= 0]

        return {
            "avg_confidence_winners":  round(float(np.mean(win_confs)),  4) if win_confs  else None,
            "avg_confidence_losers":   round(float(np.mean(loss_confs)), 4) if loss_confs else None,
            "n_winners":               len(win_confs),
            "n_losers":                len(loss_confs),
            "confidence_spread":       round(
                float(np.mean(win_confs)) - float(np.mean(loss_confs)), 4
            ) if win_confs and loss_confs else None,
        }


# ============================================================================
# Convenience: run a single strategy or all strategies
# ============================================================================

def run_strategy(
    strategy_name: str,
    watchlist: Optional[List[str]] = None,
    starting_capital: float = STARTING_CAPITAL,
    notional_per_trade: float = NOTIONAL_PER_TRADE,
) -> Dict[str, Any]:
    """Run a single strategy backtest and return results dict."""
    engine = OptionsBacktestEngine(
        strategy_name=strategy_name,
        watchlist=watchlist,
        starting_capital=starting_capital,
        notional_per_trade=notional_per_trade,
    )
    return engine.run()


def run_all_strategies(
    watchlist: Optional[List[str]] = None,
    starting_capital: float = STARTING_CAPITAL,
    notional_per_trade: float = NOTIONAL_PER_TRADE,
) -> Dict[str, Dict[str, Any]]:
    """Run all three strategies and return a dict keyed by strategy name."""
    results = {}
    for name in STRATEGY_CONFIGS:
        logger.info("Running strategy: %s", name)
        results[name] = run_strategy(
            name,
            watchlist=watchlist,
            starting_capital=starting_capital,
            notional_per_trade=notional_per_trade,
        )
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    results = run_all_strategies()
    for name, r in results.items():
        print(
            f"{name:25s}  trades={r['total_trades']:4d}  "
            f"WR={r['win_rate']*100:.1f}%  "
            f"PnL=${r['total_pnl']:,.0f}  "
            f"Ret={r['total_return_pct']:.2f}%  "
            f"Sharpe={r['sharpe_ratio']:.2f}"
        )
