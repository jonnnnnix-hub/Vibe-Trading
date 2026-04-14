#!/usr/bin/env python3
"""Fast v3 optimizer — fewer configs, focused on exit tuning."""
import sys, os, json, copy, time
sys.path.insert(0, os.path.dirname(__file__))

from engine import (
    discover_tickers, run_strategy, STRATEGY_CONFIGS,
    STARTING_CAPITAL,
)

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
    "skip_days":           [],
    "confidence_dead_zone": None,
    "symbol_blacklist":    [],
}

ALL_TICKERS = discover_tickers()
print(f"Universe: {len(ALL_TICKERS)} tickers\n")

def test(name, **overrides):
    c = copy.deepcopy(BASE_CONFIG)
    c.update(overrides)
    saved = copy.deepcopy(STRATEGY_CONFIGS["expert_committee"])
    STRATEGY_CONFIGS["expert_committee"] = c
    try:
        r = run_strategy("expert_committee", ALL_TICKERS)
    finally:
        STRATEGY_CONFIGS["expert_committee"] = saved
    row = {
        "name": name,
        "trades": r.get("total_trades",0),
        "wr": r.get("win_rate",0),
        "pnl": r.get("total_pnl",0),
        "sharpe": r.get("sharpe_ratio",0),
        "pf": r.get("profit_factor",0),
        "dd": r.get("max_drawdown_pct",0),
        "hold": r.get("avg_hold_days",0),
        "exits": str(r.get("exit_reasons",{})),
    }
    print(f"  {name:<40} {row['trades']:>4} trades | {row['wr']:>5.1%} WR | ${row['pnl']:>10,.0f} | Sh={row['sharpe']:.2f} PF={row['pf']:.2f} DD={row['dd']:.1f}%")
    sys.stdout.flush()
    return row

results = []
t0 = time.time()

# Stage 1: Exit parameter sweep (most impactful)
print("── STAGE 1: Exit Sweep ──")
results.append(test("BASE(tgt25/stop35/hold5)"))
results.append(test("tgt15/stop35", option_target_pct=15.0))
results.append(test("tgt20/stop35", option_target_pct=20.0))
results.append(test("tgt15/stop30", option_target_pct=15.0, option_stop_pct=30.0))
results.append(test("tgt15/stop25", option_target_pct=15.0, option_stop_pct=25.0))
results.append(test("tgt20/stop30", option_target_pct=20.0, option_stop_pct=30.0))
results.append(test("tgt20/stop25", option_target_pct=20.0, option_stop_pct=25.0))

print(f"\nStage 1 done in {time.time()-t0:.0f}s\n")

# Stage 2: Best exit + hold time
print("── STAGE 2: Hold Time ──")
results.append(test("tgt15/stop25/hold3", option_target_pct=15.0, option_stop_pct=25.0, max_hold_days=3))
results.append(test("tgt15/stop25/hold4", option_target_pct=15.0, option_stop_pct=25.0, max_hold_days=4))
results.append(test("tgt15/stop30/hold3", option_target_pct=15.0, option_stop_pct=30.0, max_hold_days=3))
results.append(test("tgt15/stop30/hold4", option_target_pct=15.0, option_stop_pct=30.0, max_hold_days=4))

print(f"\nStage 2 done in {time.time()-t0:.0f}s\n")

# Stage 3: Add blacklist to best combos
print("── STAGE 3: Blacklist ──")
BL = ["HD", "DHR", "BRK_B", "AMGN"]
results.append(test("tgt15/stop25+BL", option_target_pct=15.0, option_stop_pct=25.0, symbol_blacklist=BL))
results.append(test("tgt15/stop30+BL", option_target_pct=15.0, option_stop_pct=30.0, symbol_blacklist=BL))
results.append(test("tgt15/stop25/hold3+BL", option_target_pct=15.0, option_stop_pct=25.0, max_hold_days=3, symbol_blacklist=BL))
results.append(test("tgt15/stop25/hold4+BL", option_target_pct=15.0, option_stop_pct=25.0, max_hold_days=4, symbol_blacklist=BL))

print(f"\nStage 3 done in {time.time()-t0:.0f}s\n")

# Stage 4: IV floor on best combos
print("── STAGE 4: IV Floor ──")
results.append(test("tgt15/stop25+ivfloor20", option_target_pct=15.0, option_stop_pct=25.0, iv_floor=0.20))
results.append(test("tgt15/stop25+ivfloor25", option_target_pct=15.0, option_stop_pct=25.0, iv_floor=0.25))

print(f"\nStage 4 done in {time.time()-t0:.0f}s\n")

# Stage 5: Hybrid with delta bands
print("── STAGE 5: Delta Bands ──")
results.append(test("tgt15/stop25/d40-46", option_target_pct=15.0, option_stop_pct=25.0, delta_min=0.40, delta_max=0.46))
results.append(test("tgt15/stop25/d38-44", option_target_pct=15.0, option_stop_pct=25.0, delta_min=0.38, delta_max=0.44))
results.append(test("tgt15/stop25/d35-46", option_target_pct=15.0, option_stop_pct=25.0, delta_min=0.35, delta_max=0.46))

print(f"\nTotal: {time.time()-t0:.0f}s\n")

# Summary sorted by WR then trades
print("="*130)
print(f"{'Config':<42} {'Trades':>6} {'WR':>7} {'PnL':>12} {'Sharpe':>7} {'PF':>6} {'DD%':>7} {'Hold':>5}")
print("-"*130)
for r in sorted(results, key=lambda x: (-x['wr'], -x['trades'])):
    print(f"{r['name']:<42} {r['trades']:>6} {r['wr']:>6.1%} ${r['pnl']:>10,.0f} {r['sharpe']:>7.2f} {r['pf']:>6.2f} {r['dd']:>6.1f}% {r['hold']:>5.1f}")

with open("results/optimization_grid.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\nSaved {len(results)} configs")
