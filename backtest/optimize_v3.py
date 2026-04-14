#!/usr/bin/env python3
"""Systematic v3 configuration optimizer for 173-ticker universe.

Tests combinations of filters and exit parameters to find the best
tradeoff between trade count and win rate, targeting 65%+ WR.
"""
import sys, os, json, copy
sys.path.insert(0, os.path.dirname(__file__))

from engine import (
    discover_tickers, run_strategy, STRATEGY_CONFIGS,
    STARTING_CAPITAL, BACKTEST_START, BACKTEST_END,
)
import pandas as pd
import numpy as np

# Base config: only the proven fundamentals (delta band, option exits)
BASE_CONFIG = {
    "target_pct":          5.0,
    "trailing_activation": 3.0,
    "trailing_distance":   2.0,
    "hard_stop_pct":       None,
    "option_stop_pct":     35.0,
    "option_target_pct":   25.0,
    "max_hold_days":       5,
    "min_hold_days":       1,
    "delta_min":           0.38,
    "delta_max":           0.46,
    "iv_filter":           True,
    "iv_decline_threshold": -5.0,
    # Start with NO extra filters — add them one at a time
    "skip_days":           [],
    "confidence_dead_zone": None,
    "symbol_blacklist":    [],
}

ALL_TICKERS = discover_tickers()
print(f"Universe: {len(ALL_TICKERS)} tickers")

# ── Helper: run one config and return summary dict ──
def test_config(name: str, cfg: dict) -> dict:
    """Run expert_committee with given cfg and return stats."""
    saved = copy.deepcopy(STRATEGY_CONFIGS["expert_committee"])
    STRATEGY_CONFIGS["expert_committee"] = cfg
    try:
        result = run_strategy("expert_committee", ALL_TICKERS)
    finally:
        STRATEGY_CONFIGS["expert_committee"] = saved

    trades = result.get("total_trades", 0)
    wr = result.get("win_rate", 0)
    pnl = result.get("total_pnl", 0)
    sharpe = result.get("sharpe_ratio", 0)
    pf = result.get("profit_factor", 0)
    dd = result.get("max_drawdown_pct", 0)
    avg_hold = result.get("avg_hold_days", 0)
    exits = result.get("exit_reasons", {})
    return {
        "name": name, "trades": trades, "wr": wr, "pnl": pnl,
        "sharpe": sharpe, "pf": pf, "dd": dd, "avg_hold": avg_hold,
        "exits": exits, "config": cfg,
    }

results = []

# ── 1. BASE — no extra filters ──
print("\n=== 1. BASE (delta+option exits only) ===")
r = test_config("BASE", copy.deepcopy(BASE_CONFIG))
results.append(r)
print(f"   {r['trades']} trades | {r['wr']:.1%} WR | ${r['pnl']:,.0f} | Sharpe {r['sharpe']:.2f} | PF {r['pf']:.2f}")

# ── 2. Vary option_target_pct ──
for tgt in [15, 20, 30]:
    name = f"opt_target={tgt}%"
    c = copy.deepcopy(BASE_CONFIG)
    c["option_target_pct"] = float(tgt)
    print(f"\n=== {name} ===")
    r = test_config(name, c)
    results.append(r)
    print(f"   {r['trades']} trades | {r['wr']:.1%} WR | ${r['pnl']:,.0f} | Sharpe {r['sharpe']:.2f} | PF {r['pf']:.2f}")

# ── 3. Vary option_stop_pct ──
for stop in [25, 30, 40]:
    name = f"opt_stop={stop}%"
    c = copy.deepcopy(BASE_CONFIG)
    c["option_stop_pct"] = float(stop)
    print(f"\n=== {name} ===")
    r = test_config(name, c)
    results.append(r)
    print(f"   {r['trades']} trades | {r['wr']:.1%} WR | ${r['pnl']:,.0f} | Sharpe {r['sharpe']:.2f} | PF {r['pf']:.2f}")

# ── 4. Vary max_hold ──
for hold in [3, 4, 7]:
    name = f"max_hold={hold}d"
    c = copy.deepcopy(BASE_CONFIG)
    c["max_hold_days"] = hold
    print(f"\n=== {name} ===")
    r = test_config(name, c)
    results.append(r)
    print(f"   {r['trades']} trades | {r['wr']:.1%} WR | ${r['pnl']:,.0f} | Sharpe {r['sharpe']:.2f} | PF {r['pf']:.2f}")

# ── 5. Add blacklist ──
name = "BL"
c = copy.deepcopy(BASE_CONFIG)
c["symbol_blacklist"] = ["HD", "DHR", "BRK_B", "AMGN"]
print(f"\n=== {name} ===")
r = test_config(name, c)
results.append(r)
print(f"   {r['trades']} trades | {r['wr']:.1%} WR | ${r['pnl']:,.0f} | Sharpe {r['sharpe']:.2f} | PF {r['pf']:.2f}")

# ── 6. Skip Tuesday (day 1) ──
name = "skip_tue"
c = copy.deepcopy(BASE_CONFIG)
c["skip_days"] = [1]
print(f"\n=== {name} ===")
r = test_config(name, c)
results.append(r)
print(f"   {r['trades']} trades | {r['wr']:.1%} WR | ${r['pnl']:,.0f} | Sharpe {r['sharpe']:.2f} | PF {r['pf']:.2f}")

