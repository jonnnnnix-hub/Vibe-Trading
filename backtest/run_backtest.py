#!/usr/bin/env python3
"""Options backtest runner.

Runs all three strategies and saves results as JSON to backtest/results/.

Output files:
  - results/{strategy_name}_results.json   — per-strategy full results
  - results/backtest_summary.json          — combined summary across strategies

Usage:
    python3 backtest/run_backtest.py
    python3 backtest/run_backtest.py --strategy expert_committee
    python3 backtest/run_backtest.py --tickers AAPL MSFT NVDA
    python3 backtest/run_backtest.py --all-tickers
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path
# ---------------------------------------------------------------------------
_HERE      = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backtest.engine import (  # noqa: E402
    BACKTEST_START,
    BACKTEST_END,
    STRATEGY_CONFIGS,
    WATCHLIST,
    discover_tickers,
    run_all_strategies,
    run_strategy,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("run_backtest")

RESULTS_DIR = _HERE / "results"


# ============================================================================
# JSON serialisation helpers
# ============================================================================

def _sanitise(obj: Any) -> Any:
    """Recursively convert Inf/NaN floats to None for valid JSON."""
    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitise(v) for v in obj]
    return obj


class _JSONEncoder(json.JSONEncoder):
    """Handle numpy scalars and other non-standard types."""

    def default(self, obj):
        try:
            import numpy as np
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)


def save_json(data: Any, path: Path) -> None:
    """Serialise data to JSON file, handling Inf/NaN values."""
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = _sanitise(data)
    path.write_text(
        json.dumps(clean, indent=2, cls=_JSONEncoder, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved: %s", path)


# ============================================================================
# Metrics computation (additional metrics beyond engine output)
# ============================================================================

def compute_extra_metrics(results: Dict[str, Any]) -> Dict[str, Any]:
    """Compute Sortino ratio and any additional metrics not in engine output."""
    daily_returns = []
    equity_curve  = results.get("equity_curve", [])
    if len(equity_curve) >= 2:
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1][1]
            curr = equity_curve[i][1]
            if prev > 0:
                daily_returns.append((curr - prev) / prev)

    # Sortino
    rf_daily = 0.05 / 252
    sortino  = 0.0
    if len(daily_returns) >= 2:
        import numpy as np
        excess   = [r - rf_daily for r in daily_returns]
        downside = [e for e in excess if e < 0]
        if downside:
            dd_std  = math.sqrt(sum(d ** 2 for d in downside) / len(downside))
            mean_ex = sum(excess) / len(excess)
            sortino = (mean_ex / dd_std * math.sqrt(252)) if dd_std > 0 else 0.0

    return {"sortino_ratio": round(sortino, 4)}


# ============================================================================
# Pretty-print summary table
# ============================================================================

def print_summary(all_results: Dict[str, Dict]) -> None:
    """Print a formatted comparison table across strategies."""
    cols = [
        ("Strategy",   "strategy_name",     25),
        ("Trades",     "total_trades",        7),
        ("Win %",      "win_rate",            8),
        ("Total P&L",  "total_pnl",          13),
        ("Return %",   "total_return_pct",    10),
        ("Max DD %",   "max_drawdown_pct",    10),
        ("Sharpe",     "sharpe_ratio",         8),
        ("PF",         "profit_factor",        7),
        ("Avg Win $",  "avg_win",             11),
        ("Avg Loss $", "avg_loss",            11),
        ("Hold Days",  "avg_hold_days",       10),
    ]

    header = "  ".join(f"{label:<{w}}" for label, _, w in cols)
    sep    = "  ".join("-" * w for _, _, w in cols)

    print("\n" + "=" * len(sep))
    print("OPTIONS BACKTEST RESULTS — COMPARISON SUMMARY")
    print(f"Period: {BACKTEST_START} → {BACKTEST_END}")
    print("=" * len(sep))
    print(header)
    print(sep)

    for name, r in all_results.items():
        row_parts = []
        for label, key, width in cols:
            val = r.get(key)
            if val is None:
                cell = "N/A"
            else:
                try:
                    if key == "strategy_name":
                        cell = str(val)
                    elif key == "total_trades":
                        cell = str(int(val))
                    elif key == "win_rate":
                        cell = f"{float(val)*100:.1f}%"
                    elif key in ("total_pnl", "avg_win", "avg_loss"):
                        cell = f"${float(val):,.0f}"
                    elif key == "profit_factor":
                        cell = f"{float(val):.2f}" if val is not None else "∞"
                    else:
                        cell = f"{float(val):.2f}"
                except (ValueError, TypeError):
                    cell = str(val)
            row_parts.append(f"{cell:<{width}}")
        print("  ".join(row_parts))

    print(sep)
    print()


def print_exit_breakdown(all_results: Dict[str, Dict]) -> None:
    """Print exit reason counts per strategy."""
    print("Exit Reason Breakdown:")
    print("-" * 60)
    for name, r in all_results.items():
        exits = r.get("exit_reasons", {})
        if exits:
            breakdown = "  ".join(f"{k}={v}" for k, v in sorted(exits.items()))
            print(f"  {name:<25} {breakdown}")
    print()


def print_monthly_pnl(results: Dict[str, Any], strategy: str) -> None:
    """Print monthly P&L for one strategy."""
    monthly = results.get("monthly_pnl", {})
    if not monthly:
        return
    print(f"\nMonthly P&L — {strategy}:")
    print("-" * 40)
    for month, pnl in sorted(monthly.items()):
        bar = "█" * int(abs(pnl) / 500) if abs(pnl) >= 100 else ""
        sign = "+" if pnl >= 0 else ""
        print(f"  {month}   {sign}${pnl:>8,.0f}  {bar}")


# ============================================================================
# Save per-strategy and combined results
# ============================================================================

def save_all_results(all_results: Dict[str, Dict], generated_at: str) -> Dict[str, Path]:
    """Save per-strategy JSON files and combined summary.

    Returns dict of {strategy_name: path}.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    saved_paths = {}

    for name, results in all_results.items():
        # Per-strategy file
        path = RESULTS_DIR / f"{name}_results.json"
        extra = compute_extra_metrics(results)
        full_results = {**results, **extra, "generated_at": generated_at}
        save_json(full_results, path)
        saved_paths[name] = path

    # Combined summary
    summary = {
        "generated_at": generated_at,
        "backtest_start": BACKTEST_START.isoformat(),
        "backtest_end":   BACKTEST_END.isoformat(),
        "strategies": {},
    }

    for name, results in all_results.items():
        extra = compute_extra_metrics(results)
        summary["strategies"][name] = {
            "strategy_name":    results.get("strategy_name"),
            "starting_capital": results.get("starting_capital"),
            "final_equity":     results.get("final_equity"),
            "total_return_pct": results.get("total_return_pct"),
            "total_trades":     results.get("total_trades"),
            "win_rate":         results.get("win_rate"),
            "avg_win_pct":      results.get("avg_win_pct"),
            "avg_loss_pct":     results.get("avg_loss_pct"),
            "avg_win":          results.get("avg_win"),
            "avg_loss":         results.get("avg_loss"),
            "total_pnl":        results.get("total_pnl"),
            "gross_profit":     results.get("gross_profit"),
            "gross_loss":       results.get("gross_loss"),
            "profit_factor":    results.get("profit_factor"),
            "max_drawdown_pct": results.get("max_drawdown_pct"),
            "sharpe_ratio":     results.get("sharpe_ratio"),
            "sortino_ratio":    extra.get("sortino_ratio"),
            "avg_hold_days":    results.get("avg_hold_days"),
            "buy_signals":      results.get("buy_signals"),
            "exit_reasons":     results.get("exit_reasons"),
            "confidence_calibration": results.get("confidence_calibration"),
            "monthly_pnl":      results.get("monthly_pnl"),
            "equity_curve":     results.get("equity_curve"),
        }

    summary_path = RESULTS_DIR / "backtest_summary.json"
    save_json(summary, summary_path)
    saved_paths["_summary"] = summary_path

    return saved_paths


