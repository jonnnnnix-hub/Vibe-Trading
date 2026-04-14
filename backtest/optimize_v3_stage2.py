#!/usr/bin/env python3
"""Stage 2 optimizer: Layer filters on top of best base (tgt15/stop25/d38-44)."""
import sys, os, json, copy, time
sys.path.insert(0, os.path.dirname(__file__))

from engine import discover_tickers, run_strategy, STRATEGY_CONFIGS

BEST_BASE = {
    "target_pct":          5.0,
    "trailing_activation": 3.0,
    "trailing_distance":   2.0,
    "hard_stop_pct":       None,
    "option_stop_pct":     25.0,
    "option_target_pct":   15.0,
    "max_hold_days":       5,
    "min_hold_days":       1,
    "delta_min":           0.38,
    "delta_max":           0.44,
    "iv_filter":           True,
    "iv_decline_threshold": -5.0,
    "skip_days":           [],
    "confidence_dead_zone": None,
    "symbol_blacklist":    [],
}

ALL_TICKERS = discover_tickers()
BL = ["HD", "DHR", "BRK_B", "AMGN"]

def test(name, **overrides):
    c = copy.deepcopy(BEST_BASE)
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
    }
    print(f"  {name:<45} {row['trades']:>4} tr | {row['wr']:>5.1%} WR | ${row['pnl']:>10,.0f} | Sh={row['sharpe']:.2f} PF={row['pf']:.2f} DD={row['dd']:.1f}%")
    sys.stdout.flush()
    return row

results = []
t0 = time.time()

# Reproduce baseline
print("── BASELINE: tgt15/stop25/d38-44 ──")
results.append(test("BASELINE"))

# 1. Blacklist
print("\n── BLACKLIST ──")
results.append(test("+BL", symbol_blacklist=BL))

# 2. Hold time reduction  
print("\n── HOLD TIME ──")
results.append(test("+hold4", max_hold_days=4))
results.append(test("+hold3", max_hold_days=3))

# 3. Blacklist + hold combos
print("\n── BL + HOLD ──")
results.append(test("+BL+hold4", symbol_blacklist=BL, max_hold_days=4))
results.append(test("+BL+hold3", symbol_blacklist=BL, max_hold_days=3))

# 4. Skip days
print("\n── SKIP DAYS ──")
results.append(test("+skip_tue", skip_days=[1]))
results.append(test("+skip_mon", skip_days=[0]))
results.append(test("+skip_fri", skip_days=[4]))
results.append(test("+skip_mon+tue", skip_days=[0,1]))

# 5. Confidence dead zones
print("\n── DEAD ZONE ──")
results.append(test("+dz66-74", confidence_dead_zone=(0.66, 0.74)))
results.append(test("+dz60-70", confidence_dead_zone=(0.60, 0.70)))
results.append(test("+dz65-78", confidence_dead_zone=(0.65, 0.78)))

# 6. IV floor
print("\n── IV FLOOR ──")
results.append(test("+ivfloor20", iv_floor=0.20))
results.append(test("+ivfloor25", iv_floor=0.25))
results.append(test("+ivfloor30", iv_floor=0.30))

# 7. Tighter delta + combos
print("\n── DELTA TWEAKS ──")
results.append(test("d39-44", delta_min=0.39, delta_max=0.44))
results.append(test("d38-43", delta_min=0.38, delta_max=0.43))
results.append(test("d39-43", delta_min=0.39, delta_max=0.43))
results.append(test("d40-44", delta_min=0.40, delta_max=0.44))

# 8. Best so far combos (from what looks promising above)
print("\n── COMBO SWEEP ──")
results.append(test("d39-43+BL", delta_min=0.39, delta_max=0.43, symbol_blacklist=BL))
results.append(test("d40-44+BL", delta_min=0.40, delta_max=0.44, symbol_blacklist=BL))
results.append(test("d38-43+BL", delta_min=0.38, delta_max=0.43, symbol_blacklist=BL))
results.append(test("+BL+ivfloor20", symbol_blacklist=BL, iv_floor=0.20))
results.append(test("+BL+skip_tue", symbol_blacklist=BL, skip_days=[1]))
results.append(test("+BL+dz66-74", symbol_blacklist=BL, confidence_dead_zone=(0.66, 0.74)))

# 9. stop=30 variants (more room to be right)
print("\n── STOP 30 VARIANTS ──")
results.append(test("stop30", option_stop_pct=30.0))
results.append(test("stop30+BL", option_stop_pct=30.0, symbol_blacklist=BL))
results.append(test("stop30+BL+hold4", option_stop_pct=30.0, symbol_blacklist=BL, max_hold_days=4))

# 10. Tgt=12 (even tighter take profit)
print("\n── TGT 12% ──")
results.append(test("tgt12", option_target_pct=12.0))
results.append(test("tgt12+BL", option_target_pct=12.0, symbol_blacklist=BL))
results.append(test("tgt12+stop20", option_target_pct=12.0, option_stop_pct=20.0))
results.append(test("tgt10+stop20", option_target_pct=10.0, option_stop_pct=20.0))

print(f"\nTotal: {time.time()-t0:.0f}s\n")

# Summary
print("="*135)
print(f"{'Config':<47} {'Trades':>6} {'WR':>7} {'PnL':>12} {'Sharpe':>7} {'PF':>6} {'DD%':>7} {'Hold':>5}")
print("-"*135)
for r in sorted(results, key=lambda x: (-x['wr'], -x['trades'])):
    print(f"{r['name']:<47} {r['trades']:>6} {r['wr']:>6.1%} ${r['pnl']:>10,.0f} {r['sharpe']:>7.2f} {r['pf']:>6.2f} {r['dd']:>6.1f}% {r['hold']:>5.1f}")

with open("results/optimization_grid_s2.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\nSaved {len(results)} configs")