# ── 7. Confidence dead-zone ──
for lo, hi in [(0.66, 0.74), (0.60, 0.70), (0.65, 0.78)]:
    name = f"deadzone=[{lo},{hi})"
    c = copy.deepcopy(BASE_CONFIG)
    c["confidence_dead_zone"] = (lo, hi)
    print(f"\n=== {name} ===")
    r = test_config(name, c)
    results.append(r)
    print(f"   {r['trades']} trades | {r['wr']:.1%} WR | ${r['pnl']:,.0f} | Sharpe {r['sharpe']:.2f} | PF {r['pf']:.2f}")

# ── 8. Combined: best target + stop combos ──
combos = [
    ("tgt15+stop30", 15, 30, 5, [], None, []),
    ("tgt15+stop25", 15, 25, 5, [], None, []),
    ("tgt20+stop30", 20, 30, 5, [], None, []),
    ("tgt20+stop25", 20, 25, 5, [], None, []),
    ("tgt15+stop30+BL", 15, 30, 5, [], None, ["HD","DHR","BRK_B","AMGN"]),
    ("tgt15+stop25+BL", 15, 25, 5, [], None, ["HD","DHR","BRK_B","AMGN"]),
    ("tgt20+stop30+BL", 20, 30, 5, [], None, ["HD","DHR","BRK_B","AMGN"]),
    ("tgt15+stop30+hold4", 15, 30, 4, [], None, []),
    ("tgt15+stop30+hold3", 15, 30, 3, [], None, []),
    ("tgt15+stop25+hold4", 15, 25, 4, [], None, []),
    ("tgt15+stop25+hold3", 15, 25, 3, [], None, []),
    # Add BL + hold combos for the best
    ("tgt15+stop30+BL+hold4", 15, 30, 4, [], None, ["HD","DHR","BRK_B","AMGN"]),
    ("tgt15+stop25+BL+hold4", 15, 25, 4, [], None, ["HD","DHR","BRK_B","AMGN"]),
    ("tgt15+stop25+BL+hold3", 15, 25, 3, [], None, ["HD","DHR","BRK_B","AMGN"]),
    # Wider delta band experiments
]

for (name, tgt, stop, hold, skip, dz, bl) in combos:
    c = copy.deepcopy(BASE_CONFIG)
    c["option_target_pct"] = float(tgt)
    c["option_stop_pct"] = float(stop)
    c["max_hold_days"] = hold
    c["skip_days"] = skip
    c["confidence_dead_zone"] = dz
    c["symbol_blacklist"] = bl
    print(f"\n=== {name} ===")
    r = test_config(name, c)
    results.append(r)
    print(f"   {r['trades']} trades | {r['wr']:.1%} WR | ${r['pnl']:,.0f} | Sharpe {r['sharpe']:.2f} | PF {r['pf']:.2f}")

# ── 9. Delta band experiments with best exit combo ──
delta_combos = [
    ("d35-46+tgt15+stop30", 0.35, 0.46, 15, 30),
    ("d38-50+tgt15+stop30", 0.38, 0.50, 15, 30),
    ("d40-46+tgt15+stop30", 0.40, 0.46, 15, 30),
    ("d38-44+tgt15+stop30", 0.38, 0.44, 15, 30),
    ("d40-48+tgt15+stop30", 0.40, 0.48, 15, 30),
]
for (name, dmin, dmax, tgt, stop) in delta_combos:
    c = copy.deepcopy(BASE_CONFIG)
    c["delta_min"] = dmin
    c["delta_max"] = dmax
    c["option_target_pct"] = float(tgt)
    c["option_stop_pct"] = float(stop)
    print(f"\n=== {name} ===")
    r = test_config(name, c)
    results.append(r)
    print(f"   {r['trades']} trades | {r['wr']:.1%} WR | ${r['pnl']:,.0f} | Sharpe {r['sharpe']:.2f} | PF {r['pf']:.2f}")

# ── 10. IV floor experiments ──
for iv_floor in [0.20, 0.25, 0.30]:
    name = f"tgt15+stop30+ivfloor={iv_floor}"
    c = copy.deepcopy(BASE_CONFIG)
    c["option_target_pct"] = 15.0
    c["option_stop_pct"] = 30.0
    c["iv_floor"] = iv_floor
    print(f"\n=== {name} ===")
    r = test_config(name, c)
    results.append(r)
    print(f"   {r['trades']} trades | {r['wr']:.1%} WR | ${r['pnl']:,.0f} | Sharpe {r['sharpe']:.2f} | PF {r['pf']:.2f}")

# ── Summary Table ──
print("\n" + "="*120)
print(f"{'Config':<35} {'Trades':>6} {'WR':>7} {'PnL':>12} {'Sharpe':>7} {'PF':>6} {'DD%':>7} {'Hold':>5}")
print("-"*120)
for r in sorted(results, key=lambda x: (-x['wr'], -x['trades'])):
    print(f"{r['name']:<35} {r['trades']:>6} {r['wr']:>6.1%} ${r['pnl']:>10,.0f} {r['sharpe']:>7.2f} {r['pf']:>6.2f} {r['dd']:>6.1f}% {r['avg_hold']:>5.1f}")

# Save to JSON
out = []
for r in results:
    rr = {k: v for k, v in r.items() if k != 'config'}
    rr['exits'] = str(rr['exits'])
    out.append(rr)
with open("results/optimization_grid.json", "w") as f:
    json.dump(out, f, indent=2)

print(f"\nSaved {len(results)} configs to results/optimization_grid.json")
