"""Shared backtest metrics, extracted from daily_portfolio.py for reuse.

Provides annualisation helpers, trade statistics, and full metric calculation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backtest.models import TradeRecord

# ─── Annualisation factor mapping ───

_TRADING_DAYS = {"tushare": 252, "yfinance": 252, "okx": 365, "akshare": 252, "ccxt": 365}
_BARS_PER_DAY = {
    "1m":  {"tushare": 240, "okx": 1440, "yfinance": 390, "akshare": 240, "ccxt": 1440},
    "5m":  {"tushare": 48,  "okx": 288,  "yfinance": 78,  "akshare": 48,  "ccxt": 288},
    "15m": {"tushare": 16,  "okx": 96,   "yfinance": 26,  "akshare": 16,  "ccxt": 96},
    "30m": {"tushare": 8,   "okx": 48,   "yfinance": 13,  "akshare": 8,   "ccxt": 48},
    "1H":  {"tushare": 4,   "okx": 24,   "yfinance": 7,   "akshare": 4,   "ccxt": 24},
    "4H":  {"tushare": 1,   "okx": 6,    "yfinance": 2,   "akshare": 1,   "ccxt": 6},
    "1D":  {"tushare": 1,   "okx": 1,    "yfinance": 1,   "akshare": 1,   "ccxt": 1},
}


def calc_bars_per_year(interval: str = "1D", source: str = "tushare") -> int:
    """Number of bars per year for annualisation.

    Args:
        interval: Bar size (1m / 5m / 15m / 30m / 1H / 4H / 1D).
        source: Data source (tushare / yfinance / okx).

    Returns:
        Bars per year.
    """
    trading_days = _TRADING_DAYS.get(source, 252)
    bars_per_day = _BARS_PER_DAY.get(interval, {}).get(source, 1)
    return trading_days * bars_per_day


def win_rate_and_stats(trades: List[TradeRecord]) -> Dict[str, float]:
    """Win rate and P&L statistics from completed trades.

    Single-pass implementation: iterates trades once to compute all stats.

    Args:
        trades: Completed round-trip trades.

    Returns:
        Dict with win_rate, profit_loss_ratio, max_consecutive_loss,
        avg_holding_bars, profit_factor.
    """
    if not trades:
        return {
            "win_rate": 0.0,
            "profit_loss_ratio": 0.0,
            "max_consecutive_loss": 0,
            "avg_holding_bars": 0.0,
            "profit_factor": 0.0,
        }

    win_count = 0
    gross_profit = 0.0
    gross_loss = 0.0
    max_consec = 0
    cur_consec = 0
    hold_sum = 0.0
    hold_count = 0

    for t in trades:
        pnl = t.pnl
        if pnl > 0:
            win_count += 1
            gross_profit += pnl
            cur_consec = 0
        elif pnl < 0:
            gross_loss -= pnl  # accumulate as positive
            cur_consec += 1
            if cur_consec > max_consec:
                max_consec = cur_consec
        else:
            cur_consec = 0
        if t.holding_bars > 0:
            hold_sum += t.holding_bars
            hold_count += 1

    n = len(trades)
    win_rate = win_count / n
    avg_win = gross_profit / win_count if win_count else 0.0
    avg_loss = gross_loss / (n - win_count) if (n - win_count) > 0 else 1e-10
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 1e-10 else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 1e-10 else 0.0
    avg_holding = hold_sum / hold_count if hold_count else 0.0

    return {
        "win_rate": win_rate,
        "profit_loss_ratio": round(profit_loss_ratio, 4),
        "max_consecutive_loss": max_consec,
        "avg_holding_bars": round(avg_holding, 1),
        "profit_factor": round(profit_factor, 4),
    }


def by_symbol_stats(trades: List[TradeRecord]) -> Dict[str, Dict[str, Any]]:
    """Per-symbol trade statistics (single-pass accumulation).

    Args:
        trades: Completed round-trip trades.

    Returns:
        {symbol: {count, win_rate, total_pnl, avg_pnl}}.
    """
    # Accumulate counts in one pass instead of building intermediate lists
    counts: Dict[str, int] = {}
    win_counts: Dict[str, int] = {}
    pnl_sums: Dict[str, float] = {}

    for t in trades:
        sym = t.symbol
        counts[sym] = counts.get(sym, 0) + 1
        pnl_sums[sym] = pnl_sums.get(sym, 0.0) + t.pnl
        if t.pnl > 0:
            win_counts[sym] = win_counts.get(sym, 0) + 1

    return {
        sym: {
            "count": cnt,
            "win_rate": round(win_counts.get(sym, 0) / cnt, 4),
            "total_pnl": round(pnl_sums[sym], 2),
            "avg_pnl": round(pnl_sums[sym] / cnt, 2),
        }
        for sym, cnt in counts.items()
    }


def by_exit_reason_stats(trades: List[TradeRecord]) -> Dict[str, Dict[str, Any]]:
    """Per-exit-reason trade statistics (single-pass accumulation).

    Args:
        trades: Completed round-trip trades.

    Returns:
        {reason: {count, total_pnl}}.
    """
    counts: Dict[str, int] = {}
    pnl_sums: Dict[str, float] = {}

    for t in trades:
        r = t.exit_reason
        counts[r] = counts.get(r, 0) + 1
        pnl_sums[r] = pnl_sums.get(r, 0.0) + t.pnl

    return {
        reason: {"count": cnt, "total_pnl": round(pnl_sums[reason], 2)}
        for reason, cnt in counts.items()
    }


def calc_metrics(
    equity_curve: pd.Series,
    trades: List[TradeRecord],
    initial_cash: float,
    bars_per_year: int = 252,
    bench_ret: Optional[pd.Series] = None,
) -> Dict[str, Any]:
    """Full set of performance metrics.

    Args:
        equity_curve: Equity time series (index=timestamp, values=equity).
        trades: Completed round-trip trades.
        initial_cash: Starting capital.
        bars_per_year: Bars per year for annualisation.
        bench_ret: Benchmark per-bar return series (optional).

    Returns:
        Metrics dictionary (compatible with daily_portfolio format).
    """
    if len(equity_curve) == 0:
        return _empty_metrics(initial_cash)

    n = len(equity_curve)
    bpy = bars_per_year

    port_ret = equity_curve.pct_change().fillna(0.0)

    total_ret = float(equity_curve.iloc[-1] / initial_cash - 1)
    # Guard against negative equity (e.g. leveraged forex) which would produce
    # a complex number when raising a negative base to a fractional exponent.
    growth = 1 + total_ret
    ann_ret = float(abs(growth) ** (bpy / max(n, 1)) - 1) if growth > 0 else -1.0
    vol = float(port_ret.std())
    sharpe = float(port_ret.mean() / (vol + 1e-10) * np.sqrt(bpy))

    # Drawdown
    peak = equity_curve.cummax()
    dd = (equity_curve - peak) / peak.replace(0, 1)
    max_dd = float(dd.min())

    calmar = ann_ret / abs(max_dd) if abs(max_dd) > 1e-10 else 0.0

    # Sortino
    downside = port_ret[port_ret < 0]
    downside_std = float(downside.std()) if len(downside) > 1 else 1e-10
    sortino = float(port_ret.mean() / (downside_std + 1e-10) * np.sqrt(bpy))

    trade_stats = win_rate_and_stats(trades)

    # Benchmark comparison
    bench_return = 0.0
    excess = 0.0
    ir = 0.0
    if bench_ret is not None and len(bench_ret) > 0:
        bench_return = float((1 + bench_ret).prod() - 1)
        excess = total_ret - bench_return
        active_ret = port_ret - bench_ret.reindex(port_ret.index).fillna(0.0)
        active_std = float(active_ret.std())
        ir = float(active_ret.mean() / (active_std + 1e-10) * np.sqrt(bpy))

    return {
        "final_value": float(equity_curve.iloc[-1]),
        "total_return": total_ret,
        "annual_return": ann_ret,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "calmar": round(calmar, 4),
        "sortino": round(sortino, 4),
        "win_rate": trade_stats["win_rate"],
        "profit_loss_ratio": trade_stats["profit_loss_ratio"],
        "profit_factor": trade_stats["profit_factor"],
        "max_consecutive_loss": trade_stats["max_consecutive_loss"],
        "avg_holding_days": trade_stats["avg_holding_bars"],
        "trade_count": len(trades),
        "benchmark_return": round(bench_return, 6),
        "excess_return": round(excess, 6),
        "information_ratio": round(ir, 4),
    }


def _empty_metrics(initial_cash: float) -> Dict[str, Any]:
    """Return zero-valued metrics when no data is available."""
    return {
        "final_value": initial_cash,
        "total_return": 0, "annual_return": 0, "max_drawdown": 0,
        "sharpe": 0, "calmar": 0, "sortino": 0,
        "win_rate": 0, "profit_loss_ratio": 0, "profit_factor": 0,
        "max_consecutive_loss": 0, "avg_holding_days": 0, "trade_count": 0,
        "benchmark_return": 0, "excess_return": 0, "information_ratio": 0,
    }