# ============================================================================
# CLI entry point
# ============================================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Options backtest runner")
    p.add_argument(
        "--strategy",
        choices=list(STRATEGY_CONFIGS) + ["all"],
        default="all",
        help="Strategy to run (default: all)",
    )
    p.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        metavar="TICKER",
        help="Override watchlist with specific tickers",
    )
    p.add_argument(
        "--all-tickers",
        action="store_true",
        help="Use all 90 tickers in the data directory",
    )
    p.add_argument(
        "--capital",
        type=float,
        default=100_000.0,
        help="Starting capital (default: 100000)",
    )
    p.add_argument(
        "--notional",
        type=float,
        default=10_000.0,
        help="Notional per trade (default: 10000)",
    )
    p.add_argument(
        "--no-save",
        action="store_true",
        help="Skip saving results to JSON",
    )
    p.add_argument(
        "--monthly",
        action="store_true",
        help="Print monthly P&L breakdown for each strategy",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Build watchlist
    if args.all_tickers:
        watchlist = discover_tickers()
        logger.info("Using all %d tickers from data directory", len(watchlist))
    elif args.tickers:
        watchlist = [t.upper() for t in args.tickers]
        logger.info("Using custom watchlist: %s", watchlist)
    else:
        watchlist = None  # → engine uses default WATCHLIST
        logger.info("Using default watchlist: %s", WATCHLIST)

    # ── Run strategies ────────────────────────────────────────────────────────
    t0 = time.time()
    generated_at = datetime.utcnow().isoformat() + "Z"

    if args.strategy == "all":
        logger.info("Running all 3 strategies...")
        all_results = run_all_strategies(
            watchlist=watchlist,
            starting_capital=args.capital,
            notional_per_trade=args.notional,
        )
    else:
        logger.info("Running strategy: %s", args.strategy)
        r = run_strategy(
            args.strategy,
            watchlist=watchlist,
            starting_capital=args.capital,
            notional_per_trade=args.notional,
        )
        all_results = {args.strategy: r}

    elapsed = time.time() - t0
    logger.info("Backtest completed in %.1f seconds", elapsed)

    # ── Print summary ─────────────────────────────────────────────────────────
    print_summary(all_results)
    print_exit_breakdown(all_results)

    if args.monthly:
        for name, r in all_results.items():
            print_monthly_pnl(r, name)

    # Confidence calibration for expert committee strategies
    for name, r in all_results.items():
        cc = r.get("confidence_calibration", {})
        if cc and cc.get("avg_confidence_winners") is not None:
            print(f"Confidence Calibration — {name}:")
            print(f"  Avg confidence (winners):  {cc['avg_confidence_winners']:.4f}")
            print(f"  Avg confidence (losers):   {cc['avg_confidence_losers']:.4f}")
            print(f"  Spread:                    {cc.get('confidence_spread', 'N/A')}")
            print()

    # ── Save results ──────────────────────────────────────────────────────────
    if not args.no_save:
        saved = save_all_results(all_results, generated_at)
        print(f"\nResults saved:")
        for key, path in saved.items():
            print(f"  {path}")
    else:
        print("(JSON save skipped via --no-save)")


if __name__ == "__main__":
    main()
