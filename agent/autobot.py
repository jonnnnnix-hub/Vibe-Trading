#!/usr/bin/env python3
"""AutoBot v3.1 — Auto-trading bot backend for Vibe-Trading.

Implements three strategies from the Syntax-AI backtesting engine:
  1. Momentum Scanner    (v5 — 3/5 scoring)
  2. Expert Committee    (v9 — 5-expert vote)  ← recommended
  3. Aggressive Momentum (v10_aggressive — expert vote + hard stop)

v3.1 Parameters (optimized from 173-ticker backtest — 68.1% WR, 1.81 Sharpe):
  A. option_target_pct: 12%    (NEW: option-level take-profit)
  B. option_stop_pct: 30%      (tightened from 60%)
  C. max_hold_days: 4          (reduced from 10 — winners avg 2.0d)
  D. delta range: [0.38, 0.44] (tightened upper bound from 0.50)
  E. trailing: 3.0%/2.0%       (activation / distance)
  F. IV filter: skip entry when 5-day IV declining >5%

Signals are generated against a universe of watchlist symbols via yfinance
and executed against the paper trading portfolio stored in the runs directory.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Optional: use `ta` library for indicator computation
# ---------------------------------------------------------------------------
try:
    import ta
    _TA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TA_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("autobot")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BOT_STATE_DIR = Path(os.environ.get("BOT_STATE_DIR", Path(__file__).resolve().parent / "runs"))
BOT_STATE_PATH = _BOT_STATE_DIR / "autobot_state.json"

# ---------------------------------------------------------------------------
# Default watchlist
# ---------------------------------------------------------------------------
DEFAULT_WATCHLIST: List[str] = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "AMD", "NFLX", "CRM",
]

# ---------------------------------------------------------------------------
# Default bot state
# ---------------------------------------------------------------------------
DEFAULT_STATE: Dict[str, Any] = {
    "active": False,
    "strategy": "expert_committee",
    "watchlist": DEFAULT_WATCHLIST,
    "position_size_pct": 5.0,
    "max_positions": 10,
    "last_scan_time": None,
    "signals_history": [],
    "position_tracking": {},
    "cycle_count": 0,
    "total_signals_generated": 0,
    "total_trades_executed": 0,
    "config": {
        # v3.1 parameters (optimized from 173-ticker backtest — 68.1% WR)
        "target_pct": 5.0,
        "trailing_activation": 3.0,
        "trailing_distance": 2.0,
        "hard_stop_pct": None,
        "option_stop_pct": 30.0,          # v3.1: tightened from 60% → 30%
        "option_target_pct": 12.0,        # v3.1: NEW — option-level take-profit
        "max_hold_days": 4,               # v3.1: reduced from 10 → 4
        "min_hold_days": 1,
        "delta_min": 0.38,                # v3.1: option delta sweet spot
        "delta_max": 0.44,                # v3.1: tightened upper bound
        "iv_filter": True,
        "iv_decline_threshold": -5.0,
    },
}


# ============================================================================
# Indicator Computation
# ============================================================================

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all required technical indicators to an OHLCV DataFrame.

    Adds: SMA_20, SMA_50, SMA_200, EMA_9, EMA_20, EMA_50,
          RSI_14, MACD_line, MACD_signal, MACD_histogram,
          BB_lower, BB_middle, BB_upper, BB_position,
          ADX_14, ATR_14, Volume_ratio, OBV, OBV_slope_10d,
          Momentum_5d, Pullback_depth, Dist_EMA20, Dist_SMA50
    """
    if df is None or df.empty or len(df) < 30:
        return df

    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # ── Moving Averages ──────────────────────────────────────────────────────
    df["SMA_20"] = close.rolling(20).mean()
    df["SMA_50"] = close.rolling(50).mean()
    df["SMA_200"] = close.rolling(200).mean()
    df["EMA_9"] = close.ewm(span=9, adjust=False).mean()
    df["EMA_20"] = close.ewm(span=20, adjust=False).mean()
    df["EMA_50"] = close.ewm(span=50, adjust=False).mean()

    # ── RSI ─────────────────────────────────────────────────────────────────
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI_14"] = 100 - (100 / (1 + rs))

    # ── MACD (12, 26, 9) ────────────────────────────────────────────────────
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD_line"] = ema12 - ema26
    df["MACD_signal"] = df["MACD_line"].ewm(span=9, adjust=False).mean()
    df["MACD_histogram"] = df["MACD_line"] - df["MACD_signal"]

    # ── Bollinger Bands (20, 2) ─────────────────────────────────────────────
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df["BB_middle"] = bb_mid
    df["BB_upper"] = bb_mid + 2 * bb_std
    df["BB_lower"] = bb_mid - 2 * bb_std
    band_width = df["BB_upper"] - df["BB_lower"]
    df["BB_position"] = np.where(
        band_width > 0,
        (close - df["BB_lower"]) / band_width,
        0.5,
    )

    # ── ADX (14) ─────────────────────────────────────────────────────────────
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = tr.ewm(com=13, adjust=False).mean()
    df["ATR_14"] = atr14

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    smooth_plus = plus_dm.ewm(com=13, adjust=False).mean()
    smooth_minus = minus_dm.ewm(com=13, adjust=False).mean()

    di_plus = 100 * smooth_plus / atr14.replace(0, np.nan)
    di_minus = 100 * smooth_minus / atr14.replace(0, np.nan)
    dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    df["ADX_14"] = dx.ewm(com=13, adjust=False).mean()

    # ── Volume Ratio (vol / 20-day avg vol) ──────────────────────────────────
    vol_ma20 = volume.rolling(20).mean()
    df["Volume_ratio"] = volume / vol_ma20.replace(0, np.nan)

    # ── OBV ──────────────────────────────────────────────────────────────────
    direction = np.sign(close.diff()).fillna(0)
    df["OBV"] = (direction * volume).cumsum()
    df["OBV_slope_10d"] = df["OBV"].diff(10)

    # ── Williams %R (14) — replaces RSI for momentum expert (consolidation) ──
    highest_14 = high.rolling(14).max()
    lowest_14 = low.rolling(14).min()
    wr_range = highest_14 - lowest_14
    df["Williams_R_14"] = np.where(
        wr_range > 0,
        -100 * (highest_14 - close) / wr_range,
        -50.0,  # Neutral default
    )

    # ── Momentum ─────────────────────────────────────────────────────────────
    df["Momentum_5d"] = close.pct_change(5) * 100
    df["Momentum_10d"] = close.pct_change(10) * 100
    df["Momentum_20d"] = close.pct_change(20) * 100

    # ── Pullback depth (% from 20-day rolling high) ───────────────────────────
    rolling_high = close.rolling(20).max()
    df["Pullback_depth"] = ((close - rolling_high) / rolling_high) * 100

    # ── Distance from MAs ────────────────────────────────────────────────────
    df["Dist_EMA20"] = ((close - df["EMA_20"]) / df["EMA_20"]) * 100
    df["Dist_SMA50"] = ((close - df["SMA_50"]) / df["SMA_50"]) * 100

    return df


# ============================================================================
# Market Data Fetching
# ============================================================================

def fetch_market_data(
    symbols: List[str],
    period: str = "3mo",
) -> Dict[str, pd.DataFrame]:
    """Fetch OHLCV data for multiple symbols via yfinance and compute indicators.

    Returns a dict mapping symbol -> enriched DataFrame.
    Symbols that fail to download are silently omitted.
    """
    results: Dict[str, pd.DataFrame] = {}

    # Batch download for efficiency
    try:
        raw = yf.download(
            symbols,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as exc:
        logger.warning("Batch download failed (%s); falling back to individual fetches", exc)
        raw = None

    for sym in symbols:
        try:
            if raw is not None and not raw.empty:
                if len(symbols) == 1:
                    df = raw.copy()
                else:
                    # Multi-symbol: columns are multi-level (field, symbol)
                    if isinstance(raw.columns, pd.MultiIndex):
                        df = raw.xs(sym, axis=1, level=1, drop_level=True).dropna(how="all")
                    else:
                        df = raw.copy()
            else:
                ticker = yf.Ticker(sym)
                df = ticker.history(period=period, auto_adjust=True)

            if df is None or df.empty:
                logger.warning("No data for %s", sym)
                continue

            df = df.rename(columns={
                "open": "Open", "high": "High", "low": "Low",
                "close": "Close", "volume": "Volume",
            })

            required = ["Open", "High", "Low", "Close", "Volume"]
            if not all(c in df.columns for c in required):
                logger.warning("Missing OHLCV columns for %s", sym)
                continue

            df = compute_indicators(df)
            results[sym] = df

        except Exception as exc:
            logger.warning("Failed to process %s: %s", sym, exc)

    return results


# ============================================================================
# Expert Committee — Individual Experts
# ============================================================================

def evaluate_trend_expert(row: pd.Series) -> Tuple[str, float]:
    """Trend expert: moving-average alignment + momentum.

    AGREE:    close > EMA_20 > SMA_50  AND  Momentum_5d > 0
    DISAGREE: close < SMA_50  OR  SMA_50 < SMA_200
    ABSTAIN:  otherwise
    """
    try:
        close = row["Close"]
        ema20 = row["EMA_20"]
        sma50 = row["SMA_50"]
        sma200 = row.get("SMA_200", np.nan)
        mom5 = row.get("Momentum_5d", np.nan)
        adx = row.get("ADX_14", np.nan)
        dist_ema20 = row.get("Dist_EMA20", np.nan)

        if any(pd.isna([close, ema20, sma50])):
            return ("ABSTAIN", 0.5)

        # DISAGREE conditions
        if close < sma50:
            return ("DISAGREE", 0.8)
        if not pd.isna(sma200) and sma50 < sma200:
            return ("DISAGREE", 0.8)

        # AGREE conditions
        if close > ema20 and ema20 > sma50 and (pd.isna(mom5) or mom5 > 0):
            # Confidence formula
            conf = 0.5
            if not pd.isna(adx):
                conf += float(np.clip((adx - 20) / 40, 0, 1)) * 0.3
            if not pd.isna(dist_ema20):
                conf += float(np.clip(dist_ema20 / 3.0, 0, 1)) * 0.2
            conf = float(np.clip(conf, 0.5, 0.95))
            return ("AGREE", conf)

        return ("ABSTAIN", 0.5)

    except Exception as exc:
        logger.debug("Trend expert error: %s", exc)
        return ("ABSTAIN", 0.5)


def evaluate_momentum_expert(row: pd.Series) -> Tuple[str, float]:
    """Momentum expert: Williams %R + MACD + ADX health check.

    Uses Williams %R(14) instead of RSI(14) for cross-repo differentiation.
    Williams %R is on -100 to 0 scale (inverted from RSI's 0-100):
      -60 to -30 = healthy momentum (equivalent to RSI 40-70)
      > -20 = overbought (equivalent to RSI > 80)
      < -80 = oversold (equivalent to RSI < 20)

    AGREE:    Williams %R -60 to -30  AND  MACD_histogram > 0  AND  ADX >= 20
    DISAGREE: Williams %R > -20, < -80, ADX < 15, OR (MACD <= 0 in healthy range)
    ABSTAIN:  borderline
    """
    try:
        wr = row.get("Williams_R_14", np.nan)
        macd_h = row.get("MACD_histogram", np.nan)
        adx = row.get("ADX_14", np.nan)

        if any(pd.isna([wr, macd_h, adx])):
            return ("ABSTAIN", 0.5)

        # DISAGREE — extreme overbought/oversold or weak trend
        if wr > -20 or wr < -80 or adx < 15:
            return ("DISAGREE", 0.8)
        if -60 <= wr <= -30 and macd_h <= 0:
            return ("DISAGREE", 0.6)

        # AGREE — healthy momentum zone with trend confirmation
        if -60 <= wr <= -30 and macd_h > 0 and adx >= 20:
            # Confidence from Williams %R distance to center (-45 is ideal)
            wr_conf = float(np.clip(1.0 - abs(wr - (-45)) / 15, 0.3, 1.0))
            macd_conf = 0.8 if macd_h > 0 else 0.5
            adx_conf = float(np.clip((adx - 20) / 30, 0, 1)) * 0.3 + 0.5
            conf = float(np.clip(wr_conf * 0.5 + macd_conf * 0.25 + adx_conf * 0.25, 0.45, 0.95))
            return ("AGREE", conf)

        # Borderline / ABSTAIN
        return ("ABSTAIN", 0.5)

    except Exception as exc:
        logger.debug("Momentum expert error: %s", exc)
        return ("ABSTAIN", 0.5)


def evaluate_mean_reversion_expert(row: pd.Series) -> Tuple[str, float]:
    """Mean-reversion expert: Bollinger Band position + pullback depth.

    AGREE:    BB_position 0.2-0.7  AND  Pullback_depth -8% to -0.5%  AND  RSI >= 35
    DISAGREE: BB_position > 0.95, Pullback_depth < -12%, RSI < 35
    ABSTAIN:  otherwise
    """
    try:
        bb_pos = row.get("BB_position", np.nan)
        pullback = row.get("Pullback_depth", np.nan)
        rsi = row.get("RSI_14", np.nan)

        if any(pd.isna([bb_pos, pullback, rsi])):
            return ("ABSTAIN", 0.5)

        # DISAGREE
        if bb_pos > 0.95 or pullback < -12 or rsi < 35:
            return ("DISAGREE", 0.8)

        # AGREE
        if 0.2 <= bb_pos <= 0.7 and -8 <= pullback <= -0.5 and rsi >= 35:
            bb_conf = float(np.clip(1.0 - abs(bb_pos - 0.4) / 0.3, 0, 1))
            pd_conf = float(np.clip(1.0 - abs(pullback - (-3.0)) / 7.5, 0, 1))
            conf = float(np.clip(bb_conf * 0.55 + pd_conf * 0.45, 0.45, 0.92))
            return ("AGREE", conf)

        return ("ABSTAIN", 0.5)

    except Exception as exc:
        logger.debug("Mean-reversion expert error: %s", exc)
        return ("ABSTAIN", 0.5)


def evaluate_volume_expert(row: pd.Series) -> Tuple[str, float]:
    """Volume expert: volume ratio + OBV slope (accumulation signal).

    AGREE:    Volume_ratio > 1.2  AND  OBV_slope_10d >= 0
    DISAGREE: Volume_ratio < 0.5  OR  OBV_slope_10d < 0
    ABSTAIN:  medium volume (0.5-1.2)
    """
    try:
        vol_ratio = row.get("Volume_ratio", np.nan)
        obv_slope = row.get("OBV_slope_10d", np.nan)

        if pd.isna(vol_ratio):
            return ("ABSTAIN", 0.5)

        # DISAGREE
        if vol_ratio < 0.5:
            return ("DISAGREE", 0.8)
        if not pd.isna(obv_slope) and obv_slope < 0:
            return ("DISAGREE", 0.7)

        # AGREE
        if vol_ratio > 1.2 and (pd.isna(obv_slope) or obv_slope >= 0):
            conf = float(np.clip((vol_ratio - 1.2) / (3.0 - 1.2), 0, 1))
            conf = conf * 0.4 + 0.5  # scale to [0.5, 0.9]
            if not pd.isna(obv_slope) and obv_slope > 0:
                conf = min(conf + 0.05, 0.92)
            return ("AGREE", float(conf))

        return ("ABSTAIN", 0.5)

    except Exception as exc:
        logger.debug("Volume expert error: %s", exc)
        return ("ABSTAIN", 0.5)


def evaluate_macro_expert(spy_row: Optional[pd.Series]) -> Tuple[str, float]:
    """Macro expert: market regime gating via SPY trend.

    Simplified regime: check SPY > SMA_50 (uptrend / pullback → AGREE or ABSTAIN).
    Full regime (green/yellow/red) needs VIX + breadth data; we approximate
    using SPY price vs its 50- and 200-day SMAs.

    AGREE:    SPY > SMA_50 > SMA_200  (uptrend, green)
    DISAGREE: SPY < SMA_50 and SMA_50 < SMA_200  (downtrend, red)
    ABSTAIN:  mixed signals (yellow)
    """
    try:
        if spy_row is None or spy_row.empty:
            return ("ABSTAIN", 0.5)

        spy_close = spy_row.get("Close", np.nan)
        spy_sma50 = spy_row.get("SMA_50", np.nan)
        spy_sma200 = spy_row.get("SMA_200", np.nan)

        if pd.isna(spy_close) or pd.isna(spy_sma50):
            return ("ABSTAIN", 0.5)

        # Green regime
        if spy_close > spy_sma50 and (pd.isna(spy_sma200) or spy_sma50 > spy_sma200):
            return ("AGREE", 0.9)

        # Red regime
        if spy_close < spy_sma50 and not pd.isna(spy_sma200) and spy_sma50 < spy_sma200:
            return ("DISAGREE", 0.9)

        # Yellow / pullback
        if spy_close > spy_sma50:
            return ("AGREE", 0.7)  # pullback but still above SMA50

        return ("ABSTAIN", 0.5)

    except Exception as exc:
        logger.debug("Macro expert error: %s", exc)
        return ("ABSTAIN", 0.5)


# ============================================================================
# Expert Committee Aggregation
# ============================================================================

def run_expert_committee(
    row: pd.Series,
    spy_row: Optional[pd.Series],
    threshold: int = 4,
) -> Dict[str, Any]:
    """Run all 5 experts and return signal details.

    Returns::
        {
            "signal": "BUY" | "NO_SIGNAL",
            "agree_count": int,
            "threshold": int,
            "avg_confidence": float,
            "experts": {
                "trend":           {"vote": ..., "confidence": ...},
                "momentum":        {...},
                "mean_reversion":  {...},
                "volume":          {...},
                "macro":           {...},
            }
        }
    """
    trend_vote, trend_conf = evaluate_trend_expert(row)
    momentum_vote, momentum_conf = evaluate_momentum_expert(row)
    mean_rev_vote, mean_rev_conf = evaluate_mean_reversion_expert(row)
    volume_vote, volume_conf = evaluate_volume_expert(row)
    macro_vote, macro_conf = evaluate_macro_expert(spy_row)

    votes = [trend_vote, momentum_vote, mean_rev_vote, volume_vote, macro_vote]
    confs = [trend_conf, momentum_conf, mean_rev_conf, volume_conf, macro_conf]

    agree_count = votes.count("AGREE")
    avg_confidence = float(np.mean([c for v, c in zip(votes, confs) if v == "AGREE"]) if agree_count > 0 else 0.0)

    signal = "BUY" if agree_count >= threshold else "NO_SIGNAL"

    return {
        "signal": signal,
        "agree_count": agree_count,
        "threshold": threshold,
        "avg_confidence": round(avg_confidence, 4),
        "experts": {
            "trend":          {"vote": trend_vote,     "confidence": round(trend_conf, 4)},
            "momentum":       {"vote": momentum_vote,  "confidence": round(momentum_conf, 4)},
            "mean_reversion": {"vote": mean_rev_vote,  "confidence": round(mean_rev_conf, 4)},
            "volume":         {"vote": volume_vote,    "confidence": round(volume_conf, 4)},
            "macro":          {"vote": macro_vote,     "confidence": round(macro_conf, 4)},
        },
    }


# ============================================================================
# Strategy 1 — Momentum Scanner (v5)
# ============================================================================

def run_momentum_scanner(row: pd.Series) -> Dict[str, Any]:
    """Score-based strategy (v5): BUY when >= 3 of 5 conditions pass.

    Conditions:
      1. RSI_14 between 40 and 70
      2. close > EMA_20
      3. MACD_histogram > 0
      4. Volume_ratio >= 1.0
      5. ADX_14 >= 18
    """
    conditions = {
        "rsi_in_range":    40 <= row.get("RSI_14", np.nan) <= 70,
        "above_ema20":     row["Close"] > row.get("EMA_20", np.inf),
        "macd_positive":   row.get("MACD_histogram", np.nan) > 0,
        "volume_ok":       row.get("Volume_ratio", 0) >= 1.0,
        "adx_ok":          row.get("ADX_14", 0) >= 18,
    }

    score = sum(1 for v in conditions.values() if v is True)
    signal = "BUY" if score >= 3 else "NO_SIGNAL"

    return {
        "signal": signal,
        "score": score,
        "conditions": {k: bool(v) for k, v in conditions.items()},
    }


# ============================================================================
# Exit Logic
# ============================================================================

def check_exits(
    positions: Dict[str, Any],
    current_prices: Dict[str, float],
    bot_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Check exit conditions for all tracked positions (v2 parameters).

    Returns a list of exit actions::
        [{"symbol": ..., "reason": ..., "price": ..., "qty": ...}, ...]

    Exit priority order (v2 — updated from backtest analysis):
      0.   Min hold period gate
      0.25 Option premium stop (NEW: -60% on approx option value)
      0.5  Hard stop
      1-2  Trailing activation (3%) + trigger (2%)
      3.   Target profit (5%)
      4.   Time exit (10 days max, was 20)
    """
    cfg = bot_state.get("config", {})
    target_pct = cfg.get("target_pct", 5.0)
    trailing_activation = cfg.get("trailing_activation", 3.0)
    trailing_distance = cfg.get("trailing_distance", 2.0)
    hard_stop_pct = cfg.get("hard_stop_pct", None)
    option_stop_pct = cfg.get("option_stop_pct", 30.0)
    option_target_pct = cfg.get("option_target_pct", 12.0)  # v3.1
    max_hold_days = cfg.get("max_hold_days", 4)
    min_hold_days = cfg.get("min_hold_days", 1)

    tracking = bot_state.get("position_tracking", {})
    sells: List[Dict[str, Any]] = []

    for symbol, pos in positions.items():
        current_price = current_prices.get(symbol)
        if current_price is None or current_price <= 0:
            continue

        track = tracking.get(symbol, {})
        entry_price = float(pos.get("avg_price", track.get("entry_price", current_price)))
        days_held = int(track.get("days_held", 0))
        peak_price = float(track.get("peak_price", entry_price))
        trailing_active = bool(track.get("trailing_active", False))
        qty = float(pos.get("qty", 0))

        if qty <= 0:
            continue

        pnl_pct = ((current_price - entry_price) / entry_price) * 100

        # Step 0: Min hold period — skip all exits
        if days_held < min_hold_days:
            continue

        # Step 0.2: Option premium target (v3.1)
        # Approximate option gain using ~6x delta leverage
        if option_target_pct is not None:
            approx_option_gain = pnl_pct * 6
            if approx_option_gain >= abs(option_target_pct):
                sells.append({
                    "symbol": symbol,
                    "reason": "option_target",
                    "price": current_price,
                    "qty": qty,
                    "pnl_pct": round(pnl_pct, 4),
                })
                continue

        # Step 0.3: Option premium stop (v3.1 — tightened to 30%)
        # For paper trading, approximate option leverage via ~6x delta
        if option_stop_pct is not None:
            approx_option_loss = pnl_pct * 6
            if approx_option_loss <= -abs(option_stop_pct):
                sells.append({
                    "symbol": symbol,
                    "reason": "option_stop",
                    "price": current_price,
                    "qty": qty,
                    "pnl_pct": round(pnl_pct, 4),
                })
                continue

        # Step 0.5: Hard stop
        if hard_stop_pct is not None and pnl_pct <= -abs(hard_stop_pct):
            sells.append({
                "symbol": symbol,
                "reason": "hard_stop",
                "price": current_price,
                "qty": qty,
                "pnl_pct": round(pnl_pct, 4),
            })
            continue

        # Step 1: Update peak price
        if current_price > peak_price:
            peak_price = current_price
            tracking.setdefault(symbol, {})["peak_price"] = peak_price

        # Step 2: Trailing activation (state transition)
        peak_unrealized = ((peak_price - entry_price) / entry_price) * 100
        if not trailing_active and peak_unrealized >= trailing_activation:
            trailing_active = True
            tracking.setdefault(symbol, {})["trailing_active"] = True
            logger.info("Trailing stop activated for %s (peak gain: %.2f%%)", symbol, peak_unrealized)

        # Step 3: Trailing stop trigger
        if trailing_active:
            trail_level = peak_price * (1 - trailing_distance / 100)
            if current_price <= trail_level:
                sells.append({
                    "symbol": symbol,
                    "reason": "trailing_stop",
                    "price": current_price,
                    "qty": qty,
                    "pnl_pct": round(pnl_pct, 4),
                    "trail_level": round(trail_level, 4),
                })
                continue

        # Step 4: Target profit
        if pnl_pct >= target_pct:
            sells.append({
                "symbol": symbol,
                "reason": "target_profit",
                "price": current_price,
                "qty": qty,
                "pnl_pct": round(pnl_pct, 4),
            })
            continue

        # Step 5: Time exit
        if days_held >= max_hold_days:
            sells.append({
                "symbol": symbol,
                "reason": "time_exit",
                "price": current_price,
                "qty": qty,
                "pnl_pct": round(pnl_pct, 4),
            })
            continue

    return sells


# ============================================================================
# AutoBot Class
# ============================================================================

class AutoBot:
    """Auto-trading bot that generates signals and executes paper trades."""

    STRATEGIES = ("momentum_scanner", "expert_committee", "aggressive_momentum")

    def __init__(self) -> None:
        self.state = self.load_state()

    # ── State persistence ────────────────────────────────────────────────────

    def load_state(self) -> Dict[str, Any]:
        """Load or initialize bot state from JSON."""
        BOT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if BOT_STATE_PATH.exists():
            try:
                data = json.loads(BOT_STATE_PATH.read_text(encoding="utf-8"))
                # Merge with defaults to handle new fields
                merged = {**DEFAULT_STATE, **data}
                merged["config"] = {**DEFAULT_STATE["config"], **data.get("config", {})}
                return merged
            except Exception as exc:
                logger.warning("Failed to load bot state (%s); resetting", exc)
        return {**DEFAULT_STATE, "config": {**DEFAULT_STATE["config"]}}

    def save_state(self) -> None:
        """Persist bot state to JSON."""
        BOT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BOT_STATE_PATH.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    # ── Configuration ────────────────────────────────────────────────────────

    def configure(
        self,
        strategy: Optional[str] = None,
        watchlist: Optional[List[str]] = None,
        position_size_pct: Optional[float] = None,
        max_positions: Optional[int] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Configure bot parameters."""
        if strategy is not None:
            if strategy not in self.STRATEGIES:
                raise ValueError(f"Unknown strategy '{strategy}'. Choose from: {self.STRATEGIES}")
            self.state["strategy"] = strategy

            # Apply strategy-specific config defaults (v3.1 parameters)
            if strategy == "aggressive_momentum":
                self.state["config"]["hard_stop_pct"] = 5.0
                self.state["config"]["option_stop_pct"] = 30.0
                self.state["config"]["option_target_pct"] = 12.0
                self.state["config"]["trailing_activation"] = 3.0
                self.state["config"]["trailing_distance"] = 2.0
                self.state["config"]["max_hold_days"] = 4
                self.state["config"]["min_hold_days"] = 2
                self.state["config"]["delta_min"] = 0.38
                self.state["config"]["delta_max"] = 0.44
            elif strategy == "expert_committee":
                self.state["config"]["hard_stop_pct"] = None
                self.state["config"]["option_stop_pct"] = 30.0
                self.state["config"]["option_target_pct"] = 12.0
                self.state["config"]["trailing_activation"] = 3.0
                self.state["config"]["trailing_distance"] = 2.0
                self.state["config"]["max_hold_days"] = 4
                self.state["config"]["min_hold_days"] = 1
                self.state["config"]["delta_min"] = 0.38
                self.state["config"]["delta_max"] = 0.44
            else:  # momentum_scanner
                self.state["config"]["hard_stop_pct"] = None
                self.state["config"]["option_stop_pct"] = 30.0
                self.state["config"]["option_target_pct"] = 12.0
                self.state["config"]["trailing_activation"] = 3.0
                self.state["config"]["trailing_distance"] = 2.0
                self.state["config"]["max_hold_days"] = 4
                self.state["config"]["min_hold_days"] = 1
                self.state["config"]["delta_min"] = 0.38
                self.state["config"]["delta_max"] = 0.44

        if watchlist is not None:
            self.state["watchlist"] = [s.upper() for s in watchlist]
        if position_size_pct is not None:
            self.state["position_size_pct"] = float(position_size_pct)
        if max_positions is not None:
            self.state["max_positions"] = int(max_positions)
        if config_overrides:
            self.state["config"].update(config_overrides)

        self.save_state()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Mark bot as active."""
        self.state["active"] = True
        self.save_state()
        logger.info("AutoBot started (strategy=%s)", self.state["strategy"])

    def stop(self) -> None:
        """Mark bot as inactive."""
        self.state["active"] = False
        self.save_state()
        logger.info("AutoBot stopped")

    # ── Status ───────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Return current bot status."""
        recent_signals = self.state.get("signals_history", [])[-20:]
        return {
            "active": self.state.get("active", False),
            "strategy": self.state.get("strategy", "expert_committee"),
            "watchlist": self.state.get("watchlist", []),
            "position_size_pct": self.state.get("position_size_pct", 5.0),
            "max_positions": self.state.get("max_positions", 10),
            "last_scan_time": self.state.get("last_scan_time"),
            "cycle_count": self.state.get("cycle_count", 0),
            "total_signals_generated": self.state.get("total_signals_generated", 0),
            "total_trades_executed": self.state.get("total_trades_executed", 0),
            "config": self.state.get("config", {}),
            "recent_signals": recent_signals,
            "tracked_positions": list(self.state.get("position_tracking", {}).keys()),
        }

    # ── Signal scanning ──────────────────────────────────────────────────────

    def _get_spy_row(self, market_data: Dict[str, pd.DataFrame]) -> Optional[pd.Series]:
        """Get the latest SPY row for macro context."""
        if "SPY" in market_data and not market_data["SPY"].empty:
            return market_data["SPY"].iloc[-1]
        return None

    def scan_signals(
        self,
        market_data: Optional[Dict[str, pd.DataFrame]] = None,
    ) -> List[Dict[str, Any]]:
        """Scan watchlist for current signals without executing trades.

        Returns a list of signal dicts, one per symbol that generated a BUY.
        """
        watchlist = self.state.get("watchlist", DEFAULT_WATCHLIST)
        strategy = self.state.get("strategy", "expert_committee")

        # Fetch SPY for macro context alongside watchlist
        symbols_to_fetch = list(set(watchlist + ["SPY"]))

        if market_data is None:
            logger.info("Fetching market data for %d symbols...", len(symbols_to_fetch))
            market_data = fetch_market_data(symbols_to_fetch, period="3mo")

        spy_row = self._get_spy_row(market_data)
        signals: List[Dict[str, Any]] = []

        for sym in watchlist:
            df = market_data.get(sym)
            if df is None or df.empty:
                continue

            row = df.iloc[-1]
            ts = str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1])

            try:
                if strategy == "momentum_scanner":
                    result = run_momentum_scanner(row)
                elif strategy == "aggressive_momentum":
                    # Same committee, different exit config
                    result = run_expert_committee(row, spy_row, threshold=4)
                else:  # expert_committee (default)
                    result = run_expert_committee(row, spy_row, threshold=4)

                if result.get("signal") == "BUY":
                    signal_record = {
                        "signal_id": str(uuid.uuid4())[:8],
                        "symbol": sym,
                        "strategy": strategy,
                        "signal": "BUY",
                        "timestamp": ts,
                        "generated_at": datetime.now().isoformat(),
                        "close": round(float(row["Close"]), 4),
                        "details": result,
                    }
                    signals.append(signal_record)

            except Exception as exc:
                logger.warning("Signal generation failed for %s: %s", sym, exc)

        # Update state
        self.state["last_scan_time"] = datetime.now().isoformat()
        self.state["total_signals_generated"] = self.state.get("total_signals_generated", 0) + len(signals)
        history = self.state.setdefault("signals_history", [])
        history.extend(signals)
        # Keep last 500 signals
        if len(history) > 500:
            self.state["signals_history"] = history[-500:]

        self.save_state()
        logger.info("Scan complete: %d BUY signals from %d symbols", len(signals), len(watchlist))
        return signals

    # ── Increment position tracking days ─────────────────────────────────────

    def _increment_days_held(self, current_positions: Dict[str, Any]) -> None:
        """Increment days_held counter for each tracked position."""
        tracking = self.state.setdefault("position_tracking", {})
        for sym in list(tracking.keys()):
            if sym in current_positions:
                tracking[sym]["days_held"] = tracking[sym].get("days_held", 0) + 1
            else:
                # Position closed externally — remove tracking
                del tracking[sym]

    # ── Main trading cycle ────────────────────────────────────────────────────

    def run_cycle(self, paper_portfolio: Dict[str, Any]) -> Dict[str, Any]:
        """Run one full trading cycle: check exits → scan entries → return actions.

        Args:
            paper_portfolio: The paper portfolio dict (will be mutated in-place
                             for position_tracking updates; actual trades must be
                             executed via the paper trading API).

        Returns:
            {
                "cycle": int,
                "exits": [...],       # exit signals triggered
                "entries": [...],     # new buy signals
                "skipped_entries": [...],
                "actions_taken": [...],
                "timestamp": str,
            }
        """
        self.state["cycle_count"] = self.state.get("cycle_count", 0) + 1
        cycle_num = self.state["cycle_count"]
        logger.info("=== AutoBot Cycle %d ===", cycle_num)

        positions = paper_portfolio.get("positions", {})
        cash = float(paper_portfolio.get("cash", 0))
        watchlist = self.state.get("watchlist", DEFAULT_WATCHLIST)
        position_size_pct = self.state.get("position_size_pct", 5.0)
        max_positions = self.state.get("max_positions", 10)

        # 1. Fetch market data (watchlist + existing positions + SPY)
        all_symbols = list(set(watchlist + list(positions.keys()) + ["SPY"]))
        market_data = fetch_market_data(all_symbols, period="3mo")

        # Current prices
        current_prices: Dict[str, float] = {}
        for sym, df in market_data.items():
            if not df.empty:
                current_prices[sym] = float(df.iloc[-1]["Close"])

        # 2. Increment days_held for all tracked positions
        self._increment_days_held(positions)

        # 3. Check exits
        exits = check_exits(positions, current_prices, self.state)
        exit_symbols = {e["symbol"] for e in exits}

        # 4. Scan for entry signals (exclude symbols being exited)
        spy_row = self._get_spy_row(market_data)
        strategy = self.state.get("strategy", "expert_committee")
        entry_signals: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        # After exits, how many positions remain?
        remaining_positions = len(positions) - len(exit_symbols)

        for sym in watchlist:
            if sym in exit_symbols:
                continue
            if sym in positions:
                continue  # already holding

            df = market_data.get(sym)
            if df is None or df.empty:
                continue

            row = df.iloc[-1]
            current_price = current_prices.get(sym)
            if current_price is None:
                continue

            try:
                if strategy == "momentum_scanner":
                    result = run_momentum_scanner(row)
                else:
                    result = run_expert_committee(row, spy_row, threshold=4)

                if result.get("signal") == "BUY":
                    # Position sizing: position_size_pct % of total portfolio value
                    total_value = cash + sum(
                        positions.get(s, {}).get("qty", 0) * current_prices.get(s, 0)
                        for s in positions
                    )
                    position_dollars = total_value * (position_size_pct / 100)
                    qty = int(position_dollars / current_price) if current_price > 0 else 0

                    if qty <= 0:
                        skipped.append({"symbol": sym, "reason": "qty_zero", "price": current_price})
                        continue

                    cost = qty * current_price
                    if cost > cash:
                        skipped.append({"symbol": sym, "reason": "insufficient_cash",
                                        "cost": round(cost, 2), "available": round(cash, 2)})
                        continue

                    if remaining_positions >= max_positions:
                        skipped.append({"symbol": sym, "reason": "max_positions_reached"})
                        continue

                    entry_signals.append({
                        "symbol": sym,
                        "signal": "BUY",
                        "price": round(current_price, 4),
                        "qty": qty,
                        "cost": round(cost, 2),
                        "details": result,
                        "generated_at": datetime.now().isoformat(),
                    })
                    # Deduct cash optimistically to avoid over-buying
                    cash -= cost
                    remaining_positions += 1

            except Exception as exc:
                logger.warning("Entry signal error for %s: %s", sym, exc)

        # 5. Update position tracking for new entries
        tracking = self.state.setdefault("position_tracking", {})
        for entry in entry_signals:
            sym = entry["symbol"]
            tracking[sym] = {
                "entry_price": entry["price"],
                "entry_date": datetime.now().isoformat(),
                "days_held": 0,
                "peak_price": entry["price"],
                "trailing_active": False,
                "strategy": strategy,
            }

        # 6. Remove tracking for exited positions
        for exit_action in exits:
            sym = exit_action["symbol"]
            if sym in tracking:
                del tracking[sym]

        # 7. Update history
        all_signals = [
            {**e, "signal_id": str(uuid.uuid4())[:8], "type": "entry"}
            for e in entry_signals
        ] + [
            {**e, "signal_id": str(uuid.uuid4())[:8], "type": "exit"}
            for e in exits
        ]
        history = self.state.setdefault("signals_history", [])
        history.extend(all_signals)
        if len(history) > 500:
            self.state["signals_history"] = history[-500:]

        n_trades = len(entry_signals) + len(exits)
        self.state["total_trades_executed"] = self.state.get("total_trades_executed", 0) + n_trades
        self.state["last_scan_time"] = datetime.now().isoformat()
        self.save_state()

        return {
            "cycle": cycle_num,
            "timestamp": datetime.now().isoformat(),
            "exits": exits,
            "entries": entry_signals,
            "skipped_entries": skipped,
            "actions_taken": exits + entry_signals,
            "summary": {
                "exits_triggered": len(exits),
                "entries_generated": len(entry_signals),
                "skipped": len(skipped),
            },
        }


# ============================================================================
# Module-level singleton
# ============================================================================

_bot: Optional[AutoBot] = None


def get_bot() -> AutoBot:
    """Return the module-level AutoBot singleton (lazy init)."""
    global _bot
    if _bot is None:
        _bot = AutoBot()
    return _bot
